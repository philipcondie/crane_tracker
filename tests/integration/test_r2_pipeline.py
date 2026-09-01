import base64
import threading

import httpx2
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select, text

from app.core.config import get_settings
from app.models.base import (
    CranePhoto,
    CranePhotoStatus,
    JobStatus,
    OutboxJob,
    generate_uuid7,
)
from app.schemas.base import CraneInput
from app.services.crane import create_crane
from app.services.photo import create_storage_key
from app.services.storage import _get_s3_client
from app.worker.photo_jobs import run_delete_batch, run_reap_crane_photos
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG

pytestmark = pytest.mark.integration

# Smallest valid 1x1 transparent PNG
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_add_photo_succeeds(client, key_list):
    create_crane_resp = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )

    crane_data = create_crane_resp.json()

    photo_upload_resp = client.post(
        f"/cranes/{crane_data['id']}/photos",
        files={"photo": ("test.png", PNG_BYTES, "image/png")},
    )

    assert photo_upload_resp.status_code == 201
    photo_data = photo_upload_resp.json()

    storage_key = create_storage_key(
        photo_data["craneId"], photo_id=photo_data["id"], extension=".png"
    )
    key_list.append(storage_key)

    settings = get_settings()
    storage_client = _get_s3_client()

    head_obj_resp = storage_client.head_object(
        Bucket=settings.r2_bucket_name, Key=storage_key
    )
    assert head_obj_resp["ContentType"] == "image/png"

    get_photo_resp = httpx2.get(photo_data["url"])
    assert get_photo_resp.status_code == 200
    assert get_photo_resp.headers.get("content-type") == "image/png"


def test_delete_photo_succeeds(client, session, key_list):
    create_crane_resp = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
        },
    )
    crane_data = create_crane_resp.json()

    photo_upload_resp = client.post(
        f"/cranes/{crane_data['id']}/photos",
        files={"photo": ("test.png", PNG_BYTES, "image/png")},
    )
    photo_data = photo_upload_resp.json()

    storage_key = create_storage_key(
        photo_data["craneId"], photo_id=photo_data["id"], extension=".png"
    )
    key_list.append(storage_key)

    delete_resp = client.delete(f"/cranes/{crane_data['id']}/photos/{photo_data['id']}")
    assert delete_resp.status_code == 204

    delete_count = run_delete_batch(session=session, shutdown=threading.Event())
    assert delete_count == 1

    settings = get_settings()
    storage_client = _get_s3_client()

    with pytest.raises(ClientError) as exc:
        storage_client.head_object(Bucket=settings.r2_bucket_name, Key=storage_key)
    assert exc.value.response["Error"]["Code"] == "404"


def test_reap_photo_succeeds(session):
    crane_input = CraneInput(
        lat=SF_TEST_LAT,
        lng=SF_TEST_LNG,
        project_name="test_project",
    )
    crane = create_crane(
        session=session, input=crane_input, override_duplicate_warning=False
    )
    crane_id = crane.id

    storage_key = create_storage_key(
        crane_id, photo_id=generate_uuid7(), extension=".png"
    )
    photo = CranePhoto(
        crane_id=crane.id,
        storage_key=storage_key,
        original_filename="test_photo",
        content_type="image/png",
        status=CranePhotoStatus.PENDING_UPLOAD,
        # Backdate past PHOTO_REAPER_DELAY so the reaper picks it up
        # immediately, independent of the configured window.
        added_at=text("now() - INTERVAL '1 hour'"),
    )
    session.add(photo)
    session.commit()
    photo_id = photo.id

    reap_count = run_reap_crane_photos(session=session)
    assert reap_count == 1

    delete_count = run_delete_batch(session=session, shutdown=threading.Event())
    assert delete_count == 1
    assert (
        session.scalars(
            select(CranePhoto).where(CranePhoto.id == photo_id)
        ).one_or_none()
        is None
    )
    outbox_job = session.scalars(
        select(OutboxJob).where(OutboxJob.storage_key == storage_key)
    ).one_or_none()
    assert outbox_job.status == JobStatus.COMPLETED

    settings = get_settings()
    storage_client = _get_s3_client()

    with pytest.raises(ClientError) as exc:
        storage_client.head_object(Bucket=settings.r2_bucket_name, Key=storage_key)
    assert exc.value.response["Error"]["Code"] == "404"
