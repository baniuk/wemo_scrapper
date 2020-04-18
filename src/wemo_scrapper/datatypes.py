"""Datatypes."""
import datetime
from dataclasses import dataclass

from dataclasses_json import dataclass_json  # type: ignore[attr-defined]


@dataclass_json
@dataclass
class WemoResponse:
    """Response from Wemo."""

    today_kwh: float
    current_power: int
    today_on_time: int
    on_for: int
    today_standby_time: int
    device_type: str
    address: str
    collection_time: datetime.datetime
