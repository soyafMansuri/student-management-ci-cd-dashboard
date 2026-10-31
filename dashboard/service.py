"""Fetches real pipeline data from the GitHub REST API (server side only; the token never reaches the browser)."""
import threading
import time
from datetime import datetime, timezone

import requests

from .stages import SUGGESTIONS, STAGES, build_stages, find_failure, stage_for

GITHUB_API = "https://api.github.com"


class GitHubError(Exception):
    pass


class GitHubClient:
    def __init__(self, token="", session=None):
        self.token = token
        self.session = session or requests.Session()

    def get(self, path, params=None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = self.session.get(GITHUB_API + path, headers=headers, params=params, timeout=10)
        except requests.RequestException as exc:
            raise GitHubError(f"Cannot reach the GitHub API ({exc.__class__.__name__}).")
        if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
            reset = r.headers.get("X-RateLimit-Reset")
            when = ""
            if reset and reset.isdigit():
                when = " Resets at " + datetime.fromtimestamp(int(reset), timezone.utc).strftime("%H:%M:%S UTC") + "."
            raise GitHubError("GitHub API rate limit reached." + when)
        if r.status_code == 401:
            raise GitHubError("GitHub rejected the token (401). Create a new token and update GITHUB_TOKEN.")
        if r.status_code in (403, 404):
            raise GitHubError(
                f"GitHub returned {r.status_code}: repository not found, or the token lacks "
                "'Actions: read' and 'Metadata: read' permission."
            )
        if not r.ok:
            raise GitHubError(f"GitHub API returned HTTP {r.status_code}.")
        return r.json()


def parse_ts(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def overall_state(run):
    if run.get("status") == "completed":
        c = run.get("conclusion")
        if c == "success":
            return "success"
        if c in ("failure", "timed_out", "startup_failure", "action_required"):
            return "failed"
        if c == "cancelled":
            return "cancelled"
        return "skipped"
    return "in_progress" if run.get("status") == "in_progress" else "pending"


class PipelineService:
    def __init__(self, client, repo, image_repo="", health_url="", ttl=20, max_runs=20):
        self.client, self.repo = client, repo
        self.image_repo, self.health_url = image_repo, health_url
        self.ttl, self.max_runs = ttl, max_runs
        self._lock = threading.Lock()
        self._snapshot, self._snapshot_at = None, 0.0
        self._jobs_cache, self._ann_cache = {}, {}

    # ---------- public ----------
    def payload(self, force=False):
        gh = self._github(force)
        health = self.check_health()
        deployed = None
        if health.get("version") and health["state"] == "healthy":
            match = next((r for r in gh.get("runs", []) if r["sha"] == health["version"]), None)
            deployed = {
                "tag": health["version"],
                "source": "Reported by the application's /api/health endpoint",
                "run_url": match["url"] if match else None,
                "message": match["message"] if match else None,
            }
        out = dict(gh)
        out.update(
            health=health,
            deployed=deployed,
            repo=self.repo,
            image_repo=self.image_repo or None,
            dockerhub_url=f"https://hub.docker.com/r/{self.image_repo}" if "/" in self.image_repo else None,
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        return out

    def check_health(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not self.health_url:
            return {"state": "not_configured", "checked_at": now,
                    "detail": "Set APP_HEALTH_URL to enable health checks."}
        start = time.monotonic()
        try:
            r = requests.get(self.health_url, timeout=5)
            ms = int((time.monotonic() - start) * 1000)
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            ok = r.status_code == 200 and data.get("status") == "ok"
            return {"state": "healthy" if ok else "unhealthy", "http_status": r.status_code,
                    "version": data.get("version"), "latency_ms": ms, "checked_at": now}
        except (requests.RequestException, ValueError):
            return {"state": "unreachable", "checked_at": now, "detail": "The application did not respond."}

    # ---------- GitHub data ----------
    def _github(self, force):
        if not self.repo:
            return self._empty("GITHUB_REPO is not configured (expected owner/repository).")
        with self._lock:
            age = time.time() - self._snapshot_at
            if self._snapshot and (age < self.ttl or (force and age < 5)):
                return self._snapshot
            try:
                self._snapshot = self._build()
                self._snapshot_at = time.time()
                return self._snapshot
            except GitHubError as exc:
                if self._snapshot:
                    return dict(self._snapshot, error=str(exc), stale=True)
                return self._empty(str(exc))

    def _empty(self, error):
        return {"error": error, "stale": False, "runs": [], "counts": {}, "summary": {}}

    def _build(self):
        runs_path = f"/repos/{self.repo}/actions/runs"
        data = self.client.get(runs_path, {"per_page": self.max_runs})

        def total(**params):
            return self.client.get(runs_path, dict(params, per_page=1)).get("total_count", 0)

        counts = {
            "total": data.get("total_count", 0),
            "success": total(status="success"),
            "failed": total(status="failure"),
            "running": total(status="in_progress") + total(status="queued"),
        }
        runs = [self._run_view(r) for r in data.get("workflow_runs", [])]
        return {"error": None, "stale": False, "counts": counts, "runs": runs, "summary": self._summary(runs)}

    def _jobs(self, run):
        cached = self._jobs_cache.get(run["id"])
        if cached is not None:
            return cached
        jobs = self.client.get(f"/repos/{self.repo}/actions/runs/{run['id']}/jobs", {"per_page": 100}).get("jobs", [])
        if run.get("status") == "completed":
            if len(self._jobs_cache) > 200:
                self._jobs_cache.clear()
            self._jobs_cache[run["id"]] = jobs
        return jobs

    def _messages(self, job):
        jid = job["id"]
        if jid not in self._ann_cache:
            try:
                ann = self.client.get(f"/repos/{self.repo}/check-runs/{jid}/annotations")
            except GitHubError:
                return []
            self._ann_cache[jid] = [
                (a.get("message") or "")[:300] for a in ann
                if a.get("annotation_level") == "failure" and a.get("message")
            ][:5]
        return self._ann_cache[jid]

    def _run_view(self, run):
        jobs = self._jobs(run)
        completed = run.get("status") == "completed"
        stages = build_stages(jobs, completed)
        states = {s["key"]: s["state"] for s in stages}
        state = overall_state(run)

        start = parse_ts(run.get("run_started_at") or run.get("created_at"))
        end = parse_ts(run.get("updated_at")) if completed else datetime.now(timezone.utc)
        duration = max(int((end - start).total_seconds()), 0) if start and end else None

        failure = None
        if state == "failed":
            job, step = find_failure(jobs)
            key = stage_for(job["name"], step["name"]) if job and step else None
            if key is None:
                key = next((s["key"] for s in stages if s["state"] == "failed"), None)
            label = dict(STAGES).get(key)
            failure = {
                "stage": label, "job": job["name"] if job else None, "step": step["name"] if step else None,
                "status": run.get("status"), "conclusion": run.get("conclusion"),
                "messages": self._messages(job) if job else [],
                "suggestions": SUGGESTIONS.get(key, ["Open the run on GitHub and read the failed step's log."]),
                "url": run["html_url"],
            }

        sha = run.get("head_sha") or ""
        message = ((run.get("head_commit") or {}).get("message") or run.get("display_title") or "").split("\n")[0][:120]
        return {
            "id": run["id"], "run_number": run.get("run_number"), "name": run.get("name"),
            "branch": run.get("head_branch"), "sha": sha, "short_sha": sha[:7], "message": message,
            "event": run.get("event"), "status": run.get("status"), "conclusion": run.get("conclusion"),
            "state": state, "started_at": run.get("run_started_at") or run.get("created_at"),
            "completed_at": run.get("updated_at") if completed else None,
            "duration_seconds": duration, "url": run["html_url"], "stages": stages,
            "docker_build": states["docker_build"], "docker_push": states["docker_push"],
            "deploy": states["deploy"], "health": states["health"],
            "image_tag": sha if states["docker_push"] == "success" else None,
            "failure": failure,
        }

    def _summary(self, runs):
        latest = runs[0] if runs else None
        pushed = next((r for r in runs if r["docker_push"] == "success"), None)
        deploy_ran = next((r for r in runs if r["deploy"] in ("success", "failed")), None)
        deploy_ok = next((r for r in runs if r["deploy"] == "success" and r["health"] == "success"), None)
        return {
            "latest_state": latest["state"] if latest else None,
            "latest_run_url": latest["url"] if latest else None,
            "latest_image": {"tag": pushed["image_tag"], "run_url": pushed["url"],
                             "published_at": pushed["completed_at"]} if pushed else None,
            "latest_image_build": latest["docker_build"] if latest else None,
            "latest_image_push": latest["docker_push"] if latest else None,
            "last_deployment": {"state": deploy_ran["deploy"], "run_url": deploy_ran["url"],
                                "at": deploy_ran["completed_at"]} if deploy_ran else None,
            "last_successful_deployment": {"at": deploy_ok["completed_at"], "run_url": deploy_ok["url"],
                                           "tag": deploy_ok["sha"]} if deploy_ok else None,
        }
