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


def test_add_lessons_bulk(client):
    """Client-computed recurrence: 4 weekly Tuesdays at 14:00."""
    import datetime
    start = (datetime.datetime.now() + datetime.timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)
    lessons = []
    for i in range(4):
        s = start + datetime.timedelta(weeks=i)
        e = s + datetime.timedelta(hours=1)
        lessons.append({
            "course_id": 1,
            "start_datetime": s.strftime("%Y-%m-%d %H:%M:%S"),
            "end_datetime": e.strftime("%Y-%m-%d %H:%M:%S"),
        })
    r = client.post("/add_lessons_bulk", json={"lessons": lessons})
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data["lessons"]) == 4
    starts = [l["start_datetime"] for l in data["lessons"]]
    assert starts == sorted(starts)


def test_add_lessons_bulk_mixed_pattern(client):
    """Realistic pattern: Mon + Wed for 3 weeks, different times each day."""
    import datetime
    monday = (datetime.datetime.now() + datetime.timedelta(days=(7 - datetime.datetime.now().weekday()) % 7 or 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    lessons = []
    for w in range(3):
        # Monday 10:00-11:00
        s = monday + datetime.timedelta(weeks=w, hours=10)
        lessons.append({"course_id": 1, "start_datetime": s.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_datetime": (s + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")})
        # Wednesday 14:00-15:30
        s = monday + datetime.timedelta(days=2, weeks=w, hours=14)
        lessons.append({"course_id": 1, "start_datetime": s.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_datetime": (s + datetime.timedelta(hours=1, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")})

    r = client.post("/add_lessons_bulk", json={"lessons": lessons})
    assert r.status_code == 201, r.text
    assert len(r.json()["lessons"]) == 6


def test_mark_attendance_bulk_pushes_absent(client):
    """Alice registered for the first of two future lessons in course 2
    (a course with no pre-seeded lessons). push_absent=true should
    register Alice to the second lesson."""
    import datetime

    # Use course 2 — conftest leaves it empty, so the only future
    # lessons are the ones this test creates.
    start1 = (datetime.datetime.now() + datetime.timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)
    end1 = start1 + datetime.timedelta(hours=1)
    r = client.post("/add_lesson", json={
        "course_id": 2,
        "start_datetime": start1.strftime("%Y-%m-%d %H:%M:%S"),
        "end_datetime": end1.strftime("%Y-%m-%d %H:%M:%S"),
    })
    lesson1 = r.json()["lesson_id"]

    start2 = start1 + datetime.timedelta(weeks=1)
    end2 = start2 + datetime.timedelta(hours=1)
    r = client.post("/add_lesson", json={
        "course_id": 2,
        "start_datetime": start2.strftime("%Y-%m-%d %H:%M:%S"),
        "end_datetime": end2.strftime("%Y-%m-%d %H:%M:%S"),
    })
    lesson2 = r.json()["lesson_id"]

    # Register Alice for lesson1 only (she'll be absent and pushed).
    r = client.post("/add_lesson_registration", json={"student_id": 1, "lesson_id": lesson1})
    assert r.status_code == 200

    # Mark attendance: nobody attended; push_absent=true.
    r = client.post("/mark_attendance_bulk", json={
        "lesson_id": lesson1,
        "student_ids": [],
        "push_absent": True,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["marked_count"] == 0
    assert data["pushed_count"] == 1
    assert data["pushed"][0]["student_id"] == 1
    assert data["pushed"][0]["to_lesson_id"] == lesson2

    # Alice should now be registered for lesson2.
    parts = client.get("/lesson_participants", params={"lesson_id": lesson2}).json()
    assert any(p["student_id"] == 1 for p in parts)


def test_mark_attendance_bulk_push_absent_finds_next_gap(client):
    """If Alice is already registered for the next lesson, push to the
    one after that ('first available gap' algorithm)."""
    import datetime

    # Use course 2 (empty course) so push lands deterministically.
    base = (datetime.datetime.now() + datetime.timedelta(days=4)).replace(hour=16, minute=0, second=0, microsecond=0)
    lesson_ids = []
    for i in range(3):
        s = base + datetime.timedelta(weeks=i)
        e = s + datetime.timedelta(hours=1)
        r = client.post("/add_lesson", json={
            "course_id": 2,
            "start_datetime": s.strftime("%Y-%m-%d %H:%M:%S"),
            "end_datetime": e.strftime("%Y-%m-%d %H:%M:%S"),
        })
        lesson_ids.append(r.json()["lesson_id"])

    # Register Alice for lesson 1 (will miss) AND lesson 2 (already booked).
    for lid in [lesson_ids[0], lesson_ids[1]]:
        client.post("/add_lesson_registration", json={"student_id": 1, "lesson_id": lid})

    # Mark lesson 1 with Alice absent, push_absent=true.
    r = client.post("/mark_attendance_bulk", json={
        "lesson_id": lesson_ids[0],
        "student_ids": [],
        "push_absent": True,
    })
    data = r.json()
    # The first gap after lesson 1 is lesson 3 (lesson 2 is already taken).
    assert data["pushed_count"] == 1
    assert data["pushed"][0]["to_lesson_id"] == lesson_ids[2]
