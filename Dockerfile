FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS backend-builder

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/*

# uv aus dem offiziellen uv-Image kopieren
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Python-Abhaengigkeiten getrennt installieren, um den Docker-Cache zu nutzen
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend \
  && uv sync --frozen --no-dev \
  && uv pip install --python .venv/bin/python gunicorn==23.0.0


FROM python:3.11-slim AS runtime

WORKDIR /app

# Nur die gebaute Python-Umgebung uebernehmen; Compiler bleiben im Build-Stage
COPY --from=backend-builder /app/backend/.venv ./backend/.venv

# Nur die fuer den Produktionsbetrieb benoetigten Dateien uebernehmen
COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

ENV FLASK_DEBUG=false

EXPOSE 3000

WORKDIR /app/backend

# Ein Worker bewahrt die prozesslokalen Aufgaben- und Simulationszustaende
CMD ["/app/backend/.venv/bin/gunicorn", "--bind", "0.0.0.0:3000", "--workers", "1", "--threads", "8", "--timeout", "0", "app:create_app()"]
