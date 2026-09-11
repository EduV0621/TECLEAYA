"""
utils/phrase_generator.py

Generador procedural de textos en español para el juego de mecanografía.

No se guardan textos completos escritos a mano: se construyen
combinando vocabulario real (agrupado por categorías) con distintas
plantillas gramaticales, conectores y párrafos, hasta alcanzar la
longitud aproximada solicitada.

Uso principal:

    from utils.phrase_generator import generate_text

    texto = generate_text(length="medium", accents_required=True, use_enye=True)

El resultado es siempre una única línea de texto (sin saltos de línea
artificiales); el salto visual lo resuelve el navegador según el ancho
de pantalla.
"""

import random
import re
import unicodedata

# ---------------------------------------------------------------------------
# 1. VOCABULARIO POR CATEGORÍAS
# ---------------------------------------------------------------------------
# Cada lista contiene palabras reales del español. Se evita mezclar
# palabras inventadas. Las palabras con "ñ" están marcadas aparte para
# poder filtrarlas fácilmente cuando el anfitrión desactiva la "ñ".

SUJETOS = [
    "el profesor", "la doctora", "mi hermano", "la vecina", "el ingeniero",
    "la estudiante", "el cocinero", "mi abuela", "el piloto", "la escritora",
    "el jardinero", "la programadora", "el músico", "mi prima", "el capitán",
    "la periodista", "el entrenador", "la científica", "el carpintero",
    "la enfermera", "el turista", "la fotógrafa", "el mecánico", "la actriz",
]

SUJETOS_ENYE = [
    "el pequeño niño", "la niña curiosa", "el compañero de mi año",
    "la señora del mercado", "el dueño del taller",
]

PERSONAS_PLURAL = [
    "los estudiantes", "los vecinos", "los turistas", "los jugadores",
    "las familias", "los amigos", "los músicos", "los viajeros",
]

ANIMALES = [
    "el perro", "el gato", "el caballo", "el delfín", "el águila",
    "la tortuga", "el elefante", "el león", "el lobo", "el búho",
]

ANIMALES_ENYE = ["el pequeño cordero", "el rebaño de ovejas"]

OBJETOS = [
    "un libro", "una taza de café", "una mochila", "un teléfono", "una cámara",
    "un cuaderno", "una bicicleta", "un paraguas", "una maleta", "un reloj",
    "una guitarra", "un mapa antiguo", "una carta", "un balón", "una lámpara",
]

LUGARES_NOMBRE = [
    "el parque", "la biblioteca", "el mercado", "la playa",
    "la montaña", "el aeropuerto", "la estación de tren",
    "el centro de la ciudad", "el jardín botánico", "la plaza principal",
    "el museo", "la universidad", "el estadio", "el puerto",
]

LUGARES_NOMBRE_ENYE = ["la cabaña de madera", "el pequeño pueblo montañoso"]

# Versión con la preposición "en" ya incluida, para plantillas del tipo
# "[sujeto] [verbo] [lugar]" (ej. "camina en el parque").
LUGARES = ["en " + nombre for nombre in LUGARES_NOMBRE]
LUGARES_ENYE = ["en " + nombre for nombre in LUGARES_NOMBRE_ENYE]

CIUDADES = [
    "Lima", "Bogotá", "Santiago", "Buenos Aires", "Madrid", "Barcelona",
    "Ciudad de México", "Montevideo", "Quito", "La Habana", "San José",
]

PAISES = [
    "Perú", "Colombia", "Chile", "Argentina", "España", "México",
    "Uruguay", "Ecuador", "Bolivia", "Paraguay", "Costa Rica",
]

NATURALEZA = [
    "el bosque", "el río", "la montaña", "el volcán", "la selva",
    "el desierto", "el océano", "la cascada", "el valle", "la pradera",
]

TECNOLOGIA = [
    "una aplicación nueva", "un programa de computadora", "una inteligencia artificial",
    "un dispositivo electrónico", "una red social", "un videojuego", "un robot",
    "una página web", "un sistema operativo",
]

