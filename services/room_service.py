"""
services/room_service.py

Toda la lógica relacionada con salas:
- generación de códigos únicos
- creación de salas
- unión de jugadores
- gestión del anfitrión
- configuración de partida

El servidor es siempre la autoridad: el código de sala se genera aquí,
nunca se confía en un código enviado por el navegador para "crear" nada.
"""

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from config import Config
from services.firebase import get_db

ROOMS_COLLECTION = "rooms"
PLAYERS_SUBCOLLECTION = "players"

# Solo letras/números/espacios/algunos signos básicos. Nada de HTML ni scripts.
_NAME_SANITIZE_RE = re.compile(r"[^\w\sÁÉÍÓÚÑáéíóúñ\-]", re.UNICODE)


class RoomError(Exception):
    """Error de negocio relacionado con salas (código inválido, sala llena, etc.)."""


# ---------------------------------------------------------------------------
# Utilidades de validación / sanitización
# ---------------------------------------------------------------------------

def sanitize_player_name(raw_name: str) -> str:
    """
    Limpia y valida el nombre de un jugador.
    Nunca se debe confiar en la validación hecha en el navegador.
    """
    if raw_name is None:
        raise RoomError("El nombre no puede estar vacío.")

    name = raw_name.strip()
    name = _NAME_SANITIZE_RE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()

    if len(name) < Config.MIN_PLAYER_NAME_LENGTH:
        raise RoomError("El nombre no puede estar vacío.")

    if len(name) > Config.MAX_PLAYER_NAME_LENGTH:
        name = name[: Config.MAX_PLAYER_NAME_LENGTH]

    return name


def _normalize_room_code(raw_code: str) -> str:
    if raw_code is None:
        raise RoomError("El código de sala no es válido.")
    return raw_code.strip().upper()


# ---------------------------------------------------------------------------
# Generación de código de sala
# ---------------------------------------------------------------------------

def _generate_candidate_code() -> str:
    alphabet = Config.ROOM_CODE_ALPHABET
    return "".join(secrets.choice(alphabet) for _ in range(Config.ROOM_CODE_LENGTH))


def generate_unique_room_code() -> str:
    """
    Genera un código de sala que no esté actualmente en uso.
    El servidor es quien decide el código; nunca se acepta uno del cliente.
    """
    db = get_db()
    rooms_ref = db.collection(ROOMS_COLLECTION)

    for _ in range(20):  # límite razonable de intentos
        code = _generate_candidate_code()
        doc = rooms_ref.document(code).get()
        if not doc.exists:
            return code

    # Extremadamente improbable, pero por seguridad ampliamos el espacio.
    raise RoomError("No se pudo generar un código de sala único. Inténtalo de nuevo.")


# ---------------------------------------------------------------------------
# Creación / consulta de salas
# ---------------------------------------------------------------------------

def default_settings() -> dict:
    return {
        "rounds": Config.DEFAULT_ROUNDS,
        "mode": "all_finish",  # "all_finish" | "first_wins"
        "length": "medium",  # "short" | "medium" | "long"
        "accents_required": True,
        "use_enye": True,
    }


def create_room(host_name_raw: str) -> dict:
    """
    Crea una sala nueva con el jugador que la crea como anfitrión.
    Devuelve un diccionario con room_code y player_id.
    """
    name = sanitize_player_name(host_name_raw)
    db = get_db()

    try:
        cleanup_old_rooms()
    except Exception as exc:  # nunca debe romper la creación de la sala
        print(f"[TecleaYa] Aviso: no se pudo limpiar salas antiguas: {exc}")

    room_code = generate_unique_room_code()
    player_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)
    room_ref.set(
        {
            "code": room_code,
            "host_id": player_id,
            "status": "lobby",  # lobby | playing | finished
            "settings": default_settings(),
            "current_round": 0,
            "created_at": now,
        }
    )

    room_ref.collection(PLAYERS_SUBCOLLECTION).document(player_id).set(
        {
            "id": player_id,
            "name": name,
            "is_host": True,
            "sid": None,
            "connected": False,
            "score": 0,
            "joined_at": now,
        }
    )

    return {"room_code": room_code, "player_id": player_id, "name": name}


def get_room(room_code_raw: str):
    """Devuelve el documento de la sala (dict) o None si no existe."""
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    doc = db.collection(ROOMS_COLLECTION).document(room_code).get()
    if not doc.exists:
        return None
    return doc.to_dict()


def room_exists(room_code_raw: str) -> bool:
    return get_room(room_code_raw) is not None


