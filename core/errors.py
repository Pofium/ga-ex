class RpaError(Exception):
    pass


class InvalidHeaderError(RpaError):
    pass


class InvalidIndexError(RpaError):
    pass


class PathTraversalError(RpaError):
    pass


class PermissionError(RpaError):
    pass


class DiskSpaceError(RpaError):
    pass


class PathLengthError(RpaError):
    pass
