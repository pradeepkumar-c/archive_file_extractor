from datetime import datetime
from sys import path
import zipfile
import py7zr
import tarfile
import pytest

from unittest.mock import patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError

from app_factory import create_app
from service import MAX_NESTING_DEPTH, STATUS_COMPLETED, STATUS_RUNNING,STATUS_PENDING, NotFoundError, ValidationError, extract_and_find, extract_archive, extractions, FileHandlingError, DatabaseError, find_matching_files, getjobresults, job_dispatcher, mark_job_failed, process_extracted_files, process_job, store_files_in_db, store_job_in_db, getjob



@pytest.fixture
def app():
    app = create_app()

    app.config.update({
        "TESTING": True,
    })

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.mark.parametrize("pattern, pattern_output", [
    ("*.json","**/*.json"),
    ("**/*.csv", "**/*.csv")
])
@patch('service.store_job_in_db')
@patch('service.uuid.uuid4')
def test_extractions_success(
    mock_uuid,
    mock_store,
    pattern,
    pattern_output
):
    mock_uuid.return_value = "1234-uuid"
    
    archive = MagicMock()
    archive.filename = "test.zip"

    result = extractions(archive, pattern)

    assert result == "1234-uuid"

    archive.save.assert_called_once_with("archives_1234-uuid/test.zip")
    mock_store.assert_called_once()

    args, kwargs = mock_store.call_args
    assert kwargs["pattern"] == pattern_output


@ pytest.mark.parametrize("ErrorType, exception_message, ExceptionType, expected_message", [
    (OSError, "Disk error", FileHandlingError, "File operation failed"),
    (SQLAlchemyError, "Bad query", DatabaseError, "Database operation failed"),
    (Exception, "Unexpected error during extraction", RuntimeError, "Unexpected error during extraction"),
])
@ patch('service.os.makedirs')
def test_extractions_oserror(mock_makedirs, ErrorType, exception_message, ExceptionType, expected_message):
    archive = MagicMock()
    mock_makedirs.side_effect = ErrorType(exception_message)
    archive.filename = "test.zip"

    with pytest.raises(ExceptionType, match=expected_message):
        extractions(archive, "*.json")

@patch('service.db.session')
def test_store_job_in_db_ok(mock_db_session):    
    jobid = "1234-uuid"
    archivefile = "/tmp/testdir/test.zip"
    pattern = "**/*.json"
    status = "pending"

    store_job_in_db(jobid, archivefile, pattern, status)

    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()

@patch('service.db.session')
def test_store_job_in_db_exception(mock_db_session):    
    jobid = "1234-uuid"
    archivefile = "/tmp/testdir/test.zip"
    pattern = "**/*.json"
    status = "pending"
    mock_db_session.add.side_effect = SQLAlchemyError("DB error")
    with pytest.raises(DatabaseError, match="Database operation failed"):
        store_job_in_db(jobid, archivefile, pattern, status)

    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_not_called()


@pytest.fixture
def mock_queries(app):
    with app.app_context():
        with patch('service.JobStorage.query') as mock_job_query, \
            patch('service.FileMatch.query') as mock_file_query:
            yield mock_job_query, mock_file_query