ESCUELA = [
    "la tarea de matemáticas", "el examen final", "la clase de historia",
    "el proyecto escolar", "la biblioteca del colegio", "el laboratorio de ciencias",
]

UNIVERSIDAD = [
    "la facultad de ingeniería", "el laboratorio de investigación",
    "la conferencia de física", "el seminario de literatura",
]

DEPORTES = [
    "el fútbol", "el baloncesto", "el atletismo", "la natación",
    "el ciclismo", "el tenis", "el vóleibol", "el ajedrez",
]

TRANSPORTE = [
    "el autobús", "el tren", "el avión", "la bicicleta", "el barco",
    "el metro", "el automóvil", "la motocicleta",
]

COMIDA = [
    "una sopa caliente", "un plato de pasta", "una ensalada fresca",
    "un postre de chocolate", "una pizza casera", "un jugo de frutas",
    "un pan recién horneado",
]

MUSICA = [
    "una canción antigua", "un concierto en vivo", "una melodía suave",
    "un nuevo álbum", "una orquesta local",
]

VIDEOJUEGOS = [
    "un videojuego de aventuras", "un torneo en línea", "una nueva consola",
    "un juego de estrategia",
]

VIAJES = [
    "un viaje inolvidable", "una excursión de fin de semana", "un recorrido por la ciudad",
    "una travesía por la costa",
]

TRABAJO = [
    "el proyecto de la oficina", "la reunión importante", "el informe mensual",
    "la nueva propuesta", "el equipo de trabajo",
]

ACTIVIDADES = [
    "leer un buen libro", "practicar algún deporte", "cocinar una nueva receta",
    "pintar un cuadro", "escuchar música", "aprender un idioma",
    "caminar por la ciudad", "escribir una historia",
]

VERBOS_SIMPLES = [
    "camina", "corre", "observa", "explora", "visita", "recuerda",
    "estudia", "trabaja", "descansa", "sonríe", "escucha", "viaja",
]

VERBOS_ENYE = ["enseña", "sueña", "diseña", "añade"]


# Adjetivos "epicenos" (misma forma para masculino y femenino), para
# evitar errores de concordancia de género al combinarlos con
# sustantivos de distinto género dentro de las plantillas.
ADJETIVOS = [
    "sorprendente", "interesante", "impresionante", "importante",
    "memorable", "especial", "notable", "brillante", "increíble",
    "agradable",
]

MOMENTOS_DIA = [
    "por la mañana", "por la tarde", "por la noche", "al amanecer",
    "al atardecer", "durante la madrugada",
]

MOMENTOS_ENYE = ["cada año", "este otoño"]

# Formas "desnudas" (sin preposición) para plantillas que ya anteponen
# su propia preposición, como "durante {momento}".
MOMENTOS_NOMBRE = ["la mañana", "la tarde", "la noche", "el amanecer", "el atardecer", "la madrugada"]
MOMENTOS_NOMBRE_ENYE = ["cada año", "este otoño"]

CLIMA = [
    "bajo un cielo despejado", "en medio de una lluvia suave",
    "con un viento fresco", "durante una tormenta lejana",
]

RAZONES = [
    "porque quería relajarse", "porque tenía mucho tiempo libre",
    "porque necesitaba un cambio", "porque era su día de descanso",
    "porque le gustaba mucho ese lugar", "porque alguien se lo había recomendado",
]

CONECTORES = [
    "además", "sin embargo", "después", "mientras tanto", "por eso",
    "finalmente", "aunque", "luego", "también", "debido a esto",
]

SITUACIONES = [
    "el tiempo era difícil", "el camino era largo", "había mucho ruido",
    "todo parecía complicado", "el día había comenzado tarde",
]


def _contains_enye(text: str) -> bool:
    return "ñ" in text.lower()


def _pool(base_list, enye_list, use_enye: bool):
    """
    Combina la lista base con la lista de variantes con "ñ" si está
    permitido. Si no está permitido, filtra cualquier elemento con "ñ"
    de la lista base también, por seguridad.
    """
    pool = list(base_list)
    if use_enye:
        pool += enye_list
    else:
        pool = [w for w in pool if not _contains_enye(w)]
    return pool


