import pytest
from unittest.mock import patch
from flask import request
from app import app
from service import NotFoundError, DatabaseError, FileHandlingError
import io

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_success(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
    }

@patch('routes.getjob')
def test_getjob_endpoint_ok(mock_getjob, client):
    mock_getjob.return_value = {'jobid': '123'}
    response = client.get('/extractions/123')
    assert response.status_code == 200
    assert response.get_json() == {'jobid': '123'}

@pytest.mark.parametrize("ExceptionType, exception_message, expected_status, expected_error", [
    (Exception, "Random Error", 500, "Internal server error"),
    (NotFoundError, "Not Found Error", 404, "Not Found Error"),
    (DatabaseError, "Database Error", 500, "Failed to retrieve job"),
])
@patch('routes.getjob')
def test_getjob_endpoint_exception(mock_getjob, client, ExceptionType, exception_message, expected_status, expected_error):
    mock_getjob.side_effect = ExceptionType(exception_message)
    response = client.get('/extractions/123')
    assert response.status_code == expected_status
    assert expected_error in response.get_json()["error"]


@patch('routes.getjobresults')
def test_getjobresults_endpoint_ok(mock_getjobresults, client):
    mock_getjobresults.return_value = {'jobid': '123'}
    response = client.get('/extractions/123/results')
    assert response.status_code == 200
    assert response.get_json() == {'jobid': '123'}

@pytest.mark.parametrize("ExceptionType, exception_message, expected_status, expected_error", [
    (Exception, "Random Error", 500, "Internal server error"),
    (NotFoundError, "Not Found Error", 404, "Not Found Error"),
    (DatabaseError, "Database Error", 500, "Failed to retrieve job"),
])
@patch('routes.getjobresults')
def test_getjobresults_endpoint_exception(mock_getjobresults, client, ExceptionType,exception_message,  expected_status, expected_error):
    mock_getjobresults.side_effect = ExceptionType(exception_message)
    response = client.get('/extractions/123/results')
    assert response.status_code == expected_status
    assert expected_error in response.get_json()["error"]


@patch('routes.extractions')
def test_extractions_endpoint_ok(mock_extractions, client):
    mock_extractions.return_value = '123'

    response = client.post(
        '/extractions',
        data={
            'archive': (io.BytesIO(b"dummy content"), 'test.zip'),
            'pattern': '*.json'
        },
        content_type='multipart/form-data'
    )
    assert response.status_code == 202
    assert response.get_json() == {'job_id': '123'}

@pytest.mark.parametrize("archive, pattern, responsecode", [
    (None, '*.json', 400),
    (io.BytesIO(b"dummy content"), None, 400),
    (io.BytesIO(b"dummy content"), '', 400),
    ('', '*.json', 400),
])
@patch('routes.extractions')
def test_extractions_endpoint_empty_data(mock_extractions, client, archive, pattern, responsecode):
    mock_extractions.return_value = '123'
    response = client.post(
        '/extractions',
        data={
            'archive': archive,
            'pattern': pattern
        },
        content_type='multipart/form-data'
    )
    assert response.status_code == responsecode
    assert "Invalid archive or pattern" in response.get_json()["error"]


@pytest.mark.parametrize("ExceptionType, expected_status, expected_error", [
    (FileHandlingError, 500, "Failed to process extraction request"),
    (DatabaseError, 500, "Failed to process extraction request"),
    (RuntimeError, 500, "Failed to process extraction request"),
    (Exception, 500, "Internal server error"),
])
@patch('routes.extractions')
def test_extractions_endpoint_exception(mock_extractions, client, ExceptionType, expected_status, expected_error):
    mock_extractions.side_effect = ExceptionType("Test exception")

    response = client.post(
        '/extractions',
        data={
            'archive': (io.BytesIO(b"dummy content"), 'test.zip'),
            'pattern': '*.json'
        },
        content_type='multipart/form-data'
    )

    assert response.status_code == expected_status
    assert expected_error in response.get_json()["error"]