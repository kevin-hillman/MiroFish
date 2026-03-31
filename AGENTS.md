# AGENTS.md

## Projektbeschreibung

MiroFish ist eine KI-Vorhersage-Engine, die aus beliebigen Texten (Nachrichtenartikel, Pressemitteilungen, Produktankuendigungen) eine simulierte Social-Media-Welt baut. Tausende KI-Agenten mit eigenen Persoenlichkeiten diskutieren auf simuliertem Twitter/Reddit und erzeugen einen Vorhersagebericht.

## Tech-Stack

- **Frontend**: Vue 3 (Composition API, `<script setup>`), Vite, Axios
- **Backend**: Flask (Python 3.11-3.12), OpenAI SDK (kompatibel mit OpenRouter, Ollama, etc.)
- **Simulation**: camel-oasis, camel-ai (OASIS Social-Media-Simulation)
- **Gedaechtnisgraph**: Zep Cloud (GraphRAG, Langzeit-/Kurzzeitgedaechtnis)
- **Auth**: Supabase (JWT, opt-in via AUTH_ENABLED)
- **Deployment**: Docker, Coolify
- **Paketmanager**: npm (Frontend), uv (Backend)

## Architektur

```
frontend/           Vue 3 SPA
  src/views/        Seiten (Home, Process/MainView, Simulation*, Report, Interaction, Login)
  src/components/   Step1-5 Komponenten, GraphPanel, HistoryDatabase
  src/api/          Axios-Client mit Auth-Interceptor (index.js, graph.js, simulation.js, report.js)
  src/auth/         Supabase Auth Composable
  src/i18n/         Locale-Dateien (zh.json, en.json, de.json)

backend/
  app/
    api/            Flask Blueprints (graph.py, simulation.py, report.py, config_api.py, auth/)
    services/       Kernlogik (report_agent.py, zep_tools.py, simulation_runner.py, graph_builder.py, etc.)
    models/         Datenmodelle (project.py, task.py)
    utils/          LLM-Client, File-Parser, Logger, Retry
    auth/           Supabase JWT Middleware
    i18n/           Sprachpakete (zh.py, en.py, de.py) -- nur auf feat/i18n Branch
  uploads/          Persistente Daten (Projekte, Simulationen, Berichte)
```

## Konventionen

### Sprache
- Die gesamte Codebasis (UI, Kommentare, Prompts, Fehlermeldungen) ist auf **Deutsch** uebersetzt
- LLM-Prompt-Templates sind auf Deutsch (damit Simulationsausgaben auf Deutsch sind)
- "Final Answer:" bleibt als technischer Parsing-Marker auf Englisch (nicht uebersetzen)
- Das Backend parsed sowohl "Final Answer:" als auch "Endgueltige Antwort:" als Fallback

### Code-Stil
- Frontend: Vue 3 `<script setup>`, Composition API, keine Options API
- Backend: Standard Flask Blueprints, keine async Routes
- Commit-Messages: Conventional Commits auf Englisch (`feat:`, `fix:`, `i18n:`)
- Deutsche Umlaute in Strings: ue/ae/oe in technischen Kontexten (Dateinamen, Logs), echte Umlaute in UI-Texten

### API-Muster
- Alle API-Pfade beginnen mit `/api/` (graph, simulation, report, auth, config)
- Antwortformat: `{ "success": true/false, "data": {...}, "error": "..." }`
- Frontend Axios baseURL ist leer (`''`) -- alle Requests gehen relativ ueber den Vite-Proxy

### Authentifizierung
- Auth ist opt-in: `AUTH_ENABLED=false` (Standard) aendert nichts am Verhalten
- Bei `AUTH_ENABLED=true`: JWT-Validierung via `@app.before_request` Hook
- Uebersprungen fuer: `/health`, `/api/auth/*`, OPTIONS-Requests
- Frontend Navigation Guard wartet auf Auth-Laden bevor es weiterleitet

## Pipeline-Ablauf (5 Schritte)

1. **Graphaufbau**: Dokument hochladen -> Ontologie generieren (LLM) -> Graph in Zep Cloud bauen
2. **Umgebungseinrichtung**: Agent-Profile generieren -> Simulationskonfiguration (Zeitplan, Verhalten) -> Skripte vorbereiten
3. **Simulation**: Dual-Plattform (Twitter + Reddit) parallel, OASIS-Engine, GraphRAG-Update in Echtzeit
4. **Berichterstellung**: ReportAgent mit ReACT-Loop, 4 Werkzeuge (InsightForge, PanoramaSearch, QuickSearch, Interview)
5. **Tiefeninteraktion**: Chat mit ReportAgent, Chat mit einzelnen Agenten, Umfragen

## Bekannte Eigenheiten

- **Reasoning-Modelle** (MiniMax M2.7): Geben manchmal `content: null` zurueck -- der LLM-Client faellt auf das `reasoning`-Feld zurueck
- **API-Timeout**: OpenAI-Client auf 120s gesetzt (fuer langsame Provider wie OpenRouter)
- **to_text() <-> Regex**: Die `to_text()`-Methoden in `zep_tools.py` erzeugen strukturierten Text, den `Step4Report.vue` mit Regex parsed. Aenderungen an Formatstrings muessen in beiden Dateien synchron erfolgen
- **OASIS interne Prompts**: Die camel-oasis Library hat eigene englische Prompts, die nicht uebersetzt sind. Agenten koennen gemischtsprachig antworten
- **Docker Dev-Modus**: Das Dockerfile startet mit `npm run dev` (Vite + Flask Debug). Fuer Produktion muesste ein Build-Step ergaenzt werden

## Umgebungsvariablen

```env
# Pflicht
LLM_API_KEY=           # OpenAI-kompatible API (OpenRouter, Ollama, etc.)
LLM_BASE_URL=          # z.B. https://openrouter.ai/api/v1
LLM_MODEL_NAME=        # z.B. minimax/minimax-m2.7
ZEP_API_KEY=           # Zep Cloud Key

# Optional
LANGUAGE=de            # zh (Standard), en, de -- nur auf feat/i18n Branch
AUTH_ENABLED=false     # true aktiviert Supabase Auth
SUPABASE_URL=          # Self-hosted oder Cloud Supabase URL
SUPABASE_ANON_KEY=     # Supabase anon Key
SUPABASE_JWT_SECRET=   # Supabase JWT Secret

# Optional: Beschleunigte LLM-Konfiguration
LLM_BOOST_API_KEY=
LLM_BOOST_BASE_URL=
LLM_BOOST_MODEL_NAME=
```

## Deployment

### Lokal
```bash
npm run setup:all   # Node + Python Dependencies
npm run dev         # Frontend (3000) + Backend (5001)
```

### Docker (VPS/Coolify)
```bash
docker compose build
docker compose up -d
# Frontend: Port 3000, Backend: Port 5001
# Daten persistent in Docker Volume mirofish-data
```
