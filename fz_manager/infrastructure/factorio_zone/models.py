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
    referral_code: str = Field(alias="referralCode")


class StartInstanceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    launch_id: str = Field(alias="launchId")


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
    # Intentionally left untyped for now (first draft) -- the shape of
    # `options` depends on `name` (regions/versions/saves/...).
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
    launch_id: str | None = Field(default=None, alias="launchId")


class StoppingMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["stopping"]
    launch_id: str | None = Field(default=None, alias="launchId")


class RunningMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["running"]
    launch_id: str | None = Field(default=None, alias="launchId")
    socket: str | None = None


class SlotMessage(BaseModel):
    # The real message carries extra fields beyond `slot`/`type` -- allow
    # them through rather than rejecting/discarding them.
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["slot"]
    slot: str


class LogMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["log"]
    num: int
    line: str | None = None


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
