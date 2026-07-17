import pytest

from app.core.exceptions import InvalidCoordinateError, ResourceNotFoundError
from app.models.base import generate_uuid7
from app.schemas.base import CraneCreate, CraneStatus
from app.services.crane import create_crane, delete_crane, get_crane, get_cranes


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


def test_get_cranes_valid(session):
    crane_1_input = CraneCreate(
        lat=10, lng=10, project_name="crane_1", status=CraneStatus.ACTIVE
    )

    crane_2_input = CraneCreate(
        lat=2, lng=7, project_name="crane_2", status=CraneStatus.ACTIVE
    )

    crane_3_input = CraneCreate(
        lat=10.1, lng=10.1, project_name="crane_3", status=CraneStatus.ACTIVE
    )

    crane_1 = create_crane(session, crane_1_input)
    crane_2 = create_crane(session, crane_2_input)
    crane_3 = create_crane(session, crane_3_input)

    crane_list = get_cranes(session=session, north=10, south=0, east=10, west=0)
    assert len(crane_list) == 2
    id_list = [crane.id for crane in crane_list]
    assert crane_1.id in id_list
    assert crane_2.id in id_list
    assert crane_3.id not in id_list


def test_get_cranes_empty_list(session):
    crane_1_input = CraneCreate(
        lat=10, lng=10, project_name="crane_1", status=CraneStatus.ACTIVE
    )

    create_crane(session, crane_1_input)

    crane_list = get_cranes(session=session, north=0, south=-10, east=0, west=-10)
    assert len(crane_list) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"north": 91, "south": 0, "east": 1, "west": 0},
        {"north": 0, "south": 91, "east": 1, "west": 0},
        {"north": 1, "south": 0, "east": 181, "west": 0},
        {"north": 1, "south": 0, "east": 0, "west": -181},
        {"north": 0, "south": 1, "east": 1, "west": 0},
        {"north": 1, "south": 0, "east": 0, "west": 1},
    ],
)
def test_get_cranes_bad_input(session, payload):
    with pytest.raises(InvalidCoordinateError):
        get_cranes(session=session, **payload)
