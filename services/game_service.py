"""
services/game_service.py

Lógica relacionada con la partida en sí: inicio de partida, generación
del texto de cada ronda, validación autoritativa (del lado del
servidor) de la finalización de cada jugador para ambos modos de
juego, el paso "todos listos -> siguiente ronda", el manejo de
desconexiones a mitad de ronda, y el cálculo del ranking final
(con desempate) y su detalle ronda por ronda.
"""

from datetime import datetime, timezone

from firebase_admin import firestore as fb_firestore

from services.firebase import get_db
from services.room_service import (
    RoomError,
    ROOMS_COLLECTION,
    PLAYERS_SUBCOLLECTION,
    get_room,
    get_player,
    get_players,
    is_host,
)
from utils.phrase_generator import generate_text
from utils.text_validator import normalize_for_comparison

ROUNDS_SUBCOLLECTION = "rounds"


def start_game(room_code: str, player_id: str) -> dict:
    """
    Marca la sala como "playing" y prepara el contador de rondas.
    Solo el anfitrión puede iniciar la partida.
    """
    if not is_host(room_code, player_id):
        raise RoomError("Solo el anfitrión puede iniciar la partida.")

    room = get_room(room_code)
    if room is None:
        raise RoomError("La sala no existe.")
    if room.get("status") == "playing":
        raise RoomError("La partida ya está en curso.")
    if room.get("status") == "finished":
        raise RoomError("Esta sala ya terminó su partida.")

    db = get_db()
    db.collection(ROOMS_COLLECTION).document(room_code).update(
        {"status": "playing", "current_round": 0}
    )
    return room["settings"]


def _get_used_texts(room_code: str) -> list:
    db = get_db()
    rounds_ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(ROUNDS_SUBCOLLECTION)
    )
    docs = rounds_ref.stream()
    return [d.to_dict().get("text", "") for d in docs]


def start_next_round(room_code: str) -> dict:
    """
    Genera el texto de la siguiente ronda según la configuración de la
    sala y guarda un documento de ronda en Firestore.

    Devuelve un diccionario con la información de la ronda que el
    servidor enviará a todos los jugadores vía Socket.IO.
    """
    room = get_room(room_code)
    if room is None:
        raise RoomError("La sala no existe.")

    settings = room.get("settings", {})
    current_round = room.get("current_round", 0) + 1

    used_texts = _get_used_texts(room_code)

    text = generate_text(
        length=settings.get("length", "medium"),
        accents_required=settings.get("accents_required", True),
        use_enye=settings.get("use_enye", True),
        forbidden_texts=used_texts,
    )

    now = datetime.now(timezone.utc)

    db = get_db()
    room_ref = db.collection(ROOMS_COLLECTION).document(room_code)
    room_ref.update({"current_round": current_round})

    round_id = f"round_{current_round}"
    room_ref.collection(ROUNDS_SUBCOLLECTION).document(round_id).set(
        {
            "round_number": current_round,
            "text": text,
            "mode": settings.get("mode", "all_finish"),
            "accents_required": settings.get("accents_required", True),
            "started_at": now,
            "finished": False,
            "results": {},  # player_id -> {time_seconds, order}
        }
    )

    return {
        "round_number": current_round,
        "total_rounds": settings.get("rounds", 5),
        "text": text,
        "mode": settings.get("mode", "all_finish"),
        "accents_required": settings.get("accents_required", True),
    }


def get_current_round_number(room_code: str) -> int:
    room = get_room(room_code)
    if room is None:
        return 0
    return room.get("current_round", 0)


def is_last_round(room_code: str) -> bool:
    room = get_room(room_code)
    if room is None:
        return True
    settings = room.get("settings", {})
    return room.get("current_round", 0) >= settings.get("rounds", 5)


def finish_game(room_code: str):
    """Marca la sala como finalizada (el ranking se calcula en
    get_final_scoreboard, a partir del puntaje y el tiempo acumulado
    de cada jugador)."""
    db = get_db()
    db.collection(ROOMS_COLLECTION).document(room_code).update(
        {
            "status": "finished",
            "finished_at": datetime.now(timezone.utc),
        }
    )


