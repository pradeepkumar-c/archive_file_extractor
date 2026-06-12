import pytest
from unittest.mock import patch, MagicMock
from service import extractions, FileHandlingError, DatabaseError, store_job_in_db, getjob
from sqlalchemy.exc import SQLAlchemyError
from app_factory import create_app


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

@patch('service.shutil.rmtree')
@patch('service.shutil.copy2')
@patch('service.os.makedirs')
@patch('service.store_job_in_db')
@patch('service.uuid.uuid4')
@patch('service.tempfile.mkdtemp')
def test_extractions_success(
    mock_mkdtemp,
    mock_uuid,
    mock_store,
    mock_makedirs,
    mock_copy,
    mock_rmtree,
    pattern,
    pattern_output
):

    mock_mkdtemp.return_value = "/tmp/testdir"
    mock_uuid.return_value = "1234-uuid"
    
    archive = MagicMock()
    archive.filename = "test.zip"

    result = extractions(archive, pattern)

    assert result == "1234-uuid"

    archive.save.assert_called_once_with("/tmp/testdir/test.zip")
    mock_copy.assert_called_once()
    mock_store.assert_called_once()

    args, kwargs = mock_store.call_args
    assert kwargs["pattern"] == pattern_output

    mock_rmtree.assert_called_once()


@ pytest.mark.parametrize("ErrorType, exception_message, ExceptionType, expected_message", [
    (OSError, "Disk error", FileHandlingError, "File operation failed"),
    (SQLAlchemyError, "Bad query", DatabaseError, "Database operation failed"),
    (Exception, "Unexpected error during extraction", RuntimeError, "Unexpected error during extraction"),
])
@ patch('service.tempfile.mkdtemp')
def test_extractions_oserror(mock_mkdtemp, ErrorType, exception_message, ExceptionType, expected_message):
    archive = MagicMock()
    mock_mkdtemp.side_effect = ErrorType(exception_message)
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




def test_getjob_ok(app):
    with app.app_context():

        with patch('service.JobStorage.query') as mock_job_query, \
            patch('service.FileMatch.query') as mock_file_query:


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



