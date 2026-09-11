# ⌨️ TecleaYa — Juego de mecanografía multijugador

Juego web multijugador de mecanografía. Los jugadores entran a una sala
mediante un código, reciben exactamente el mismo texto generado de
forma procedural, y compiten por escribirlo correctamente lo más
rápido posible, ronda tras ronda, hasta que se define un ranking final.

> **Estado del proyecto:** completo e integrado. Incluye lobby, partida
> en tiempo real, cierre y transición entre rondas, ranking final con
> desempate, manejo de desconexiones/anfitrión, y preparación para
> despliegue en Render.

---

## 🧱 Tecnologías

- **Backend:** Python, Flask, Flask-SocketIO (tiempo real)
- **Frontend:** HTML5, CSS3 y JavaScript puro (sin frameworks), plantillas Jinja2
- **Base de datos:** Firebase Cloud Firestore (vía Firebase Admin SDK)
- **Despliegue:** GitHub + Render (Gunicorn con worker de eventlet)

No se utilizan React, Vue, Angular ni frameworks CSS pesados.

---

## 📁 Estructura del proyecto

```
typing-game/
│
├── app.py                     # App Flask + rutas + arranque de Socket.IO
├── config.py                  # Configuración centralizada (lee variables de entorno)
├── requirements.txt
├── Procfile                    # Comando de arranque para Render (gunicorn + eventlet)
├── .env.example                # Plantilla de variables de entorno (sin credenciales)
├── .gitignore
├── README.md
│
├── services/
│   ├── firebase.py             # Inicialización de Firebase Admin SDK / Firestore
│   ├── room_service.py         # Crear/unir salas, jugadores, anfitrión, configuración
│   └── game_service.py         # Rondas, puntuación, "Continuar ronda", ranking final
│
├── sockets/
│   ├── room_events.py          # Eventos de lobby y desconexiones en tiempo real
│   └── game_events.py          # Eventos de partida (cuenta regresiva, rondas, avance)
│
├── utils/
│   ├── phrase_generator.py     # Generador procedural de textos en español
│   └── text_validator.py       # Validaciones de textos generados / comparación
│
├── templates/                  # Plantillas Jinja2 (una por pantalla)
│   ├── index.html, join_room.html, lobby.html, game.html
│   ├── final_results.html, round_details.html, details.html
│
└── static/
    ├── css/style.css
    └── js/ (main.js, lobby.js, game.js)
```

Los resultados de **cada ronda** (quién ganó, tiempos, puntos) se
muestran en tiempo real dentro de la propia pantalla de juego
(`game.html` + `game.js`) vía Socket.IO — no hace falta navegar a otra
página entre ronda y ronda. Solo el **ranking final** (al terminar
todas las rondas) tiene su propia página, con un botón "Ver detalles"
para el desglose ronda por ronda.

---

## 🚀 Instalación y ejecución local

### 1. Clonar / abrir el proyecto en VS Code

### 2. Crear entorno virtual

```bash
python -m venv venv
```

Activarlo:

- **Windows:** `venv\Scripts\activate`
- **macOS / Linux:** `source venv/bin/activate`

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar Firebase

