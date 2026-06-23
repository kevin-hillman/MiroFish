# MiroFish — lokales Setup

Autarkes lokales Dev-Setup, eingerichtet 2026-06-21. Läuft unabhängig vom Server `imp` (von dort als lauffähiger Stand übernommen).

## Starten / Stoppen

```bash
cd ~/Projekte/Coding/mirofish

# Start (im Hintergrund)
docker compose -f docker-compose.local.yml up -d

# UI öffnen
open http://localhost:3000

# Logs verfolgen
docker compose -f docker-compose.local.yml logs -f

# Stoppen
docker compose -f docker-compose.local.yml down

# Neu bauen (nach Code-Änderungen)
docker compose -f docker-compose.local.yml up -d --build
```

## Eckdaten

- **UI:** http://localhost:3000 (Frontend Vite) · **Backend:** http://localhost:5001 (Flask, `/api/...`)
- **Modus:** Entwicklungsmodus (`npm run dev`, Flask Debug) — nur lokal, nicht für Produktion.
- **Auth:** deaktiviert (`AUTH_ENABLED=false` in `.env`) → kein Login, keine Supabase nötig.
- **Daten:** Bind-Mount `./_local-data` → `/app/backend/uploads`. Enthält die von imp importierten Analysen (3 Reports, 3 Projekte, 2 Simulationen, u.a. die CoachPilot-Branchensimulation). Nicht im git (`.gitignore`).
- **Modell (in `.env`):** `LLM_MODEL_NAME=deepseek/deepseek-v4-pro` über OpenRouter, mit `LLM_REASONING_EFFORT=high` (Reasoning, höchster Effort). Der Effort-Schalter wird vom zentralen `LLMClient` (`backend/app/utils/llm_client.py`) als `reasoning.effort` durchgereicht und greift bei **Report, Ontologie/Graph und Zep**. Setzt man `LLM_REASONING_EFFORT` leer, wird kein reasoning-Parameter gesendet.
- **Kosten/Hinweis:** Reasoning-Modell → höhere Tokenkosten/Latenz. Ohne gesetztes Boost-Modell (`LLM_BOOST_*`) läuft auch die Massen-Simulation über dieses Modell. Keys (LLM via OpenRouter + Zep) aus imp übernommen, unabhängig von imp.

## Herkunft
- Repo-Remote: `github.com/kevin-hillman/MiroFish` (Fork von `666ghj/MiroFish`).
- Original-`docker-compose.yml` = imp-/Coolify-Variante (Traefik). Für lokal nutzen wir `docker-compose.local.yml`.
