from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import PhotoStorageError
from app.main import app
from app.models.base import CranePhoto
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG, TEST_IP_ADDR
from tests.utils.images import TEST_GIF_BYTES, TEST_JPEG_BYTES


def test_create_crane_route(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["lat"] == SF_TEST_LAT
    assert data["lng"] == SF_TEST_LNG
    assert data["projectName"] == "test_project"
    assert data["status"] == "active"
    assert data["city"] == "San Francisco"
    assert data["neighborhood"] == "Mission Bay"


def test_create_crane_route_returns_status_409(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    assert response.status_code == 409


def test_create_crane_route_returns_status_201_with_duplicate_override(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    assert response.status_code == 201

    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
            "overrideDuplicateWarning": True,
        },
    )

    assert response.status_code == 201


def test_get_crane_route(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    crane_id = response.json()["id"]

    get_response = client.get(f"/cranes/{crane_id}")

    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == crane_id
    assert data["city"] == "San Francisco"
    assert data["neighborhood"] == "Mission Bay"
    assert data["photos"] == 0
    assert data["photoItems"] == []


def test_get_cranes_route_filters_by_bounds(client):
    client.post(
        "/cranes",
        json={
            "lat": 5,
            "lng": 5,
            "projectName": "inside",
        },
    )

    client.post(
        "/cranes",
        json={
            "lat": 50,
            "lng": 50,
            "projectName": "inside",
        },
    )

    response = client.get("/cranes?north=10&south=0&east=10&west=0")

    assert response.status_code == 200

    data = response.json()
    cranes = data["cranes"]
    assert len(cranes) == 1
    assert cranes[0]["projectName"] == "inside"
    assert data["truncated"] is False


def test_get_crane_route_returns_404_for_missing_crane(client):
    response = client.get("/cranes/019f6854-fcc3-7831-b1ee-d642e12732cc")

    assert response.status_code == 404


def test_get_cranes_route_rejects_out_of_range_query_params(client):
    response = client.get("/cranes?north=91&south=0&east=10&west=0")

    assert response.status_code == 422


def test_get_cranes_route_rejects_reversed_bounds(client):
    response = client.get("/cranes?north=0&south=10&east=10&west=0")

    assert response.status_code == 400


def test_report_crane_as_gone_route_returns_409_for_duplicate(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    crane_id = response.json()["id"]

    report_response = client.post(
        f"/cranes/{crane_id}/report", headers={"X-Forwarded-For": TEST_IP_ADDR}
    )
    report_response = client.post(
        f"/cranes/{crane_id}/report", headers={"X-Forwarded-For": TEST_IP_ADDR}
    )

    assert report_response.status_code == 409


def test_report_crane_as_gone_route_returns_404_for_missing_crane(client):
    response = client.post(
        "/cranes/019f6854-fcc3-7831-b1ee-d642e12732cc/report",
        headers={"X-Forwarded-For": TEST_IP_ADDR},
    )

    assert response.status_code == 404


def test_report_crane_as_gone_succeeds(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    crane_id = response.json()["id"]

    ip_addresses = [
        "127.0.0.1",
        "192.168.1.10",
        "203.0.113.42",
        "2001:db8::1",
    ]

    for ip_address in ip_addresses:
        with TestClient(app, client=(ip_address, 12345)) as report_client:
            report_response = report_client.post(f"/cranes/{crane_id}/report")
            assert report_response.status_code == 200

    crane_response = client.get(f"/cranes/{crane_id}")
    data = crane_response.json()
    assert data["status"] == "gone"


def test_upload_crane_photo_route(client, session, monkeypatch):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]

    def fake_upload(file, *, object_key, content_type):
        assert session.in_transaction() is False
        with Image.open(BytesIO(file.read())) as uploaded:
            assert uploaded.format == "JPEG"
            assert len(uploaded.getexif()) == 0
        assert object_key.startswith(f"cranes/{crane_id}/photos/")
        assert content_type == "image/jpeg"

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["craneId"] == crane_id
    assert data["url"].startswith("https://photos.example/")
    assert data["originalFilename"] == "site.jpg"
    assert data["contentType"] == "image/jpeg"
    assert data["addedAt"] is not None

    detail_response = client.get(f"/cranes/{crane_id}")
    detail = detail_response.json()
    assert detail["photos"] == 1
    assert detail["photoItems"] == [data]
    assert "imgs" not in detail

    list_response = client.get("/cranes?north=38&south=37&east=-122&west=-123")
    listed_crane = list_response.json()["cranes"][0]
    assert listed_crane["id"] == crane_id
    assert listed_crane["photos"] == 1


def test_upload_crane_photo_route_rejects_fourth_photo(client, monkeypatch):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]
    upload_count = 0

    def fake_upload(file, *, object_key, content_type):
        nonlocal upload_count
        upload_count += 1

    monkeypatch.setattr("app.services.storage.upload_photo", fake_upload)

    for photo_number in range(3):
        response = client.post(
            f"/cranes/{crane_id}/photos",
            files={
                "photo": (
                    f"site-{photo_number}.jpg",
                    TEST_JPEG_BYTES,
                    "image/jpeg",
                )
            },
        )
        assert response.status_code == 201

    response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site-4.jpg", TEST_JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "A crane can have at most 3 photos"
    assert upload_count == 3


def test_upload_crane_photo_route_returns_404_for_missing_crane(client):
    response = client.post(
        "/cranes/019f6854-fcc3-7831-b1ee-d642e12732cc/photos",
        files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 404


def test_upload_crane_photo_route_rejects_non_image(client, monkeypatch):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]

    response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.txt", b"not a photo", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_crane_photo_route_rejects_gif(client):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]

    response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.gif", TEST_GIF_BYTES, "image/gif")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported photo content type: image/gif"


def test_upload_crane_photo_route_rejects_invalid_image_contents(client):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]

    response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.jpg", b"not really a JPEG", "image/jpeg")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "File is not a valid image"


def test_upload_crane_photo_route_returns_503_until_storage_is_configured(client):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]

    response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 503


