"""Vercel serverless entry point: exposes the signup FastAPI app as `app`."""

from signup_api.app import create_app_from_env

app = create_app_from_env()
