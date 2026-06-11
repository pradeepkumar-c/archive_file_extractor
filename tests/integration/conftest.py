collect_ignore = ["test_app.py"]

import json
import os
import sys
from unittest.mock import patch, mock_open

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.chdir(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Fake config
# ---------------------------------------------------------------------------
FAKE_CONFIG = {
    "DB_HOST": "localhost",
    "DB_PORT": 5432,
    "DB_NAME": "test_db",
    "DB_USER": "test_user",
    "DB_PASSWORD": "test_pass",
    "DB_TABLE_JOBS": "jobs_storage",
    "DB_TABLE_FILE_MATCHES": "file_matches",
}

_real_open = open

def _patched_open(file, *args, **kwargs):
    if str(file) == "config.json":
        return mock_open(read_data=json.dumps(FAKE_CONFIG))()
    return _real_open(file, *args, **kwargs)

with patch("builtins.open", side_effect=_patched_open):
    import app
