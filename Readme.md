# wemo_scrapper

Simple Wemo Insight plug metrics scrapper. Exports [metrics](src/wemo_scrapper/datatypes.py) to Prometheus.

## Usage

```bash
# run service at port 8080 and scrap from Wemo at 192.168.4.6
python -m wemo_scrapper -d start --address 192.168.4.6 -p 8080

# one time scrap - export to json
python -m wemo_scrapper --quiet onescrap --address 192.168.4.6
```

### Docker

```bash
docker run --rm -it -p 8080:8080 baniuk/wemo-scrapper -d start -a <wemo_ip>
```

# License
The code in pywemo/ouimeaux_device is written and copyright by Ian McCracken and released under the BSD license. The rest is released under the MIT license.
