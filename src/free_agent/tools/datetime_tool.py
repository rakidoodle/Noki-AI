from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict


class DateTimeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "UTC"


class CurrentDateTime:
    name = "current_datetime"
    description = "Return the current date and time in an IANA timezone."
    side_effects = False
    args_model = DateTimeArgs

    def execute(self, arguments: DateTimeArgs) -> str:
        try:
            zone = ZoneInfo(arguments.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {arguments.timezone}") from exc
        return datetime.now(zone).isoformat()
