FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestor.py .

RUN echo "0 */6 * * * root . /etc/environment; python /app/ingestor.py >> /var/log/ingestor.log 2>&1" \
    > /etc/cron.d/ingestor \
    && chmod 0644 /etc/cron.d/ingestor

CMD ["sh", "-c", "printenv >> /etc/environment; python /app/ingestor.py; cron -f"]
