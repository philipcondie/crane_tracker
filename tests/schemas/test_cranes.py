import pytest
from pydantic import ValidationError

from app.schemas.base import CraneInput, CreateCraneRequest


@pytest.mark.parametrize(
    "payload,valid",
    [
        ({"lat": -90, "lng": 0, "project_name": "test_project"}, True),
        ({"lat": 90, "lng": 0, "project_name": "test_project"}, True),
        ({"lat": 0, "lng": -180, "project_name": "test_project"}, True),
        ({"lat": 0, "lng": 180, "project_name": "test_project"}, True),
        ({"lat": 0, "lng": 0, "project_name": 2}, False),
        ({"lat": 0, "lng": 0}, True),
        ({"lat": -91, "lng": 0, "project_name": "test_project"}, False),
        ({"lat": 91, "lng": 0, "project_name": "test_project"}, False),
        ({"lat": 0, "lng": -181, "project_name": "test_project"}, False),
        ({"lat": 0, "lng": 181, "project_name": "test_project"}, False),
    ],
)
def test_crane_create_schema(payload, valid):
    if valid:
        CraneInput(**payload)
    else:
        with pytest.raises(ValidationError):
            CraneInput(**payload)


def test_create_crane_request_defaults_duplicate_override_to_false():
    request = CreateCraneRequest(lat=0, lng=0)

    assert request.override_duplicate_warning is False


def test_create_crane_request_accepts_camel_case_duplicate_override():
    request = CreateCraneRequest(
        lat=0,
        lng=0,
        overrideDuplicateWarning=True,
    )

    assert request.override_duplicate_warning is True


def test_create_crane_request_rejects_invalid_duplicate_override():
    with pytest.raises(ValidationError):
        CreateCraneRequest(
            lat=0,
            lng=0,
            overrideDuplicateWarning="not-a-boolean",
        )
