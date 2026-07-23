from tests.utils.constants import SF_TEST_LAT, SF_TEST_LNG


def test_create_crane_route(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
            "status": "active",
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


def test_get_crane_route(client):
    response = client.post(
        "/cranes",
        json={
            "lat": SF_TEST_LAT,
            "lng": SF_TEST_LNG,
            "projectName": "test_project",
            "status": "active",
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
            "status": "active",
        },
    )

    client.post(
        "/cranes",
        json={
            "lat": 50,
            "lng": 50,
            "projectName": "inside",
            "status": "active",
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