def _choice(pool):
    return random.choice(pool)


def _choice_two_distinct(pool):
    """Elige dos elementos distintos de la lista cuando sea posible,
    para evitar frases como 'quería X, pero tuvo que X'."""
    if len(pool) < 2:
        first = _choice(pool)
        return first, first
    first, second = random.sample(pool, 2)
    return first, second


# ---------------------------------------------------------------------------
# 2. PLANTILLAS GRAMATICALES
# ---------------------------------------------------------------------------
# Cada plantilla es una función que recibe el "vocabulario disponible"
# (ya filtrado según ñ) y devuelve una frase con la primera letra en
# mayúscula y punto final.

def _tpl_sujeto_verbo_lugar(v):
    return f"{_choice(v['sujetos']).capitalize()} {_choice(v['verbos'])} {_choice(v['lugares'])}."


def _tpl_momento_sujeto_verbo_lugar_accion(v):
    return (
        f"{_choice(v['momentos']).capitalize()}, {_choice(v['sujetos'])} "
        f"{_choice(v['verbos'])} {_choice(v['lugares'])} antes de "
        f"{_choice(v['actividades'])}."
    )


def _tpl_despues_de_accion(v):
    primera, segunda = _choice_two_distinct(v["actividades"])
    return (
        f"Después de {primera}, {_choice(v['sujetos'])} decidió "
        f"{segunda} {_choice(v['razones'])}."
    )


def _tpl_aunque_situacion(v):
    return (
        f"Aunque {_choice(v['situaciones'])}, {_choice(v['sujetos'])} quiso "
        f"{_choice(v['actividades'])} durante {_choice(v['momentos_nombre'])}."
    )


def _tpl_mientras_accion(v):
    return (
        f"Cerca de {_choice(v['lugares_nombre'])}, {_choice(v['sujetos'])} "
        f"observó {_choice(v['objetos'])} y pensó en {_choice(v['actividades'])}."
    )


def _tpl_queria_pero(v):
    primera, segunda = _choice_two_distinct(v["actividades"])
    return (
        f"{_choice(v['sujetos']).capitalize()} quería {primera}, "
        f"pero primero tuvo que {segunda}."
    )


def _tpl_cada_manana(v):
    return (
        f"Cada mañana, {_choice(v['sujetos'])} {_choice(v['verbos'])} antes de "
        f"{_choice(v['actividades'])}."
    )


def _tpl_durante_la_tarde(v):
    return (
        f"Durante la tarde, {_choice(v['sujetos'])} encontró {_choice(v['objetos'])} "
        f"y decidió {_choice(v['actividades'])}."
    )


def _tpl_viaje_ciudad(v):
    return (
        f"{_choice(v['sujetos']).capitalize()} viajó hasta {_choice(v['ciudades'])}, "
        f"en {_choice(v['paises'])}, para conocer {_choice(v['naturaleza'])}."
    )


def _tpl_animal_naturaleza(v):
    return (
        f"{_choice(v['animales']).capitalize()} descansaba cerca de "
        f"{_choice(v['naturaleza'])} {_choice(v['clima'])}."
    )


def _tpl_grupo_deporte(v):
    return (
        f"{_choice(v['personas_plural']).capitalize()} practicaban "
        f"{_choice(v['deportes'])} {_choice(v['lugares'])} {_choice(v['momentos'])}."
    )


def _tpl_tecnologia(v):
    return (
        f"{_choice(v['sujetos']).capitalize()} descubrió {_choice(v['tecnologia'])} "
        f"que resultó {_choice(v['adjetivos'])} y muy útil para el trabajo."
    )


def _tpl_transporte(v):
    return (
        f"{_choice(v['sujetos']).capitalize()} tomó {_choice(v['transporte'])} para "
        f"llegar a {_choice(v['lugares_nombre'])} durante {_choice(v['momentos_nombre'])}."
    )


