import os

from flask import Flask, jsonify

from .db import close_db, init_db
from .routes import bp

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def create_app(config=None):
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = os.environ.get(
        "DATABASE_PATH", os.path.join(BASE_DIR, "data", "students.db")
    )
    app.config["APP_VERSION"] = os.environ.get("APP_VERSION", "dev")
    if config:
        app.config.update(config)

    init_db(app.config["DATABASE_PATH"])
    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="Not found"), 404

    @app.errorhandler(405)
    def bad_method(_):
        return jsonify(error="Method not allowed"), 405

    return app
