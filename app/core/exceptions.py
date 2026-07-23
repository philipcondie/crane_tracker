class ResourceNotFoundError(Exception):
    """Exception for when items are not found in database"""

    def __init__(self, resource, identifier):
        super().__init__(f"Resource ({resource}) not found for {identifier}")


class InvalidCoordinateError(Exception):
    """Exception for when user supplies invalid lat/lng"""

    def __init__(self, message):
        super().__init__(message)


class GeocodeRetrievalError(Exception):
    """Exception for failures with the geocode lookup"""

    def __init__(self, message):
        super().__init__(f"Geocode API request failed for {message}")
