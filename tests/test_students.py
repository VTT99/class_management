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
