FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/
RUN chmod +x scripts/*.sh

VOLUME ["/certs", "/uploads"]
EXPOSE 443 3000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
