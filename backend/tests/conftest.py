import os
import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("DATABASE_URL must be set to a PostgreSQL URI for tests.", allow_module_level=True)

from backend.app import create_app, init_db  # noqa: E402
from backend.db.session import engine  # noqa: E402
from backend.models import Base  # noqa: E402


@pytest.fixture()
def client():
    app = create_app()
    with app.app_context():
        Base.metadata.drop_all(bind=engine)
        init_db()
    with app.test_client() as client:
        yield client
    with app.app_context():
        Base.metadata.drop_all(bind=engine)
