import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.auth import api as auth


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth, "ITERATIONS", 1000)
    app = FastAPI()
    app.include_router(auth.router)

    @app.post("/protected")
    def protected(user: dict = Depends(auth.current_user)):
        return user
    return TestClient(app)


def reg(c, email="a.b@yale.edu", pw="correct horse"):
    return c.post("/api/auth/register", json={"email": email, "name": "A B", "password": pw})


def test_protected_requires_sign_in(client):
    assert client.post("/protected").status_code == 401


def test_register_sign_in_sign_out(client):
    assert reg(client).status_code == 200
    assert client.post("/protected").json()["email"] == "a.b@yale.edu"
    client.post("/api/auth/logout")
    assert client.post("/protected").status_code == 401
    assert client.post("/api/auth/login", json={"email": "A.B@yale.edu", "password": "correct horse"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_rejects_non_yale_short_password_duplicates_and_wrong_password(client):
    assert reg(client, email="x@gmail.com").status_code == 422
    assert reg(client, pw="short").status_code == 422
    assert reg(client).status_code == 200
    assert reg(client).status_code == 409
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": "a.b@yale.edu", "password": "wrong password"}).status_code == 401


def test_password_not_stored_in_plain_text(client):
    reg(client)
    with auth.auth_db() as db:
        u = db.query(auth.User).one()
        assert "correct horse" not in u.password_hash and u.password_hash.startswith("pbkdf2_sha256$")


def test_forged_cookie_rejected(client):
    client.cookies.set(auth.COOKIE, "not-a-real-token")
    assert client.post("/protected").status_code == 401
