from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FzBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class LoginResponse(FzBaseModel):
    user_token: str = Field(alias="userToken")
    referral_code: str | None = Field(default=None, alias="referralCode")


class VisitMessage(FzBaseModel):
    type: Literal["visit"]
    secret: str


class OptionsMessage(FzBaseModel):
    type: Literal["options"]
    name: str
    options: Any


class ModEntry(FzBaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    text: str
    enabled: bool


class ModsMessage(FzBaseModel):
    type: Literal["mods"]
    mods: list[ModEntry]


class IdleMessage(FzBaseModel):
    type: Literal["idle"]


class StartingMessage(FzBaseModel):
    type: Literal["starting"]
    launch_id: int | None = Field(default=None, alias="launchId")


class StoppingMessage(FzBaseModel):
    type: Literal["stopping"]
    launch_id: int | None = Field(default=None, alias="launchId")


class RunningMessage(FzBaseModel):
    type: Literal["running"]
    launch_id: int | None = Field(default=None, alias="launchId")
    socket: str | None = None


class SlotMessage(FzBaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["slot"]
    slot: str


class LogMessage(FzBaseModel):
    type: Literal["log"]
    num: int
    line: str | None = None
    launch_id: int | None = Field(default=None, alias="launchId")


class InfoMessage(FzBaseModel):
    type: Literal["info"]
    line: str | None = None


class WarnMessage(FzBaseModel):
    type: Literal["warn"]
    line: str | None = None


class ErrorMessage(FzBaseModel):
    type: Literal["error"]
    line: str | None = None


class ConsoleMessage(FzBaseModel):
    type: Literal["console"]
    input: str | None = None


class BlankMessage(FzBaseModel):
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
    | ErrorMessage
    | ConsoleMessage,
    Field(discriminator="type"),
]
