"""Pydantic models for the Factorio Zone REST responses and WS messages.

The WS message shapes are derived from `fz_manager/api/client.py`'s
`FZClient.connect()` (the `match data['type']` block), which is the source
of truth for the real payloads sent by the server.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# REST responses
# ---------------------------------------------------------------------------


class LoginResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_token: str = Field(alias="userToken")
    referral_code: str | None = Field(default=None, alias="referralCode")


# ---------------------------------------------------------------------------
# WS messages
# ---------------------------------------------------------------------------


class VisitMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["visit"]
    secret: str


class OptionsMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["options"]
    name: str
    options: Any


class ModsMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["mods"]
    mods: list[Any]


class IdleMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["idle"]


class StartingMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["starting"]
    launch_id: int | None = Field(default=None, alias="launchId")


class StoppingMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["stopping"]
    launch_id: int | None = Field(default=None, alias="launchId")


class RunningMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["running"]
    launch_id: int | None = Field(default=None, alias="launchId")
    socket: str | None = None


class SlotMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["slot"]
    slot: str


class LogMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["log"]
    num: int
    line: str | None = None
    launch_id: int | None = Field(default=None, alias="launchId")


class InfoMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["info"]
    line: str | None = None


class WarnMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["warn"]
    line: str | None = None


class ErrorMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["error"]
    line: str | None = None


class BlankMessage(BaseModel):
    """Fallback for a WS frame that failed to validate against any of the
    models above -- an unrecognized `type`, or a known `type` whose payload
    changed shape in some way we haven't modeled (e.g. a field showing up
    with an unexpected JSON type).

    Not a member of `FzMessage` -- pydantic's discriminated unions have no
    built-in "anything else" case, every tag must be declared up front, or
    validation raises. Instead, `FactorioZoneSocket` catches that
    `ValidationError` and constructs this directly from the raw frame (see
    its `on_decode_error` hook), so `FactorioZoneSession.run()`'s message
    loop never crashes on a message shape we simply haven't modeled yet --
    it just falls through to `@FactorioZoneSocket.on(BlankMessage)`.
    `extra="allow"` keeps whatever fields came in instead of discarding
    them, so they're still visible (e.g. in logs) for debugging.
    """

    model_config = ConfigDict(extra="allow")

    type: str


FzMessage = Annotated[
    VisitMessage
    | OptionsMessage
    | ModsMessage
    | IdleMessage
    | StartingMessage
    | StoppingMessage
    | RunningMessage
    | SlotMessage
    | LogMessage
    | InfoMessage
    | WarnMessage
    | ErrorMessage,
    Field(discriminator="type"),
]
