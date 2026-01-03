# Backend (Python API + Scheduler)
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies
# gcc/python3-dev might be needed for some python packages like numpy/pandas
RUN apt-get update && apt-get install -y gcc python3-dev && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose API port
EXPOSE 8000

# Start server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
