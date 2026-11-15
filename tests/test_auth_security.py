import jwt

from app import auth


def test_token_creation_requires_configured_secret(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "")
    try:
        auth.create_access_token({"sub": "test"})
    except RuntimeError as exc:
        assert "JWT_SECRET_KEY" in str(exc)
    else:
        raise AssertionError("Missing JWT secret must not create a token")


def test_invalid_token_returns_none(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "x" * 40)
    assert auth.decode_token("not-a-valid-jwt") is None


def test_signed_token_decodes(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", "x" * 40)
    token = jwt.encode({"sub": "tester"}, auth.SECRET_KEY, algorithm="HS256")
    assert auth.decode_token(token)["sub"] == "tester"
