# MiroFish Production Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den aktuell gesunden MiroFish-Produktionsstand vollständig in `kevin-hillman/MiroFish:main` versionieren und den bestehenden Coolify-App-Service anschließend reproduzierbar aus genau diesem Main-Commit bauen.

**Architecture:** Das Produktions-Dockerfile baut die Vue-SPA in einem Node-Stage, installiert die Python-Laufzeit in einem separaten Builder und startet Flask über einen einzelnen Gunicorn-Worker, damit prozesslokale Task-Zustände konsistent bleiben. Flask liefert die gebauten Assets und SPA-Routen aus, schützt bei aktivierter Authentifizierung ausschließlich `/api/*`, und die Reddit-Simulation schreibt tatsächlich persistierte Aktionen in das bestehende JSONL-Protokoll.

**Tech Stack:** Vue 3, Vite 7, Flask 3, Python 3.11, pytest, uv, Docker, Gunicorn, Coolify/Docker Compose.

**Spec:** `docs/superpowers/plans/2026-09-02-mirofish-production-parity.md#global-constraints`

## Global Constraints

- Nur der bestehende Coolify-Service `mirofish` im Projekt `qfxqzproqpzgtkqyx4kv0yzo` darf neu erstellt werden.
- Der Volume `qfxqzproqpzgtkqyx4kv0yzo_mirofish-uploads` sowie alle Environment-Werte bleiben unverändert.
- `kevin-hillman/MiroFish:main` wird die vollständige Source of Truth; kein produktiver Build aus einem Dirty-Worktree.
- Die vorhandenen Frontend-Fixes `RouterLink` und `font-size: 2.5em` bleiben erhalten.
- Secrets werden weder gelesen noch ausgegeben; Environment-Prüfungen verwenden ausschließlich Variablennamen.
- Vor Löschungen wird eine konkrete, wiederherstellbare Zielinventur erstellt.

---

### Task 1: Runtime-Verhalten durch Tests charakterisieren

**Files:**
- Test: `backend/tests/test_frontend_routes.py`
- Test: `backend/tests/test_reddit_simulation_action_logging.py`

**Interfaces:**
- Consumes: `app.create_app()`, `RedditSimulationRunner.run()`, `SimulationRunner._read_action_log()`.
- Produces: Nachweise für SPA-Fallback, API-404/Auth-Grenze und Reddit-JSONL-Fortschritt.

- [ ] **Step 1: Tests in einen sauberen `origin/main`-Snapshot kopieren.**

```bash
CLEAN_SNAPSHOT=$(mktemp -d /tmp/mirofish-main-red.XXXXXX)
git archive origin/main | tar -x -C "$CLEAN_SNAPSHOT"
mkdir -p "$CLEAN_SNAPSHOT/backend/tests"
cp backend/tests/test_frontend_routes.py "$CLEAN_SNAPSHOT/backend/tests/"
cp backend/tests/test_reddit_simulation_action_logging.py "$CLEAN_SNAPSHOT/backend/tests/"
```

- [ ] **Step 2: RED gegen den ungepatchten Main-Stand nachweisen.**

```bash
cd "$CLEAN_SNAPSHOT/backend"
/Users/kevin/Projekte/Coding/github-oss/MiroFish-release-patch/backend/.venv/bin/pytest -q tests/test_frontend_routes.py tests/test_reddit_simulation_action_logging.py
```

Expected: Die Frontend-Routen liefern kein gebautes SPA-Fallback und das Reddit-Aktionsprotokoll wird nicht geschrieben.

- [ ] **Step 3: GREEN im gepatchten Worktree nachweisen.**

```bash
cd backend
uv run pytest -q tests/test_frontend_routes.py tests/test_reddit_simulation_action_logging.py
```

Expected: `3 passed`.

### Task 2: Produktionsruntime vollständig versionieren

**Files:**
- Modify: `Dockerfile`
- Modify: `backend/app/__init__.py`
- Modify: `backend/scripts/run_reddit_simulation.py`
- Modify: `frontend/src/views/Home.vue`
- Create: `backend/tests/test_frontend_routes.py`
- Create: `backend/tests/test_reddit_simulation_action_logging.py`

**Interfaces:**
- Consumes: Vue-Build unter `frontend/dist`, Flask-Blueprints unter `/api/*`, OASIS-SQLite-Trace-Tabelle.
- Produces: Produktionsimage auf Port 3000, SPA-Fallback und `reddit/actions.jsonl` für den bestehenden SimulationRunner.