def _tpl_comida(v):
    return (
        f"{_choice(v['sujetos']).capitalize()} preparó {_choice(v['comida'])} "
        f"para compartir con {_choice(v['personas_plural'])}."
    )


def _tpl_trabajo(v):
    return (
        f"En {_choice(v['trabajo'])}, {_choice(v['sujetos'])} propuso una idea "
        f"{_choice(v['adjetivos'])} que sorprendió a todos."
    )


TEMPLATES = [
    _tpl_sujeto_verbo_lugar,
    _tpl_momento_sujeto_verbo_lugar_accion,
    _tpl_despues_de_accion,
    _tpl_aunque_situacion,
    _tpl_mientras_accion,
    _tpl_queria_pero,
    _tpl_cada_manana,
    _tpl_durante_la_tarde,
    _tpl_viaje_ciudad,
    _tpl_animal_naturaleza,
    _tpl_grupo_deporte,
    _tpl_tecnologia,
    _tpl_transporte,
    _tpl_comida,
    _tpl_trabajo,
]


# ---------------------------------------------------------------------------
# 3. CONSTRUCCIÓN DEL VOCABULARIO DISPONIBLE SEGÚN CONFIGURACIÓN
# ---------------------------------------------------------------------------

def _build_vocab(use_enye: bool) -> dict:
    return {
        "sujetos": _pool(SUJETOS, SUJETOS_ENYE, use_enye),
        "personas_plural": PERSONAS_PLURAL,
        "animales": _pool(ANIMALES, ANIMALES_ENYE, use_enye),
        "objetos": OBJETOS,
        "lugares": _pool(LUGARES, LUGARES_ENYE, use_enye),
        "lugares_nombre": _pool(LUGARES_NOMBRE, LUGARES_NOMBRE_ENYE, use_enye),
        "ciudades": CIUDADES,
        "paises": PAISES,
        "naturaleza": NATURALEZA,
        "tecnologia": TECNOLOGIA,
        "escuela": ESCUELA,
        "universidad": UNIVERSIDAD,
        "deportes": DEPORTES,
        "transporte": TRANSPORTE,
        "comida": COMIDA,
        "musica": MUSICA,
        "videojuegos": VIDEOJUEGOS,
        "viajes": VIAJES,
        "trabajo": TRABAJO,
        "actividades": ACTIVIDADES,
        "verbos": _pool(VERBOS_SIMPLES, VERBOS_ENYE, use_enye),
        "adjetivos": ADJETIVOS,
        "momentos": _pool(MOMENTOS_DIA, MOMENTOS_ENYE, use_enye),
        "momentos_nombre": _pool(MOMENTOS_NOMBRE, MOMENTOS_NOMBRE_ENYE, use_enye),
        "clima": CLIMA,
        "razones": RAZONES,
        "situaciones": SITUACIONES,
    }


# ---------------------------------------------------------------------------
# 4. NORMALIZACIÓN DE TILDES
# ---------------------------------------------------------------------------

def _strip_accents_keep_enye(text: str) -> str:
    """
    Elimina las tildes de vocales (á->a, é->e, í->i, ó->o, ú->u) pero
    mantiene la "ñ" intacta (no es una tilde, es una letra distinta).
    El texto sigue estando bien escrito ortográficamente en su versión
    "con tildes"; esta función solo se usa para generar la variante que
    el jugador puede escribir sin tildes cuando estas no son obligatorias.
    """
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


# ---------------------------------------------------------------------------
# 5. LÍMITES DE LONGITUD POR NIVEL
# ---------------------------------------------------------------------------
# Los límites están pensados en caracteres, para acercarse de forma
# orientativa a la cantidad de líneas visuales pedida (sin insertar
# saltos de línea artificiales).

LENGTH_RANGES = {
    "short": (170, 260),
    "medium": (320, 480),
    "long": (600, 850),
}


_CONTRACTION_RE = re.compile(r"\b([Dd]e|[Aa]) el\b")


