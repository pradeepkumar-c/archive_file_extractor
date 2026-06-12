import pytest
from unittest.mock import patch, MagicMock
from app import app, init_db, shutdown_session, start_app

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

@patch('app.db.create_all')
def test_init_db_ok(mock_create_all, client):
    init_db()
    mock_create_all.assert_called_once()

@patch('app.db.create_all')
def test_init_db_error(mock_create_all, client):
    mock_create_all.side_effect = Exception("Database error")
    init_db()
    mock_create_all.assert_called_once()

@patch('app.db.session.remove')
def test_app_context_teardown(mock_remove, client):
    shutdown_session()
    mock_remove.assert_called_once()

@patch('app.init_db')
@patch('app.Thread')
@patch('app.app.run')
def test_start_app(mock_run, mock_thread, mock_init_db, client):
    start_app()
    mock_init_db.assert_called_once()
    mock_thread.assert_called_once()
    mock_run.assert_called_once_with(host='0.0.0.0', port=8080)