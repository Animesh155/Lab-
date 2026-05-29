FROM python:3.12-slim

WORKDIR /app

# Install protocol adapter dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code is mounted via volume at runtime, but we have a default copy
# so the image works standalone too
COPY frame.py ot_proxy.py ./
COPY adapters/ ./adapters/

CMD ["python", "-u", "ot_proxy.py"]
