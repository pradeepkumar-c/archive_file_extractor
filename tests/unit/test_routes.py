import pytest
from unittest.mock import patch, MagicMock
from routes import app
from flask import app, request

def test_health():
    response = request.args.get('/health')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}

@patch('service.getjob')
def test_getjob_endpoint_ok(mock_getjob):
    mock_getjob.return_value = {'jobid': '123', 'status': 'completed'}
    response = request.args.get('/extractions/123')
    assert response.status_code == 200
    assert response.get_json() == {'jobid': '123', 'status': 'completed'}