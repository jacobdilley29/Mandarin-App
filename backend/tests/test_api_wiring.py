"""Every router is actually mounted on the app (spec §4).

This file exists because of a real escape: app/routers/dictionary.py was
written, ten unit tests passed against the module, and the endpoints were dead
in the running app — `app.include_router(dictionary_router.router)` referenced a
name that was never imported, so `app.main` raised NameError at import and every
route 500'd. Nothing in the suite imported app.main, so nothing noticed.

The unit tests elsewhere cover behaviour. What these cover is wiring: that the
module imports at all, that each router is mounted under the prefix the frontend
calls, and that a request through the real dependency stack comes back.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app

from .conftest import attached_conn

# Prefixes the frontend calls. A router quietly dropped from main.py takes its
# whole feature offline, which is what this list is here to prevent.
EXPECTED_PREFIXES = [
    "/api/content",
    "/api/dictionary",
    "/api/settings",
    "/api/curriculum",
    "/api/lesson",
    "/api/placement",
    "/api/review",
    "/api/listen",
    "/api/practice",
    "/api/reading",
    "/api/speak",
    "/api/talk",
    "/api/tutor",
    "/api/progress",
    "/api/audio",
    "/api/admin",
    "/api/health",
]


@pytest.fixture
def client(tmp_path):
    """The real app, over a real two-file database, with no network."""
    conn = attached_conn(tmp_path, same_thread=False)
    conn.executemany(
        """INSERT INTO vocab (id, traditional, pinyin, gloss, zhuyin)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("v_wo", "我", "wǒ", "I; me", "ㄨㄛˇ"),
            ("v_yao", "要", "yào", "to want", "ㄧㄠˋ"),
            ("v_bl", "便利商店", "biànlì shāngdiàn", "convenience store", "ㄅㄧㄢˋ ㄌㄧˋ ㄕㄤ ㄉㄧㄢˋ"),
        ],
    )
    conn.commit()

    app.dependency_overrides[get_db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    conn.close()


@pytest.mark.parametrize("prefix", EXPECTED_PREFIXES)
def test_every_router_is_mounted(prefix):
    """Importing app.main is half the test; the other half is the prefix."""
    paths = {route.path for route in app.routes}
    assert any(p.startswith(prefix) for p in paths), f"no routes under {prefix}"


def test_annotate_answers_over_http(client):
    r = client.post("/api/dictionary/annotate", json={"text": "我要去便利商店。"})
    assert r.status_code == 200
    spans = r.json()["spans"]
    assert [s["text"] for s in spans] == ["我", "要", "去", "便利商店", "。"]
    store = next(s for s in spans if s["text"] == "便利商店")
    assert store["entry"]["pinyin"] == "biànlì shāngdiàn"
    assert store["entry"]["source"] == "curriculum"


def test_define_answers_over_http(client):
    r = client.get("/api/dictionary/我")
    assert r.status_code == 200
    assert r.json()["gloss"] == "I; me"


def test_an_unknown_word_is_a_404_not_a_crash(client):
    assert client.get("/api/dictionary/龘").status_code == 404


def test_annotate_refuses_an_essay(client):
    """The body cap is a guard, not a suggestion."""
    r = client.post("/api/dictionary/annotate", json={"text": "我" * 2001})
    assert r.status_code == 422
