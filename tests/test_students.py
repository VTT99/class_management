def test_get_existing_student(client):
    r = client.post("/student_data", json={"student_id": 1})
    assert r.status_code == 200
    data = r.json()
    assert data["student"]["name"] == "Alice"
    assert 1 in data["course_summary"] or "1" in data["course_summary"]


def test_get_missing_student(client):
    r = client.post("/student_data", json={"student_id": 9999})
    assert r.status_code == 404


def test_add_student(client):
    payload = {
        "name": "Charlie",
        "parent_contact": "c@x",
        "gender": "Other",
        "payment_method": "Card",
    }
    r = client.post("/add_student", json=payload)
    assert r.status_code == 201, r.text
    new_id = r.json()["student_id"]
    r2 = client.post("/student_data", json={"student_id": new_id})
    assert r2.status_code == 200
    assert r2.json()["student"]["name"] == "Charlie"


def test_add_student_bad_gender(client):
    r = client.post("/add_student", json={
        "name": "X", "parent_contact": "y", "gender": "Z", "payment_method": "Cash",
    })
    assert r.status_code == 422


def test_csv_export(client):
    r = client.get("/students/1/lessons.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "lesson_id" in r.text


def test_search_students_by_name(client):
    r = client.get("/search_students", params={"q": "ali"})
    assert r.status_code == 200
    data = r.json()
    assert any(s["name"] == "Alice" for s in data)


def test_search_students_by_id(client):
    r = client.get("/search_students", params={"q": "1"})
    assert r.status_code == 200
    data = r.json()
    # The exact-ID match should come first.
    assert data[0]["student_id"] == 1


def test_search_students_no_match(client):
    r = client.get("/search_students", params={"q": "zzzzz"})
    assert r.status_code == 200
    assert r.json() == []


def test_search_students_empty_query_rejected(client):
    r = client.get("/search_students", params={"q": ""})
    assert r.status_code == 422


def test_purchase_outstanding_and_unassigned(client):
    """When a student pays for N classes but only M future lessons exist:
       - paid = N
       - completed = number attended so far
       - outstanding = paid - completed
       - unassigned = outstanding - count(future scheduled)"""
    import datetime

    # 3 future lessons in course 2 (empty in conftest).
    base = (datetime.datetime.now() + datetime.timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
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

    # Alice pays for 5 classes via Cash, but only 3 are available.
    r = client.post("/add_to_next_n_lessons", json={
        "student_id": 1,
        "lesson_id": lesson_ids[0],
        "count": 5,
        "payment_method": "Cash",
    })
    assert r.status_code == 200, r.text
    assert len(r.json()["added"]) == 3
    assert r.json()["purchase_id"] is not None

    # Read student data: paid should be 5, scheduled 3, unassigned 2.
    data = client.post("/student_data", json={"student_id": 1}).json()
    course2 = data["course_summary"].get(2) or data["course_summary"].get("2")
    assert course2 is not None
    assert course2["paid"] == 5
    assert course2["not_yet_complete"] == 3   # 3 future lessons scheduled
    assert course2["outstanding"] == 5        # paid - completed (0)
    assert course2["unassigned"] == 2         # 5 - 3 scheduled
    assert course2["payment_method"] == "Cash"


def test_add_course_then_extend(client):
    """Create a course, add one lesson to anchor a recurring pattern,
    then extend by 3 weeks should add 3 new weekly lessons."""
    import datetime

    r = client.post("/add_course", json={"course_name": "Drama Tutorial", "active": True})
    assert r.status_code == 201, r.text
    course_id = r.json()["course_id"]

    start = (datetime.datetime.now() + datetime.timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(hours=1)
    client.post("/add_lesson", json={
        "course_id": course_id,
        "start_datetime": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_datetime": end.strftime("%Y-%m-%d %H:%M:%S"),
    })

    r = client.post("/extend_course", json={"course_id": course_id, "weeks": 3})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["patterns_extended"] == 1
    assert len(data["lessons"]) == 3
    # Each new lesson should be exactly one week apart from the previous.
    starts = [datetime.datetime.strptime(l["start_datetime"], "%Y-%m-%d %H:%M:%S") for l in data["lessons"]]
    deltas = [(starts[i+1] - starts[i]).days for i in range(len(starts) - 1)]
    assert deltas == [7, 7]


def test_extend_course_without_lessons_rejected(client):
    r = client.post("/add_course", json={"course_name": "Empty Course"})
    cid = r.json()["course_id"]
    r2 = client.post("/extend_course", json={"course_id": cid, "weeks": 4})
    assert r2.status_code == 400
