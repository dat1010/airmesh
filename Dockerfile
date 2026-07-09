FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector.py query.py run_all.py writer.py ./

RUN mkdir -p /data

ENTRYPOINT ["python", "writer.py"]
CMD ["--mqtt-host", "localhost", "--topic", "meshair/airquality/+", "--jsonl", "/data/airquality.jsonl", "--db", "/data/meshair.db"]
