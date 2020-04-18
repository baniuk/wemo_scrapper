"""Datatypes."""
from dataclasses import dataclass
import datetime
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class WemoResponse:
    today_kwh:float
    current_power:int
    today_on_time:int
    on_for:int
    today_standby_time:int
    device_type:str
    address:str
    collection_time:datetime.datetime
