"""Simple Wemo power scrapper."""
import datetime
import logging
import threading
import time
from typing import Optional

import click
import pywemo
from prometheus_client import REGISTRY, start_http_server
from pywemo.ouimeaux_device.api.service import ActionException
from tenacity import (RetryError, before_sleep_log, retry, retry_if_exception,
                      stop_after_attempt, wait_exponential)

from .datatypes import WemoResponse
from .exporter import CustomWemoExporter

logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

LOGGER = logging.getLogger('wemo_scrapper')

_ONE_DAY_IN_SECONDS = 24*60*60


class DeviceNotAvailable(Exception):
    pass


def _predicate(exc: Exception) -> bool:
    return isinstance(exc, (DeviceNotAvailable, ActionException))


class Connect:

    def __init__(self, address: str):
        self.address = address
        self.device = None
        self._reconnect_thread = None
        self._reconnecting_finished = threading.Event()
        self._is_dead = threading.Event()

    def connect(self, block: bool = True) -> None:
        if not (self._reconnect_thread and self._reconnect_thread.is_alive()):
            self._reconnect_thread = threading.Thread(target=self.threaded_connect, daemon=True)
            self._reconnect_thread.start()
            if block:
                self._reconnecting_finished.wait()
        else:
            LOGGER.warning('Connection already in progress.')

    def threaded_connect(self):
        @retry(stop=stop_after_attempt(2),  # type: ignore[misc]
               wait=wait_exponential(min=10, max=60*60),
               retry=retry_if_exception(_predicate),
               before_sleep=before_sleep_log(LOGGER, logging.WARNING))
        def _connect():
            self._reconnecting_finished.clear()
            LOGGER.debug('Trying to connect to %s', self.address)
            port = pywemo.ouimeaux_device.probe_wemo(self.address)
            if port is None:
                LOGGER.warning('Device %s is not available', self.address)
                self.device = None
                raise DeviceNotAvailable(f'Device {self.address} was not found. Connection failed.')

            url = 'http://%s:%i/setup.xml' % (self.address, port)
            self.device = pywemo.discovery.device_from_description(url, None, rediscovery_enabled=False)
            LOGGER.info('Connected to: url: %s, device: %s', url, self.device)
            self._reconnecting_finished.set()
        try:
            _connect()
        except RetryError:
            self._is_dead.set()
            LOGGER.error(  # pylint: disable=maybe-no-member;
                "Reconnecting failed. Some stats %s", connect.connect.retry.statistics)  # type: ignore[attr-defined]

    def update(self):
        try:
            if self.device:
                self.device.update_insight_params()
            # elif not self._reconnect_thread.is_alive():
            #     self._reconnect_thread.run()
        except ActionException as aexp:
            self.device = None
            logging.warning('Device is not available: %s, reconnecting in background', aexp)
            self.connect(block=False)

    @property
    def is_ready(self) -> bool:
        return bool(self.device)

    @property
    def is_working(self) -> bool:
        return not self._is_dead.is_set()


@click.group()
@click.option('-d', '--debug', count=True, help='Verbosity: d:INFO, dd:DEBUG (default WARN)')
@click.option('--quiet/--no-quiet', default=False, help='Mute all logs')
def cli(debug: int, quiet: bool) -> None:
    """Wemo power statistics to prometheus exporter."""
    if quiet:
        LOGGER.setLevel(logging.ERROR)
    elif debug == 1:
        LOGGER.setLevel(logging.INFO)
    elif debug > 1:
        LOGGER.setLevel(logging.DEBUG)
    LOGGER.debug('Debug mode enabled')


def scrap(address: str) -> Optional[WemoResponse]:
    """Wemo scrapper."""
    port = pywemo.ouimeaux_device.probe_wemo(address)
    if port is None:
        LOGGER.warning('Device is not available')
        return None
    url = 'http://%s:%i/setup.xml' % (address, port)
    device = pywemo.discovery.device_from_description(url, None)
    device.update_insight_params()

    ret = WemoResponse(today_kwh=device.today_kwh,
                       current_power=device.current_power,
                       today_on_time=device.today_on_time,
                       on_for=device.on_for,
                       today_standby_time=device.today_standby_time,
                       device_type=device.device_type,
                       address=address,
                       collection_time=datetime.datetime.utcnow())

    LOGGER.info('url: %s, data: %s', url, ret)
    return ret


@cli.command()
@click.option('-a', '--address', required=True, type=str, help='Wemo IP address')
@click.option('-p', '--port', type=int, default=8080, help='Prometheus port (default 8080)')
def start(address: str, port: int) -> None:
    """Start service."""
    start_http_server(port)
    LOGGER.info('Started prometheus server at port %s', port)
    REGISTRY.register(CustomWemoExporter(lambda: scrap(address)))

    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        LOGGER.info('Exiting')
    except Exception:  # pylint: disable=broad-except
        logging.exception('Finishing with exception')


@cli.command()
@click.option('-a', '--address', required=True, type=str, help='Wemo IP address')
def onescrap(address: str) -> None:
    """
    One time scrap.

    Return json representation of Wemo data or empty json if device is not available
    """
    ret = scrap(address)
    if ret:
        print(ret.to_json())  # type: ignore[attr-defined] # pylint: disable=no-member
    else:
        print('{}')


@cli.command()
@click.option('-a', '--address', required=True, type=str, help='Wemo IP address')
@click.option('-f', '--frequency', type=float, default=1.0, help='Sampling frequency [Hz]')
def loopscrap(address: str, frequency: float) -> None:
    try:
        connect = Connect(address)
        connect.connect()
        while connect.is_working:
            if connect.is_ready:
                connect.update()
                LOGGER.debug(connect.device)
            else:
                LOGGER.debug('Device is not ready')
            time.sleep(1.0/frequency)
    except RetryError:
        LOGGER.error(  # pylint: disable=maybe-no-member;
            "Some stats %s", connect.connect.retry.statistics)  # type: ignore[attr-defined]
