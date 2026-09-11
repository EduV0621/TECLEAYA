"""
utils/text_validator.py

Validaciones relacionadas con los textos generados por
utils/phrase_generator.py y con la comparación, carácter por carácter,
entre el texto original de cada ronda y lo que escribe cada jugador.

Mantener esta lógica separada del generador permite reutilizarla
tanto en el servidor (autoridad final) como para pruebas unitarias.
"""

from utils.phrase_generator import LENGTH_RANGES


def validate_generated_text(
    text: str,
    length: str,
    accents_required: bool,
    use_enye: bool,
    forbidden_texts=None,
) -> bool:
    """
    Comprueba que un texto generado cumpla todas las reglas antes de
    entregarlo a los jugadores:

    1. Longitud dentro de un rango razonable para el nivel elegido.
    2. Coherencia con la configuración de tildes (verificación básica).
    3. Coherencia con la configuración de "ñ".
    4. Que no sea idéntico a un texto ya utilizado en la partida.
    5. Que tenga contenido (no esté vacío).
    """
    if not text or not text.strip():
        return False

    min_chars, max_chars = LENGTH_RANGES.get(length, LENGTH_RANGES["medium"])
    # Se usa un margen de tolerancia porque la generación combina frases
    # completas y no siempre cae exactamente en el rango.
    if not (min_chars * 0.7 <= len(text) <= max_chars * 1.5):
        return False

    if not use_enye and "ñ" in text.lower():
        return False

    if not accents_required:
        tildes = "áéíóúÁÉÍÓÚ"
        if any(ch in text for ch in tildes):
            return False

    forbidden = set(forbidden_texts or [])
    if text in forbidden:
        return False

    return True


def normalize_for_comparison(text: str, accents_required: bool) -> str:
    """
    Normaliza un texto escrito por el jugador para compararlo con el
    texto original, respetando la regla de tildes configurada.

    Esta función es la base de la validación carácter por carácter que
    hace el servidor en services/game_service.submit_player_finish, la
    única autoridad sobre si un jugador realmente terminó una ronda.
    """
    if accents_required:
        return text

    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
    }
    return "".join(replacements.get(ch, ch) for ch in text)
