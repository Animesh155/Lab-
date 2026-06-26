FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code is mounted via volume at runtime; copy as fallback for standalone runs
COPY frame.py fpga_sim.py ./

CMD ["python", "-u", "fpga_sim.py"]
