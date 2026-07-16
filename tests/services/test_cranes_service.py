import pytest

from app.core.exceptions import ResourceNotFoundError
from app.models.base import generate_uuid7
from app.schemas.base import CraneCreate, CraneStatus
from app.services.cranes import create_crane, delete_crane, get_crane


def test_create_crane_valid(session):

    crane_input = CraneCreate(
        lat=0, lng=0, project_name="test_project", status=CraneStatus.ACTIVE
    )
    crane = create_crane(session=session, input=crane_input)

    assert crane.id is not None
    assert crane.lat == 0
    assert crane.lng == 0
    assert crane.project_name == "test_project"
    assert crane.status == CraneStatus.ACTIVE


def test_get_crane_valid(session):
    crane_input = CraneCreate(
        lat=0, lng=0, project_name="test_project", status=CraneStatus.ACTIVE
    )
    crane_create = create_crane(session=session, input=crane_input)

    crane_get = get_crane(session, crane_create.id)

    assert crane_create.id == crane_get.id
    assert crane_create.lat == crane_get.lat
    assert crane_create.lng == crane_get.lng
    assert crane_create.project_name == crane_get.project_name


def test_get_crane_invalid(session):
    with pytest.raises(ResourceNotFoundError):
        get_crane(session=session, id=generate_uuid7())


def test_delete_crane_valid(session):
    crane_input = CraneCreate(
        lat=0, lng=0, project_name="test_project", status=CraneStatus.ACTIVE
    )
    crane_create = create_crane(session=session, input=crane_input)

    delete_crane(session=session, id=crane_create.id)

    with pytest.raises(ResourceNotFoundError):
        get_crane(session=session, id=crane_create.id)


def test_delete_crane_invalid(session):
    with pytest.raises(ResourceNotFoundError):
        delete_crane(session=session, id=generate_uuid7())
