"""
config.py

Configuración central de la aplicación.
Toda la configuración sensible se obtiene de variables de entorno.
Nunca se deben escribir credenciales reales directamente en este archivo.
"""

import os
from dotenv import load_dotenv

# Carga las variables definidas en el archivo .env (solo en desarrollo local)
load_dotenv()


class Config:
    """Configuración general de la aplicación Flask."""

    # Clave secreta usada por Flask para firmar la sesión / cookies.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # Modo debug (nunca debe estar activo en producción).
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # Puerto en el que corre la aplicación en local.
    PORT = int(os.environ.get("PORT", 5000))

    # --- Firebase ---
    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID")
    FIREBASE_PRIVATE_KEY = os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
    FIREBASE_CLIENT_EMAIL = os.environ.get("FIREBASE_CLIENT_EMAIL")

    # --- Reglas del juego (valores por defecto / límites de seguridad) ---
    MAX_PLAYER_NAME_LENGTH = 18
    MIN_PLAYER_NAME_LENGTH = 1

    MAX_ROUNDS = 30
    MIN_ROUNDS = 1
    DEFAULT_ROUNDS = 5

    ROOM_CODE_LENGTH = 6
    MAX_PLAYERS_PER_ROOM = 12

    # Caracteres permitidos para generar códigos de sala.
    # Se evitan caracteres confusos como: 0, O, 1, I, L
    ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    # --- Limpieza de salas antiguas en Firestore ---
    # Para no acumular datos indefinidamente: cuánto tiempo se conserva
    # una sala después de terminar (para que el ranking final siga
    # siendo consultable un rato) y cuánto tiempo se conserva una sala
    # que quedó abandonada sin terminar nunca la partida.
    ROOM_FINISHED_RETENTION_HOURS = int(os.environ.get("ROOM_FINISHED_RETENTION_HOURS", 24))
    ROOM_STALE_RETENTION_HOURS = int(os.environ.get("ROOM_STALE_RETENTION_HOURS", 72))
