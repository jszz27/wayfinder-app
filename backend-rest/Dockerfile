# Staged for Sprint 4 (Cloud Run). Not wired into any pipeline yet.
FROM python:3.12-slim

WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Cloud Run injects PORT; default to the local dev port.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
