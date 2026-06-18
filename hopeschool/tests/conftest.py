import pytest
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

def pytest_configure(config):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
