# Cloud Run image for the REST API (Plan.md section 3).
FROM python:3.12-slim

WORKDIR /srv

# Source before install: setuptools finds the package in pyproject.toml,
# so installing without app/ present would build an empty wheel and only
# fail later, at import.
COPY pyproject.toml ./
COPY app ./app
# The migrations travel with the image, so the same artefact that serves
# requests can also bring the schema up to date -- run as a Cloud Run job,
# against the same database, with no second set of credentials.
COPY alembic ./alembic
COPY alembic.ini ./

# [gemini] because guide mode runs on Vertex in production. Not optional
# and not a fallback: a build that cannot install it should fail here
# rather than start and answer every question with a 502.
RUN pip install --no-cache-dir ".[gemini]"

# Nothing here needs to be root.
RUN useradd --system --uid 10001 wayfinder
USER 10001

# Cloud Run injects PORT and defaults it to 8080.
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
