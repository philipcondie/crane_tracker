from io import BytesIO
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

import app.services.storage as storage_service
from app.core.exceptions import PhotoStorageError


@pytest.fixture(autouse=True)
def clear_s3_client_cache():
    storage_service._get_s3_client.cache_clear()
    yield
    storage_service._get_s3_client.cache_clear()


@pytest.fixture
def r2_settings():
    return SimpleNamespace(
        r2_endpoint_url="https://account.r2.cloudflarestorage.com",
        r2_access_key_id="access-key",
        r2_secret_access_key="secret-key",
        r2_bucket_name="crane-photos",
        r2_public_base_url="https://photos.example.com",
    )


def test_upload_photo_uses_r2_s3_client(monkeypatch, r2_settings):
    client = SimpleNamespace(upload_fileobj=lambda *args, **kwargs: None)
    client_calls = []
    upload_calls = []

    def fake_client(service_name, **kwargs):
        client_calls.append((service_name, kwargs))

        def fake_upload_fileobj(file, bucket, object_key, *, ExtraArgs):
            upload_calls.append((file.read(), bucket, object_key, ExtraArgs))

        client.upload_fileobj = fake_upload_fileobj
        return client

    monkeypatch.setattr(storage_service, "get_settings", lambda: r2_settings)
    monkeypatch.setattr(storage_service.boto3, "client", fake_client)

    result = storage_service.upload_photo(
        BytesIO(b"photo bytes"),
        object_key="cranes/crane id/photos/photo 1.jpg",
        content_type="image/jpeg",
    )

    assert client_calls == [
        (
            "s3",
            {
                "endpoint_url": "https://account.r2.cloudflarestorage.com",
                "aws_access_key_id": "access-key",
                "aws_secret_access_key": "secret-key",
                "region_name": "auto",
            },
        )
    ]
    assert upload_calls == [
        (
            b"photo bytes",
            "crane-photos",
            "cranes/crane id/photos/photo 1.jpg",
            {"ContentType": "image/jpeg"},
        )
    ]
    assert result is None


def test_get_public_url_uses_current_domain(monkeypatch, r2_settings):
    monkeypatch.setattr(storage_service, "get_settings", lambda: r2_settings)

    url = storage_service.get_public_url(
        object_key="cranes/crane id/photos/photo 1.jpg"
    )

    assert url == "https://photos.example.com/cranes/crane%20id/photos/photo%201.jpg"

    r2_settings.r2_public_base_url = "https://new-photos.example.com"
    updated_url = storage_service.get_public_url(
        object_key="cranes/crane id/photos/photo 1.jpg"
    )
    assert (
        updated_url
        == "https://new-photos.example.com/cranes/crane%20id/photos/photo%201.jpg"
    )


def test_delete_photo_uses_r2_s3_client(monkeypatch, r2_settings):
    delete_calls = []
    client = SimpleNamespace(delete_object=lambda **kwargs: delete_calls.append(kwargs))
    monkeypatch.setattr(storage_service, "get_settings", lambda: r2_settings)
    monkeypatch.setattr(storage_service.boto3, "client", lambda *args, **kwargs: client)

    storage_service.delete_photo(object_key="cranes/id/photos/photo.jpg")

    assert delete_calls == [
        {"Bucket": "crane-photos", "Key": "cranes/id/photos/photo.jpg"}
    ]


def test_upload_photo_rejects_missing_configuration(monkeypatch, r2_settings):
    r2_settings.r2_bucket_name = None
    monkeypatch.setattr(storage_service, "get_settings", lambda: r2_settings)

    with pytest.raises(PhotoStorageError, match="not configured"):
        storage_service.upload_photo(
            BytesIO(b"photo bytes"),
            object_key="cranes/id/photos/photo.jpg",
            content_type="image/jpeg",
        )


def test_upload_photo_wraps_s3_error(monkeypatch, r2_settings):
    error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}},
        "PutObject",
    )

    def fail_upload(*args, **kwargs):
        raise error

    client = SimpleNamespace(upload_fileobj=fail_upload)
    monkeypatch.setattr(storage_service, "get_settings", lambda: r2_settings)
    monkeypatch.setattr(storage_service.boto3, "client", lambda *args, **kwargs: client)

    with pytest.raises(PhotoStorageError, match="could not be stored") as exc_info:
        storage_service.upload_photo(
            BytesIO(b"photo bytes"),
            object_key="cranes/id/photos/photo.jpg",
            content_type="image/jpeg",
        )

    assert exc_info.value.__cause__ is error
