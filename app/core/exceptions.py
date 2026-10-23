class ResourceNotFoundError(Exception):
    """Exception for when items are not found in database"""

    def __init__(self, resource, identifier):
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"Resource ({resource}) not found for {identifier}")


class InvalidCoordinateError(Exception):
    """Exception for when user supplies invalid lat/lng"""

    def __init__(self, message):
        super().__init__(message)


class GeocodeRetrievalError(Exception):
    """Exception for failures with the geocode lookup"""

    def __init__(self, message):
        super().__init__(f"Geocode API request failed for {message}")


class DuplicateGoneReportError(Exception):
    """Exception for when the same ip reports the same crane as gone"""

    def __init__(self, crane_id):
        self.crane_id = crane_id
        super().__init__("Duplicate gone reports submitted by same IP for same crane")


class DuplicateCraneError(Exception):
    """Exception for if the user may be entering a duplicate crane"""

    def __init__(self, *, lat: float, lng: float) -> None:
        self.lat = lat
        self.lng = lng
        super().__init__("Possible duplicate crane entry. Ensure it is a new crane")


class InvalidPhotoError(Exception):
    """Exception for a photo that fails upload validation.

    Subclasses set ``status_code`` to the response status the API should
    return; a single exception handler reads it via the MRO lookup.
    """

    status_code = 422


class PhotoTooLargeError(InvalidPhotoError):
    """Exception for a photo that exceeds the upload size limit."""

    status_code = 413


class UnsupportedPhotoTypeError(InvalidPhotoError):
    """Exception for a photo with a disallowed media type."""

    status_code = 415


class PhotoLimitExceededError(Exception):
    """Exception for a crane that already has the maximum number of photos."""

    def __init__(
        self, message: str, *, crane_id, active_photo_count: int | None
    ) -> None:
        self.crane_id = crane_id
        self.active_photo_count = active_photo_count
        super().__init__(message)


class PhotoStorageError(Exception):
    """Exception for a failure while storing a photo."""


class PhotoUploadRaceError(Exception):
    """Exception for a failure to upload the photo"""

    def __init__(self) -> None:
        super().__init__("Race error during photo upload. Try again.")