1. Crea un proyecto en [Firebase Console](https://console.firebase.google.com/).
2. Activa **Cloud Firestore** (modo producción o de prueba, según prefieras).
3. Ve a **Configuración del proyecto → Cuentas de servicio** y genera una
   nueva clave privada. Se descargará un archivo `.json`.
4. De ese archivo necesitarás: `project_id`, `client_email` y `private_key`.

### 5. Configurar variables de entorno

Copia `.env.example` como `.env`:

```bash
cp .env.example .env        # macOS / Linux
copy .env.example .env      # Windows
```

Y completa los valores con los datos de tu cuenta de servicio de Firebase.
**Nunca subas el archivo `.env` real a GitHub** (ya está incluido en `.gitignore`).

### 6. Ejecutar la aplicación

```bash
python app.py
```

La aplicación quedará disponible en:

```
http://localhost:5000
```

---

## 🎮 Cómo jugar / cómo probar con varias pestañas

1. Abre `http://localhost:5000`, escribe tu nombre y pulsa **"Crear sala"**.
   Quedarás en el lobby como anfitrión, con un código de sala (p. ej. `K7X92P`).
2. Abre una **segunda pestaña** (o una ventana de incógnito, o un
   segundo navegador) en la misma URL, pulsa **"Unirse a sala"** y
   escribe el código. Repite con una tercera pestaña si quieres probar
   con más jugadores.
3. Desde la primera pestaña (el anfitrión), ajusta la configuración
   (número de rondas, modo de juego, longitud del texto, tildes, "ñ")
   y pulsa **"Iniciar partida"**.
4. Todas las pestañas verán la cuenta regresiva (3, 2, 1, ¡YA!) y
   recibirán exactamente el mismo texto.
5. Escribe el texto en cada pestaña. Al terminar todos (o el primero,
   según el modo), se muestra el resultado de la ronda dentro de la
   misma pantalla.
6. Cada jugador pulsa **"Continuar ronda"** cuando esté listo; en
   cuanto todos los jugadores activos lo confirman, arranca la
   siguiente ronda automáticamente.
7. Al completar la última ronda, todas las pestañas son enviadas al
   **ranking final**, donde también puedes pulsar **"Ver detalles"**
   para el desglose ronda por ronda.
8. Para probar desconexiones: cierra una de las pestañas a mitad de
   partida. El resto debe poder seguir jugando sin quedar bloqueado
   esperando a quien se fue.

---

## ✅ Funcionalidades

- Página principal con validación de nombre (frontend + backend).
- Creación de salas con código único generado por el servidor.
- Unión a salas existentes, con validaciones de sala inexistente / llena / en juego.
- Lobby en tiempo real (Flask-SocketIO): lista de jugadores, anfitrión,
  reasignación automática de anfitrión si este se desconecta.
- Configuración completa de partida por parte del anfitrión: número de
  rondas (con opción personalizada), modo de juego ("Todos pueden
  terminar" / "El primero termina la ronda"), longitud del texto,
  tildes obligatorias u opcionales, uso o no de la letra "ñ".
- Generador procedural de textos en español, con vocabulario real por
  categorías, múltiples plantillas gramaticales, control de longitud,
  filtros de tildes/"ñ" y prevención de repeticiones dentro de la partida.
- Cuenta regresiva y pantalla de juego con retroalimentación visual
  carácter por carácter mientras el jugador escribe.
- Validación **autoritativa del servidor**: el tiempo se calcula con el
  reloj del servidor, el texto escrito se compara contra el texto real
  de la ronda, y nunca se confía en que el navegador declare "terminé"
  o "gané".
- Anti-cheat básico: bloqueo de pegado/arrastrar-soltar, sin aceptar
  tiempos ni resultados arbitrarios del cliente, verificación de que la
  ronda sigue activa y de que el texto corresponde.
- Resultado de cada ronda mostrado en tiempo real (ganador, tiempos,
  puntos), con medallas para los primeros lugares.
- Botón "Continuar ronda" con lista de "listos" en vivo; la siguiente
  ronda arranca automáticamente en cuanto todos los jugadores activos
  confirman.
- Puntuación acumulada (+1 al ganador de cada ronda) y ranking final
  con desempate por menor tiempo acumulado en caso de puntos iguales.
- Pantalla de ranking final y pantalla de detalle ronda por ronda.
- Manejo de desconexiones: un jugador que cierra la pestaña o pierde
  conexión durante la partida se marca como desconectado (sin perder su
  puntaje) y nunca bloquea la ronda ni el botón "Continuar ronda"; si
  era el anfitrión, el rol pasa a otro jugador conectado.
- Persistencia de salas, jugadores, configuración, rondas y resultados
  en Firestore (nunca se usa Firestore para sincronizar cada tecla:
  eso lo hace Socket.IO).
- Diseño responsive, limpio y minimalista (sin frameworks CSS), probado
  en layouts de escritorio y móvil.

---

## ☁️ Despliegue en Render

1. Sube el proyecto a GitHub (ver sección siguiente).
2. En Render, crea un **Web Service** nuevo apuntando a tu repositorio.
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** ya está definido en el `Procfile`:
   ```
   gunicorn --worker-class eventlet -w 1 app:app --bind 0.0.0.0:$PORT
   ```
   No se usa el servidor de desarrollo de Flask (`python app.py`) en
   producción: Gunicorn con el worker de `eventlet` es quien soporta
   correctamente las conexiones WebSocket de Flask-SocketIO.
5. En la sección **Environment** de Render, configura las mismas
   variables que en tu `.env` local: `SECRET_KEY`, `FLASK_DEBUG=False`,
   `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY`
   (con los `\n` literales, tal como vienen en el JSON de credenciales).
6. Despliega. Render asignará automáticamente la variable `PORT`, que
   el `Procfile` ya utiliza.

---

## 🐙 GitHub

El proyecto está listo para subir a un repositorio:

```bash
git init
git add .
git commit -m "TecleaYa: juego de mecanografía multijugador"
git push
```

`.gitignore` ya excluye `.env`, entornos virtuales, `__pycache__/` y
cualquier archivo de credenciales. **Nunca** subas tu archivo `.env`
real ni un JSON de credenciales de Firebase al repositorio.

---

## 🔐 Firebase y credenciales

- Las credenciales de Firebase se leen siempre desde variables de
  entorno (`config.py`), nunca están escritas en el código.
- En Render, esas variables se configuran en el panel de
  **Environment** del servicio (ver sección de despliegue arriba).
- El servidor nunca imprime la clave privada en los logs.

---

## 📦 requirements.txt

Incluye únicamente lo necesario: Flask, Flask-SocketIO (y sus
dependencias `python-socketio`/`python-engineio`), `eventlet` (servidor
asíncrono), `firebase-admin`, `python-dotenv` y `gunicorn` (servidor de
producción para Render).
