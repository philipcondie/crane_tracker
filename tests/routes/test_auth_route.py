import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.base import (
    AdminToken,
    AdminUser,
    CranePhoto,
    CranePhotoStatus,
    OutboxJob,
)
from app.services.auth import hash_password, token_hash, verify_password
from tests.utils.images import TEST_JPEG_BYTES

PASSWORD = "a long test password for admins"


@pytest.fixture
def admin(session):
    user = AdminUser(username="reviewer", password_hash=hash_password(PASSWORD))
    session.add(user)
    session.commit()
    return user


def login(client):
    return client.post(
        "/admin/login", json={"username": "reviewer", "password": PASSWORD}
    )


def headers(client):
    return {"Authorization": f"Bearer {login(client).json()['access_token']}"}


def test_password_hashing():
    first = hash_password(PASSWORD)
    assert first != hash_password(PASSWORD)
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong", first)
    assert not verify_password(PASSWORD, "invalid")


def test_login_logout(client, session, admin):
    response = login(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600
    stored = session.get(AdminToken, token_hash(data["access_token"]))
    assert stored.user_id == admin.id
    assert stored.token_hash != data["access_token"]
    auth = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.get("/cranes/photos", headers=auth).json() == {
        "photos": [],
        "end": True,
    }
    assert client.post("/admin/logout", headers=auth).status_code == 204
    assert client.get("/cranes/photos", headers=auth).status_code == 401


@pytest.mark.parametrize(
    "username,password", [("unknown", PASSWORD), ("reviewer", "wrong")]
)
def test_invalid_credentials(client, session, admin, username, password):
    response = client.post(
        "/admin/login", json={"username": username, "password": password}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert session.scalar(select(AdminToken)) is None


def test_disabled_admin(client, session, admin):
    auth = headers(client)
    admin.is_active = False
    session.commit()
    assert login(client).status_code == 401
    assert client.get("/cranes/photos", headers=auth).status_code == 401


def test_expired_token(client, session, admin):
    auth = headers(client)
    stored = session.scalar(select(AdminToken))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert client.get("/cranes/photos", headers=auth).status_code == 401
    assert (
        client.delete(
            f"/cranes/{uuid.uuid4()}/photos/{uuid.uuid4()}", headers=auth
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "auth", [{}, {"Authorization": "Bearer bogus"}, {"Authorization": "Basic bogus"}]
)
def test_photo_paths_require_auth(client, session, auth):
    assert client.get("/cranes/photos", headers=auth).status_code == 401
    response = client.delete(
        f"/cranes/{uuid.uuid4()}/photos/{uuid.uuid4()}", headers=auth
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert session.scalar(select(OutboxJob)) is None


def test_review_and_delete_public_upload(client, session, admin, monkeypatch):
    monkeypatch.setattr("app.services.storage.upload_photo", lambda *a, **kw: None)
    crane = client.post("/cranes", json={"lat": 37.77, "lng": -122.42}).json()
    photo_ids = []
    for _ in range(2):
        upload = client.post(
            f"/cranes/{crane['id']}/photos",
            files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
        )
        assert upload.status_code == 201
        photo_ids.append(upload.json()["id"])
    session.add(
        CranePhoto(
            crane_id=uuid.UUID(crane["id"]),
            storage_key="pending-test.jpg",
            original_filename="pending.jpg",
            content_type="image/jpeg",
            status=CranePhotoStatus.PENDING_UPLOAD,
        )
    )
    session.commit()
    auth = headers(client)
    assert len(client.get("/cranes/photos", headers=auth).json()["photos"]) == 2
    page = client.get("/cranes/photos?limit=1", headers=auth)
    assert page.status_code == 200
    assert page.json()["end"] is False
    assert page.json()["photos"][0]["id"] == photo_ids[1]
    next_page = client.get(
        f"/cranes/photos?limit=1&cursor={photo_ids[1]}", headers=auth
    ).json()
    assert next_page["photos"][0]["id"] == photo_ids[0]
    assert next_page["end"] is True
    path = f"/cranes/{crane['id']}/photos/{photo_ids[1]}"
    assert client.delete(path).status_code == 401
    assert (
        session.get(CranePhoto, uuid.UUID(photo_ids[1])).status
        == CranePhotoStatus.ACTIVE
    )
    assert client.delete(path, headers=auth).status_code == 204
    photo = session.get(CranePhoto, uuid.UUID(photo_ids[1]))
    assert photo.status == CranePhotoStatus.PENDING_DELETE
    assert session.scalar(select(OutboxJob)).storage_key == photo.storage_key
    assert client.delete(path, headers=auth).status_code == 404
    assert len(client.get("/cranes/photos", headers=auth).json()["photos"]) == 1
    assert client.get(f"/cranes/{crane['id']}").status_code == 200
    assert (
        client.delete(
            f"/cranes/{uuid.uuid4()}/photos/{photo_ids[0]}", headers=auth
        ).status_code
        == 404
    )


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_review_limits(client, admin, limit):
    assert (
        client.get(f"/cranes/photos?limit={limit}", headers=headers(client)).status_code
        == 422
    )


def test_login_rate_limited(client, admin):
    for _ in range(5):
        assert (
            client.post(
                "/admin/login", json={"username": "reviewer", "password": "wrong"}
            ).status_code
            == 401
        )
    assert login(client).status_code == 429
