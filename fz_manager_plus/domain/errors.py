class OperationError(Exception):
    """An operation cannot be completed; safe to display to the user."""


class DisconnectedError(OperationError):
    pass


class AuthenticationError(OperationError):
    pass


class ApiError(OperationError):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


class DecodeError(OperationError):
    def __init__(self, source: Exception, raw_body: str):
        self.source = source
        self.raw_body = raw_body
        super().__init__("The server returned an invalid response.")
