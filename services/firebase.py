"""
services/firebase.py

Inicializa Firebase Admin SDK y expone el cliente de Firestore
que utilizará el resto de la aplicación.

Las credenciales se leen SIEMPRE desde variables de entorno
(ver config.py). Nunca se deben escribir credenciales reales
directamente en este archivo ni subirlas a GitHub.
"""

import firebase_admin
from firebase_admin import credentials, firestore

from config import Config

_db = None


def init_firebase():
    """
    Inicializa la app de Firebase (si aún no ha sido inicializada)
    y devuelve el cliente de Firestore.

    Es seguro llamar a esta función varias veces: solo se inicializa
    una vez el SDK, gracias a la comprobación de `firebase_admin._apps`.
    """
    global _db

    if _db is not None:
        return _db

    if not firebase_admin._apps:
        if not all(
            [
                Config.FIREBASE_PROJECT_ID,
                Config.FIREBASE_PRIVATE_KEY,
                Config.FIREBASE_CLIENT_EMAIL,
            ]
        ):
            raise RuntimeError(
                "Faltan variables de entorno de Firebase. "
                "Revisa FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY y "
                "FIREBASE_CLIENT_EMAIL en tu archivo .env"
            )

        cred_dict = {
            "type": "service_account",
            "project_id": Config.FIREBASE_PROJECT_ID,
            "private_key": Config.FIREBASE_PRIVATE_KEY,
            "client_email": Config.FIREBASE_CLIENT_EMAIL,
            "token_uri": "https://oauth2.googleapis.com/token",
        }

        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    return _db


def get_db():
    """
    Devuelve el cliente de Firestore ya inicializado.
    Si todavía no se ha inicializado, lo hace en este momento.
    """
    global _db
    if _db is None:
        return init_firebase()
    return _db
