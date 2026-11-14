"""
MediGuard AI – Pytest Configuration & Test Fixtures
"""
import pytest
from backend.app import create_app
from backend.config import TestConfig
from backend.db.seed import seed_all
from backend.services.db_service import db_service
from backend.services.auth_service import AuthService


@pytest.fixture(scope="session")
def app():
    """Create and configure a Flask application for testing."""
    test_app = create_app(TestConfig)
    with test_app.app_context():
        seed_all()
        yield test_app


@pytest.fixture(scope="function")
def client(app):
    """Test HTTP client."""
    return app.test_client()


@pytest.fixture
def admin_token(app):
    with app.app_context():
        user = db_service.get_user_by_email("admin@mediguard.local")
        return AuthService.generate_token(user)


@pytest.fixture
def staff_token(app):
    with app.app_context():
        user = db_service.get_user_by_email("staff1@mediguard.local")
        return AuthService.generate_token(user)


@pytest.fixture
def cardio_token(app):
    with app.app_context():
        user = db_service.get_user_by_email("cardio1@mediguard.local")
        return AuthService.generate_token(user)
