import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-which-is-long-enough-1234567890")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-value")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://mailapp:mailapp@localhost:5432/mailapp")
os.environ.setdefault("DATABASE_SYNC_URL", "postgresql://mailapp:mailapp@localhost:5432/mailapp")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
