"""User-facing exceptions for expected data and export failures."""


class STDEError(Exception):
    """Base class for errors that can be explained cleanly in the GUI."""


class DatasetError(STDEError):
    """Input data cannot be interpreted as a supported time series."""


class TimeConfigurationRequired(DatasetError):
    """No defensible absolute time was discovered and user choice is needed."""


class WCSUnavailableError(STDEError):
    """A requested world-coordinate operation lacks a valid two-dimensional WCS."""


class ExportError(STDEError):
    """An image, movie, or data product could not be written."""
