import base64

from dashboard.app import create_dashboard_app
from dashboard.service import PipelineService
from dashboard.stages import build_stages


def job(name, conclusion, steps=(), status="completed", jid=1):
    return {"id": jid, "name": name, "status": status, "conclusion": conclusion,
            "steps": [{"name": n, "status": "completed" if c else "queued", "conclusion": c} for n, c in steps]}


GOOD = [
    job("Validate", "success", [("Checkout", "success"), ("Validate Python syntax", "success"),
                                ("Validate configuration", "success")]),
    job("Test", "success"),
    job("Docker Build & Push", "success", [("Build Docker image", "success"), ("Smoke test image", "success"),
                                           ("Push image to Docker Hub", "success")]),
    job("Deploy to EC2", "success", [("Deploy to EC2", "success"), ("Verify deployment health", "success")]),
]


def states(jobs, completed=True):
    return {s["key"]: s["state"] for s in build_stages(jobs, completed)}


def test_all_stages_success():
    assert set(states(GOOD).values()) == {"success"}


def test_failed_tests_skip_later_stages():
    jobs = [GOOD[0], job("Test", "failure", jid=2),
            job("Docker Build & Push", "skipped"), job("Deploy to EC2", "skipped")]
    s = states(jobs)
    assert s["tests"] == "failed" and s["docker_build"] == "skipped" and s["deploy"] == "skipped"
    assert s["checkout"] == "success"


def test_missing_job_is_pending_while_running_and_unknown_after():
    assert states([GOOD[0]], completed=False)["tests"] == "pending"
    assert states([GOOD[0]], completed=True)["tests"] == "unknown"


def test_in_progress_step():
    jobs = [GOOD[0], GOOD[1], job("Docker Build & Push", None, [
        ("Build Docker image", "success"), ("Smoke test image", None), ("Push image to Docker Hub", None)],
        status="in_progress")]
    jobs[2]["steps"][1]["status"] = "in_progress"
    s = states(jobs, completed=False)
    assert s["docker_build"] == "in_progress" and s["docker_push"] == "pending"


def test_deploy_skipped_when_secrets_missing():
    jobs = GOOD[:3] + [job("Deploy to EC2", "success", [("Deploy to EC2", "skipped"),
                                                         ("Verify deployment health", "skipped")])]
    s = states(jobs)
    assert s["docker_push"] == "success" and s["deploy"] == "skipped" and s["health"] == "skipped"


class FakeClient:
    def __init__(self, runs, jobs):
        self.runs, self.jobs = runs, jobs

    def get(self, path, params=None):
        if path.endswith("/actions/runs"):
            return {"total_count": len(self.runs), "workflow_runs": self.runs}
        if path.endswith("/jobs"):
            rid = int(path.split("/")[-2])
            return {"jobs": self.jobs[rid]}
        if path.endswith("/annotations"):
            return [{"annotation_level": "failure", "message": "Process completed with exit code 1."}]
        raise AssertionError(path)


def run(rid, conclusion, sha):
    return {"id": rid, "run_number": rid, "name": "CI/CD Pipeline", "head_branch": "main", "head_sha": sha,
            "head_commit": {"message": "change\nbody"}, "event": "push", "status": "completed",
            "conclusion": conclusion, "run_started_at": "2026-01-01T10:00:00Z",
            "created_at": "2026-01-01T10:00:00Z", "updated_at": "2026-01-01T10:03:30Z",
            "html_url": f"https://github.com/o/r/actions/runs/{rid}"}


def make_app():
    failed_jobs = [GOOD[0], job("Test", "failure", [("Run tests", "failure")], jid=77),
                   job("Docker Build & Push", "skipped"), job("Deploy to EC2", "skipped")]
    client = FakeClient([run(2, "failure", "b" * 40), run(1, "success", "a" * 40)], {1: GOOD, 2: failed_jobs})
    svc = PipelineService(client, "o/r", image_repo="user/student-management-system", health_url="", ttl=0)
    return create_dashboard_app({"DASHBOARD_PASSWORD": "pw", "GITHUB_REPO": "o/r"}, service=svc)


def auth(user="admin", pw="pw"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def test_dashboard_requires_auth():
    c = make_app().test_client()
    assert c.get("/api/dashboard").status_code == 401
    assert c.get("/api/dashboard", headers=auth(pw="wrong")).status_code == 401
    assert c.get("/healthz").status_code == 200


def test_dashboard_locked_without_password():
    app = create_dashboard_app({"DASHBOARD_PASSWORD": ""}, service=make_app().extensions["pipeline_service"])
    assert app.test_client().get("/").status_code == 503


def test_dashboard_payload():
    c = make_app().test_client()
    d = c.get("/api/dashboard", headers=auth()).get_json()
    assert d["error"] is None
    bad, good = d["runs"]
    assert bad["state"] == "failed" and bad["failure"]["stage"] == "Tests"
    assert bad["failure"]["messages"] == ["Process completed with exit code 1."]
    assert bad["duration_seconds"] == 210 and bad["message"] == "change"
    assert good["state"] == "success" and good["image_tag"] == "a" * 40
    assert d["summary"]["latest_image"]["tag"] == "a" * 40
    assert d["summary"]["last_successful_deployment"]["tag"] == "a" * 40
    assert d["health"]["state"] == "not_configured" and d["deployed"] is None
    assert d["dockerhub_url"] == "https://hub.docker.com/r/user/student-management-system"
    assert "token" not in str(d).lower()


def test_github_failure_returns_message_not_crash():
    from dashboard.service import GitHubError

    class Broken:
        def get(self, *a, **k):
            raise GitHubError("GitHub API rate limit reached.")

    svc = PipelineService(Broken(), "o/r", ttl=0)
    d = create_dashboard_app({"DASHBOARD_PASSWORD": "pw", "GITHUB_REPO": "o/r"}, service=svc) \
        .test_client().get("/api/dashboard", headers=auth()).get_json()
    assert "rate limit" in d["error"] and d["runs"] == []
