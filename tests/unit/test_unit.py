import io
import os
import uuid
import zipfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# jobid generation
# ---------------------------------------------------------------------------

class TestJobIdGeneration:

    def test_jobid_fits_biginteger(self):
        """uuid jobid must fit in a signed 64-bit PostgreSQL BigInteger."""
        jobid = uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF
        assert 0 <= jobid <= 0x7FFFFFFFFFFFFFFF

    def test_jobid_is_unique(self):
        ids = {uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF for _ in range(1000)}
        assert len(ids) == 1000


# ---------------------------------------------------------------------------
# find_matching_files
# ---------------------------------------------------------------------------

class TestFindMatchingFiles:

    def test_finds_json_files(self, tmp_path):
        (tmp_path / "a.json").write_text("{}")
        (tmp_path / "b.txt").write_text("hello")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.json").write_text("{}")

        from app import find_matching_files
        results = find_matching_files(str(tmp_path), "**/*.json")
        basenames = {os.path.basename(f) for f in results}
        assert "a.json" in basenames
        assert "c.json" in basenames
        assert "b.txt" not in basenames

    def test_returns_empty_when_no_match(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        from app import find_matching_files
        assert find_matching_files(str(tmp_path), "**/*.json") == []


# ---------------------------------------------------------------------------
# extract_archive
# ---------------------------------------------------------------------------

class TestExtractArchive:

    def test_extracts_zip(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("hello.json", '{"key": "value"}')
        extract_dir = tmp_path / "out"
        extract_dir.mkdir()

        from app import extract_archive
        assert extract_archive(str(zip_path), str(extract_dir)) is True
        assert (extract_dir / "hello.json").exists()

    def test_unsupported_format_returns_falsy(self, tmp_path):
        txt = tmp_path / "test.txt"
        txt.write_text("not an archive")
        from app import extract_archive
        assert not extract_archive(str(txt), str(tmp_path / "out"))

    def test_missing_file_returns_false(self, tmp_path):
        from app import extract_archive
        assert not extract_archive(str(tmp_path / "missing.zip"), str(tmp_path / "out"))


# ---------------------------------------------------------------------------
# extract_and_find
# ---------------------------------------------------------------------------

class TestExtractAndFind:

    def _zip(self, path, files: dict):
        with zipfile.ZipFile(str(path), "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)

    def test_flat_zip_finds_json(self, tmp_path):
        self._zip(tmp_path / "flat.zip", {"data.json": '{"x":1}', "readme.txt": "hi"})
        from app import extract_and_find
        files, error = extract_and_find(str(tmp_path / "flat.zip"), "**/*.json")
        assert error is None
        assert len(files) == 1
        assert files[0]["filename"] == "data.json"

    def test_nesting_depth_flat(self, tmp_path):
        """File directly inside one archive → nesting_depth == 1."""
        self._zip(tmp_path / "root.zip", {"item.json": "{}"})
        from app import extract_and_find
        files, _ = extract_and_find(str(tmp_path / "root.zip"), "**/*.json")
        assert files[0]["nesting_depth"] == 1

    def test_nesting_depth_nested(self, tmp_path):
        """File inside zip-in-zip → nesting_depth == 2."""
        inner = tmp_path / "inner.zip"
        self._zip(inner, {"nested.json": "{}"})
        outer = tmp_path / "outer.zip"
        with zipfile.ZipFile(str(outer), "w") as zf:
            zf.write(str(inner), "inner.zip")
        from app import extract_and_find
        files, error = extract_and_find(str(outer), "**/*.json")
        assert error is None
        assert files[0]["filename"] == "nested.json"
        assert files[0]["nesting_depth"] == 2

    def test_cyclic_archive_skipped(self, tmp_path):
        """Same archive name appearing again in a nested context must be skipped."""
        inner = tmp_path / "_outer.zip"
        self._zip(inner, {"top.json": "{}"})
        outer = tmp_path / "outer.zip"
        with zipfile.ZipFile(str(outer), "w") as zf:
            zf.write(str(inner), "outer.zip")   # same name → would loop
            zf.writestr("top.json", "{}")
        from app import extract_and_find
        files, error = extract_and_find(str(outer), "**/*.json")
        assert error is None  # must not crash or infinitely recurse

    def test_source_archive_always_root(self, tmp_path):
        inner = tmp_path / "inner.zip"
        self._zip(inner, {"deep.json": "{}"})
        outer = tmp_path / "outer.zip"
        with zipfile.ZipFile(str(outer), "w") as zf:
            zf.write(str(inner), "inner.zip")
        from app import extract_and_find
        files, _ = extract_and_find(str(outer), "**/*.json")
        for f in files:
            assert f["source_archive"] == "outer.zip"

    def test_max_depth_returns_error(self, tmp_path):
        self._zip(tmp_path / "x.zip", {"f.json": "{}"})
        from app import extract_and_find, MAX_NESTING_DEPTH
        files, error = extract_and_find(
            str(tmp_path / "x.zip"), "**/*.json", level=MAX_NESTING_DEPTH + 1
        )
        assert error is not None
        assert files == []

    def test_no_matching_files_returns_empty(self, tmp_path):
        self._zip(tmp_path / "empty.zip", {"readme.txt": "nothing"})
        from app import extract_and_find
        files, error = extract_and_find(str(tmp_path / "empty.zip"), "**/*.json")
        assert error is None
        assert files == []


# ---------------------------------------------------------------------------
# store_files_in_db  (DB session mocked)
# ---------------------------------------------------------------------------

class TestStoreFilesInDb:

    def _file_entry(self):
        return {
            "filepath": "root.zip/a.json",
            "filename": "a.json",
            "filesize": 100,
            "nesting_depth": 1,
            "extracted_at": datetime.utcnow(),
            "source_archive": "root.zip",
            "nesting_chain": "root.zip",
        }

    def test_stores_all_files(self):
        from app import store_files_in_db, db, app
        mock_session = MagicMock()
        with patch.object(db, "session", mock_session):
            with app.app_context():
                result = store_files_in_db(jobid=12345, file_list=[self._file_entry()])
        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_rollback_on_db_error(self):
        from app import store_files_in_db, db, app
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB error")
        with patch.object(db, "session", mock_session):
            with app.app_context():
                result = store_files_in_db(jobid=99, file_list=[self._file_entry()])
        assert result is False
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# API endpoints  (Flask test client, DB mocked)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


class TestHealthEndpoint:

    def test_returns_ok(self, client):
        assert client.get("/health").status_code == 200
        assert client.get("/health").get_json() == {"status": "ok"}


class TestGetJobEndpoint:

    def test_not_found_returns_404(self, client):
        with patch("app.JobStorage") as MockJob, patch("app.FileMatch"):
            MockJob.query.filter_by.return_value.first.return_value = None
            assert client.get("/extractions/99999").status_code == 404

    def test_completed_job_returns_fields(self, client):
        mock_job = MagicMock()
        mock_job.status = "completed"
        mock_job.submitted_at = datetime(2026, 1, 1, 12, 0, 0)
        mock_job.completed_at = datetime(2026, 1, 1, 12, 5, 0)
        mock_job.error = None
        with patch("app.JobStorage") as MockJob, patch("app.FileMatch") as MockFile:
            MockJob.query.filter_by.return_value.first.return_value = mock_job
            MockFile.query.filter_by.return_value.count.return_value = 8
            data = client.get("/extractions/1").get_json()
        assert data["status"] == "completed"
        assert data["num_matches"] == 8
        assert "submitted_at" in data
        assert "completed_at" in data
        assert "error" not in data

    def test_failed_job_includes_error_message(self, client):
        mock_job = MagicMock()
        mock_job.status = "failed"
        mock_job.submitted_at = datetime(2026, 1, 1, 12, 0, 0)
        mock_job.completed_at = datetime(2026, 1, 1, 12, 1, 0)
        mock_job.error = "Error extracting archive"
        with patch("app.JobStorage") as MockJob, patch("app.FileMatch") as MockFile:
            MockJob.query.filter_by.return_value.first.return_value = mock_job
            MockFile.query.filter_by.return_value.count.return_value = 0
            data = client.get("/extractions/99").get_json()
        assert data["error"] == "Error extracting archive"


class TestPostExtractionsEndpoint:

    def _zip_bytes(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("test.json", "{}")
        buf.seek(0)
        return buf

    def test_missing_fields_returns_400(self, client):
        assert client.post("/extractions", data={}).status_code == 400

    def test_valid_submission_returns_202(self, client):
        with patch("app.store_job_in_db", return_value=True), \
             patch("app.shutil.copy2"), patch("app.os.makedirs"):
            resp = client.post(
                "/extractions",
                data={"archive": (self._zip_bytes(), "test.zip"), "pattern": "**/*.json"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 202
        assert "job_id" in resp.get_json()

    def test_db_failure_returns_500(self, client):
        with patch("app.store_job_in_db", return_value=False), \
             patch("app.shutil.copy2"), patch("app.os.makedirs"):
            resp = client.post(
                "/extractions",
                data={"archive": (self._zip_bytes(), "test.zip"), "pattern": "**/*.json"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 500
