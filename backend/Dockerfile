# PIC Lite API image. The same image is used locally (docker-compose.yml) and on Render
# (render.yaml) — see docs/PRD.md Locked Decisions.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY analytics ./analytics
COPY backend ./backend
COPY tests/fixtures/synthetic_generator.py ./tests/fixtures/synthetic_generator.py

RUN mkdir -p /srv/uploads

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
