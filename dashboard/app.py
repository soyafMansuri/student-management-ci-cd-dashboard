"""CI/CD monitoring dashboard. Runs as its own container so it stays up if the student app fails."""
import hmac
import os

from flask import Flask, Response, jsonify, render_template, request

from .service import GitHubClient, PipelineService


def create_dashboard_app(config=None, service=None):
    app = Flask(__name__)
    app.config.update(
        DASHBOARD_USER=os.environ.get("DASHBOARD_USER", "admin"),
        DASHBOARD_PASSWORD=os.environ.get("DASHBOARD_PASSWORD", ""),
        GITHUB_REPO=os.environ.get("GITHUB_REPO", ""),
        GITHUB_TOKEN=os.environ.get("GITHUB_TOKEN", ""),
        IMAGE_REPO=os.environ.get("IMAGE_REPO", ""),
        APP_HEALTH_URL=os.environ.get("APP_HEALTH_URL", ""),
        REFRESH_SECONDS=int(os.environ.get("DASHBOARD_REFRESH_SECONDS", "20")),
    )
    if config:
        app.config.update(config)

    app.extensions["pipeline_service"] = service or PipelineService(
        GitHubClient(app.config["GITHUB_TOKEN"]),
        repo=app.config["GITHUB_REPO"],
        image_repo=app.config["IMAGE_REPO"],
        health_url=app.config["APP_HEALTH_URL"],
        ttl=max(app.config["REFRESH_SECONDS"] - 2, 10),
    )

    @app.before_request
    def require_auth():
        if request.path == "/healthz":
            return None
        password = app.config["DASHBOARD_PASSWORD"]
        if not password:
            return Response("Dashboard is locked: set DASHBOARD_PASSWORD in the environment.", 503)
        auth = request.authorization
        if auth and hmac.compare_digest((auth.username or "").encode(), app.config["DASHBOARD_USER"].encode()) \
                and hmac.compare_digest((auth.password or "").encode(), password.encode()):
            return None
        return Response("Authentication required.", 401, {"WWW-Authenticate": 'Basic realm="CI/CD Dashboard"'})

    @app.after_request
    def no_cache(resp):
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/")
    def index():
        return render_template("dashboard.html", refresh=app.config["REFRESH_SECONDS"])

    @app.get("/api/dashboard")
    def api_dashboard():
        data = app.extensions["pipeline_service"].payload(force=request.args.get("force") == "1")
        if not app.config["GITHUB_REPO"] and not data.get("error"):
            data["error"] = "GITHUB_REPO is not configured (expected owner/repository)."
        return jsonify(data)

    return app


app = create_dashboard_app()
