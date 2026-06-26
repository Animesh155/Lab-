FROM python:3.12-slim

WORKDIR /app

# python-snap7 ships libsnap7 in its wheel for linux x86_64; on other
# arches pip falls back to source. Keep ca-certificates handy for that.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install protocol adapter dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code is mounted via volume at runtime, but we have a default copy
# so the image works standalone too
COPY frame.py ot_proxy.py ./
COPY adapters/ ./adapters/

CMD ["python", "-u", "ot_proxy.py"]
