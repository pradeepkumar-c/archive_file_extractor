
from threading import Thread
from app_factory import create_app
from extensions import db
from service import job_dispatcher
from routes import bp

app = create_app()

def init_db():
    print("Initializing database connection")
    try:
        with app.app_context():
            db.create_all()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")


@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

if __name__ == '__main__':
    print("Starting Flask app and job dispatcher...")

    init_db()

    dispatcher = Thread(target=job_dispatcher, args=(app,), daemon=True)
    dispatcher.start()

    app.run(host='0.0.0.0', port=8090)
