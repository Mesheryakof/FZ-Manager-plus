"""Small HTTP transport; clients own their dependencies and expose async methods."""

import functools
from collections.abc import Callable
from typing import BinaryIO

import httpx
from pydantic import TypeAdapter, ValidationError

from fz_manager_plus.domain.errors import ApiError as ApiError
from fz_manager_plus.domain.errors import DecodeError as DecodeError
from fz_manager_plus.domain.errors import DisconnectedError


class UploadProgressFile:
    """Compatibility wrapper for file-like multipart consumers."""

    def __init__(self, file: BinaryIO, cb: Callable[[int], None] | None = None):
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
    def __init__(self, client: httpx.AsyncClient):
        self._http = client

    def build_request(self, method: str, path: str, **kwargs) -> httpx.Request:
        return self._http.build_request(method, path, **kwargs)

    async def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        try:
            return await self._http.send(request, **kwargs)
        except httpx.RequestError as error:
            raise DisconnectedError(str(error)) from error

    @staticmethod
    def check_response(response: httpx.Response) -> None:
        if not response.is_success:
            raise ApiError(response.status_code, response.text)

    async def execute[T](
        self, request: httpx.Request, response_model: type[T] | None = None
    ) -> T | None:
        response = await self.send(request)
        try:
            self.check_response(response)
            if response_model is None:
                return None
            try:
                return TypeAdapter(response_model).validate_json(response.content)
            except ValidationError as error:
                raise DecodeError(error, response.text) from error
        finally:
            await response.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    def endpoint(self, response_model=None):
        """Compatibility for existing consumers; application APIs use execute directly."""

        def decorator(builder):
            @functools.wraps(builder)
            async def call(instance, *args, **kwargs):
                return await self.execute(builder(instance, *args, **kwargs), response_model)

            return call

        return decorator
