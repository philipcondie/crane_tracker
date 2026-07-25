import pytest
from pydantic import ValidationError

from app.schemas.base import CraneCreate


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
        CraneCreate(**payload)
    else:
        with pytest.raises(ValidationError):
            CraneCreate(**payload)
