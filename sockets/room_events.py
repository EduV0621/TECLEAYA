"""
sockets/room_events.py

Eventos de Socket.IO relacionados con la sala y el lobby:
- un jugador entra al lobby (registra su sid)
- un jugador se desconecta
- el anfitrión cambia la configuración
- se notifica a todos cuando cambia la lista de jugadores o el anfitrión

Estos eventos NO gestionan la lógica de la partida en sí (eso vive en
sockets/game_events.py), salvo por un caso: cuando alguien se
desconecta mientras la partida ya está en curso, aquí se decide cómo
tratarlo (marcarlo como desconectado sin borrarlo) y se delega a
sockets/game_events.handle_disconnect_effects() por si esa desconexión
debe cerrar la ronda actual o desbloquear "Continuar ronda".

Flask-SocketIO se usa exclusivamente para estos eventos de "estado de
sala" y para la partida en tiempo real; nunca se usa Firebase para
enviar cada pulsación de teclado ni cada evento efímero del lobby.
"""

from flask import request
from flask_socketio import join_room, leave_room, emit

from services import room_service
from services.room_service import RoomError

# Relaciona el sid de socket.io -> (room_code, player_id)
# Se mantiene en memoria porque es información efímera de la conexión,
# no un dato persistente del juego.
_SID_INDEX = {}


def _broadcast_lobby_state(room_code: str):
    room = room_service.get_room(room_code)
    if room is None:
        return

    players = room_service.get_players(room_code)

    emit(
        "lobby_update",
        {
            "room_code": room_code,
            "status": room.get("status"),
            "host_id": room.get("host_id"),
            "settings": room.get("settings"),
            "players": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "is_host": p.get("is_host", False),
                    "connected": p.get("connected", False),
                }
                for p in players
            ],
        },
        to=room_code,
    )


def register_room_events(socketio):
    @socketio.on("connect")
    def handle_connect():
        # No se hace nada especial todavía; la sala se asocia en "join_lobby".
        pass

    @socketio.on("join_lobby")
    def handle_join_lobby(data):
        """
        data: { room_code, player_id }

        El cliente llama a este evento justo después de cargar la
        pantalla de lobby, para registrar su conexión en tiempo real.
        """
        room_code = (data or {}).get("room_code")
        player_id = (data or {}).get("player_id")

        if not room_code or not player_id:
            emit("error_message", {"message": "Datos de sala inválidos."})
            return

        room_code = room_code.strip().upper()
        player = room_service.get_player(room_code, player_id)

        if player is None:
            emit("error_message", {"message": "No se encontró tu jugador en esta sala."})
            return

        join_room(room_code)
        room_service.set_player_socket(room_code, player_id, request.sid, True)
        _SID_INDEX[request.sid] = (room_code, player_id)

        _broadcast_lobby_state(room_code)

    @socketio.on("update_settings")
    def handle_update_settings(data):
        """
        data: { room_code, player_id, settings }
        Solo el anfitrión puede modificar la configuración.
        """
        room_code = (data or {}).get("room_code", "").strip().upper()
        player_id = (data or {}).get("player_id")
        new_settings = (data or {}).get("settings", {})

        try:
            room_service.update_settings(room_code, player_id, new_settings)
        except RoomError as exc:
            emit("error_message", {"message": str(exc)})
            return

        _broadcast_lobby_state(room_code)

    @socketio.on("leave_lobby")
    def handle_leave_lobby(data):
        room_code = (data or {}).get("room_code", "").strip().upper()
        player_id = (data or {}).get("player_id")

        if not room_code or not player_id:
            return

        _handle_player_leave(socketio, room_code, player_id)
        leave_room(room_code)
        _SID_INDEX.pop(request.sid, None)

    @socketio.on("disconnect")
    def handle_disconnect():
        entry = _SID_INDEX.pop(request.sid, None)
        if entry is None:
            return

        room_code, player_id = entry
        _handle_player_leave(socketio, room_code, player_id)


def _handle_player_leave(socketio, room_code: str, player_id: str):
    """
    Se llama tanto ante un cierre de pestaña/pérdida de conexión
    (evento "disconnect") como ante un abandono explícito del lobby.

    - Si la sala todavía está en el lobby (la partida no ha empezado),
      el jugador se elimina por completo: no tiene puntaje ni historial
      que conservar, y así la lista de jugadores y el conteo quedan
      correctos de inmediato.
    - Si la sala ya está en partida (o ya terminó), el jugador NO se
      elimina: se marca como desconectado para conservar su puntaje, y
      se delega a game_events.handle_disconnect_effects() por si su
      ausencia debe cerrar la ronda actual o destrabar "Continuar
      ronda" para el resto.
    """
    room = room_service.get_room(room_code)
    if room is None:
        return

    if room.get("status") == "lobby":
        new_host_id = room_service.remove_player(room_code, player_id)
        deleted = room_service.delete_room_if_empty(room_code)

        if not deleted:
            _broadcast_lobby_state(room_code)
            if new_host_id:
                emit(
                    "host_changed",
                    {"room_code": room_code, "new_host_id": new_host_id},
                    to=room_code,
                )
        return

    new_host_id = room_service.disconnect_player(room_code, player_id)
    emit(
        "player_disconnected",
        {"room_code": room_code, "player_id": player_id},
        to=room_code,
    )
    if new_host_id:
        emit(
            "host_changed",
            {"room_code": room_code, "new_host_id": new_host_id},
            to=room_code,
        )

    # Importación diferida para evitar un ciclo de importación entre
    # los dos módulos de sockets al arrancar la aplicación.
    from sockets.game_events import handle_disconnect_effects

    handle_disconnect_effects(socketio, room_code, player_id)