def get_players(room_code_raw: str) -> list:
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    players_ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(PLAYERS_SUBCOLLECTION)
    )
    docs = players_ref.stream()
    players = [d.to_dict() for d in docs]
    players.sort(key=lambda p: p.get("joined_at") or 0)
    return players


def join_room_service(room_code_raw: str, player_name_raw: str) -> dict:
    """
    Une a un jugador a una sala existente.
    Lanza RoomError si la sala no existe, ya está en juego, o está llena.
    """
    room_code = _normalize_room_code(room_code_raw)
    name = sanitize_player_name(player_name_raw)

    db = get_db()
    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)
    room_doc = room_ref.get()

    if not room_doc.exists:
        raise RoomError("La sala no existe. Revisa el código e inténtalo de nuevo.")

    room_data = room_doc.to_dict()

    if room_data.get("status") != "lobby":
        raise RoomError("Esta sala ya está en juego y no admite nuevos jugadores.")

    players_ref = room_ref.collection(PLAYERS_SUBCOLLECTION)
    existing_players = [d.to_dict() for d in players_ref.stream()]

    if len(existing_players) >= Config.MAX_PLAYERS_PER_ROOM:
        raise RoomError("La sala está llena.")

    player_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    players_ref.document(player_id).set(
        {
            "id": player_id,
            "name": name,
            "is_host": False,
            "sid": None,
            "connected": False,
            "score": 0,
            "joined_at": now,
        }
    )

    return {"room_code": room_code, "player_id": player_id, "name": name}


def get_player(room_code_raw: str, player_id: str):
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    doc = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(PLAYERS_SUBCOLLECTION)
        .document(player_id)
        .get()
    )
    if not doc.exists:
        return None
    return doc.to_dict()


def is_host(room_code_raw: str, player_id: str) -> bool:
    room = get_room(room_code_raw)
    if room is None:
        return False
    return room.get("host_id") == player_id


# ---------------------------------------------------------------------------
# Conexión / desconexión de jugadores (usado por los eventos de socket)
# ---------------------------------------------------------------------------

def set_player_socket(room_code_raw: str, player_id: str, sid: str, connected: bool):
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    player_ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(PLAYERS_SUBCOLLECTION)
        .document(player_id)
    )
    player_ref.update({"sid": sid, "connected": connected})


def remove_player(room_code_raw: str, player_id: str):
    """
    Elimina a un jugador de la sala. Si era el anfitrión, reasigna el
    rol al jugador conectado más antiguo restante (si existe alguno).
    """
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)
    players_ref = room_ref.collection(PLAYERS_SUBCOLLECTION)

    players_ref.document(player_id).delete()

    room_doc = room_ref.get()
    if not room_doc.exists:
        return None

    room_data = room_doc.to_dict()
    new_host_id = None

    if room_data.get("host_id") == player_id:
        remaining = [d.to_dict() for d in players_ref.stream()]
        remaining.sort(key=lambda p: p.get("joined_at") or 0)
        if remaining:
            new_host = remaining[0]
            new_host_id = new_host["id"]
            players_ref.document(new_host_id).update({"is_host": True})
            room_ref.update({"host_id": new_host_id})

    return new_host_id


def disconnect_player(room_code_raw: str, player_id: str):
    """
    Marca a un jugador como desconectado SIN eliminarlo de la sala.

    Se usa cuando la sala ya está en partida (o terminada): a diferencia
    del lobby, aquí no se puede simplemente borrar al jugador, porque
    perdería su puntaje y su historial de rondas, y porque una ronda o
    el botón "Continuar ronda" no deben quedar esperando para siempre a
    alguien que ya no va a volver.

    Si el jugador desconectado era el anfitrión, el rol se reasigna al
    jugador conectado más antiguo restante (si existe alguno); si no
    queda nadie conectado, el anfitrión original conserva el rol hasta
    que alguien vuelva a estar disponible.

    Devuelve el id del nuevo anfitrión si hubo reasignación, o None.
    """
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)
    players_ref = room_ref.collection(PLAYERS_SUBCOLLECTION)

    players_ref.document(player_id).update({"sid": None, "connected": False})

    room_doc = room_ref.get()
    if not room_doc.exists:
        return None

    room_data = room_doc.to_dict()
    new_host_id = None

    if room_data.get("host_id") == player_id:
        remaining = [d.to_dict() for d in players_ref.stream()]
        connected_others = [
            p for p in remaining if p.get("connected") and p["id"] != player_id
        ]
        connected_others.sort(key=lambda p: p.get("joined_at") or 0)
        if connected_others:
            new_host = connected_others[0]
            new_host_id = new_host["id"]
            players_ref.document(player_id).update({"is_host": False})
            players_ref.document(new_host_id).update({"is_host": True})
            room_ref.update({"host_id": new_host_id})

    return new_host_id


