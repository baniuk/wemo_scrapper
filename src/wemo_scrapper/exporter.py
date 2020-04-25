"""Prometheus exporter."""
import logging
from typing import Callable, Optional

from prometheus_client.core import GaugeMetricFamily, Metric, CounterMetricFamily

from .datatypes import WemoResponse

LOGGER = logging.getLogger(__name__)


class CustomWemoExporter:  # pylint: disable=too-few-public-methods
    """Prometheus on-demand exporter."""

    def __init__(self, source: Callable[..., Optional[WemoResponse]]):
        self.source = source

    def collect(self) -> Metric:
        """Query Wemo and return Prometheus metrics."""
        ret = self.source()
        if ret is None:
            LOGGER.warning('Statistics are not available')
            return
        gauge = GaugeMetricFamily('wemo_device_state', 'Status of Wemo device', labels=['address', 'parameter'])
        gauge.add_metric([ret.address, 'today_kwh'], ret.today_kwh, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'current_power_mW'], ret.current_power,
                         timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'today_on_time'], ret.today_on_time, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'on_for'], ret.on_for, timestamp=ret.collection_time.timestamp())
        gauge.add_metric([ret.address, 'today_standby_time'], ret.today_standby_time,
                         timestamp=ret.collection_time.timestamp())

        yield gauge

        counter = CounterMetricFamily('wemo_power_usage', 'Today power consumption', labels=['address'])
        counter.add_metric([ret.address], ret.today_kwh, timestamp=ret.collection_time.timestamp())
        yield counter
