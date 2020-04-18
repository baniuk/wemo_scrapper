"""Prometheus exporter."""
import logging
from typing import Callable

from prometheus_client.core import GaugeMetricFamily

import dataclasses

from .datatypes import WemoResponse

LOGGER = logging.getLogger(__name__)
class CustomWemoExporter:

    def __init__(self, source:Callable[...,WemoResponse]):
        self.source = source

    def collect(self):
        ret: WemoResponse = self.source()
        if ret is None:
            LOGGER.warning('Statistics are not available')
            return
        gauge = GaugeMetricFamily('wemo_device_state', 'Status of Wemo device', labels=['address', 'parameter'])
        gauge.add_metric([ret.address, 'today_kwh'], ret.today_kwh, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'current_power'], ret.current_power, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'today_on_time'], ret.today_on_time, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'on_for'], ret.on_for, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'today_standby_time'], ret.today_standby_time,
                            timestamp=ret.collection_time.timestamp())

        yield gauge
