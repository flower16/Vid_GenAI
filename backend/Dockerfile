FROM python:3.11-slim

WORKDIR /app

# Build deps for any packages without manylinux wheels (kept minimal).
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Seed the Oncor plans + TDU (idempotent) on first boot, then serve.
CMD ["sh", "-c", "python seed_plans.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
