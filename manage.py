#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # INFO ve WARNING ve ERROR'u bastırır
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'  # oneDNN custom ops kapatılırsa bazı uyarılar gitmiş olur
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='tensorflow')

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hexense_platform.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
