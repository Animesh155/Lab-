FROM python:3.12-slim

WORKDIR /app

# openssl needed to generate the self-signed server cert when running
# in secure mode (OPCUA_SECURITY=basic256sha256).
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY process_sim.py opcua_server.py ./

EXPOSE 4840

CMD ["python", "-u", "opcua_server.py"]
