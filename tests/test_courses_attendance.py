def test_search_courses(client):
    r = client.get("/search_courses", params={"course_name_partial": "Math"})
    assert r.status_code == 200
    data = r.json()
    assert any(c["course_name"] == "Math class" for c in data)


def test_lesson_participants_missing(client):
    # Our seed uses string lesson_ids like "1_1"; the endpoint expects int.
    # A nonexistent integer id returns 404.
    r = client.get("/lesson_participants", params={"lesson_id": 9999})
    assert r.status_code == 404


def test_lesson_participants_invalid(client):
    r = client.get("/lesson_participants", params={"lesson_id": "not-a-number"})
    assert r.status_code == 422


def test_mark_attendance_unregistered(client):
    r = client.post("/mark_attendance", json={"lesson_id": 999999, "student_id": 1})
    assert r.status_code == 404


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
