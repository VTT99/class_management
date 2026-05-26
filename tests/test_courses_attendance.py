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


def test_list_courses(client):
    r = client.get("/courses")
    assert r.status_code == 200
    data = r.json()
    assert any(c["course_name"] == "Math class" for c in data)


def test_list_lessons_range(client):
    import datetime
    today = datetime.date.today().isoformat()
    later = (datetime.date.today() + datetime.timedelta(days=70)).isoformat()
    r = client.get("/lessons", params={"start_date": today, "end_date": later})
    assert r.status_code == 200
    data = r.json()
    # Expect at least the future-dated lessons from conftest.
    assert any("course_name" in row for row in data)


def test_add_lesson_then_register_then_attend(client):
    import datetime
    course_id = 1
    start = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d 09:00:00")
    end = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d 10:00:00")

    r = client.post("/add_lesson", json={
        "course_id": course_id, "start_datetime": start, "end_datetime": end,
    })
    assert r.status_code == 201, r.text
    new_lesson_id = r.json()["lesson_id"]

    # Register Alice (id 1) to it.
    r = client.post("/add_lesson_registration", json={"student_id": 1, "lesson_id": new_lesson_id})
    assert r.status_code == 200, r.text

    # Re-registering is a no-op (idempotent).
    r = client.post("/add_lesson_registration", json={"student_id": 1, "lesson_id": new_lesson_id})
    assert r.status_code == 200

    # Mark attendance.
    r = client.post("/mark_attendance", json={"student_id": 1, "lesson_id": new_lesson_id})
    assert r.status_code == 200


def test_add_lesson_unknown_course(client):
    r = client.post("/add_lesson", json={
        "course_id": 9999,
        "start_datetime": "2030-01-01 09:00:00",
        "end_datetime": "2030-01-01 10:00:00",
    })
    assert r.status_code == 404
