import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.main import app
from app.models.base import (
    AdminUser,
    CranePhoto,
    CranePhotoStatus,
    OutboxJob,
    PhotoReport,
)
from app.services.auth import hash_password
from app.services.crane import hash_ip
from tests.utils.images import TEST_JPEG_BYTES


@pytest.fixture
def photos(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.storage.upload_photo", lambda *args, **kwargs: None
    )
    crane = client.post("/cranes", json={"lat": 37.77, "lng": -122.42}).json()
    uploaded = []
    for _ in range(3):
        response = client.post(
            f"/cranes/{crane['id']}/photos",
            files={"photo": ("test.jpg", TEST_JPEG_BYTES, "image/jpeg")},
        )
        assert response.status_code == 201
        uploaded.append(response.json())
    return crane, uploaded


@pytest.fixture
def auth(client, session):
    password = "long admin report testing password"
    session.add(AdminUser(username="reviewer", password_hash=hash_password(password)))
    session.commit()
    token = client.post(
        "/admin/login", json={"username": "reviewer", "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def path(photo):
    return f"/cranes/{photo['craneId']}/photos/{photo['id']}/report"


def test_anonymous_reporting_deduplicates_and_ignores_forwarded_headers(
    client, session, photos
):
    _, uploaded = photos
    with TestClient(app, client=("192.0.2.1", 1234)) as reporter:
        assert reporter.post(path(uploaded[0])).status_code == 201
        assert (
            reporter.post(
                path(uploaded[0]), headers={"X-Forwarded-For": "192.0.2.2"}
            ).status_code
            == 409
        )
        assert reporter.post(path(uploaded[1])).status_code == 201
    with TestClient(app, client=("192.0.2.2", 1234)) as reporter:
        assert reporter.post(path(uploaded[0])).status_code == 201
    reports = session.scalars(select(PhotoReport)).all()
    assert len(reports) == 3
    assert {report.reporter_ip_hash for report in reports} == {
        hash_ip("192.0.2.1"),
        hash_ip("192.0.2.2"),
    }
    assert all(len(report.reporter_ip_hash) == 64 for report in reports)
    assert session.scalar(select(OutboxJob)) is None
    assert (
        session.get(CranePhoto, uuid.UUID(uploaded[0]["id"])).status
        == CranePhotoStatus.ACTIVE
    )
    # Public viewing and upload responses never expose report metadata.
    assert "reportCount" not in uploaded[0]
    assert (
        "reportCount"
        not in client.get(f"/cranes/{uploaded[0]['craneId']}").json()["photoItems"][0]
    )


def test_admin_report_counts_filter_and_cursor(client, session, photos, auth):
    _, uploaded = photos
    for photo in uploaded[:2]:
        assert client.post(path(photo)).status_code == 201
    assert client.get("/cranes/photos?reported_only=true").status_code == 401
    all_photos = client.get("/cranes/photos", headers=auth).json()["photos"]
    assert [photo["reportCount"] for photo in all_photos] == [0, 1, 1]
    page = client.get("/cranes/photos?reported_only=true&limit=1", headers=auth).json()
    assert page["end"] is False
    assert page["photos"][0]["id"] == uploaded[1]["id"]
    next_page = client.get(
        f"/cranes/photos?reported_only=true&limit=1&cursor={uploaded[1]['id']}",
        headers=auth,
    ).json()
    assert next_page["end"] is True
    assert next_page["photos"][0]["id"] == uploaded[0]["id"]
    assert (
        client.delete(
            f"/cranes/{uploaded[1]['craneId']}/photos/{uploaded[1]['id']}", headers=auth
        ).status_code
        == 204
    )
    assert client.post(path(uploaded[1])).status_code == 404
    assert (
        len(
            client.get("/cranes/photos?reported_only=true", headers=auth).json()[
                "photos"
            ]
        )
        == 1
    )
    # Permanent photo deletion cascades reports, as in the existing worker.
    session.execute(
        delete(CranePhoto).where(CranePhoto.id == uuid.UUID(uploaded[1]["id"]))
    )
    session.commit()
    assert session.scalar(select(func.count(PhotoReport.id))) == 1


@pytest.mark.parametrize(
    "photo_status", [CranePhotoStatus.PENDING_UPLOAD, CranePhotoStatus.PENDING_DELETE]
)
def test_unavailable_photos_cannot_be_reported(client, session, photos, photo_status):
    _, uploaded = photos
    photo = session.get(CranePhoto, uuid.UUID(uploaded[0]["id"]))
    photo.status = photo_status
    session.commit()
    assert client.post(path(uploaded[0])).status_code == 404
    assert session.scalar(select(PhotoReport)) is None


def test_missing_or_mismatched_photo(client, session, photos):
    _, uploaded = photos
    assert (
        client.post(
            f"/cranes/{uuid.uuid4()}/photos/{uploaded[0]['id']}/report"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/cranes/{uploaded[0]['craneId']}/photos/{uuid.uuid4()}/report"
        ).status_code
        == 404
    )
    assert session.scalar(select(PhotoReport)) is None


def test_missing_client_address(client, session, photos):
    _, uploaded = photos
    with TestClient(app, client=None) as reporter:
        assert reporter.post(path(uploaded[0])).status_code == 400
    assert session.scalar(select(PhotoReport)) is None


def test_report_rate_limit(client, session, photos):
    _, uploaded = photos
    assert client.post(path(uploaded[0])).status_code == 201
    for _ in range(9):
        assert client.post(path(uploaded[0])).status_code == 409
    assert client.post(path(uploaded[0])).status_code == 429
    assert session.scalar(select(func.count(PhotoReport.id))) == 1
