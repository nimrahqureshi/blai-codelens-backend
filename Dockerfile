# Use the official Python image as a base
FROM python:3.11-slim

# Install system dependencies needed for the worker process (especially git for cloning repos)
RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the requirements file first to leverage Docker caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port (FastAPI default is 8000)
ENV PORT 8000
EXPOSE 8000

# Set the default entrypoint to be used by Koyeb's multi-process structure.
# Koyeb will use a different command for 'web' and 'worker' services.

# Command for the Web Service (main.py):
# This is typically set in Koyeb's control panel as: uvicorn main:app --host 0.0.0.0 --port $PORT

# Command for the Worker Service (worker.py):
# This is typically set in Koyeb's control panel as: python worker.py

# We don't need a default CMD here since Koyeb will provide the run commands for both services.
