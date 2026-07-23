from dataclasses import dataclass

import requests
from requests.exceptions import (
    ConnectionError,
    HTTPError,
    JSONDecodeError,
    RequestException,
    Timeout,
)

from app.core.exceptions import GeocodeRetrievalError

GEOCODE_API_URL = "https://nominatim.openstreetmap.org/reverse?"
TIMEOUT_SECONDS = 5


@dataclass
class GeocodeData:
    city: str | None
    neighborhood: str | None


def extract_neighborhood(address: dict) -> str | None:
    for field in (
        "neighbourhood",
        "quarter",
        "suburb",
        "city_district",
        "borough",
        "district",
    ):
        if value := address.get(field):
            return value

    return None


def extract_city(address: dict) -> str | None:
    for field in ("city", "town", "village", "municipality"):
        if value := address.get(field):
            return value

    return None


def reverse_geocode(lat: float, lng: float) -> GeocodeData:
    query_params = {
        "format": "jsonv2",
        "addressdetails": "1",
        "zoom": "18",
        "lat": lat,
        "lon": lng,
    }

    headers = {"User-Agent": "crane-tracker/0.1 (contact: philipcondie@gmail.com)"}
    try:
        resp = requests.get(
            GEOCODE_API_URL,
            params=query_params,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except Timeout:
        raise GeocodeRetrievalError(f"timeout {TIMEOUT_SECONDS} seconds")
    except ConnectionError:
        raise GeocodeRetrievalError("connection error")
    except HTTPError as e:
        status_code = e.response.status_code if e.response else "unknown"
        raise GeocodeRetrievalError(f"bad status {status_code}")
    except RequestException as e:
        raise GeocodeRetrievalError(f"request error {e}")

    try:
        if address := resp.json().get("address"):
            return GeocodeData(
                city=extract_city(address), neighborhood=extract_neighborhood(address)
            )
        else:
            return GeocodeData(city=None, neighborhood=None)
    except JSONDecodeError:
        raise GeocodeRetrievalError("JSON parse")