# ---------------------------------------------------------------------------
# Finalización de un jugador (autoridad del servidor)
# ---------------------------------------------------------------------------

def _round_ref(room_code: str, round_number: int):
    db = get_db()
    return (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(ROUNDS_SUBCOLLECTION)
        .document(f"round_{round_number}")
    )


def _connected_player_ids(room_code: str) -> set:
    return {p["id"] for p in get_players(room_code) if p.get("connected")}


def _increment_player_score(room_code: str, player_id: str, amount: int):
    db = get_db()
    player_ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(PLAYERS_SUBCOLLECTION)
        .document(player_id)
    )
    player_ref.update({"score": fb_firestore.Increment(amount)})


def submit_player_finish(
    room_code: str, player_id: str, round_number: int, typed_text: str
) -> dict:
    """
    Autoridad del servidor sobre la finalización de una ronda.

    Nunca se confía en que el navegador declare "terminé" o "gané":
    el servidor recalcula todo lo importante a partir de su propio
    estado (texto de la ronda, marca de tiempo de inicio, jugadores
    conectados) y solo entonces decide si la finalización es válida,
    quién quedó primero y si la ronda se cierra.

    Devuelve un diccionario con el resultado de la operación. Nunca
    lanza RoomError por un simple "todavía no terminaste" o "ya había
    terminado esta ronda": eso se refleja como {"accepted": False, ...}
    para que el llamador decida cómo informarlo al jugador.
    """
    room = get_room(room_code)
    if room is None:
        raise RoomError("La sala no existe.")
    if room.get("status") != "playing":
        raise RoomError("La partida no está en curso.")
    if room.get("current_round") != round_number:
        raise RoomError("Esa ronda ya no está activa.")

    player = get_player(room_code, player_id)
    if player is None:
        raise RoomError("No perteneces a esta sala.")

    round_ref = _round_ref(room_code, round_number)
    db = get_db()
    accents_required = room.get("settings", {}).get("accents_required", True)

    @fb_firestore.transactional
    def _txn(transaction):
        snapshot = round_ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"accepted": False, "reason": "round_not_found"}

        data = snapshot.to_dict()

        if data.get("finished"):
            return {"accepted": False, "reason": "round_already_finished"}

        results = dict(data.get("results", {}))
        if player_id in results:
            return {"accepted": False, "reason": "already_finished"}

        expected_text = data.get("text", "")
        normalized_expected = normalize_for_comparison(expected_text, accents_required)
        normalized_typed = normalize_for_comparison(typed_text or "", accents_required)

        if normalized_typed != normalized_expected:
            return {"accepted": False, "reason": "text_mismatch"}

        started_at = data.get("started_at")
        now = datetime.now(timezone.utc)
        elapsed = (now - started_at).total_seconds() if started_at else None

        mode = data.get("mode", "all_finish")
        order = len(results) + 1
        is_first = order == 1

        results[player_id] = {"time_seconds": elapsed, "order": order}

        update = {"results": results}
        round_finished_now = False
        winner_id = None

        if mode == "first_wins":
            update["finished"] = True
            round_finished_now = True
            winner_id = player_id
        else:
            active_ids = _connected_player_ids(room_code)
            if active_ids and active_ids.issubset(set(results.keys())):
                update["finished"] = True
                round_finished_now = True

        transaction.update(round_ref, update)

        return {
            "accepted": True,
            "order": order,
            "is_first": is_first,
            "elapsed": elapsed,
            "mode": mode,
            "round_finished": round_finished_now,
            "winner_id": winner_id,
            "results": results,
        }

    outcome = _txn(db.transaction())

    if outcome.get("accepted") and outcome.get("is_first"):
        # El primero en terminar recibe +1 punto, en ambos modos.
        _increment_player_score(room_code, player_id, 1)

    return outcome


