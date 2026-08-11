# Project: APEX AI Portfolio Management System
# Course: Graduation Project / Engineering Project
# Team Members:
# - Saleem A. S. AbuZaid
# - Rashad Naghdiyev
# Advisor:
# Prof.Dr. Selim Akyokuş
# Description:
# - Container and deployment configuration for the APEX AI project environment.
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for asyncpg and other c-extensions
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

COPY . .

# Expose FastAPI port
EXPOSE 8000

ENV PYTHONPATH=/app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
