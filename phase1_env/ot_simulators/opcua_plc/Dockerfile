FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY process_sim.py opcua_server.py ./

EXPOSE 4840

CMD ["python", "-u", "opcua_server.py"]
