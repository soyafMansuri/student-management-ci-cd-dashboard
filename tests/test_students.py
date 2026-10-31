def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "database": "ok", "version": "test-sha"}


def test_index_page(client):
    assert client.get("/").status_code == 200


def test_create_and_get(client, sample):
    r = client.post("/api/students", json=sample)
    assert r.status_code == 201
    body = r.get_json()
    assert body["id"] == 1 and body["email"] == "asha@example.com" and body["created_at"]
    assert client.get("/api/students/1").get_json()["name"] == "Asha Verma"


def test_validation_errors(client):
    r = client.post("/api/students", json={"name": "A", "email": "bad", "course": "", "semester": 99})
    assert r.status_code == 400
    assert set(r.get_json()["errors"]) == {"name", "email", "course", "semester"}


def test_invalid_json_body(client):
    assert client.post("/api/students", data="nope", content_type="application/json").status_code == 400


def test_duplicate_email(client, sample):
    client.post("/api/students", json=sample)
    r = client.post("/api/students", json=sample)
    assert r.status_code == 409
    assert "email" in r.get_json()["errors"]


def test_update_and_not_found(client, sample):
    client.post("/api/students", json=sample)
    r = client.put("/api/students/1", json={**sample, "course": "MCA", "semester": 4})
    assert r.status_code == 200 and r.get_json()["course"] == "MCA"
    assert client.put("/api/students/99", json=sample).status_code == 404


def test_delete(client, sample):
    client.post("/api/students", json=sample)
    assert client.delete("/api/students/1").status_code == 200
    assert client.delete("/api/students/1").status_code == 404
    assert client.get("/api/students").get_json() == []


def test_search_and_wildcards(client, sample):
    client.post("/api/students", json=sample)
    client.post("/api/students", json={**sample, "name": "Rohan", "email": "rohan@example.com", "course": "BBA"})
    assert len(client.get("/api/students?q=asha").get_json()) == 1
    assert len(client.get("/api/students?q=bba").get_json()) == 1
    assert len(client.get("/api/students?q=example.com").get_json()) == 2
    assert client.get("/api/students?q=%25").get_json() == []  # '%' is literal, not a wildcard


def test_stats(client, sample):
    assert client.get("/api/stats").get_json()["total"] == 0
    client.post("/api/students", json=sample)
    client.post("/api/students", json={**sample, "email": "b@example.com", "semester": 5})
    s = client.get("/api/stats").get_json()
    assert s["total"] == 2 and s["average_semester"] == 4.0 and s["by_course"][0]["count"] == 2


def test_unknown_api_route_is_json(client):
    r = client.get("/api/nothing")
    assert r.status_code == 404 and r.get_json()["error"]
