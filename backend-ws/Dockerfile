# Cloud Run image for the WebSocket caption server (Plan.md section 3).
FROM python:3.12-slim

WORKDIR /srv

# Source before install, for the same reason as the REST image.
COPY pyproject.toml ./
COPY app ./app

# [google] is the real speech adapter; the mock is for tests only.
RUN pip install --no-cache-dir ".[google]"

RUN useradd --system --uid 10001 wayfinder
USER 10001

ENV PORT=8080
# --ws websockets stated rather than inferred: this service is the
# WebSocket half of the system, so the dependency should be visible here.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --ws websockets"]
