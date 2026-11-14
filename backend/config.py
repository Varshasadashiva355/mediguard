"""
MediGuard AI – Application Configuration
Handles environment variables, Supabase connection details, JWT security, and CORS.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "mediguard-super-secret-dev-key-change-in-prod-8923489")
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
    TESTING = False

    # CORS origins
    cors_raw = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000,http://localhost:3000,http://127.0.0.1:5500")
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

    # JWT Settings
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mediguard-jwt-secret-dev-key-784391208943")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "12"))

    # Rate Limiting (login max attempts per window)
    LOGIN_RATE_LIMIT_MAX = int(os.getenv("LOGIN_RATE_LIMIT_MAX", "10"))
    LOGIN_RATE_LIMIT_WINDOW_SECS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECS", "60"))

    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
    SUPABASE_ECG_BUCKET = os.getenv("SUPABASE_ECG_BUCKET", "ecg-files")

    # Offline / Test Demo Mode
    # If True or if Supabase is unreachable/not configured, runs with local in-memory/seed demo storage
    OFFLINE_DEMO_MODE = os.getenv("OFFLINE_DEMO_MODE", "true").lower() in ("true", "1", "yes")

    # Hospital Emergency Contact Configurations
    HOSPITAL_EMERGENCY_CODE_BLUE_EXT = os.getenv("HOSPITAL_EMERGENCY_CODE_BLUE_EXT", "2222")
    HOSPITAL_CARDIAC_CATH_LAB_EXT = os.getenv("HOSPITAL_CARDIAC_CATH_LAB_EXT", "4400")
    HOSPITAL_ICU_TRIAGE_EXT = os.getenv("HOSPITAL_ICU_TRIAGE_EXT", "3300")


class TestConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = False
    OFFLINE_DEMO_MODE = True
    JWT_EXPIRATION_HOURS = 1
    LOGIN_RATE_LIMIT_MAX = 50
    LOGIN_RATE_LIMIT_WINDOW_SECS = 60
