# Dockerized Flask Archive Extraction API

## Overview
A Flask-based REST API that accepts uploaded archives (`.zip`, `.7z`), recursively extracts nested archives, matches files by pattern, and stores full metadata in PostgreSQL. Jobs are processed asynchronously by a background process pool.

## Features
- Submit archive extraction jobs via REST API
- Supports `.zip` and `.7z` (including deeply nested archives)
- Pattern-based file matching (e.g., `**/*.json`)
- Tracks job status (`pending` → `running` → `completed`/`failed`) and full file metadata in PostgreSQL
- Configurable parallel workers via `POOL_SIZE` environment variable
- Dockerized: runs with a single `docker compose up`

## Main Files

| File | Purpose |
|---|---|
| `app.py` | Flask app — API endpoints, extraction logic, DB models, job dispatcher |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image for the Flask app |
| `docker-compose.yml` | Multi-container setup (app + PostgreSQL) |
| `config.json` | Default DB config (overridden by Docker env vars) |
| `tests/test_unit.py` | Unit tests — no DB required |
| `tests/test_integration.py` | Integration test — requires running DB |

## API Endpoints

| Method | Endpoint | Description | Request Body | Response |
|---|---|---|---|---|
| `POST` | `/extractions` | Submit an archive extraction job | `archive` (file), `pattern` (string) | `{"job_id": <id>}` — 202 |
| `GET` | `/extractions/<jobid>` | Get job status and match count | — | `{"jobid", "status", "submitted_at", "completed_at", "num_matches"}` |
| `GET` | `/extractions/<jobid>/results` | Paginated list of matched file paths | `?page=1&per_page=10` | `{"files": [...], "total", "pages"}` |
| `GET` | `/health` | Health check | — | `{"status": "ok"}` |

## Build & Run

### 1. Build and start with Docker Compose
```sh
docker compose up --build
```
- App API: http://localhost:8080
- DB: localhost:5432 (user: `myuser`, pass: `mypassword`, db: `mydb`)

### 2. Change worker pool size (optional)
Edit `POOL_SIZE` in `docker-compose.yml` before starting:
```yaml
POOL_SIZE: 8   # run 8 parallel extraction processes
```

### 3. Access the database
```sh
docker compose exec db psql -U myuser -d mydb
```

## Feature Test Examples

### Submit a job
```sh
curl.exe -i -X POST http://localhost:8080/extractions \
  -F "archive=@./BMW_ICON_25.zip" \
  -F "pattern=**/*.json"
```
**Response:**
```
HTTP/1.1 202 ACCEPTED
{"job_id": 4048386263501496562}
```

### Check job status
```sh
curl.exe -i -X GET http://localhost:8080/extractions/4048386263501496562
```
**Response:**
```json
{
  "jobid": "4048386263501496562",
  "status": "completed",
  "num_matches": 5,
  "submitted_at": "2026-05-15T06:57:34.509447",
  "completed_at": "2026-05-15T06:57:34.868648"
}
```

### Get matched files (paginated)
```sh
curl.exe -i -X GET "http://localhost:8080/extractions/4048386263501496562/results?page=1&per_page=10"
```
**Response:**
```json
{
  "jobid": "4048386263501496562",
  "files": [
    "BMW_ICON_25.zip/BMW_ICON_25/Cybellum_SBOM-CycloneDX-1.6-...-en.json",
    "BMW_ICON_25.zip/BMW_ICON_25/Cybellum_SBOM-undefined-...-en.json"
  ],
  "page": 1,
  "per_page": 10,
  "total": 5,
  "pages": 1
}
```

### Health check
```sh
curl.exe -i -X GET http://localhost:8080/health
```
**Response:**
```json
{"status": "ok"}
```

### Verify in DB
```sql
-- Connect: docker compose exec db psql -U myuser -d mydb
SELECT jobid, status, submitted_at, completed_at FROM jobs_storage;
SELECT filename, filepath, nesting_depth, source_archive FROM file_matches WHERE jobid = 4048386263501496562;
```

## Testing

### Unit tests (no DB required)
```sh
venv\Scripts\python.exe -m pytest tests/test_unit.py -v
```

### Integration test (requires DB running via Docker Compose)
```sh
venv\Scripts\python.exe -m pytest tests/test_integration.py -v
```

## Known Limitations & Design Notes

- **Supported archive types:** Only `.zip` and `.7z` are supported. To add more formats, extend the `extract_archive` function in `app.py`.
- **Concurrency:** The job dispatcher uses `multiprocessing.Pool` with a configurable `POOL_SIZE` (default: 4). Set via the `POOL_SIZE` environment variable in `docker-compose.yml`.
- **Why processes, not threads?**
  Archive extraction and file I/O are CPU- and disk-bound operations. Python's Global Interpreter Lock (GIL) prevents true parallelism with threads for CPU-bound work. Separate processes bypass the GIL and can run on multiple CPU cores, giving real parallel throughput for simultaneous extraction jobs.