def build_round_results_payload(room_code: str, outcome: dict) -> dict:
    """
    Construye el payload que se envía a toda la sala cuando una ronda
    se cierra: combina los resultados guardados en la ronda con los
    nombres y la puntuación (ya actualizada) de cada jugador.
    """
    players_by_id = {p["id"]: p for p in get_players(room_code)}
    results = outcome.get("results", {})

    entries = []
    for pid, res in results.items():
        player = players_by_id.get(pid, {})
        entries.append(
            {
                "player_id": pid,
                "player_name": player.get("name", "Jugador"),
                "time_seconds": res.get("time_seconds"),
                "order": res.get("order"),
                "score": player.get("score", 0),
            }
        )

    entries.sort(key=lambda e: (e["order"] is None, e["order"]))

    return {
        "mode": outcome.get("mode"),
        "winner_id": outcome.get("winner_id"),
        "results": entries,
    }


# ---------------------------------------------------------------------------
# "Continuar ronda": todos los jugadores activos deben confirmar que
# están listos antes de que el servidor prepare la siguiente ronda.
# ---------------------------------------------------------------------------

def mark_player_ready(room_code: str, player_id: str, round_number: int) -> dict:
    """
    Registra que `player_id` pulsó "Continuar ronda" para `round_number`.

    Usa una transacción para poder distinguir, de forma segura ante
    varios clientes pulsando casi al mismo tiempo, cuál es la llamada
    que realmente hace que TODOS los jugadores activos ya estén listos
    (esa llamada es la única que debe disparar la siguiente ronda).
    """
    room = get_room(room_code)
    if room is None:
        raise RoomError("La sala no existe.")

    player = get_player(room_code, player_id)
    if player is None:
        raise RoomError("No perteneces a esta sala.")

    round_ref = _round_ref(room_code, round_number)
    db = get_db()

    @fb_firestore.transactional
    def _txn(transaction):
        snapshot = round_ref.get(transaction=transaction)
        if not snapshot.exists:
            return {"all_ready": False, "ready_ids": [], "triggered": False}

        data = snapshot.to_dict()
        ready_ids = set(data.get("ready_players", []))
        ready_ids.add(player_id)

        active_ids = _connected_player_ids(room_code)
        already_triggered = bool(data.get("advance_triggered", False))
        all_ready = bool(active_ids) and active_ids.issubset(ready_ids)

        update = {"ready_players": list(ready_ids)}
        triggered_now = False
        if all_ready and not already_triggered:
            update["advance_triggered"] = True
            triggered_now = True

        transaction.update(round_ref, update)

        return {
            "all_ready": all_ready,
            "ready_ids": list(ready_ids),
            "triggered": triggered_now,
        }

    return _txn(db.transaction())


def build_ready_status_payload(room_code: str, ready_ids) -> dict:
    """
    Construye el payload de "quién está listo" para la pantalla de
    resultados de ronda. Solo se muestran los jugadores activos: un
    jugador desconectado nunca debe aparecer bloqueando la lista.
    """
    ready_set = set(ready_ids or [])
    players = [p for p in get_players(room_code) if p.get("connected")]

    entries = [
        {
            "player_id": p["id"],
            "player_name": p.get("name", "Jugador"),
            "ready": p["id"] in ready_set,
        }
        for p in players
    ]

    return {"players": entries}


def get_current_ready_status(room_code: str):
    """
    Devuelve el payload de "quién está listo" para la ronda actual, o
    None si la ronda todavía está en curso (no aplica) o no existe.
    Se usa para refrescar la lista tras una desconexión que por sí sola
    no alcanza a destrabar "Continuar ronda", pero sí cambia quién
    cuenta como jugador activo.
    """
    room = get_room(room_code)
    if room is None:
        return None

    round_number = room.get("current_round", 0)
    if round_number == 0:
        return None

    doc = _round_ref(room_code, round_number).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    if not data.get("finished"):
        return None

    return build_ready_status_payload(room_code, data.get("ready_players", []))


