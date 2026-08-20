FROM python:3.12-slim

# Keep Python predictable and make src/ importable inside the container.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

# The API image intentionally installs only API/database dependencies, not OCR.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Alembic files are copied because the API container runs migrations on startup.
COPY alembic.ini .
COPY alembic ./alembic
COPY src ./src

EXPOSE 8000

# exec makes uvicorn PID 1 after migrations, so Docker stop signals are graceful.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn belgian_deed_pipeline.api.main:app --host 0.0.0.0 --port 8000"]
