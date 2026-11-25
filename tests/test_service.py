import sqlite3

import pytest

from service import create_app


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "demo.sqlite"
    monkeypatch.setenv("SUBMIT_DB", str(path))
    monkeypatch.delenv("FAIL_CONFIRMATION", raising=False)
    return path


@pytest.mark.parametrize(
    "group, status, rows",
    [
        pytest.param("SE-42", 201, 1, id="regular"),
        pytest.param("SE-00", 201, 1, id="leading-zero"),
        pytest.param("si-42", 400, 0, id="prefix"),
        pytest.param("SE-4", 400, 0, id="short"),
        pytest.param("SE-042", 400, 0, id="long"),
        pytest.param("SE-４２", 400, 0, id="unicode"),
    ],
)
def test_group_format(db_path, group, status, rows):
    client = create_app().test_client()
    answer = client.post("/submissions", json={"group_code": group, "submission_key": "check"})
    assert answer.status_code == status
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT count(*) FROM submissions").fetchone() == (rows,)


def test_lookup_and_idempotent_retry(db_path):
    client = create_app().test_client()
    payload = {"submission_key": "same-work", "group_code": "SE-42"}
    first = client.post("/submissions", json=payload)
    assert first.status_code == 201
    number = first.json["id"]

    again = client.post("/submissions", json=payload)
    assert again.status_code == 200
    assert again.json == {"id": number}
    assert client.get(f"/submissions/{number}").json == {"id": number, **payload}
    assert client.get("/submissions/999").status_code == 404
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT count(*) FROM submissions").fetchone() == (1,)


def test_health_endpoint(db_path):
    response = create_app().test_client().get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
