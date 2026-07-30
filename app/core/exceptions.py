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


class DuplicateGoneReportError(Exception):
    """Exception for when the same ip reports the same crane as gone"""

    def __init__(self):
        super().__init__("Duplicate gone reports submitted by same IP for same crane")


class DuplicateCraneError(Exception):
    """Exception for if the user may be entering a duplicate crane"""

    def __init__(
        self,
    ) -> None:
        super().__init__("Possible duplicate crane entry. Ensure it is a new crane")


class InvalidPhotoError(Exception):
    """Exception for a photo that fails upload validation."""


class PhotoTooLargeError(InvalidPhotoError):
    """Exception for a photo that exceeds the upload size limit."""


class PhotoLimitExceededError(InvalidPhotoError):
    """Exception for a crane that already has the maximum number of photos."""


class UnsupportedPhotoTypeError(InvalidPhotoError):
    """Exception for a photo with a disallowed media type."""


class PhotoStorageError(Exception):
    """Exception for a failure while storing a photo."""
