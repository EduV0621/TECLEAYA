/**
 * main.js
 * Lógica de la página principal: pasa el nombre ya escrito hacia la
 * pantalla de "Unirse a sala" para no obligar al jugador a escribirlo
 * dos veces.
 */

document.addEventListener("DOMContentLoaded", () => {
  const joinBtn = document.getElementById("join-btn");
  const nameInput = document.getElementById("player_name");

  if (joinBtn && nameInput) {
    joinBtn.addEventListener("click", () => {
      const baseUrl = joinBtn.dataset.joinUrl;
      const name = nameInput.value.trim();
      const url = name
        ? `${baseUrl}?player_name=${encodeURIComponent(name)}`
        : baseUrl;
      window.location.href = url;
    });
  }

  // Si llegamos a /join-room con ?player_name=... precargado desde el
  // botón "Unirse a sala" del inicio, lo colocamos en el campo.
  const params = new URLSearchParams(window.location.search);
  const prefillName = params.get("player_name");
  const joinNameInput = document.getElementById("player_name");
  if (prefillName && joinNameInput && !joinNameInput.value) {
    joinNameInput.value = prefillName;
  }
});