def _apply_contractions(text: str) -> str:
    """
    Aplica las contracciones obligatorias del español "de + el = del"
    y "a + el = al", preservando la mayúscula inicial si corresponde.
    Se aplica como paso final sobre el texto ya construido, ya que
    varias plantillas combinan preposiciones con lugares que empiezan
    en "el" (ej. "el bosque", "el centro de la ciudad").
    """

    def _replace(match: "re.Match") -> str:
        word = match.group(1)
        if word == "De":
            return "Del"
        if word == "de":
            return "del"
        if word == "A":
            return "Al"
        return "al"

    return _CONTRACTION_RE.sub(_replace, text)


def _generate_paragraph(vocab: dict, target_chars: int) -> str:
    """Construye un párrafo combinando frases de distintas plantillas
    y conectores, hasta acercarse a la longitud objetivo."""
    sentences = []
    used_templates = []

    while True:
        # Evita repetir la misma plantilla dos veces seguidas cuando es posible.
        available = [t for t in TEMPLATES if t not in used_templates[-2:]]
        template = random.choice(available if available else TEMPLATES)
        sentence = template(vocab)

        # Ocasionalmente antepone un conector para dar fluidez al párrafo.
        if sentences and random.random() < 0.35:
            connector = _choice(CONECTORES)
            sentence = f"{connector.capitalize()}, {sentence[0].lower()}{sentence[1:]}"

        sentences.append(sentence)
        used_templates.append(template)

        current_length = len(" ".join(sentences))
        if current_length >= target_chars:
            break

        # Salvaguarda para evitar bucles excesivamente largos.
        if len(sentences) > 40:
            break

    return _apply_contractions(" ".join(sentences))


def _apply_accents_rule(text: str, accents_required: bool) -> str:
    if accents_required:
        return text
    return _strip_accents_keep_enye(text)


def _passes_enye_filter(text: str, use_enye: bool) -> bool:
    if use_enye:
        return True
    return "ñ" not in text.lower()


def generate_text(
    length: str = "medium",
    accents_required: bool = True,
    use_enye: bool = True,
    forbidden_texts=None,
    max_attempts: int = 25,
) -> str:
    """
    Genera un texto procedural en español.

    Parámetros:
        length: "short" | "medium" | "long"
        accents_required: si es False, el texto se devuelve sin tildes
            (manteniendo la "ñ" intacta).
        use_enye: si es False, el generador evita por completo cualquier
            palabra que contenga "ñ" (no la reemplaza por "n").
        forbidden_texts: colección de textos ya usados en la partida,
            para evitar repetir exactamente el mismo texto.
        max_attempts: intentos máximos antes de rendirse.

    Devuelve una cadena de texto en una sola línea.
    """
    if length not in LENGTH_RANGES:
        length = "medium"

    forbidden = set(forbidden_texts or [])
    min_chars, max_chars = LENGTH_RANGES[length]
    target_chars = random.randint(min_chars, max_chars)

    vocab = _build_vocab(use_enye)

    last_candidate = None

    for _ in range(max_attempts):
        raw_text = _generate_paragraph(vocab, target_chars)

        # Filtro de longitud (con tolerancia razonable).
        if not (min_chars * 0.8 <= len(raw_text) <= max_chars * 1.3):
            last_candidate = raw_text
            continue

        # Filtro de ñ (comprobación final por seguridad, aunque el
        # vocabulario ya está filtrado).
        if not _passes_enye_filter(raw_text, use_enye):
            continue

        candidate = _apply_accents_rule(raw_text, accents_required)

        # Filtro de repetición dentro de la misma partida.
        if candidate in forbidden:
            last_candidate = candidate
            continue

        return candidate

    # Si tras varios intentos no se logró un resultado ideal, se devuelve
    # el último candidato válido en cuanto a contenido, para no bloquear
    # el flujo del juego.
    if last_candidate:
        return _apply_accents_rule(last_candidate, accents_required)

    # Último recurso absoluto: nunca debería llegar aquí.
    return _apply_accents_rule(_generate_paragraph(vocab, target_chars), accents_required)
