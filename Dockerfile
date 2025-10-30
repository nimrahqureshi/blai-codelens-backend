# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY server/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY server/ ./server

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
