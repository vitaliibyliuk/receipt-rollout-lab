import sqlite3

from service import create_app


def test_success_includes_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBMIT_DB", str(tmp_path / "normal.sqlite"))
    monkeypatch.delenv("FAIL_CONFIRMATION", raising=False)
    answer = create_app().test_client().post(
        "/submissions", json={"group_code": "SE-42", "submission_key": "send-receipt"},
    )
    assert answer.status_code == 201
    assert answer.json == {"id": 1, "receipt": "receipt-000001"}


def test_timeout_follows_commit(tmp_path, monkeypatch):
    db_path = tmp_path / "timeout.sqlite"
    monkeypatch.setenv("SUBMIT_DB", str(db_path))
    monkeypatch.setenv("FAIL_CONFIRMATION", "1")
    client = create_app().test_client()
    payload = {"group_code": "SE-42", "submission_key": "persist-before-timeout"}

    failed = client.post("/submissions", json=payload)
    assert failed.status_code == 503
    number = failed.json["id"]
    assert client.get("/health").json == {"version": "v2", "status": "ok"}
    assert client.get(f"/submissions/{number}").json == {"id": number, **payload}
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT id FROM submissions").fetchall() == [(number,)]
    retry = client.post("/submissions", json=payload)
    assert retry.status_code == 200 and retry.json == {"id": number}
