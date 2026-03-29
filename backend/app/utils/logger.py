"""
Protokollierungskonfigurationsmodul
Bietet einheitliche Protokollverwaltung mit Ausgabe an Konsole und Datei
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler


def _ensure_utf8_stdout():
    """
    Sicherstellen, dass stdout/stderr UTF-8-Kodierung verwenden
    Behebt Zeichenkodierungsprobleme in der Windows-Konsole
    """
    if sys.platform == 'win32':
        # Unter Windows Standardausgabe auf UTF-8 umkonfigurieren
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Protokollverzeichnis
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(name: str = 'mirofish', level: int = logging.DEBUG) -> logging.Logger:
    """
    Logger einrichten

    Args:
        name: Logger-Name
        level: Protokollierungsstufe

    Returns:
        Konfigurierter Logger
    """
    # Sicherstellen, dass das Protokollverzeichnis existiert
    os.makedirs(LOG_DIR, exist_ok=True)

    # Logger erstellen
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Protokollweitergabe an Root-Logger verhindern, um doppelte Ausgabe zu vermeiden
    logger.propagate = False

    # Wenn bereits Handler vorhanden sind, nicht erneut hinzufuegen
    if logger.handlers:
        return logger

    # Protokollformat
    detailed_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    # 1. Datei-Handler - Detailliertes Protokoll (nach Datum benannt, mit Rotation)
    log_filename = datetime.now().strftime('%Y-%m-%d') + '.log'
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # 2. Konsolen-Handler - Kompaktes Protokoll (INFO und hoeher)
    # Sicherstellen, dass unter Windows UTF-8-Kodierung verwendet wird
    _ensure_utf8_stdout()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # Handler hinzufuegen
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = 'mirofish') -> logging.Logger:
    """
    Logger abrufen (erstellt einen neuen, falls nicht vorhanden)

    Args:
        name: Logger-Name

    Returns:
        Logger-Instanz
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# Standard-Logger erstellen
logger = setup_logger()


# Komfortmethoden
def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)
