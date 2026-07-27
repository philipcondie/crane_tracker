from fastapi.testclient import TestClient

from app.main import app
from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG, TEST_IP_ADDR


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
