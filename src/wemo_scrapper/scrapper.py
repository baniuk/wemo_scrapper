"""Simple Wemo power scrapper."""
import datetime
import logging
import signal
import threading
import time

import click
from prometheus_client import REGISTRY, Gauge, start_http_server

import pywemo

from .datatypes import WemoResponse
from .exporter import CustomWemoExporter

logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

LOGGER = logging.getLogger('wemo_scrapper')

_ONE_DAY_IN_SECONDS = 24*60*60

@click.group()
@click.option('-d', '--debug', count=True, help='Verbosity: d:INFO, dd:DEBUG (default WARN)')
@click.option('--quiet/--no-quiet', default=False, help='Mute all logs')
def cli(debug:int, quiet:bool):
    """
    Wemo power statistics to prometheus exporter.
    """
    if quiet:
        LOGGER.setLevel(logging.ERROR)
    elif debug == 1:
        LOGGER.setLevel(logging.INFO)
    elif debug > 1:
        LOGGER.setLevel(logging.DEBUG)
    LOGGER.debug('Debug mode enabled')

def scrap(address:str):
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
@click.option('--address', required=True, type=str, help='Wemo IP address')
@click.option('-p', '--port', type=int, required=True, help='Prometheus port')
def start(address:str, port:int):
    """
    Start service.
    """

    start_http_server(port)
    LOGGER.info('Started prometheus server at port %s',port)
    REGISTRY.register(CustomWemoExporter(lambda: scrap(address)))

    try:
        while True:
            time.sleep(_ONE_DAY_IN_SECONDS)
    except KeyboardInterrupt:
        LOGGER.info('Exiting')
    except Exception:
        LOGGER.exception('Finishing with exception')


@cli.command()
@click.option('-a', '--address', required=True, type=str, help='Wemo IP address')
def onescrap(address:str):
    """
    One time scrap.

    Return json representation of Wemo data or empty json if device is not available
    """
    ret = scrap(address)
    if ret:
        print(ret.to_json())
    else:
        print('{}')