def test_getjob_ok(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    jobid = "12345678-1234-5678-1234-567812345678"
    mock_job = MagicMock()
    mock_job.jobid = jobid
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = None

    mock_job_query.filter_by.return_value.first.return_value = mock_job
    mock_file_query.filter_by.return_value.count.return_value = 1
    result = getjob(jobid)

    assert result['jobid'] == jobid
    assert result['status'] == "completed"
    assert result['num_matches'] == 1
    assert result['submitted_at'] == "ABC"
    assert result['completed_at'] == "XYZ"

def test_getjob_uuid_exception(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "invalid-uuid"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = None

    mock_job_query.filter_by.return_value.first.return_value = mock_job
    mock_file_query.filter_by.return_value.count.return_value = 1
    with pytest.raises(NotFoundError, match="Invalid job id format"):
        result = getjob("invalid-uuid")

def test_getjob_job_not_found_exception(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "12345678-1234-5678-1234-567812345678"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = None

    mock_job_query.filter_by.return_value.first.return_value = None
    mock_file_query.filter_by.return_value.count.return_value = 1
    with pytest.raises(NotFoundError, match="Job not found"):
        result = getjob("12345678-1234-5678-1234-567812345678")


def test_getjob_job_error(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "12345678-1234-5678-1234-567812345678"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = "Job failed due to error"

    mock_job_query.filter_by.return_value.first.return_value = mock_job
    mock_file_query.filter_by.return_value.count.return_value = 1
    response = getjob("12345678-1234-5678-1234-567812345678")
    assert response['error'] == "Job failed due to error"

def test_getjob_database_error(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "12345678-1234-5678-1234-567812345678"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = "Job failed due to error"

    mock_job_query.filter_by.return_value.first.side_effect = SQLAlchemyError("DB error")
    mock_file_query.filter_by.return_value.count.return_value = 1
    with pytest.raises(DatabaseError, match="Database operation failed"):
        getjob("12345678-1234-5678-1234-567812345678")

def test_getjobresults_ok(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    jobid = "12345678-1234-5678-1234-567812345678"
    mock_job = MagicMock()
    mock_job.jobid = jobid
    mock_job.files = {"abc.json", "def.json"}
    mock_job.error = None

    mock_job_query.filter_by.return_value.first.return_value = mock_job
    mock_file_query.filter_by.return_value.count.return_value = 1
    result = getjobresults(jobid)

    print(result)
    assert result['jobid'] == jobid

def test_getjobresults_uuid_exception(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "invalid-uuid"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = None

    mock_job_query.filter_by.return_value.first.return_value = mock_job
    mock_file_query.filter_by.return_value.count.return_value = 1
    with pytest.raises(NotFoundError, match="Invalid job id format"):
        getjobresults("invalid-uuid")

def test_getjobresults_job_not_found_exception(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "12345678-1234-5678-1234-567812345678"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = None

    mock_job_query.filter_by.return_value.first.return_value = None
    mock_file_query.filter_by.return_value.count.return_value = 1
    with pytest.raises(NotFoundError, match="Job not found"):
        getjobresults("12345678-1234-5678-1234-567812345678")


def test_getjobresults_database_error(app, mock_queries):
    mock_job_query, mock_file_query = mock_queries
    mock_job = MagicMock()
    mock_job.jobid = "12345678-1234-5678-1234-567812345678"
    mock_job.status = "completed"
    mock_job.submitted_at.isoformat.return_value = "ABC"
    mock_job.completed_at.isoformat.return_value = "XYZ"
    mock_job.error = "Job failed due to error"

    mock_job_query.filter_by.return_value.first.side_effect = SQLAlchemyError("DB error")
    mock_file_query.filter_by.return_value.count.return_value = 1
    with pytest.raises(DatabaseError, match="Database operation failed"):
        getjobresults("12345678-1234-5678-1234-567812345678")

@patch('service.db.session')
def test_store_files_in_db_ok(mock_db_session):
    jobid = "12345678-1234-5678-1234-567812345678"
    files =[
            {"filepath":"/tmp/testdir/test1.json", "filename": "test1.json", "filesize": 1234, "nesting_depth": 1, "source_archive":"test.zip", "nesting_chain":"sad", "extracted_at": "2024-06-01T12:00:00"},
            {"filepath":"/tmp/testdir/test2.json", "filename": "test2.json", "filesize": 4321, "nesting_depth": 2, "source_archive":"test.zip", "nesting_chain":"sad", "extracted_at": "2024-06-01T12:00:00"},
            ]

    store_files_in_db(jobid, files)

    assert mock_db_session.add.call_count == 2
    mock_db_session.commit.assert_called_once()

@patch('service.db.session')
def test_store_files_in_db_exception(mock_db_session):
    jobid = "12345678-1234-5678-1234-567812345678"
    files =[
            {"filepath":"/tmp/testdir/test1.json", "filename": "test1.json", "filesize": 1234, "nesting_depth": 1, "source_archive":"test.zip", "nesting_chain":"sad", "extracted_at": "2024-06-01T12:00:00"},
            {"filepath":"/tmp/testdir/test2.json", "filename": "test2.json", "filesize": 4321, "nesting_depth": 2, "source_archive":"test.zip", "nesting_chain":"sad", "extracted_at": "2024-06-01T12:00:00"},
            ]
    mock_db_session.add.side_effect = SQLAlchemyError("DB error")
    with pytest.raises(DatabaseError, match="Database operation failed"):
        store_files_in_db(jobid, files)


@patch('service.glob.glob')
def test_find_matching_files(mock_glob):
    search_dir = "/tmp/data"
    pattern = "**/*.json"
    expected_path = "/tmp/data/**/*.json"

    mock_glob.return_value = ["file1.json", "dir/file2.json"]


    result = find_matching_files(search_dir, pattern)

    mock_glob.assert_called_once_with(expected_path, recursive=True)
    assert result == ["file1.json", "dir/file2.json"]


@pytest.mark.parametrize("archive_type", ["zip", "7z", "tar"])
@patch('service.zipfile')
@patch('service.py7zr')
@patch('service.tarfile')
def test_extract_archive_ok(mock_tarfile, mock_py7zr, mock_zipfile, archive_type):

    mock_zipfile.is_zipfile.return_value = archive_type == "zip"
    mock_py7zr.is_7zfile.return_value = archive_type == "7z"
    mock_tarfile.is_tarfile.return_value = archive_type == "tar"
    
    if archive_type == "zip":
        mock_zipfile.is_zipfile.return_value = True
        input_path = "/tmp/testdir/test.zip"
        mock_zipfile.ZipFile.return_value.__enter__.return_value.extractall.return_value = None
    elif archive_type == "7z":
        input_path = "/tmp/testdir/test.7z"
        mock_py7zr.SevenZipFile.return_value.__enter__.return_value.extractall.return_value = None
    elif archive_type == "tar":
        input_path = "/tmp/testdir/test.tar"
        mock_tarfile.open.return_value.__enter__.return_value.extractall.return_value = None

    extract_archive(input_path, "/tmp/extractdir")

    if archive_type == "zip":
        mock_zipfile.is_zipfile.assert_called_once_with(input_path)
        mock_zipfile.ZipFile.return_value.__enter__.return_value.extractall.assert_called_once_with("/tmp/extractdir")
    elif archive_type == "7z":
        mock_py7zr.is_7zfile.assert_called_once_with(input_path)
        mock_py7zr.SevenZipFile.return_value.__enter__.return_value.extractall.assert_called_once_with(path="/tmp/extractdir")
    elif archive_type == "tar":
        mock_tarfile.is_tarfile.assert_called_once_with(input_path)
        mock_tarfile.open.return_value.__enter__.return_value.extractall.assert_called_once_with("/tmp/extractdir")


@pytest.mark.parametrize("archive_type", ["zip", "7z", "tar"])
@patch('service.tarfile.open')
@patch('service.tarfile.is_tarfile')
@patch('service.py7zr.SevenZipFile')
@patch('service.py7zr.is_7zfile')
@patch('service.zipfile.ZipFile')
@patch('service.zipfile.is_zipfile')
def test_extract_archive_exception(
    mock_is_zipfile,
    mock_zipfile_cls,
    mock_is_7zfile,
    mock_7z_cls,
    mock_is_tarfile,
    mock_tar_open,
    archive_type
):

    input_path = "/tmp/testdir/test.file"

    mock_is_zipfile.return_value = False
    mock_is_7zfile.return_value = False
    mock_is_tarfile.return_value = False

    if archive_type == "zip":
        mock_is_zipfile.return_value = True
        mock_zipfile_cls.side_effect = zipfile.BadZipFile("corrupted zip")

    elif archive_type == "7z":
        mock_is_7zfile.return_value = True
        mock_7z_cls.side_effect = py7zr.exceptions.Bad7zFile("corrupted 7z")

    elif archive_type == "tar":
        mock_is_tarfile.return_value = True
        mock_tar_open.side_effect = tarfile.TarError("corrupted tar")

    with pytest.raises(FileHandlingError):
        extract_archive(input_path, "/tmp/extractdir")


@patch('service.zipfile.is_zipfile', return_value=False)
@patch('service.py7zr.is_7zfile', return_value=False)
@patch('service.tarfile.is_tarfile', return_value=False)
def test_extract_archive_unsupported_format(
    mock_is_tar, mock_is_7z, mock_is_zip
):
    input_path = "/tmp/testdir/test.unknown"

    with pytest.raises(RuntimeError, match="Unexpected extraction error"):
        extract_archive(input_path, "/tmp/extractdir")



@patch('service.zipfile.is_zipfile', return_value=True)
@patch('service.zipfile.ZipFile')
def test_extract_archive_oserror_zip(mock_zip_cls, mock_is_zip):

    input_path = "/tmp/testdir/test.zip"
    mock_zip_cls.side_effect = OSError("disk error")

    with pytest.raises(FileHandlingError, match="Archive extraction failed"):
        extract_archive(input_path, "/tmp/extractdir")


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp')
@patch('service.process_extracted_files')
@patch('service.extract_archive')
def test_extract_and_find_success(
    mock_extract,
    mock_process,
    mock_mkdtemp,
    mock_rmtree
):
    mock_mkdtemp.return_value = "/tmp/testdir"
    mock_process.return_value = ["file1.json"]

    result = extract_and_find("/tmp/archive.zip", "*.json")

    assert result == ["file1.json"]

    mock_extract.assert_called_once_with("/tmp/archive.zip", "/tmp/testdir")
    mock_process.assert_called_once()

    mock_rmtree.assert_called_once_with("/tmp/testdir", ignore_errors=True)


def test_extract_and_find_max_depth():
    with pytest.raises(RuntimeError, match="Maximum extraction depth reached"):
        extract_and_find(
            "/tmp/archive.zip",
            "*.json",
            level=MAX_NESTING_DEPTH + 1
        )


def test_extract_and_find_already_processed():
    processed = {"archive.zip"}

    result = extract_and_find(
        "/tmp/archive.zip",
        "*.json",
        processed=processed
    )

    assert result == []


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp', return_value="/tmp/x")
@patch('service.extract_archive')
def test_extract_and_find_runtime_error(
    mock_extract,
    mock_mkdtemp,
    mock_rmtree
):
    mock_extract.side_effect = RuntimeError("Extraction failed")

    with pytest.raises(RuntimeError):
        extract_and_find("/tmp/archive.zip", "*.json")

    mock_rmtree.assert_called_once_with("/tmp/x", ignore_errors=True)


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp', return_value="/tmp/x")
@patch('service.extract_archive')
def test_extract_and_find_unexpected_exception(
    mock_extract,
    mock_mkdtemp,
    mock_rmtree
):
    mock_extract.side_effect = Exception("random failure")

    with pytest.raises(RuntimeError, match="Unexpected extraction error"):
        extract_and_find("/tmp/archive.zip", "*.json")

    mock_rmtree.assert_called_once()


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp', return_value="/tmp/x")
@patch('service.process_extracted_files')
@patch('service.extract_archive')
def test_extract_and_find_chain_passed(
    mock_extract,
    mock_process,
    mock_mkdtemp,
    mock_rmtree
):
    extract_and_find("/tmp/archive.zip", "*.json")

    args = mock_process.call_args[0]

    assert args[3] == ["archive.zip"]


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp', return_value="/tmp/x")
@patch('service.process_extracted_files')
@patch('service.extract_archive')
def test_extract_and_find_source_archive_default(
    mock_extract,
    mock_process,
    mock_mkdtemp,
    mock_rmtree
):
    extract_and_find("/tmp/path/archive.zip", "*.json")

    args = mock_process.call_args[0]
    assert args[4] == "archive.zip"


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp', return_value="/tmp/x")
@patch('service.process_extracted_files')
@patch('service.extract_archive')
def test_extract_and_find_processed_updated(
    mock_extract,
    mock_process,
    mock_mkdtemp,
    mock_rmtree
):
    processed = set()

    extract_and_find("/tmp/archive.zip", "*.json", processed=processed)

    assert "archive.zip" in processed


@patch('service.shutil.rmtree')
@patch('service.tempfile.mkdtemp', return_value="/tmp/x")
@patch('service.extract_archive')
def test_extract_and_find_cleanup_on_error(
    mock_extract,
    mock_mkdtemp,
    mock_rmtree
):
    mock_extract.side_effect = Exception("fail")

    with pytest.raises(RuntimeError):
        extract_and_find("/tmp/archive.zip", "*.json")

    mock_rmtree.assert_called_once_with("/tmp/x", ignore_errors=True)

@patch('service.os.path.getsize', return_value=100)
@patch('service.os.path.basename')
@patch('service.os.path.relpath')
@patch('service.find_matching_files')
@patch('service.zipfile.is_zipfile', return_value=False)
@patch('service.py7zr.is_7zfile', return_value=False)
@patch('service.tarfile.is_tarfile', return_value=False)
@patch('service.glob.glob')
def test_process_extracted_files_ok(
    mock_glob,
    mock_is_tar,
    mock_is_7z,
    mock_is_zip,
    mock_find,
    mock_relpath,
    mock_basename,
    mock_getsize
):

    mock_find.return_value = ["/tmp/a.txt"]
    mock_relpath.return_value = "a.txt"
    mock_basename.return_value = "a.txt"
    mock_glob.return_value = []

    result = process_extracted_files(
        "/tmp",
        "*.txt",
        0,
        ["archive.zip"],
        "archive.zip",
        set()
    )

    assert len(result) == 1
    assert result[0]['filename'] == "a.txt"
    assert result[0]['filesize'] == 100


@patch('service.find_matching_files')
@patch('service.zipfile.is_zipfile', return_value=True)
@patch('service.glob.glob', return_value=[])
def test_process_extracted_files_skip_archive_files(mock_glob, mock_is_zip, mock_find):

    mock_find.return_value = ["/tmp/archive.zip"]

    result = process_extracted_files(
        "/tmp", "*", 0, ["a.zip"], "a.zip", set()
    )

    assert result == []


@patch('service.extract_and_find')
@patch('service.os.path.exists', return_value=True)
@patch('service.glob.glob')
@patch('service.find_matching_files', return_value=[])
@patch('service.zipfile.is_zipfile')
@patch('service.py7zr.is_7zfile')
@patch('service.tarfile.is_tarfile')
def test_process_extracted_files_nested_archive_processing(
    mock_is_tar,
    mock_is_7z,
    mock_is_zip,
    mock_find,
    mock_glob,
    mock_exists,
    mock_extract
):

    mock_glob.return_value = ["/tmp/nested.zip"]
    mock_is_zip.return_value = True
    mock_is_7z.return_value = False
    mock_is_tar.return_value = False

    mock_extract.return_value = [{"filename": "inner.txt"}]

    result = process_extracted_files(
        "/tmp", "*", 0, ["a.zip"], "a.zip", set()
    )

    assert len(result) == 1
    mock_extract.assert_called_once()


@patch('service.os.path.exists', return_value=False)
@patch('service.glob.glob')
@patch('service.find_matching_files', return_value=[])
def test_process_extracted_files_skip_non_existing_files(mock_find, mock_glob, mock_exists):

    mock_glob.return_value = ["/tmp/missing.txt"]

    result = process_extracted_files(
        "/tmp", "*", 0, ["a.zip"], "a.zip", set()
    )

    assert result == []


@patch('service.extract_and_find', return_value=[{"filename": "inner.txt"}])
@patch('service.os.path.exists', return_value=True)
@patch('service.os.path.getsize', return_value=50)
@patch('service.os.path.basename', side_effect=["a.txt", "nested.zip"])
@patch('service.os.path.relpath', return_value="a.txt")
@patch('service.find_matching_files')
@patch('service.zipfile.is_zipfile', side_effect=[False, True])
@patch('service.py7zr.is_7zfile', return_value=False)
@patch('service.tarfile.is_tarfile', return_value=False)
@patch('service.glob.glob')
def test_process_extracted_files_mixed_files(
    mock_glob,
    mock_is_tar,
    mock_is_7z,
    mock_is_zip,
    mock_find,
    mock_relpath,
    mock_basename,
    mock_getsize,
    mock_exists,
    mock_extract
):

    mock_find.return_value = ["/tmp/a.txt"]
    mock_glob.return_value = ["/tmp/nested.zip"]

    result = process_extracted_files(
        "/tmp", "*", 0, ["a.zip"], "a.zip", set()
    )

    assert len(result) == 2  


@patch('service.os.path.exists', return_value=True)
@patch('service.tarfile.is_tarfile', return_value=False)
@patch('service.py7zr.is_7zfile', return_value=False)
@patch('service.zipfile.is_zipfile', return_value=False)
@patch('service.os.path.getsize', side_effect=OSError("fail"))
@patch('service.os.path.basename', return_value="a.txt")
@patch('service.os.path.relpath', return_value="a.txt")
@patch('service.find_matching_files')
@patch('service.glob.glob', return_value=[])
def test_process_extracted_files_metadata_oserror(
    mock_glob,
    mock_find,
    mock_relpath,
    mock_basename,
    mock_getsize,
    mock_is_zip,
    mock_is_7z,
    mock_is_tar,
    mock_exists
):

    mock_find.return_value = ["/tmp/a.txt"]

    result = process_extracted_files(
        "/tmp", "*", 0, ["a.zip"], "a.zip", set()
    )

    assert result == []

@patch('service.db.session')
def test_mark_job_failed_ok(mock_db_session):
    mock_job = MagicMock()
    mock_job.status = "failed"
    mock_job.error = "Job failed due to error"
    mock_job.completed_at = datetime.utcnow()
    jobid = "1234-uuid"
    error_message = "Job failed due to error"

    mark_job_failed(mock_job, error_message)

    mock_db_session.commit.assert_called_once()

@patch('service.db.session')
def test_mark_job_failed_db_error(mock_db_session):
    mock_job = MagicMock()
    mock_job.status = "failed"
    mock_job.error = "Job failed due to error"
    mock_job.completed_at = datetime.utcnow()
    jobid = "1234-uuid"
    error_message = "Job failed due to error"
    mock_db_session.commit.side_effect = SQLAlchemyError("DB error")
    
    mark_job_failed(mock_job, error_message)
    
    mock_db_session.rollback.assert_called_once()


@pytest.fixture
def mock_queries_job(app):
    with app.app_context():
        with patch('service.db.session.remove') as mock_remove, \
            patch('service.shutil.rmtree') as mock_rmtree, \
            patch('service.store_files_in_db') as mock_store, \
            patch('service.extract_and_find') as mock_extract, \
            patch('service.db.session.commit') as mock_commit, \
            patch('service.mark_job_failed') as mock_mark_failed, \
            patch('service.JobStorage.query') as mock_query:

            yield {
                "remove": mock_remove,
                "rmtree": mock_rmtree,
                "store": mock_store,
                "extract": mock_extract,
                "commit": mock_commit,
                "mark_failed": mock_mark_failed,
                "query": mock_query
            }


def test_process_job_ok(app, mock_queries_job):
    mocks = mock_queries_job

    jobid = "123"

    job = MagicMock()
    job.archivename = "file.zip"
    job.pattern = "*.json"

    mocks["query"].filter_by.return_value.first.return_value = job
    mocks["extract"].return_value = [{"file": "a.json"}]

    process_job(app, jobid)

    assert job.status == STATUS_COMPLETED
    assert job.completed_at is not None

    assert mocks["extract"].call_count == 1
    assert mocks["store"].call_count == 1
    assert mocks["commit"].call_count == 1
    assert mocks["rmtree"].call_count == 1
    assert mocks["remove"].call_count == 2



@pytest.mark.parametrize(
    "exception",
    [
        FileHandlingError("file error"),
        DatabaseError("db error"),
        RuntimeError("runtime error"),
    ]
)
def test_process_job_handled_exceptions(app, mock_queries_job, exception):
    mocks = mock_queries_job
    jobid = "123"

    job = MagicMock()
    job.archivename = "file.zip"
    job.pattern = "*"

    mocks["query"].filter_by.return_value.first.return_value = job

    mocks["extract"].side_effect = exception
    process_job(app, jobid)

    assert mocks["store"].call_count == 0
    assert mocks["commit"].call_count == 0
    assert mocks["rmtree"].call_count == 1
    assert mocks["remove"].call_count == 2

def test_process_job_unexpected_exception(app, mock_queries_job):
    mocks = mock_queries_job
    jobid = "123"

    job = MagicMock()
    job.archivename = "file.zip"
    job.pattern = "*"

    mocks["query"].filter_by.return_value.first.return_value = job

    mocks["extract"].side_effect = Exception("boom")

    process_job(app, jobid)

    assert mocks["store"].call_count == 0
    assert mocks["rmtree"].call_count == 1
    assert mocks["remove"].call_count == 2

@pytest.mark.parametrize(
    "store_exception",
    [
        DatabaseError("db fail"),
        RuntimeError("runtime fail"),
    ]
)
def test_process_job_store_failure(app, mock_queries_job, store_exception):
    mocks = mock_queries_job
    jobid = "123"

    job = MagicMock()
    job.archivename = "file.zip"
    job.pattern = "*"

    mocks["query"].filter_by.return_value.first.return_value = job

    mocks["extract"].return_value = [{"file": "a.json"}]
    mocks["store"].side_effect = store_exception

    process_job(app, jobid)

    assert mocks["store"].call_count == 1
    assert mocks["rmtree"].call_count == 1
    assert mocks["remove"].call_count == 2

@patch('service.print')
def test_process_job_cleanup_exception(mock_print, mock_queries_job, app):
    mocks = mock_queries_job
    jobid = "123"

    job = MagicMock()
    job.archivename = "file.zip"
    job.pattern = "*"

    mocks["query"].filter_by.return_value.first.return_value = job
    mocks["extract"].return_value = []


    mocks["rmtree"].side_effect = Exception("cleanup failed")
    process_job(app, jobid)
    assert mocks["rmtree"].call_count == 1
    mock_print.assert_any_call("Failed to cleanup archive dir: cleanup failed")
    assert mocks["remove"].call_count == 2


def test_process_job_not_found(app, mock_queries_job):
    mocks = mock_queries_job
    jobid = "123"

    mocks["query"].filter_by.return_value.first.return_value = None

    process_job(app, jobid)

    assert mocks["extract"].call_count == 0
    assert mocks["store"].call_count == 0
    assert mocks["commit"].call_count == 0

    mocks["mark_failed"].assert_called_once()

from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_dispatcher(app):
    with app.app_context():
        with patch('service.time.sleep') as mock_sleep, \
            patch('service.ThreadPoolExecutor') as mock_executor, \
            patch('service.db.session.commit') as mock_commit, \
            patch('service.db.session.rollback') as mock_rollback, \
            patch('service.JobStorage.query.filter_by') as mock_filter:

            yield {
                "sleep": mock_sleep,
                "executor": mock_executor,
                "commit": mock_commit,
                "rollback": mock_rollback,
                "filter": mock_filter
            }


def test_job_dispatcher_ok(app, mock_dispatcher):
    mocks = mock_dispatcher

    job = MagicMock()
    job.jobid = "1"
    job.status = STATUS_PENDING

    mocks["sleep"].side_effect = Exception("stop")

    executor_instance = mocks["executor"].return_value

    with app.app_context():

        fake_query = MagicMock()
        fake_query.filter_by.return_value.limit.return_value.all.return_value = [job]

        with patch('service.JobStorage.query', fake_query):
            try:
                job_dispatcher(app)
            except Exception:
                pass

    assert job.status == STATUS_RUNNING

    assert mocks["commit"].call_count == 1
    executor_instance.submit.assert_called_once_with(process_job, app, "1")

def test_job_dispatcher_exception(app, mock_dispatcher):
    mocks = mock_dispatcher

    job = MagicMock()
    job.jobid = "1"
    job.status = STATUS_PENDING

    mocks["sleep"].side_effect = Exception("stop")

    executor_instance = mocks["executor"].return_value

    with app.app_context():

        fake_query = MagicMock()
        fake_query.filter_by.return_value.limit.return_value.all.return_value = [job]

        with patch('service.JobStorage.query', fake_query):
            try:
                job_dispatcher(app)
            except Exception:
                pass

    assert job.status == STATUS_RUNNING

    assert mocks["commit"].call_count == 1
    executor_instance.submit.assert_called_once_with(process_job, app, "1")


def test_job_dispatcher_no_jobs(app, mock_dispatcher):
    mocks = mock_dispatcher

    mocks["sleep"].side_effect = Exception("stop")

    executor_instance = mocks["executor"].return_value

    with app.app_context():
        fake_query = MagicMock()
        fake_query.filter_by.return_value.limit.return_value.all.return_value = []

        with patch('service.JobStorage.query', fake_query):
            try:
                job_dispatcher(app)
            except Exception:
                pass

    executor_instance.submit.assert_not_called()
    assert mocks["commit"].call_count == 1


def test_job_dispatcher_multiple_jobs(mock_dispatcher, app):
    mocks = mock_dispatcher

    job1 = MagicMock()
    job1.jobid = "1"
    job1.status = STATUS_PENDING

    job2 = MagicMock()
    job2.jobid = "2"
    job2.status = STATUS_PENDING

    mocks["sleep"].side_effect = Exception("stop")

    executor_instance = mocks["executor"].return_value

    with app.app_context():
        fake_query = MagicMock()
        fake_query.filter_by.return_value.limit.return_value.all.return_value = [job1, job2]

        with patch('service.JobStorage.query', fake_query):
            try:
                job_dispatcher(app)
            except Exception:
                pass

    assert job1.status == STATUS_RUNNING
    assert job2.status == STATUS_RUNNING

    assert executor_instance.submit.call_count == 2


def test_job_dispatcher_commit_failure(mock_dispatcher, app):
    mocks = mock_dispatcher

    job = MagicMock()
    job.jobid = "1"
    job.status = STATUS_PENDING

    mocks["commit"].side_effect = SQLAlchemyError("db error")
    mocks["sleep"].side_effect = Exception("stop")

    executor_instance = mocks["executor"].return_value

    with app.app_context():
        fake_query = MagicMock()
        fake_query.filter_by.return_value.limit.return_value.all.return_value = [job]

        with patch('service.JobStorage.query', fake_query):
            try:
                job_dispatcher(app)
            except Exception:
                pass

    asserts = mocks["rollback"].call_count == 1

def test_validation_error_init():
    error = ValidationError("Invalid input")

    assert error.error_body == "Invalid input"


def test_validation_error_raise():
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError("Invalid request")

    assert exc_info.value.error_body == "Invalid request"
