/**
 * lobby.js
 * Mantiene el lobby sincronizado en tiempo real vía Flask-SocketIO:
 * lista de jugadores, anfitrión, configuración de partida y arranque
 * de la cuenta regresiva antes de redirigir a la pantalla de juego.
 */

document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("lobby-root");
  const roomCode = root.dataset.roomCode;
  const playerId = root.dataset.playerId;
  const gameUrl = root.dataset.gameUrl;
  let isHost = root.dataset.isHost === "true";

  const playersList = document.getElementById("players-list");
  const playerCountEl = document.getElementById("player-count");
  const startBtn = document.getElementById("start-game-btn");
  const waitingHostNote = document.getElementById("waiting-host-note");
  const settingsReadonlyNote = document.getElementById("settings-readonly-note");
  const settingsForm = document.getElementById("settings-form");
  const customRoundsInput = document.getElementById("custom-rounds");
  const copyBtn = document.getElementById("copy-code-btn");

  // Estado local de la configuración (se sincroniza con el servidor,
  // que es quien valida y decide los valores finales).
  let currentSettings = {
    rounds: 5,
    mode: "all_finish",
    length: "medium",
    accents_required: true,
    use_enye: true,
  };

  const socket = io();

  socket.on("connect", () => {
    socket.emit("join_lobby", { room_code: roomCode, player_id: playerId });
  });

  socket.on("error_message", (data) => {
    alert(data.message || "Ocurrió un error.");
  });

  socket.on("lobby_update", (data) => {
    isHost = data.host_id === playerId;
    renderPlayers(data.players, data.host_id);
    if (data.settings) {
      currentSettings = data.settings;
      renderSettings(currentSettings, isHost);
    }
    renderHostControls(isHost);
  });

  socket.on("host_changed", (data) => {
    isHost = data.new_host_id === playerId;
    renderHostControls(isHost);
  });

  socket.on("game_starting", () => {
    // Redirigimos a todos los jugadores a la pantalla de juego de
    // inmediato. La cuenta regresiva ("3, 2, 1, ¡YA!") y el texto de
    // la ronda llegan ya en esa pantalla, cuando todos están conectados
    // desde allí: si esperáramos aquí a "round_start", ese evento se
    // emite una sola vez y quien todavía esté cargando /game nunca lo
    // recibiría.
    startBtn.disabled = true;
    waitingHostNote.classList.add("hidden");
    window.location.href = `${gameUrl}?player_id=${encodeURIComponent(playerId)}`;
  });

  // -----------------------------------------------------------------
  // Render de jugadores
  // -----------------------------------------------------------------
  function renderPlayers(players, hostId) {
    playersList.innerHTML = "";
    playerCountEl.textContent = `(${players.length})`;

    players.forEach((player) => {
      const li = document.createElement("li");
      li.className =
        "player-item" + (player.connected ? "" : " player-item--disconnected");

      const crown = player.id === hostId ? "👑 " : "";
      li.innerHTML = `<span class="status-dot"></span><span>${crown}${escapeHtml(
        player.name
      )}</span>`;
      playersList.appendChild(li);
    });
  }

  // -----------------------------------------------------------------
  // Render de configuración (chips activos + habilitado/deshabilitado)
  // -----------------------------------------------------------------
  function renderSettings(settings, editable) {
    document.querySelectorAll(".chip-row").forEach((row) => {
      const settingKey = row.dataset.setting;
      const value = settings[settingKey];

      row.querySelectorAll(".chip").forEach((chip) => {
        const chipValue = parseChipValue(chip.dataset.value);
        chip.classList.toggle("chip--active", chipValue === value);
        chip.disabled = !editable;
      });
    });

    if (![5, 7, 10, 12].includes(settings.rounds)) {
      customRoundsInput.value = settings.rounds;
    } else {
      customRoundsInput.value = "";
    }
    customRoundsInput.disabled = !editable;
  }

  function renderHostControls(host) {
    startBtn.classList.toggle("hidden", !host);
    waitingHostNote.classList.toggle("hidden", host);
    settingsReadonlyNote.classList.toggle("hidden", host);
  }

  function parseChipValue(rawValue) {
    if (rawValue === "true") return true;
    if (rawValue === "false") return false;
    const asNumber = Number(rawValue);
    return Number.isNaN(asNumber) ? rawValue : asNumber;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // -----------------------------------------------------------------
  // Interacciones del anfitrión
  // -----------------------------------------------------------------
  settingsForm.addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (!chip || chip.disabled) return;

    const row = chip.closest(".chip-row");
    const settingKey = row.dataset.setting;
    currentSettings[settingKey] = parseChipValue(chip.dataset.value);

    if (settingKey === "rounds") {
      customRoundsInput.value = "";
    }

    emitSettingsUpdate();
  });

  customRoundsInput.addEventListener("change", () => {
    const value = parseInt(customRoundsInput.value, 10);
    if (!Number.isNaN(value) && value > 0) {
      currentSettings.rounds = value;
      emitSettingsUpdate();
    }
  });

  function emitSettingsUpdate() {
    socket.emit("update_settings", {
      room_code: roomCode,
      player_id: playerId,
      settings: currentSettings,
    });
  }

  startBtn.addEventListener("click", () => {
    socket.emit("start_game", { room_code: roomCode, player_id: playerId });
  });

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(roomCode);
      copyBtn.textContent = "¡Copiado!";
      setTimeout(() => (copyBtn.textContent = "Copiar código"), 1500);
    } catch (err) {
      // Si el navegador bloquea el portapapeles, no interrumpimos el flujo.
      console.warn("No se pudo copiar el código:", err);
    }
  });

  // Estado inicial (antes de recibir el primer lobby_update).
  renderHostControls(isHost);

  window.addEventListener("beforeunload", () => {
    socket.emit("leave_lobby", { room_code: roomCode, player_id: playerId });
  });
});
