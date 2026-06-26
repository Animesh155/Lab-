FROM python:3.12-slim

WORKDIR /app

# python-snap7 1.3 wheels bundle libsnap7 for linux x86_64.
# On other archs pip falls back to source build, which needs build-essential.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY process_sim.py s7_server.py ./

EXPOSE 102

CMD ["python", "-u", "s7_server.py"]