- [ ] **Step 1: Nur die sechs bestätigten Runtime-/Testdateien und diese Plan-Datei stagen.**

```bash
git add Dockerfile backend/app/__init__.py backend/scripts/run_reddit_simulation.py frontend/src/views/Home.vue backend/tests/test_frontend_routes.py backend/tests/test_reddit_simulation_action_logging.py docs/superpowers/plans/2026-09-02-mirofish-production-parity.md
```

- [ ] **Step 2: Python-Tests und Frontend-Build ausführen.**

```bash
cd backend && uv run pytest -q tests/test_frontend_routes.py tests/test_reddit_simulation_action_logging.py
cd .. && npm run build
```

Expected: `3 passed` und Vite-Build mit Exit-Code 0.

- [ ] **Step 3: Commit erstellen.**

```bash
git commit -m "fix: make production runtime reproducible"
```

Expected: Der Commit umfasst ausschließlich die sieben in Task 2 genannten Dateien.

- [ ] **Step 4: Kandidatenimage auf dem amd64-Coolify-Host aus dem exakten Commit-Archiv bauen und vor dem Umschalten prüfen.**

```bash
MIROFISH_RELEASE_SHA=$(git rev-parse HEAD)
git archive "$MIROFISH_RELEASE_SHA" | ssh imp-8-16-320 "sudo docker build -t mirofish-coolify-local:candidate-${MIROFISH_RELEASE_SHA}-amd64 -"
ssh imp-8-16-320 "sudo docker image inspect mirofish-coolify-local:candidate-${MIROFISH_RELEASE_SHA}-amd64"
```

Expected: amd64-Image, Gunicorn-CMD, `font-size:2.5em`, Healthcheck-kompatible App.

### Task 3: Pull Request nach Main integrieren

**Files:**
- Verify only: Git-Diff und GitHub-PR-Metadaten.

**Interfaces:**
- Consumes: grünen Commit aus Task 2.
- Produces: gemergten Main-Commit als einzigen Build-Eingang für Coolify.

- [ ] **Step 1: Branch pushen und exakten Drei-Punkt-Diff gegen `origin/main` prüfen.**

