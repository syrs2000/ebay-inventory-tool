"""
Django settings for config project (eBay 出品/在庫管理ツール).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_apscheduler",
    "core",
    "listings",
    "mercari_link",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- eBay API settings ------------------------------------------------
EBAY_ENV = os.getenv("EBAY_ENV", "sandbox")  # "sandbox" or "production"
EBAY_APP_ID = os.getenv("EBAY_APP_ID", "")
EBAY_DEV_ID = os.getenv("EBAY_DEV_ID", "")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID", "")
EBAY_AUTH_TOKEN = os.getenv("EBAY_AUTH_TOKEN", "")  # User (OAuth) token for Trading API
EBAY_SITE_ID = os.getenv("EBAY_SITE_ID", "0")  # 0 = US
EBAY_TRADING_API_VERSION = os.getenv("EBAY_TRADING_API_VERSION", "1193")

EBAY_TRADING_API_URL = (
    "https://api.sandbox.ebay.com/ws/api.dll"
    if EBAY_ENV == "sandbox"
    else "https://api.ebay.com/ws/api.dll"
)

# --- Mercari / auto-delist settings -----------------------------------
MERCARI_CHECK_INTERVAL_MINUTES = int(os.getenv("MERCARI_CHECK_INTERVAL_MINUTES", "30"))
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "1") == "1"

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "app.log",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
