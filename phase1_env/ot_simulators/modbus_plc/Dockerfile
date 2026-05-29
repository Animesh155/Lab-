FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sensors.py .
COPY hai_replay.py .
COPY modbus_server.py .
COPY data/ /app/data/

EXPOSE 502

CMD ["python", "-u", "modbus_server.py"]
