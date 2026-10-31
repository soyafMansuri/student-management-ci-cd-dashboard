"""Gunicorn entry point for the student application: gunicorn wsgi:app"""
from app import create_app

app = create_app()
