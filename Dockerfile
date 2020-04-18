FROM python:3.8.2-alpine3.11

RUN apk --update --no-cache --repository add git && rm -rf /var/cache/apk/*

COPY requirements/ /build/requirements
COPY src/ /src/

RUN pip install -r /build/requirements/wemo_scrapper.txt && \
    rm -rf /build/requirements

STOPSIGNAL SIGINT

ENV PYTHONPATH=/src

ENTRYPOINT ["python", "-m", "wemo_scrapper"]

EXPOSE 8080
