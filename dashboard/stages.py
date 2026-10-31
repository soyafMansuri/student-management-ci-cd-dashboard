"""Maps real GitHub Actions jobs/steps onto the dashboard's seven pipeline stages.

The job and step names below MUST match the names in .github/workflows/ci-cd.yml.
If a name cannot be found, the stage is reported as "unknown" instead of guessing.
"""

STAGES = [
    ("checkout", "Checkout"),
    ("validation", "Validation"),
    ("tests", "Tests"),
    ("docker_build", "Docker Build"),
    ("docker_push", "Docker Hub Push"),
    ("deploy", "AWS Deploy"),
    ("health", "Health Check"),
]

# stage key -> (job name, [step names]); steps=None means "use the whole job"
STAGE_MAP = {
    "checkout": ("Validate", ["Checkout"]),
    "validation": ("Validate", ["Validate Python syntax", "Validate configuration"]),
    "tests": ("Test", None),
    "docker_build": ("Docker Build & Push", ["Build Docker image", "Smoke test image"]),
    "docker_push": ("Docker Build & Push", ["Push image to Docker Hub"]),
    "deploy": ("Deploy to EC2", ["Deploy to EC2"]),
    "health": ("Deploy to EC2", ["Verify deployment health"]),
}

SUGGESTIONS = {
    "checkout": ["Check that the repository is reachable and the workflow has 'contents: read' permission."],
    "validation": [
        "Open the failed step and fix the Python syntax or configuration error it reports.",
        "Run 'python -m compileall app dashboard tests' and 'docker compose config' locally.",
    ],
    "tests": [
        "Run 'pytest -v' locally and fix the failing test.",
        "Check that requirements.txt and requirements-dev.txt are up to date.",
    ],
    "docker_build": [
        "Run 'docker build -t sms-test .' locally to reproduce the error.",
        "Check the Dockerfile, requirements.txt and .dockerignore (a needed file may be excluded).",
        "If the smoke test failed, run the image locally and check 'docker logs'.",
    ],
    "docker_push": [
        "Check the DOCKERHUB_USERNAME and DOCKERHUB_TOKEN secrets; the token needs Read & Write access.",
        "Check that the Docker Hub repository name matches IMAGE_REPO.",
    ],
    "deploy": [
        "Check EC2_HOST, EC2_USER and EC2_SSH_KEY, and that the security group allows SSH from GitHub runners or your CI source.",
        "SSH to the server and run 'docker compose logs --tail 100 app' in the deployment directory.",
        "The deploy script rolls back automatically; confirm with 'docker ps'.",
    ],
    "health": [
        "Open http://<server>/api/health and check the 'status' and 'version' fields.",
        "Check that the security group allows HTTP (port 80) and that Nginx is running.",
        "The workflow attempts a rollback after a failed health check; confirm with 'docker ps'.",
    ],
}


def item_state(item):
    """State of one GitHub job or step."""
    status, concl = item.get("status"), item.get("conclusion")
    if status == "completed":
        if concl in ("success", "neutral"):
            return "success"
        if concl in ("failure", "timed_out", "startup_failure", "action_required"):
            return "failed"
        if concl == "cancelled":
            return "cancelled"
        if concl == "skipped":
            return "skipped"
        return "unknown"
    if status == "in_progress":
        return "in_progress"
    return "pending"  # queued / waiting / pending


def combine(states):
    s = set(states)
    if not s:
        return "unknown"
    if "failed" in s:
        return "failed"
    if "in_progress" in s:
        return "in_progress"
    if "cancelled" in s:
        return "cancelled"
    if "pending" in s:
        return "in_progress" if "success" in s else "pending"
    if "unknown" in s:
        return "unknown"
    if "success" in s:
        return "success"
    return "skipped"


def _find(items, name):
    for it in items or []:
        if (it.get("name") or "").strip().lower() == name.lower():
            return it
    return None


def stage_state(jobs, run_completed, job_name, steps):
    job = _find(jobs, job_name)
    if job is None:
        # Jobs that have not started yet are not listed; after completion a missing job is a mapping problem.
        return "unknown" if run_completed else "pending"
    jstate = item_state(job)
    if jstate in ("skipped", "cancelled"):
        return jstate
    if steps is None:
        return jstate
    job_done = job.get("status") == "completed"
    states = []
    for name in steps:
        step = _find(job.get("steps"), name)
        if step is None:
            states.append("unknown" if job_done else "pending")
        else:
            states.append(item_state(step))
    return combine(states)


def build_stages(jobs, run_completed):
    return [
        {"key": key, "label": label, "state": stage_state(jobs, run_completed, *STAGE_MAP[key])}
        for key, label in STAGES
    ]


def find_failure(jobs):
    """Return (job, step) for the first failed job / step, or (None, None)."""
    for job in jobs or []:
        if job.get("conclusion") in ("failure", "timed_out", "startup_failure"):
            for step in job.get("steps") or []:
                if step.get("conclusion") in ("failure", "timed_out"):
                    return job, step
            return job, None
    return None, None


def stage_for(job_name, step_name):
    for key, label in STAGES:
        jname, steps = STAGE_MAP[key]
        if (job_name or "").lower() == jname.lower() and (steps is None or step_name in steps):
            return key
    return None
