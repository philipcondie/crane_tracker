def test_create_crane_route(client):

    response = client.post(
        "/cranes",
        json={
            "lat": 10,
            "lng": 20,
            "project_name": "test_project",
            "status": "active",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] is not None
    assert data["lat"] == 10
    assert data["lng"] == 20
    assert data["project_name"] == "test_project"
    assert data["status"] == "active"


def test_get_crane_route(client):

    response = client.post(
        "/cranes",
        json={
            "lat": 10,
            "lng": 20,
            "project_name": "test_project",
            "status": "active",
        },
    )

    crane_id = response.json()["id"]

    get_response = client.get(f"/cranes/{crane_id}")

    assert get_response.status_code == 200
    assert get_response.json()["id"] == crane_id


def test_get_cranes_route_filters_by_bounds(client):
    client.post(
        "/cranes",
        json={
            "lat": 5,
            "lng": 5,
            "project_name": "inside",
            "status": "active",
        },
    )

    client.post(
        "/cranes",
        json={
            "lat": 50,
            "lng": 50,
            "project_name": "inside",
            "status": "active",
        },
    )

    response = client.get("/cranes?north=10&south=0&east=10&west=0")

    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["project_name"] == "inside"


def test_get_crane_route_returns_404_for_missing_crane(client):
    response = client.get("/cranes/019f6854-fcc3-7831-b1ee-d642e12732cc")

    assert response.status_code == 404


def test_get_cranes_route_rejects_out_of_range_query_params(client):
    response = client.get("/cranes?north=91&south=0&east=10&west=0")

    assert response.status_code == 422


def test_get_cranes_route_rejects_reversed_bounds(client):
    response = client.get("/cranes?north=0&south=10&east=10&west=0")

    assert response.status_code == 400
