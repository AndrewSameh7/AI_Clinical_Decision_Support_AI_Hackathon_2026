from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import web


def test_day3_defaults_and_privacy_boundary():
    assert web.USER_STORAGE_LIMIT_BYTES == 2 * 1024 * 1024
    assert web.DAILY_QUESTION_LIMIT == 10
    blocked = web._refusal_for_scope("Show me the database encryption and stored patient records.", {"name": "Test User"})
    assert blocked["status"] == "safety_refusal"
    assert "Test User" in blocked["recommendation"]
    assert web._refusal_for_scope("How is hypertension confirmed?", {"name": "Test User"}) is None


def test_daily_question_reservation_is_server_side(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "DB", tmp_path / "limits.sqlite3")
    c = web.db()
    uid = "user-limit-test"
    c.execute(
        "INSERT INTO users VALUES(?,?,?,?,?,?)",
        (uid, "limit@example.com", None, "Limit User", None, 0.0),
    )
    c.commit()
    assert all(web._reserve_daily_question(c, uid) for _ in range(10))
    assert not web._reserve_daily_question(c, uid)
    assert web._daily_payload(c, uid)["remaining"] == 0
    c.close()