def handle_player_disconnect_game_state(room_code: str, player_id: str):
    """
    Comprueba si la desconexión de `player_id` (que ya fue marcado como
    desconectado en services.room_service) hace que algo deba avanzar:

    - si la ronda actual seguía en curso y, sin este jugador, todos los
      jugadores activos restantes ya habían terminado -> cierra la
      ronda y devuelve su resultado;
    - si la ronda ya había terminado y estábamos esperando "Continuar
      ronda" -> si el resto ya estaba listo, marca que se debe avanzar.

    Devuelve None si no hay nada que hacer (por ejemplo, la partida no
    está en curso, o siguen faltando jugadores activos).
    """
    room = get_room(room_code)
    if room is None or room.get("status") != "playing":
        return None

    round_number = room.get("current_round", 0)
    if round_number == 0:
        return None

    round_ref = _round_ref(room_code, round_number)
    db = get_db()

    doc = round_ref.get()
    if not doc.exists:
        return None
    data = doc.to_dict()

    if not data.get("finished"):
        active_ids = _connected_player_ids(room_code)
        results = data.get("results", {})
        if not active_ids or not active_ids.issubset(set(results.keys())):
            return None

        @fb_firestore.transactional
        def _close_txn(transaction):
            snapshot = round_ref.get(transaction=transaction)
            d = snapshot.to_dict()
            if d.get("finished"):
                return None
            transaction.update(round_ref, {"finished": True})
            return d.get("results", {})

        results_after = _close_txn(db.transaction())
        if results_after is None:
            return None

        outcome = {
            "mode": data.get("mode"),
            "winner_id": None,
            "results": results_after,
        }
        payload = build_round_results_payload(room_code, outcome)
        return {"type": "round_finished", "payload": payload}

    # La ronda ya había terminado: estamos en la fase de "Continuar ronda".
    if data.get("advance_triggered"):
        return None

    ready_ids = set(data.get("ready_players", []))
    active_ids = _connected_player_ids(room_code)
    if not active_ids or not active_ids.issubset(ready_ids):
        return None

    @fb_firestore.transactional
    def _advance_txn(transaction):
        snapshot = round_ref.get(transaction=transaction)
        d = snapshot.to_dict()
        if d.get("advance_triggered"):
            return False
        transaction.update(round_ref, {"advance_triggered": True})
        return True

    if _advance_txn(db.transaction()):
        return {"type": "advance_round"}
    return None


# ---------------------------------------------------------------------------
# Ranking final (con desempate) y detalle ronda por ronda
# ---------------------------------------------------------------------------

def _get_total_times_by_player(room_code: str) -> dict:
    """Suma, por jugador, el tiempo en las rondas en las que participó."""
    db = get_db()
    rounds_ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(ROUNDS_SUBCOLLECTION)
    )

    totals = {}
    for doc in rounds_ref.stream():
        data = doc.to_dict()
        for pid, res in (data.get("results") or {}).items():
            time_seconds = res.get("time_seconds")
            if time_seconds is not None:
                totals[pid] = totals.get(pid, 0.0) + time_seconds
    return totals


def get_final_scoreboard(room_code: str) -> list:
    """
    Ranking final: ordenado por puntos (mayor a menor) y, en caso de
    empate, por menor tiempo acumulado en las rondas donde participó
    cada jugador (segundo criterio de desempate).
    """
    players = get_players(room_code)
    total_times = _get_total_times_by_player(room_code)

    for p in players:
        p["total_time"] = total_times.get(p["id"], 0.0)

    players.sort(key=lambda p: (-p.get("score", 0), p.get("total_time", 0.0)))
    return players


def get_round_by_round_details(room_code: str) -> list:
    """
    Devuelve, para cada ronda ya jugada (en orden), la lista de
    resultados de esa ronda: jugador, tiempo, puntos obtenidos. Se usa
    en la pantalla "Ver detalles" del ranking final.
    """
    db = get_db()
    rounds_ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_code)
        .collection(ROUNDS_SUBCOLLECTION)
    )
    players_by_id = {p["id"]: p for p in get_players(room_code)}

    docs = list(rounds_ref.stream())
    docs.sort(key=lambda d: d.to_dict().get("round_number", 0))

    rounds = []
    for doc in docs:
        data = doc.to_dict()
        results = data.get("results") or {}

        entries = []
        for pid, res in results.items():
            player = players_by_id.get(pid, {})
            entries.append(
                {
                    "player_id": pid,
                    "player_name": player.get("name", "Jugador"),
                    "time_seconds": res.get("time_seconds"),
                    "order": res.get("order"),
                    "points": 1 if res.get("order") == 1 else 0,
                }
            )
        entries.sort(key=lambda e: (e["order"] is None, e["order"]))

        rounds.append({"round_number": data.get("round_number"), "results": entries})

    return rounds
