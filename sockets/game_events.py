"""
sockets/game_events.py

Eventos de Socket.IO relacionados con el desarrollo de la partida:
inicio de partida, cuenta regresiva, arranque de cada ronda,
finalización de cada jugador (con el servidor como autoridad final),
el paso "todos listos -> siguiente ronda" y el cierre de partida.

También expone `handle_disconnect_effects`, que sockets/room_events.py
invoca cuando un jugador se desconecta a mitad de ronda o en la
pantalla de resultados, para que su ausencia nunca bloquee a los demás.

CORRECCIÓN respecto a la primera parte:
Antes, el cliente esperaba en el lobby a recibir "round_start" (que
el servidor solo emite una vez, tras la cuenta regresiva) y solo
entonces redirigía a la pantalla de juego. Como esa redirección tarda
en cargar la página nueva y reconectar el socket, los jugadores
llegaban a /game DESPUÉS de que el servidor ya hubiera emitido el
texto de la ronda, y se quedaban esperando para siempre. Ahora la
redirección ocurre en cuanto se recibe "game_starting" (antes de la
cuenta regresiva), y la cuenta regresiva + "round_start" ocurren ya
con todos los jugadores conectados desde la pantalla de juego.
"""

from flask_socketio import emit
from flask import request

from services import game_service, room_service
from services.room_service import RoomError

# Cuenta regresiva antes de cada ronda, en segundos.
COUNTDOWN_SECONDS = 3

# Mensajes legibles para cada motivo de rechazo de "player_finished".
_REJECTION_MESSAGES = {
    "round_not_found": "Esa ronda ya no existe.",
    "round_already_finished": "La ronda ya terminó.",
    "already_finished": "Ya habías registrado tu resultado en esta ronda.",
    "text_mismatch": "Lo que enviaste no coincide con el texto de la ronda.",
}


def register_game_events(socketio):
    @socketio.on("start_game")
    def handle_start_game(data):
        """
        data: { room_code, player_id }
        Solo el anfitrión puede iniciar la partida.
        """
        room_code = (data or {}).get("room_code", "").strip().upper()
        player_id = (data or {}).get("player_id")

        try:
            settings = game_service.start_game(room_code, player_id)
        except RoomError as exc:
            emit("error_message", {"message": str(exc)})
            return

        # Todos los clientes (lobby) redirigen a la pantalla de juego en
        # cuanto reciben este evento; la cuenta regresiva y el texto de
        # la ronda llegarán ya con todos conectados desde esa pantalla.
        emit("game_starting", {"room_code": room_code, "settings": settings}, to=room_code)

        socketio.start_background_task(run_round_sequence, socketio, room_code)

    @socketio.on("player_finished")
    def handle_player_finished(data):
        """
        data: { room_code, player_id, round_number, typed_text }

        El servidor es quien decide si la finalización es válida:
        recalcula el tiempo a partir de su propia marca de inicio,
        compara el texto recibido contra el texto real de la ronda
        (respetando la regla de tildes de la sala) y solo entonces
        aplica la lógica de puntuación de cada modo de juego.
        """
        room_code = (data or {}).get("room_code", "").strip().upper()
        player_id = (data or {}).get("player_id")
        typed_text = (data or {}).get("typed_text", "")

        try:
            round_number = int((data or {}).get("round_number"))
        except (TypeError, ValueError):
            emit("error_message", {"message": "Datos de ronda inválidos."}, to=request.sid)
            return

        try:
            outcome = game_service.submit_player_finish(
                room_code, player_id, round_number, typed_text
            )
        except RoomError as exc:
            emit("error_message", {"message": str(exc)}, to=request.sid)
            return

        if not outcome.get("accepted"):
            reason = outcome.get("reason")
            emit(
                "finish_rejected",
                {
                    "reason": reason,
                    "message": _REJECTION_MESSAGES.get(
                        reason, "No se pudo validar tu resultado."
                    ),
                },
                to=request.sid,
            )
            return

        player = room_service.get_player(room_code, player_id)
        player_name = player["name"] if player else "Jugador"

        socketio.emit(
            "player_finished_result",
            {
                "player_id": player_id,
                "player_name": player_name,
                "order": outcome["order"],
                "is_first": outcome["is_first"],
                "time_seconds": outcome["elapsed"],
            },
            to=room_code,
        )

        if outcome.get("round_finished"):
            payload = game_service.build_round_results_payload(room_code, outcome)
            socketio.emit("round_finished", payload, to=room_code)

    @socketio.on("player_ready_next_round")
    def handle_player_ready_next_round(data):
        """
        data: { room_code, player_id }

        Cuando un jugador pulsa "Continuar ronda", se registra su
        confirmación. En cuanto TODOS los jugadores activos (conectados)
        han confirmado, el servidor prepara la siguiente ronda, o
        finaliza la partida si la que acaba de terminar era la última.
        Un jugador desconectado nunca bloquea este avance.
        """
        room_code = (data or {}).get("room_code", "").strip().upper()
        player_id = (data or {}).get("player_id")

        round_number = game_service.get_current_round_number(room_code)

        try:
            outcome = game_service.mark_player_ready(room_code, player_id, round_number)
        except RoomError as exc:
            emit("error_message", {"message": str(exc)}, to=request.sid)
            return

        status_payload = game_service.build_ready_status_payload(
            room_code, outcome.get("ready_ids")
        )
        socketio.emit("ready_status_update", status_payload, to=room_code)

        if outcome.get("triggered"):
            _advance_after_round(socketio, room_code)


