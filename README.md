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
{"job_id": "14316009-3d9d-4d62-8cd6-11e74f8022a0"}
```

### Check job status
```sh
curl.exe -i -X GET http://localhost:8080/extractions/14316009-3d9d-4d62-8cd6-11e74f8022a0
```
**Response:**
```json
{
  "jobid": "d99a5b73-02b0-4f30-b58c-7e0eaeb30a31",
  "status": "completed",
  "num_matches": 2,
  "submitted_at": "2026-05-15T06:57:34.509447",
  "completed_at": "2026-05-15T06:57:34.868648"
}
```

### Get matched files (paginated)
```sh
curl.exe -i -X GET "http://localhost:8080/extractions/d99a5b73-02b0-4f30-b58c-7e0eaeb30a31/results?page=1&per_page=10"
```
**Response:**
```json
{
  "jobid": "d99a5b73-02b0-4f30-b58c-7e0eaeb30a31",
  "files": [
    "BMW_ICON_25.zip/BMW_ICON_25/Cybellum_SBOM-CycloneDX-1.6-...-en.json",
    "BMW_ICON_25.zip/BMW_ICON_25/Cybellum_SBOM-undefined-...-en.json"
  ],
  "page": 1,
  "per_page": 10,
  "total": 2,
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
SELECT filename, filepath, nesting_depth, source_archive FROM file_matches WHERE jobid = d99a5b73-02b0-4f30-b58c-7e0eaeb30a31;
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
- **Concurrency:** The job dispatcher uses a background thread (or thread pool) to process extraction jobs asynchronously. This allows the application to handle multiple requests while processing jobs in the background without blocking the main Flask server.
  - **Why threads?**
    - The workload in this project is primarily **I/O-bound**, involving archive extraction, file system traversal (glob pattern matching), and database operations. For such tasks, multithreading is efficient because threads can continue execution while waiting for I/O operations to complete.
    - Threads are also lightweight and share the same memory space, making them easier to integrate with Flask’s application context and database connections. In contrast, multiprocessing introduces additional overhead due to separate memory spaces and inter-process communication, and requires more complex setup for managing application context and database sessions.
    - Since the project does not involve CPU-intensive computations, the limitations of Python’s Global Interpreter Lock (GIL) are not a bottleneck in this case. Therefore, multithreading provides a simpler and efficient concurrency model for the current use case.

- **Input Format:** The API accepts the archive as `multipart/form-data`.
    - `multipart/form-data` was selected because it is a standard and widely supported method for file uploads in REST APIs. It allows clients to directly send archive files (e.g., `.zip`, `.7z`) along with additional parameters such as the glob pattern in a single request.

    - This approach simplifies implementation and testing, as it can be easily validated using tools like `curl` or Postman without requiring external file hosting or URL management. It also ensures better control over input validation, file handling, and security within the application.
