import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"DATABASE_PATH": str(tmp_path / "test.db"), "TESTING": True, "APP_VERSION": "test-sha"})
    return app.test_client()


@pytest.fixture()
def sample():
    return {"name": "Asha Verma", "email": "asha@example.com", "course": "BCA", "semester": 3}
