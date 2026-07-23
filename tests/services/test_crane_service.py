import pytest

from app.core.exceptions import InvalidCoordinateError, ResourceNotFoundError
from app.models.base import generate_uuid7
from app.schemas.base import CraneCreate, CraneStatus
from app.services.crane import create_crane, delete_crane, get_crane, get_cranes
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG


def test_create_crane_valid(session):
    crane_input = CraneCreate(
        lat=SF_TEST_LAT,
        lng=SF_TEST_LNG,
        project_name="test_project",
        status=CraneStatus.ACTIVE,
    )
    crane = create_crane(session=session, input=crane_input)

    assert crane.id is not None
    assert crane.lat == SF_TEST_LAT
    assert crane.lng == SF_TEST_LNG
    assert crane.project_name == "test_project"
    assert crane.status == CraneStatus.ACTIVE
    assert crane.city == "San Francisco"
    assert crane.neighborhood == "Mission Bay"


def test_get_crane_valid(session):
    crane_input = CraneCreate(
        lat=SF_TEST_LAT,
        lng=SF_TEST_LNG,
        project_name="test_project",
        status=CraneStatus.ACTIVE,
    )
    crane_create = create_crane(session=session, input=crane_input)

    crane_get = get_crane(session, crane_create.id)

    assert crane_create.id == crane_get.id
    assert crane_create.lat == crane_get.lat
    assert crane_create.lng == crane_get.lng
    assert crane_create.project_name == crane_get.project_name
    assert crane_create.city == crane_get.city
    assert crane_create.neighborhood == crane_get.neighborhood


def test_get_crane_invalid(session):
    with pytest.raises(ResourceNotFoundError):
        get_crane(session=session, id=generate_uuid7())


def test_delete_crane_valid(session):
    crane_input = CraneCreate(
        lat=SF_TEST_LAT,
        lng=SF_TEST_LNG,
        project_name="test_project",
        status=CraneStatus.ACTIVE,
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

    crane_result = get_cranes(session=session, north=10, south=0, east=10, west=0)
    assert len(crane_result.cranes) == 2
    id_list = [crane.id for crane in crane_result.cranes]
    assert crane_1.id in id_list
    assert crane_2.id in id_list
    assert crane_3.id not in id_list
    assert crane_result.truncated is False


def test_get_cranes_at_limit(session):
    crane_1_input = CraneCreate(
        lat=10, lng=10, project_name="crane_1", status=CraneStatus.ACTIVE
    )

    crane_2_input = CraneCreate(
        lat=2, lng=7, project_name="crane_2", status=CraneStatus.ACTIVE
    )

    crane_1 = create_crane(session, crane_1_input)
    crane_2 = create_crane(session, crane_2_input)
    crane_result = get_cranes(
        session=session, north=10, south=0, east=10, west=0, limit=2
    )

    crane_result = get_cranes(session=session, north=10, south=0, east=10, west=0)
    assert len(crane_result.cranes) == 2
    id_list = [crane.id for crane in crane_result.cranes]
    assert crane_1.id in id_list
    assert crane_2.id in id_list
    assert crane_result.truncated is False


def test_get_cranes_above_limit(session):
    crane_1_input = CraneCreate(
        lat=10, lng=10, project_name="crane_1", status=CraneStatus.ACTIVE
    )

    crane_2_input = CraneCreate(
        lat=2, lng=7, project_name="crane_2", status=CraneStatus.ACTIVE
    )

    crane_3_input = CraneCreate(
        lat=4, lng=4, project_name="crane_3", status=CraneStatus.ACTIVE
    )

    crane_1 = create_crane(session, crane_1_input)
    crane_2 = create_crane(session, crane_2_input)
    crane_3 = create_crane(session, crane_3_input)

    crane_result = get_cranes(
        session=session, north=10, south=0, east=10, west=0, limit=2
    )
    assert len(crane_result.cranes) == 2
    id_list = [crane.id for crane in crane_result.cranes]
    assert crane_1.id in id_list
    assert crane_2.id in id_list
    assert crane_3.id not in id_list
    assert crane_result.truncated is True


def test_get_cranes_empty_list(session):
    crane_1_input = CraneCreate(
        lat=10, lng=10, project_name="crane_1", status=CraneStatus.ACTIVE
    )

    create_crane(session, crane_1_input)

    crane_result = get_cranes(session=session, north=0, south=-10, east=0, west=-10)
    assert len(crane_result.cranes) == 0


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
