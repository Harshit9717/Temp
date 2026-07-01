import os

class Config:
    SECRET_KEY = "placementportal_secret_key_2024"
    SQLALCHEMY_DATABASE_URI = "sqlite:///placement.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Redis config
    REDIS_URL = "redis://localhost:6379/0"

    # Cache config
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = "redis://localhost:6379/0"
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes

    # Mail config (update with your credentials)
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = "your_email@gmail.com"
    MAIL_PASSWORD = "your_app_password"
    MAIL_DEFAULT_SENDER = "your_email@gmail.com"
    ADMIN_EMAIL = "admin@gmail.com"

    # Celery config
    CELERY_BROKER_URL = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND = "redis://localhost:6379/0"