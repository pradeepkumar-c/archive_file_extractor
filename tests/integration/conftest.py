import pytest
from testcontainers.postgres import PostgresContainer
from flask import Flask
from extensions import db
from routes import bp
from threading import Thread
from service import job_dispatcher


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def test_app(postgres_container):
    # Build a fresh Flask app for tests so we can initialize DB with testcontainer URI
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = postgres_container.get_connection_url()
    app.config["TESTING"] = True

    # Register routes blueprint
    app.register_blueprint(bp)

    # Initialize DB with this app and create tables
    db.init_app(app)

    with app.app_context():
        db.create_all()

        # start job dispatcher in background for integration tests
        dispatcher = Thread(target=job_dispatcher, args=(app,), daemon=True)
        dispatcher.start()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()
