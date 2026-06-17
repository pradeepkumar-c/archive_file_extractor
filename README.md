# Archive Extractor Service

---

## 1. Overview

This service accepts an archive file and a file pattern, recursively extracts nested archives, finds matching files, and stores results in a database.

The processing is asynchronous and supports concurrent execution.

---

## 2. Features

- Recursive extraction of nested archives (.zip, .tar, .tar.gz, .7z)
- Pattern-based file search (glob)
- Asynchronous job processing
- Database persistence of results
- Pagination support for results
- Concurrent processing using ThreadPool

---

## 3. Project Structure

| File | Description |
|------|------------|
| app.py | Flask entry point |
| routes.py | API endpoints |
| service.py | Core logic and job execution |
| model.py | Database models |
| tests/ | Unit + integration tests |

---

## 4. Build & Run

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run service
```bash
python app.py
```

---

## 5. Docker Run

### Build image
```bash
docker build -t archive-extractor .
```

### Run container
```bash
docker run -p 8080:8080 \
-e DB_HOST=localhost \
-e DB_PORT=5432 \
-e DB_NAME=extractor \
-e DB_USER=user \
-e DB_PASSWORD=pass \
archive-extractor
```

---

## 6. API Endpoints

### 1. Submit Job

```bash
POST /extractions
```

Example:
```bash
curl -X POST http://localhost:8080/extractions \
  -F "archive=@file.zip" \
  -F "pattern=**/*.json"
```

Response:
```json
{ "job_id": "uuid" }
```

---

### 2. Get Job Status

```bash
GET /extractions/{job_id}
```

Response:
```json
{
  "jobid": "...",
  "status": "completed",
  "num_matches": 10
}
```

---

### 3. Get Results

```bash
GET /extractions/{job_id}/results?page=1&per_page=10
```

Response:
```json
{
  "files": ["file1.json", "file2.json"]
}
```

---

### 4. Health Check

```bash
GET /health
```

---

## 7. Example Usage

1. Submit job
2. Get job_id
3. Poll status
4. Fetch results

---

## 8. Database Design

### Jobs Table
- jobid
- status
- submitted_at
- completed_at
- error

### FileMatch Table
- jobid
- filepath (with nesting chain)
- filename
- filesize
- nesting_depth
- source_archive
- extracted_at

---

## 9. Concurrency Design

### ThreadPoolExecutor
- Handles job execution
- Supports multiple jobs concurrently
- Used for I/O operations (file extraction)

### Nested Extraction
- Recursive processing with safety depth limit

### Why Threading
- Archive extraction is I/O-bound
- Efficient for parallel jobs

---

## 10. Assumptions

- Archive may contain nested archives
- Pattern uses glob format
- Max nesting depth is limited
- Database is available and reachable

---

## 11. Error Handling

- Invalid archive → 400
- Unsupported format → failure
- DB error → job marked failed
- Cleanup always happens

---

## 12. Limitations

- No distributed processing
- No authentication
- In-memory dispatcher loop
- Limited scalability

---

## 13. Future Improvements

- Add queue system (Kafka/Redis)
- Add authentication
- Add distributed workers
- Optimize large archive handling
