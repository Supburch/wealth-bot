FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached between builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application.
COPY . .

ENV PYTHONUNBUFFERED=1

# Render exposes the service on $PORT (default 10000).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
