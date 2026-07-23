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
# Demo endpoint reads tests/fixtures/demo_plant_scada.csv (or generates via synthetic_generator).
# Ship both so cold starts do not depend on runtime generation / missing package markers.
COPY tests/__init__.py ./tests/__init__.py
COPY tests/fixtures/__init__.py ./tests/fixtures/__init__.py
COPY tests/fixtures/synthetic_generator.py ./tests/fixtures/synthetic_generator.py
COPY tests/fixtures/demo_plant_scada.csv ./tests/fixtures/demo_plant_scada.csv

RUN mkdir -p /srv/uploads

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
