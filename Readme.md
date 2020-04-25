# wemo_scrapper

Simple Wemo Insight plug metrics scrapper. Exports [metrics](src/wemo_scrapper/datatypes.py) to Prometheus.

## Usage

```bash
# supported options
python -m wemo_scrapper --help

# run service at port 8080 and scrap from Wemo at <wemo_ip>
python -m wemo_scrapper -d start --address <wemo_ip> -p 8080

# produce metrics to stdout - export to json
python -m wemo_scrapper --quiet scrap --address <wemo_ip>
```

### Docker

```bash
docker run --rm -it -p 8080:8080 baniuk/wemo-scrapper -d start -a <wemo_ip>
```

# License
The code in pywemo/ouimeaux_device is written and copyright by Ian McCracken and released under the BSD license. The rest is released under the MIT license.