def _advance_after_round(socketio, room_code: str):
    """
    Se llama una única vez, justo cuando el servidor detecta que todos
    los jugadores activos ya están listos para continuar (ya sea porque
    el último pulsó "Continuar ronda" o porque el jugador que faltaba
    se desconectó). Decide si toca preparar la siguiente ronda o si la
    partida ya llegó a su última ronda y debe finalizar.
    """
    if game_service.is_last_round(room_code):
        game_service.finish_game(room_code)
        socketio.emit("game_finished", {"room_code": room_code}, to=room_code)
    else:
        socketio.start_background_task(run_round_sequence, socketio, room_code)


def handle_disconnect_effects(socketio, room_code: str, player_id: str):
    """
    Se llama desde sockets/room_events.py cuando un jugador se
    desconecta mientras la partida está en curso (o en la pantalla de
    resultados de una ronda). Comprueba si esa desconexión hace que la
    ronda actual deba cerrarse, o que la partida deba avanzar a la
    siguiente ronda / a la pantalla final, para que un jugador que se
    fue nunca bloquee al resto.
    """
    try:
        outcome = game_service.handle_player_disconnect_game_state(room_code, player_id)
    except RoomError:
        return

    if outcome is None:
        # La desconexión no alcanzó por sí sola a cerrar la ronda ni a
        # destrabar "Continuar ronda", pero puede que sí cambie quién
        # cuenta como jugador activo: refrescamos la lista de listos
        # para que el jugador que se fue deje de aparecer pendiente.
        status_payload = game_service.get_current_ready_status(room_code)
        if status_payload is not None:
            socketio.emit("ready_status_update", status_payload, to=room_code)
        return

    if outcome["type"] == "round_finished":
        socketio.emit("round_finished", outcome["payload"], to=room_code)
    elif outcome["type"] == "advance_round":
        _advance_after_round(socketio, room_code)


def run_round_sequence(socketio, room_code: str):
    """
    Ejecuta la cuenta regresiva y arranca la ronda. Se ejecuta en una
    tarea de fondo para no bloquear al servidor.
    """
    # Pequeña pausa para dar tiempo a que todos los clientes terminen de
    # navegar del lobby a la pantalla de juego (en la primera ronda) o
    # de reconectar su socket (emitiendo "join_lobby" de nuevo) antes de
    # que arranque la cuenta regresiva. En rondas siguientes no hay
    # navegación de por medio, pero la pausa no afecta la experiencia.
    socketio.sleep(1.5)

    for remaining in range(COUNTDOWN_SECONDS, 0, -1):
        socketio.emit("countdown_tick", {"value": remaining}, to=room_code)
        socketio.sleep(1)

    socketio.emit("countdown_tick", {"value": "¡YA!"}, to=room_code)
    socketio.sleep(0.6)

    try:
        round_info = game_service.start_next_round(room_code)
    except RoomError as exc:
        socketio.emit("error_message", {"message": str(exc)}, to=room_code)
        return

    socketio.emit("round_start", round_info, to=room_code)