```bash
git push -u origin fix/minimal-release-runtime
git fetch origin main
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

- [ ] **Step 2: Pull Request gegen `kevin-hillman/MiroFish:main` erstellen.**

```bash
gh pr create --repo kevin-hillman/MiroFish --base main --head fix/minimal-release-runtime --title "fix: make production runtime reproducible"
```

- [ ] **Step 3: Nur bei `MERGEABLE`, `CLEAN` und grünen Checks mergen.**

```bash
gh pr view --repo kevin-hillman/MiroFish --json number,mergeable,mergeStateStatus,statusCheckRollup
gh pr merge --repo kevin-hillman/MiroFish --merge
```

- [ ] **Step 4: Per Ancestor- und Remote-Dateiprüfung bestätigen, dass der Runtime-Commit in `main` liegt.**

```bash
git fetch origin main
git merge-base --is-ancestor "$MIROFISH_RELEASE_SHA" origin/main
git show origin/main:Dockerfile
```

### Task 4: Bestehenden Coolify-Service aus Main reproduzieren

**Files:**
- Remote modify with backup: `/data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml`

**Interfaces:**
- Consumes: exaktes `git archive` des gemergten Main-Commits.
- Produces: lokal adressierbares amd64-Image `mirofish-coolify-local:main-${MIROFISH_MAIN_SHA}-amd64` und gesunden Service `mirofish`.

- [ ] **Step 1: Image aus dem exakten Remote-Main-Commit ohne lokale Overlays bauen.**

```bash
git fetch origin main
MIROFISH_MAIN_SHA=$(git rev-parse origin/main)
git archive "$MIROFISH_MAIN_SHA" | ssh imp-8-16-320 "sudo docker build -t mirofish-coolify-local:main-${MIROFISH_MAIN_SHA}-amd64 -"
```

- [ ] **Step 2: Image-Inhalt, Architektur und Backend-Dateihashes gegen Main prüfen.**

```bash
ssh imp-8-16-320 "sudo docker image inspect mirofish-coolify-local:main-${MIROFISH_MAIN_SHA}-amd64"
git show origin/main:backend/app/__init__.py | shasum -a 256
git show origin/main:backend/scripts/run_reddit_simulation.py | shasum -a 256
```

- [ ] **Step 3: Compose-Datei sichern, genau eine Image-Referenz ersetzen und `docker compose config --quiet` ausführen.**

```bash
MIROFISH_OLD_IMAGE=$(ssh imp-8-16-320 'sudo docker inspect mirofish-qfxqzproqpzgtkqyx4kv0yzo --format "{{.Config.Image}}"')
MIROFISH_NEW_IMAGE="mirofish-coolify-local:main-${MIROFISH_MAIN_SHA}-amd64"
ssh imp-8-16-320 "sudo cp -a /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml.before-main-${MIROFISH_MAIN_SHA}"
ssh imp-8-16-320 "test \"\$(sudo grep -Foc '$MIROFISH_OLD_IMAGE' /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml)\" -eq 1 && sudo sed -i 's|$MIROFISH_OLD_IMAGE|$MIROFISH_NEW_IMAGE|' /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml"
ssh imp-8-16-320 'sudo docker compose -f /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml config --quiet'
```

- [ ] **Step 4: Ausschließlich den MiroFish-Service neu erstellen.**

```bash
ssh imp-8-16-320 'sudo docker compose -f /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo/docker-compose.yml up -d --no-deps --force-recreate mirofish'
```

- [ ] **Step 5: Container, Volume, Health, Logs, öffentliche Zugriffskontrolle, Startseite und echten Report-Pfad prüfen.**

```bash
ssh imp-8-16-320 'sudo docker inspect mirofish-qfxqzproqpzgtkqyx4kv0yzo'
curl -I https://mirofish.impulsphase.de/
curl -I https://mirofish.impulsphase.de/report/report_72c960cf9828
```

### Task 5: NPM-Vulnerabilities read-only triagieren

**Files:**
- Verify only: `package-lock.json`, `frontend/package-lock.json` und Audit-Ausgaben.

**Interfaces:**
- Consumes: `npm audit --json` und `npm audit --omit=dev --json`.
- Produces: getrennte Bewertung von Runtime- und Dev-Abhängigkeiten ohne automatische Versionsänderungen.

- [ ] **Step 1: Root- und Frontend-Audit vollständig sowie mit `--omit=dev` ausführen.**

```bash
npm audit --json
npm audit --omit=dev --json
npm --prefix frontend audit --json
npm --prefix frontend audit --omit=dev --json
```

- [ ] **Step 2: Direkte/transitive Pakete, Advisory, Fix-Verfügbarkeit und Breaking-Change-Risiko dokumentieren.**

```bash
npm audit --json > /tmp/mirofish-root-audit.json
npm --prefix frontend audit --json > /tmp/mirofish-frontend-audit.json
```

- [ ] **Step 3: Keine Abhängigkeit ohne separaten Freigabe- und Regressionstest ändern.**

Expected: `package.json` und Lockfiles bleiben in diesem Schritt unverändert.

### Task 6: Cleanup mit konkretem Lösch-Gate

**Files:**
- Inspect only until approval: lokale Worktrees/Branches sowie Remote-Images und Compose-Sicherungen.

**Interfaces:**
- Consumes: gesunden main-basierten Produktionsstand aus Task 4.
- Produces: konkrete Liste aus Ziel, Größe, Alter, Referenzen, Rollback-Wert und Wiederherstellbarkeit.

- [ ] **Step 1: Alle Kandidaten read-only inventarisieren und aktive Referenzen ausschließen.**

```bash
git worktree list --porcelain
git branch -vv
ssh imp-8-16-320 'sudo docker image ls --no-trunc mirofish-coolify-local'
ssh imp-8-16-320 'sudo find /data/coolify/services/qfxqzproqpzgtkqyx4kv0yzo -maxdepth 1 -type f -name "docker-compose.yml.before-*" -print'
```

- [ ] **Step 2: Exakte Löschliste mit einem verbleibenden Rollback-Stand vorlegen.**

Expected: Jeder Kandidat enthält exakten Namen, Größe, aktive Referenzen und Wiederherstellbarkeit; das unmittelbar vorherige gesunde Image bleibt erhalten.

- [ ] **Step 3: Erst nach konkreter Freigabe die benannten Ziele löschen; keine Globs und kein Force-Worktree-Remove verwenden.**

Expected: Ohne diese Freigabe endet Task 6 nach der Inventur ohne Löschung.
