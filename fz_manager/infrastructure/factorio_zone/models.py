from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_token: str = Field(alias="userToken")
    referral_code: str | None = Field(default=None, alias="referralCode")


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
