/**
 * game.js
 * Pantalla de juego: mecánica principal de mecanografía.
 *
 * - El texto de la ronda lo entrega siempre el servidor (mismo texto
 *   para todos los jugadores).
 * - La escritura se valida carácter por carácter, en orden estricto:
 *   no se puede saltar caracteres, mover el cursor ni corregir una
 *   posición ya superada. Un carácter incorrecto simplemente no avanza.
 * - El campo de entrada nunca conserva el texto escrito (se vacía en
 *   cada evento): solo existe para capturar pulsaciones reales del
 *   teclado (incluido el teclado del celular) y bloquear pegado.
 * - La finalización SIEMPRE se confirma con el servidor: el cliente
 *   solo avisa que "cree" haber terminado y envía lo que realmente
 *   escribió; el servidor decide si es válido, calcula el tiempo con
 *   su propio reloj y aplica la puntuación según el modo de juego.
 */

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("game-root");
  const roomCode = root.dataset.roomCode;
  const playerId = root.dataset.playerId;
  const indexUrl = root.dataset.indexUrl;

  const waitingPanel = document.getElementById("waiting-panel");
  const typingPanel = document.getElementById("typing-panel");
  const textEl = document.getElementById("text-to-type");
  const inputEl = document.getElementById("typing-input");
  const roundIndicator = document.getElementById("round-indicator");
  const timerDisplay = document.getElementById("timer-display");
  const progressFill = document.getElementById("progress-fill");
  const progressLabel = document.getElementById("progress-label");
  const finishStatus = document.getElementById("finish-status");
  const liveFinishers = document.getElementById("live-finishers");
  const countdownOverlay = document.getElementById("countdown-overlay");
  const countdownNumber = document.getElementById("countdown-number");
  const roundFinishedPanel = document.getElementById("round-finished-panel");
  const roundFinishedSummary = document.getElementById("round-finished-summary");
  const roundFinishedList = document.getElementById("round-finished-list");
  const continueBtn = document.getElementById("continue-round-btn");
  const readyList = document.getElementById("ready-list");
  const leaveGameBtn = document.getElementById("leave-game-btn");

  // Mapa de tildes de vocales -> vocal sin tilde. La "ñ" nunca se toca
  // aquí: no es una tilde, es una letra distinta (ver utils/text_validator.py).
  const ACCENT_MAP = {
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
    "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
  };

  let currentText = "";
  let pointer = 0;
  let typedChars = [];
  let accentsRequired = true;
  let roundNumber = 0;
  let totalRounds = 0;
  let mode = "all_finish";
  let roundActive = false;
  let hasClickedContinue = false;

  let timerHandle = null;
  let startedAtClient = null;

  const socket = io();

  socket.on("connect", () => {
    socket.emit("join_lobby", { room_code: roomCode, player_id: playerId });
  });

  socket.on("error_message", (data) => {
    console.warn(data && data.message);
  });

  socket.on("countdown_tick", (data) => {
    waitingPanel.classList.add("hidden");
    typingPanel.classList.add("hidden");
    roundFinishedPanel.classList.add("hidden");
    countdownOverlay.classList.remove("hidden");
    countdownNumber.textContent = data.value;
  });

  socket.on("round_start", (data) => {
    currentText = data.text;
    accentsRequired = !!data.accents_required;
    roundNumber = data.round_number;
    totalRounds = data.total_rounds;
    mode = data.mode;
    pointer = 0;
    typedChars = [];
    roundActive = true;
    hasClickedContinue = false;

    roundIndicator.textContent = `Ronda ${roundNumber} de ${totalRounds}`;

    countdownOverlay.classList.add("hidden");
    waitingPanel.classList.add("hidden");
    roundFinishedPanel.classList.add("hidden");
    typingPanel.classList.remove("hidden");

    finishStatus.classList.add("hidden");
    finishStatus.textContent = "";
    liveFinishers.classList.add("hidden");
    liveFinishers.innerHTML = "";

    continueBtn.disabled = false;
    continueBtn.textContent = "Continuar ronda";
    readyList.innerHTML = "";

    renderText();

    inputEl.value = "";
    inputEl.disabled = false;
    inputEl.focus();

    startTimer();
  });

  socket.on("player_finished_result", (data) => {
    liveFinishers.classList.remove("hidden");
    const li = document.createElement("li");
    li.className = "scoreboard-item" + (data.is_first ? " scoreboard-item--first" : "");
    const points = data.is_first ? "+1" : "0";
    li.innerHTML =
      `<span class="scoreboard-position">${medalFor(data.order)}</span>` +
      `<span class="scoreboard-name">${escapeHtml(data.player_name)} — ${formatSeconds(data.time_seconds)} s</span>` +
      `<span class="scoreboard-score">${points}</span>`;
    liveFinishers.appendChild(li);
  });

  socket.on("finish_rejected", (data) => {
    finishStatus.classList.remove("hidden");
    finishStatus.textContent = (data && data.message) || "No se pudo validar tu resultado.";
  });

  socket.on("round_finished", (data) => {
    roundActive = false;
    stopTimer();
    inputEl.disabled = true;
    inputEl.blur();

    typingPanel.classList.add("hidden");
    roundFinishedPanel.classList.remove("hidden");

    hasClickedContinue = false;
    continueBtn.disabled = false;
    continueBtn.textContent = "Continuar ronda";
    readyList.innerHTML = "";

    if (data.mode === "first_wins") {
      const winner = data.results.find((r) => r.player_id === data.winner_id);
      const winnerName = winner ? winner.player_name : "Un jugador";
      roundFinishedSummary.textContent =
        winner && winner.player_id === playerId
          ? "¡Ganaste esta ronda!"
          : `${winnerName} terminó primero y ganó la ronda.`;
    } else {
      roundFinishedSummary.textContent = "Todos los jugadores activos terminaron la ronda.";
    }

    roundFinishedList.innerHTML = "";
    data.results.forEach((entry) => {
      const li = document.createElement("li");
      li.className = "scoreboard-item" + (entry.order === 1 ? " scoreboard-item--first" : "");
      li.innerHTML =
        `<span class="scoreboard-position">${medalFor(entry.order)}</span>` +
        `<span class="scoreboard-name">${escapeHtml(entry.player_name)} — ${formatSeconds(entry.time_seconds)} s</span>` +
        `<span class="scoreboard-score">${entry.score}</span>`;
      roundFinishedList.appendChild(li);
    });
  });

  // -----------------------------------------------------------------
  // "Continuar ronda": cada jugador activo confirma por su cuenta.
  // Mientras no estén todos listos, se muestra quién sigue pendiente;
  // el servidor decide cuándo arrancar la siguiente ronda (o cuándo
  // enviar a todos a la pantalla final).
  // -----------------------------------------------------------------

  socket.on("ready_status_update", (data) => {
    readyList.innerHTML = "";
    (data.players || []).forEach((player) => {
      const li = document.createElement("li");
      li.className = "ready-item" + (player.ready ? " ready-item--ready" : "");
      const status = player.ready ? "✓ Listo" : "⏳";
      li.innerHTML =
        `<span>${escapeHtml(player.player_name)}</span><span>${status}</span>`;
      readyList.appendChild(li);
    });
  });

  socket.on("game_finished", () => {
    window.location.href = `/final-results/${roomCode}`;
  });

  continueBtn.addEventListener("click", () => {
    if (hasClickedContinue) return;
    hasClickedContinue = true;
    continueBtn.disabled = true;
    continueBtn.textContent = "Esperando a los demás…";

    socket.emit("player_ready_next_round", {
      room_code: roomCode,
      player_id: playerId,
    });
  });

  // -----------------------------------------------------------------
  // Abandonar la partida: reutiliza el mismo evento "leave_lobby" que
  // ya usa el lobby (el backend lo maneja igual en cualquier estado de
  // la sala: si ya está en partida, marca al jugador como desconectado
  // y transfiere el rol de anfitrión si hacía falta).
  // -----------------------------------------------------------------

  if (leaveGameBtn) {
    leaveGameBtn.addEventListener("click", () => {
      const confirmed = window.confirm("¿Seguro que quieres abandonar la partida?");
      if (!confirmed) return;

      socket.emit("leave_lobby", { room_code: roomCode, player_id: playerId });
      window.location.href = indexUrl;
    });
  }

  // -----------------------------------------------------------------
  // Captura de teclado: cada pulsación real se procesa una por una.
  // Nunca se deja que el input conserve texto, se mueva el cursor
  // dentro de él, ni se pegue contenido.
  // -----------------------------------------------------------------

  inputEl.addEventListener("beforeinput", (event) => {
    event.preventDefault();

    if (!roundActive) return;

    const insertTypes = ["insertText", "insertCompositionText", "insertFromComposition"];
    if (!insertTypes.includes(event.inputType) || !event.data) {
      // Ignora borrados, pegado (insertFromPaste), saltos de línea, etc.
      return;
    }

    for (const ch of event.data) {
      const accepted = tryAcceptChar(ch);
      if (!accepted) break; // se detiene en el primer carácter que no coincide
    }
  });

  // Red de seguridad: si algún navegador no respeta preventDefault en
  // "beforeinput", el campo igual se vacía en cada "input".
  inputEl.addEventListener("input", () => {
    if (inputEl.value !== "") inputEl.value = "";
  });

  inputEl.addEventListener("paste", (event) => event.preventDefault());
  inputEl.addEventListener("drop", (event) => event.preventDefault());
  inputEl.addEventListener("contextmenu", (event) => event.preventDefault());

  function tryAcceptChar(ch) {
    if (pointer >= currentText.length) return false;

    const expectedChar = currentText[pointer];
    if (!charsMatch(expectedChar, ch)) {
      flashIncorrect();
      return false;
    }

    typedChars.push(ch);
    pointer += 1;
    renderText();

    if (pointer >= currentText.length) {
      handleLocalCompletion();
    }
    return true;
  }

  function charsMatch(expectedChar, typedChar) {
    return normalizeChar(expectedChar) === normalizeChar(typedChar);
  }

  function normalizeChar(ch) {
    if (accentsRequired) return ch;
    return ACCENT_MAP[ch] || ch;
  }

  function flashIncorrect() {
    const current = textEl.querySelector(".char-current");
    if (!current) return;
    current.classList.add("char-shake");
    setTimeout(() => current.classList.remove("char-shake"), 180);
  }

  function renderText() {
    let html = "";
    for (let i = 0; i < currentText.length; i++) {
      const ch = escapeHtml(currentText[i]);
      let className = "char-pending";
      if (i < pointer) className = "char-correct";
      else if (i === pointer) className = "char-current";
      html += `<span class="${className}">${ch}</span>`;
    }
    textEl.innerHTML = html;

    const percent = currentText.length ? Math.floor((pointer / currentText.length) * 100) : 0;
    progressFill.style.width = `${percent}%`;
    progressLabel.textContent = `Progreso: ${percent} %`;
  }

  function handleLocalCompletion() {
    inputEl.disabled = true;
    finishStatus.classList.remove("hidden");
    finishStatus.textContent = "¡Terminaste! Confirmando con el servidor…";

    socket.emit("player_finished", {
      room_code: roomCode,
      player_id: playerId,
      round_number: roundNumber,
      typed_text: typedChars.join(""),
    });
  }

  // -----------------------------------------------------------------
  // Cronómetro visual (fluido, en el navegador). El tiempo OFICIAL que
  // decide la puntuación siempre lo calcula el servidor a partir de su
  // propia marca de inicio de ronda; este cronómetro es solo para que
  // el jugador vea su avance en pantalla.
  // -----------------------------------------------------------------

  function startTimer() {
    startedAtClient = Date.now();
    stopTimer();
    timerHandle = setInterval(updateTimerDisplay, 30);
    updateTimerDisplay();
  }

  function stopTimer() {
    if (timerHandle) {
      clearInterval(timerHandle);
      timerHandle = null;
    }
  }

  function updateTimerDisplay() {
    const elapsedMs = Date.now() - startedAtClient;
    timerDisplay.textContent = formatClock(elapsedMs);
  }

  function formatClock(ms) {
    const totalHundredths = Math.floor(ms / 10);
    const minutes = String(Math.floor(totalHundredths / 6000)).padStart(2, "0");
    const seconds = String(Math.floor((totalHundredths / 100) % 60)).padStart(2, "0");
    const hundredths = String(totalHundredths % 100).padStart(2, "0");
    return `${minutes}:${seconds}.${hundredths}`;
  }

  function formatSeconds(value) {
    if (value === null || value === undefined) return "—";
    return value.toFixed(2);
  }

  function medalFor(order) {
    if (order === 1) return "🥇";
    if (order === 2) return "🥈";
    if (order === 3) return "🥉";
    return String(order);
  }

  function escapeHtml(char) {
    const div = document.createElement("div");
    div.textContent = char;
    return div.innerHTML;
  }
});