def test_upload_crane_photo_route_cleans_up_r2_when_commit_fails(
    client, session, monkeypatch
):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]
    deleted_keys = []
    events = []
    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: (
            f"https://photos.example/{object_key}"
        ),
    )

    def track_delete(*, object_key):
        events.append("delete")
        deleted_keys.append(object_key)

    monkeypatch.setattr("app.services.storage.delete_photo", track_delete)
    original_rollback = session.rollback

    def track_rollback():
        events.append("rollback")
        return original_rollback()

    monkeypatch.setattr(session, "rollback", track_rollback)

    original_commit = session.commit
    commit_count = 0

    def fail_final_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("commit failed")
        return original_commit()

    with monkeypatch.context() as commit_patch:
        commit_patch.setattr(session, "commit", fail_final_commit)
        response = client.post(
            f"/cranes/{crane_id}/photos",
            files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Photo metadata could not be saved"
    assert len(deleted_keys) == 1
    assert events == ["rollback", "delete"]
    assert session.scalar(select(CranePhoto)) is None


def test_delete_crane_photo_route(client, monkeypatch):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]
    deleted_keys = []
    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: (
            f"https://photos.example/{object_key}"
        ),
    )
    monkeypatch.setattr(
        "app.services.storage.delete_photo",
        lambda *, object_key: deleted_keys.append(object_key),
    )
    upload_response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
    )
    photo_id = upload_response.json()["id"]

    response = client.delete(f"/cranes/{crane_id}/photos/{photo_id}")

    assert response.status_code == 204
    assert len(deleted_keys) == 1
    detail = client.get(f"/cranes/{crane_id}").json()
    assert detail["photos"] == 0
    assert detail["photoItems"] == []


def test_delete_crane_photo_route_keeps_record_when_r2_delete_fails(
    client, monkeypatch
):
    crane_response = client.post(
        "/cranes",
        json={"lat": SF_TEST_LAT, "lng": SF_TEST_LNG},
    )
    crane_id = crane_response.json()["id"]
    monkeypatch.setattr(
        "app.services.storage.upload_photo",
        lambda file, *, object_key, content_type: (
            f"https://photos.example/{object_key}"
        ),
    )
    upload_response = client.post(
        f"/cranes/{crane_id}/photos",
        files={"photo": ("site.jpg", TEST_JPEG_BYTES, "image/jpeg")},
    )
    photo_id = upload_response.json()["id"]

    def fail_delete(*, object_key):
        raise PhotoStorageError("Photo could not be deleted")

    monkeypatch.setattr("app.services.storage.delete_photo", fail_delete)

    response = client.delete(f"/cranes/{crane_id}/photos/{photo_id}")

    assert response.status_code == 503
    detail = client.get(f"/cranes/{crane_id}").json()
    assert detail["photos"] == 1
    assert detail["photoItems"][0]["id"] == photo_id


def test_delete_crane_photo_route_returns_404_for_missing_photo(client):
    response = client.delete(
        "/cranes/019f6854-fcc3-7831-b1ee-d642e12732cc/"
        "photos/019f6854-fcc3-7831-b1ee-d642e12732cd"
    )

    assert response.status_code == 404
