#    pytest tests/test_integration.py -v
import io
import os
import shutil
import uuid
import zipfile
from datetime import datetime

import pytest


@pytest.mark.integration
class TestFullJobLifecycle:
    def test_post_and_get_job(self):
        from app import app as flask_app, db, JobStorage, FileMatch

        # Build a small zip with 2 JSON files
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("result1.json", '{"a": 1}')
            zf.writestr("result2.json", '{"b": 2}')
        zip_buf.seek(0)

        with flask_app.test_client() as client:
            # Submit the job
            resp = client.post(
                "/extractions",
                data={"archive": (zip_buf, "integ_test.zip"), "pattern": "**/*.json"},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 202, f"Expected 202, got {resp.status_code}"
            jobid = resp.get_json()["job_id"]
            assert jobid is not None

            # Job should be created in DB with status pending/running/completed
            status_resp = client.get(f"/extractions/{jobid}")
            assert status_resp.status_code == 200
            data = status_resp.get_json()
            assert data["status"] in ("pending", "running", "completed", "failed")
            assert "submitted_at" in data

        # Cleanup
        archive_path = os.path.join("archives", "integ_test.zip")
        if os.path.exists(archive_path):
            os.remove(archive_path)
        with flask_app.app_context():
            FileMatch.query.filter_by(jobid=jobid).delete()
            JobStorage.query.filter_by(jobid=jobid).delete()
            db.session.commit()