def delete_room_if_empty(room_code_raw: str) -> bool:
    """Borra la sala si ya no quedan jugadores. Devuelve True si se borró."""
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)
    players_ref = room_ref.collection(PLAYERS_SUBCOLLECTION)

    remaining = list(players_ref.stream())
    if not remaining:
        room_ref.delete()
        return True
    return False


def delete_room_completely(room_code_raw: str) -> None:
    """
    Borra una sala por completo de Firestore: todos sus jugadores, todas
    sus rondas y finalmente el documento de la sala. A diferencia de
    delete_room_if_empty(), esto se usa para salas que YA terminaron (o
    quedaron abandonadas) y cuyos datos ya no hace falta conservar.
    """
    room_code = _normalize_room_code(room_code_raw)
    db = get_db()
    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)

    for sub_name in (PLAYERS_SUBCOLLECTION, "rounds"):
        _delete_all_docs(room_ref.collection(sub_name))

    room_ref.delete()


def _delete_all_docs(collection_ref, batch_size: int = 100) -> None:
    """Borra todos los documentos de una subcolección, en lotes."""
    while True:
        docs = list(collection_ref.limit(batch_size).stream())
        if not docs:
            return
        for doc in docs:
            doc.reference.delete()
        if len(docs) < batch_size:
            return


def cleanup_old_rooms() -> int:
    """
    Limpieza oportunista de salas viejas, para no acumular datos en
    Firestore para siempre. Se ejecuta cada vez que se crea una sala
    nueva (ver create_room), envuelta en un try/except allí para que
    un fallo aquí nunca le impida a nadie crear su sala.

    Borra:
    - Salas ya "finished" con más de ROOM_FINISHED_RETENTION_HORAS desde
      que terminaron (así el ranking final sigue disponible un rato).
    - Salas "lobby"/"playing" abandonadas (nunca se terminaron ni se
      vaciaron) con más de ROOM_STALE_RETENTION_HOURS desde su creación.

    Devuelve la cantidad de salas eliminadas.
    """
    db = get_db()
    rooms_ref = db.collection(ROOMS_COLLECTION)
    now = datetime.now(timezone.utc)
    deleted = 0

    finished_cutoff = now - timedelta(hours=Config.ROOM_FINISHED_RETENTION_HOURS)
    finished_query = (
        rooms_ref.where("status", "==", "finished")
        .where("finished_at", "<=", finished_cutoff)
        .limit(50)
    )
    for doc in finished_query.stream():
        delete_room_completely(doc.id)
        deleted += 1

    stale_cutoff = now - timedelta(hours=Config.ROOM_STALE_RETENTION_HOURS)
    for status in ("lobby", "playing"):
        stale_query = (
            rooms_ref.where("status", "==", status)
            .where("created_at", "<=", stale_cutoff)
            .limit(50)
        )
        for doc in stale_query.stream():
            delete_room_completely(doc.id)
            deleted += 1

    return deleted


# ---------------------------------------------------------------------------
# Configuración de partida (solo el anfitrión puede modificarla)
# ---------------------------------------------------------------------------

def update_settings(room_code_raw: str, player_id: str, new_settings: dict) -> dict:
    room_code = _normalize_room_code(room_code_raw)

    if not is_host(room_code, player_id):
        raise RoomError("Solo el anfitrión puede cambiar la configuración.")

    rounds = int(new_settings.get("rounds", Config.DEFAULT_ROUNDS))
    rounds = max(Config.MIN_ROUNDS, min(Config.MAX_ROUNDS, rounds))

    mode = new_settings.get("mode", "all_finish")
    if mode not in ("all_finish", "first_wins"):
        mode = "all_finish"

    length = new_settings.get("length", "medium")
    if length not in ("short", "medium", "long"):
        length = "medium"

    accents_required = bool(new_settings.get("accents_required", True))
    use_enye = bool(new_settings.get("use_enye", True))

    settings = {
        "rounds": rounds,
        "mode": mode,
        "length": length,
        "accents_required": accents_required,
        "use_enye": use_enye,
    }

    db = get_db()
    db.collection(ROOMS_COLLECTION).document(room_code).update({"settings": settings})
    return settings
