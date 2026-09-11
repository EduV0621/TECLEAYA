"""
app.py

Punto de entrada de la aplicación. Define:
- la app Flask y su configuración;
- las rutas HTTP (páginas: inicio, crear/unirse a sala, lobby, juego, resultados);
- la inicialización de Flask-SocketIO y el registro de sus eventos.

Para ejecutar en local:

    python app.py

La app quedará disponible en http://localhost:5000
"""

from flask import Flask, render_template, request, redirect, url_for, flash

from config import Config
from services import room_service, game_service
from services.room_service import RoomError
from services.firebase import init_firebase
from sockets.room_events import register_room_events
from sockets.game_events import register_game_events

from flask_socketio import SocketIO


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializa Firebase al arrancar la aplicación. Si faltan variables
    # de entorno, lanzará un error claro en los logs en lugar de fallar
    # de forma confusa más adelante.
    try:
        init_firebase()
    except RuntimeError as exc:
        app.logger.warning(
            "Firebase no se pudo inicializar todavía: %s. "
            "Configura tu archivo .env antes de crear o unirte a salas.",
            exc,
        )

    register_routes(app)
    return app


def register_routes(app: Flask):
    # -----------------------------------------------------------------
    # Página principal
    # -----------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    # -----------------------------------------------------------------
    # Crear sala
    # -----------------------------------------------------------------
    @app.route("/create-room", methods=["POST"])
    def create_room():
        player_name = request.form.get("player_name", "")

        try:
            result = room_service.create_room(player_name)
        except RoomError as exc:
            flash(str(exc))
            return redirect(url_for("index"))

        return redirect(
            url_for(
                "lobby",
                room_code=result["room_code"],
                player_id=result["player_id"],
            )
        )

    # -----------------------------------------------------------------
    # Unirse a sala
    # -----------------------------------------------------------------
    @app.route("/join-room", methods=["GET", "POST"])
    def join_room_route():
        if request.method == "GET":
            return render_template("join_room.html")

        player_name = request.form.get("player_name", "")
        room_code = request.form.get("room_code", "")

        try:
            result = room_service.join_room_service(room_code, player_name)
        except RoomError as exc:
            flash(str(exc))
            return render_template("join_room.html", room_code=room_code, player_name=player_name)

        return redirect(
            url_for(
                "lobby",
                room_code=result["room_code"],
                player_id=result["player_id"],
            )
        )

    # -----------------------------------------------------------------
    # Lobby
    # -----------------------------------------------------------------
    @app.route("/lobby/<room_code>")
    def lobby(room_code):
        player_id = request.args.get("player_id")

        room = room_service.get_room(room_code)
        if room is None:
            flash("Esa sala no existe.")
            return redirect(url_for("index"))

        player = room_service.get_player(room_code, player_id) if player_id else None
        if player is None:
            flash("No se encontró tu jugador en esta sala. Únete de nuevo.")
            return redirect(url_for("join_room_route"))

        return render_template(
            "lobby.html",
            room_code=room_code.upper(),
            player_id=player_id,
            player_name=player["name"],
            is_host=player.get("is_host", False),
        )

    # -----------------------------------------------------------------
    # Pantalla de juego
    # -----------------------------------------------------------------
    @app.route("/game/<room_code>")
    def game(room_code):
        player_id = request.args.get("player_id")

        room = room_service.get_room(room_code)
        if room is None:
            flash("Esa sala no existe.")
            return redirect(url_for("index"))

        player = room_service.get_player(room_code, player_id) if player_id else None
        if player is None:
            flash("No se encontró tu jugador en esta sala.")
            return redirect(url_for("join_room_route"))

        return render_template(
            "game.html",
            room_code=room_code.upper(),
            player_id=player_id,
            player_name=player["name"],
        )

    # -----------------------------------------------------------------
    # Resultados finales
    #
    # Los resultados de CADA ronda se muestran en tiempo real dentro de
    # la propia pantalla de juego (ver templates/game.html y
    # static/js/game.js), vía Socket.IO: no hace falta navegar a otra
    # página entre ronda y ronda. Esta ruta es solo para el ranking
    # final, al terminar todas las rondas.
    # -----------------------------------------------------------------
    @app.route("/final-results/<room_code>")
    def final_results(room_code):
        scoreboard = game_service.get_final_scoreboard(room_code)
        return render_template(
            "final_results.html", room_code=room_code.upper(), scoreboard=scoreboard
        )

    # -----------------------------------------------------------------
    # Ver detalles: desglose ronda por ronda del ranking final
    # -----------------------------------------------------------------
    @app.route("/room-details/<room_code>")
    def room_details(room_code):
        rounds = game_service.get_round_by_round_details(room_code)
        return render_template(
            "round_details.html", room_code=room_code.upper(), rounds=rounds
        )

    # -----------------------------------------------------------------
    # Página de detalles / acerca del proyecto
    # -----------------------------------------------------------------
    @app.route("/details")
    def details():
        return render_template("details.html")


app = create_app()

# async_mode="threading" evita depender de eventlet, que aún no es
# compatible con versiones recientes de Python (como 3.14). El modo
# "threading" usa hilos nativos de Python. Con el paquete
# "simple-websocket" instalado (ver requirements.txt), este modo
# soporta WebSocket real además de long-polling, mucho más liviano
# en memoria que depender solo de polling.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

register_room_events(socketio)
register_game_events(socketio)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
