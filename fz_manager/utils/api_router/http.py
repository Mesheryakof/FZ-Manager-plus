"""Declarative REST client toolkit built on top of httpx + pydantic.

The pattern (inspired by Retrofit/uplink): an API method is a *request
builder*. It has access to ``self`` (client context: tokens, secrets, ...)
and only builds and returns an `httpx.Request` via `router.build_request(...)`
-- its own return annotation is honestly `httpx.Request`, since that's what
the function body actually returns.

`ApiRouterHttp` wraps an already-built `httpx.AsyncClient` and hands out an
`.endpoint(response_model)` decorator. It takes care of actually sending the
request and decoding the response into `response_model` via
`pydantic.TypeAdapter` (works for `BaseModel` subclasses as well as generic
containers like `list[Model]` or `dict[str, Model]`). The response type is
declared as an argument to the decorator rather than as the method's own
return annotation, and the decorator is typed with `ParamSpec`/`Concatenate`
so that the *wrapped* callable -- the one callers actually await -- is seen
by static type checkers as `Awaitable[response_model]`. This keeps both the
request-builder body and the public call site honestly typed, instead of
lying about what the undecorated function returns.

Domain classes don't inherit from anything to use this -- see
`ApiRouterHttp`'s docstring.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import Any, Concatenate, ParamSpec, TypeVar, overload

import httpx
from pydantic import TypeAdapter, ValidationError

P = ParamSpec("P")
T = TypeVar("T")


class ApiError(Exception):
    """Raised when an HTTP response is not a 2xx success."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


class DecodeError(Exception):
    """Raised when a successful response body cannot be decoded into the
    type declared by the endpoint's return annotation."""

    def __init__(self, source: ValidationError, raw_body: str):
        self.source = source
        self.raw_body = raw_body
        super().__init__(f"Failed to decode response: {source}")


class UploadProgressFile:
    """Wraps a binary file object and reports cumulative bytes read via `cb`.

    Used in place of requests-toolbelt's MultipartEncoderMonitor to track
    upload progress with httpx's native multipart encoding, which reads the
    file object in chunks via `.read(size)`.
    """

    def __init__(self, file, cb: Callable[[int], None] | None = None):
        self._file = file
        self._cb = cb
        self._bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._file.read(size)
        self._bytes_read += len(chunk)
        if self._cb:
            self._cb(self._bytes_read)
        return chunk

    def seek(self, *args, **kwargs):
        return self._file.seek(*args, **kwargs)

    def tell(self):
        return self._file.tell()

    def fileno(self):
        return self._file.fileno()


class ApiRouterHttp:
    """Standalone transport (wraps an already-built `httpx.AsyncClient`) that
    hands out an `.endpoint(...)` decorator.

    Domain classes don't inherit from anything -- their methods just take
    `self` for their own state (tokens, secrets, ...) and call
    `router.build_request(...)`:

        router_factorio_api = ApiRouterHttp(httpx.AsyncClient(base_url=f"https://{get_settings().factorio_zone_endpoint}"))

        class FactorioZone:
            @router_factorio_api.endpoint(response_model=LoginResponse)
            def login(self, reconnected: bool = False) -> httpx.Request:
                return router_factorio_api.build_request(method="POST", path="/api/user/login", ...)

    This does not build the `httpx.AsyncClient` itself -- the caller
    constructs and injects one. Whoever builds that client is responsible
    for not doing so as an import-time side effect if its configuration
    comes from something like `fz_manager.config.get_settings` (which
    parses `sys.argv` on first call).
    """

    def __init__(self, client: httpx.AsyncClient):
        self._http = client

    def build_request(self, method: str, path: str, **kwargs) -> httpx.Request:
        return self._http.build_request(method, path, **kwargs)

    async def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        """Send a request directly, bypassing `.endpoint(...)`.

        For endpoints `.endpoint(...)` doesn't fit -- e.g. streaming
        responses, where the caller needs to consume `response.aiter_bytes()`
        itself instead of a single `response.json()` parse.
        """
        return await self._http.send(request, **kwargs)

    @overload
    def endpoint(
        self,
        response_model: type[T],
    ) -> Callable[
        [Callable[Concatenate[Any, P], httpx.Request]],
        Callable[Concatenate[Any, P], Awaitable[T]],
    ]: ...

    @overload
    def endpoint(
        self,
        response_model: None = None,
    ) -> Callable[
        [Callable[Concatenate[Any, P], httpx.Request]],
        Callable[Concatenate[Any, P], Awaitable[None]],
    ]: ...

    def endpoint(self, response_model: type[T] | None = None):
        """Decorate a request-builder method to turn it into an async API call.

        `fn(self, ...)` must ONLY build and return an `httpx.Request` (no
        `await` inside, pure builder) -- its own return annotation should be
        `httpx.Request`. The decorator sends the request through this
        router's injected client, checks that the response is a success, and
        parses `response.json()` into `response_model` via `TypeAdapter`. If
        `response_model` is omitted, the response body is not parsed and the
        call returns `None`.

        Raises:
            ApiError: if the response is not a 2xx success.
            DecodeError: if the response body cannot be parsed into
                `response_model`.
        """
        router = self

        def decorator(fn: Callable[Concatenate[Any, P], httpx.Request]):
            @functools.wraps(fn)
            async def wrapper(instance, *args: P.args, **kwargs: P.kwargs):
                request = fn(instance, *args, **kwargs)
                response = await router._http.send(request)
                if not response.is_success:
                    raise ApiError(response.status_code, response.text)
                if response_model is None:
                    return None
                try:
                    return TypeAdapter(response_model).validate_python(response.json())
                except ValidationError as e:
                    raise DecodeError(e, response.text) from e

            return wrapper

        return decorator
