"""Simple Wemo power scrapper."""
import datetime
import logging
import signal
import sys
import threading
import time
from types import FrameType
from typing import Optional

import click
import pywemo
from prometheus_client import REGISTRY, start_http_server
from pywemo.ouimeaux_device.api.service import ActionException
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout
from tenacity import (RetryError, before_sleep_log, retry, retry_if_exception,
                      wait_exponential)

from .datatypes import WemoResponse
from .exporter import CustomWemoExporter

logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

LOGGER = logging.getLogger('wemo_scrapper')

_ONE_HOUR_IN_SECONDS = 60*60


class DeviceNotAvailable(Exception):
    """Device not available exception."""

    ...


def _predicate(exc: Exception) -> bool:
    return isinstance(exc, (DeviceNotAvailable, ActionException, RequestsConnectionError, ReadTimeout))


class WemoConnector:
    """
    Wemo device connector.

    Connect and produce metrics. Can reconnect if connection is lost.
    """

    def __init__(self, address: str):
        self.address = address
        self.device = None
        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnecting_finished = threading.Event()
        self._is_dead = threading.Event()

    def connect(self, block: bool = True) -> None:
        """
        Connect to the device.

        In block mode this method blocks until connection is established. Connection process runs in thread
        and current status of the device can be read from properties `is_working` and `is_ready`.

        Args:
            block: If True this command will block until connection is established.

        """
        if not (self._reconnect_thread and self._reconnect_thread.is_alive()):
            self._reconnect_thread = threading.Thread(target=self._threaded_connect, daemon=True)
            self._reconnect_thread.start()
            if block:
                self._reconnecting_finished.wait()
        else:
            LOGGER.warning('Connection already in progress.')

    def _threaded_connect(self) -> None:
        """Connect to Wemo in thread."""
        # wait from 10s to max 10min between connections, repeat infinitely
        @retry(wait=wait_exponential(min=10, max=60*10),  # type: ignore[misc]
               retry=retry_if_exception(_predicate),
               before_sleep=before_sleep_log(LOGGER, logging.WARNING))
        def _connect() -> None:
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
            self._reconnecting_finished.set()
            LOGGER.error(  # pylint: disable=maybe-no-member;
                "Reconnecting failed. Some stats %s", _connect.retry.statistics)

    def update(self) -> None:
        """
        Update Wemo internal state.

        If connection with device is lost it will try to reconnect setting `is_ready` to False.

        """
        try:
            if self.is_ready:
                self.device.update_insight_params()
            else:
                logging.info("Device is not ready and cannot be updated.")
        except ActionException as aexp:
            self.device = None
            logging.warning('Device is not available: %s, reconnecting in background', aexp)
            self.connect(block=False)

    def scrap(self) -> Optional[WemoResponse]:
        """
        Wemo scrapper.

        Update and read device state.

        Returns:
            `WemoResponse` or None if device is not ready or dead.

        """
        ret: Optional[WemoResponse]
        self.update()
        if self.is_ready:
            ret = WemoResponse(today_kwh=self.device.today_kwh,
                               current_power=self.device.current_power,
                               today_on_time=self.device.today_on_time,
                               on_for=self.device.on_for,
                               today_standby_time=self.device.today_standby_time,
                               device_type=self.device.device_type,
                               address=self.address,
                               collection_time=datetime.datetime.utcnow())

            LOGGER.info('url: %s, data: %s', self.address, ret)
        else:
            ret = None

        return ret

    @property
    def is_ready(self) -> bool:
        """
        Return status of the device.

        Returns:
            True if device is connected.
            False if device is disconnected but reconnecting is in progress.

        """
        return bool(self.device)

    @property
    def is_working(self) -> bool:
        """
        Return status of reconnecting.

        Returns:
            True if device is working.
            False if device is in unrecoverable bad state.

        """
        return not self._is_dead.is_set()

    def wait_as_alive(self) -> None:
        """Block as long as device is alive."""
        self._is_dead.wait()


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


@cli.command()
@click.option('-a', '--address', required=True, type=str, help='Wemo IP address')
@click.option('-p', '--port', type=int, default=8080, help='Prometheus port (default 8080)')
def start(address: str, port: int) -> None:
    """
    Start service.

    The service connects to the Wemo device and refresh metrics on each
    prometheus request. If connection is lost it will be detected on next
    prometheus request. The service will be trying to reconnect infinitely in
    non-blocking way, prometheus requests are served as normal but no metrics
    are returned.
    """
    start_http_server(port)
    LOGGER.info('Started prometheus server at port %s', port)
    connect = WemoConnector(address)
    connect.connect()
    if connect.is_working:
        REGISTRY.register(CustomWemoExporter(connect.scrap))
    else:
        logging.error("Device is not working. Cannot register scrapper.")
        sys.exit(1)

    def shutdown(sig: int, frame: FrameType) -> None:  # pylint: disable=unused-argument
        LOGGER.info("Received exit signal %s", signal.Signals(sig).name)  # pylint: disable=no-member
        connect._is_dead.set()  # pylint: disable=protected-access

    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT):
        signal.signal(sig, shutdown)

    try:
        connect.wait_as_alive()
    except KeyboardInterrupt:
        LOGGER.info('Exiting')
    except Exception:  # pylint: disable=broad-except
        logging.exception('Finishing with exception')


@cli.command()
@click.option('-a', '--address', required=True, type=str, help='Wemo IP address')
@click.option('-f', '--frequency', type=float, default=0.5, help="Sampling frequency [Hz]. If set to 0 device is " +
              "queried only once. Defaults to 0.5 Hz")
def scrap(address: str, frequency: float) -> None:
    """
    Scrap device and output json response.

    Return json representation of Wemo data or empty json if device is not available
    """
    try:
        connect = WemoConnector(address)
        connect.connect()
        while connect.is_working:
            if connect.is_ready:
                ret = connect.scrap()
                if ret:
                    print(ret.to_json())  # type: ignore[attr-defined] # pylint: disable=no-member
                else:
                    print('{}')
            else:
                logging.warning("Device is not ready.")
            if frequency == 0:
                sys.exit(0)
            else:
                time.sleep(1.0/frequency)
    except KeyboardInterrupt:
        LOGGER.info('Exiting')
    except Exception:  # pylint: disable=broad-except
        logging.exception('Finishing with exception')
