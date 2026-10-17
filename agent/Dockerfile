FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY agent/pyproject.toml /app/pyproject.toml
COPY agent/busfactor /app/busfactor
RUN pip install .

COPY data/snapshot.json /app/data/snapshot.json

ENV FALKORDB_HOST=falkordb \
    FALKORDB_PORT=6379 \
    SNAPSHOT_PATH=/app/data/snapshot.json

EXPOSE 8000
CMD ["uvicorn", "busfactor.api:app", "--host", "0.0.0.0", "--port", "8000"]
