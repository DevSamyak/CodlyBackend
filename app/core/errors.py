"""Application errors. Mapped to JSON responses in app.main."""


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class UpstreamError(AppError):
    """A third-party site (Codeforces, LeetCode, ...) failed or changed shape."""

    status_code = 502
    code = "upstream_error"


class UpstreamHTTPError(Exception):
    """Raised by HttpClient implementations for HTTP status >= 400."""

    def __init__(self, status: int, body: str = ""):
        super().__init__(f"upstream HTTP {status}")
        self.status = status
        self.body = body
