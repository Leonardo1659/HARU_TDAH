"""
Motor de Comprobación Activa (Opción B — Micro-Validación Interactiva de Haru)
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Previene el avance impulsivo ("clic automático" característico de la impulsividad
en el TDAH) sin recurrir a castigos ni vigilancia invasiva:
- Al presionar «¡Paso Listo!», Haru formula una micro-pregunta amable y contextual
  sobre el paso recién trabajado (operación matemática, color usado, material
  escolar o palabra leída).
- El niño puede responder tocando un botón grande o diciendo la respuesta en voz alta
  con el micrófono (ej. «doce», «azul», «mi cuaderno»).
"""

import random
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from core.ia.calculadora_ast import evaluar_ast_seguro


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (texto or "").lower())
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip()


# Mapa de números hablados en español (0..100) para respuestas por micrófono
_UNIDADES_ES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiun": 21, "veintidos": 22,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}

_DECENAS_ES = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
}


def extraer_numeros_de_respuesta(texto: str) -> List[int]:
    """Extrae números tanto escritos en dígitos ('12') como hablados ('doce', 'treinta y dos')."""
    norm = _normalizar(texto)
    encontrados: List[int] = [int(m) for m in re.findall(r"\b\d+\b", norm)]

    tokens = re.findall(r"[a-zñ]+", norm)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _UNIDADES_ES:
            encontrados.append(_UNIDADES_ES[tok])
            i += 1
            continue
        if tok in _DECENAS_ES:
            val = _DECENAS_ES[tok]
            if i + 2 < len(tokens) and tokens[i + 1] == "y" and tokens[i + 2] in _UNIDADES_ES:
                val += _UNIDADES_ES[tokens[i + 2]]
                i += 3
            elif i + 1 < len(tokens) and tokens[i + 1] in _UNIDADES_ES:
                val += _UNIDADES_ES[tokens[i + 1]]
                i += 2
            else:
                i += 1
            encontrados.append(val)
            continue
        i += 1

    # Eliminar duplicados preservando orden
    vistos = set()
    unicos = []
    for n in encontrados:
        if n not in vistos:
            vistos.add(n)
            unicos.append(n)
    return unicos


def _extraer_operaciones_del_texto(texto: str) -> List[Tuple[str, int]]:
    """
    Detecta expresiones aritméticas simples como '15 + 7', '(5 más 7)', '8 x 4', '20 - 6'.
    Retorna lista de `(expresion_legible, resultado_entero)`.
    """
    norm = _normalizar(texto)
    reemplazos = [
        (r"\bdividido\s+entre\b", "/"),
        (r"\bdividido\s+por\b", "/"),
        (r"\bmultiplicado\s+por\b", "*"),
        (r"\bmas\b", "+"),
        (r"\bmenos\b", "-"),
        (r"(?<=\d)\s*x\s*(?=\d)", " * "),
        (r"\bpor\b", "*"),
    ]
    proc = norm
    for pat, rep in reemplazos:
        proc = re.sub(pat, rep, proc)

    hallazgos: List[Tuple[str, int]] = []
    for m in re.finditer(r"(\d{1,3})\s*([+\-*/])\s*(\d{1,3})", proc):
        a_s, op, b_s = m.group(1), m.group(2), m.group(3)
        expr_py = f"{a_s} {op} {b_s}"
        try:
            res = evaluar_ast_seguro(expr_py)
        except ValueError:
            continue
        if isinstance(res, float) and not res.is_integer():
            continue
        op_vis = {"*": "×", "/": "÷"}.get(op, op)
        etiqueta = f"{int(a_s)} {op_vis} {int(b_s)}"
        hallazgos.append((etiqueta, int(round(res))))
    return hallazgos


def _opciones_numericas(correcto: int, semilla: int = 0, dificil: bool = False) -> List[str]:
    deltas = ([1, -1, 2, -2, 10, -10] if dificil else [2, -2, 3, -3, 1, 4])
    distractores = []
    for d in deltas:
        cand = correcto + d
        if cand >= 0 and cand != correcto and str(cand) not in distractores:
            distractores.append(str(cand))
        if len(distractores) == 2:
            break
    opciones = [str(correcto)] + distractores
    rng = random.Random(correcto * 31 + semilla)
    rng.shuffle(opciones)
    return opciones


_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "en", "con", "por", "para", "y", "o", "u", "su", "sus", "tu", "tus",
    "mi", "mis", "te", "se", "lo", "le", "que", "como", "sobre", "luego",
    "primero", "despues", "ahora", "solo", "cada", "mas", "muy", "bien",
    "paso", "presiona", "listo", "cuando", "termines", "calma", "hoja",
}


def _extraer_palabras_clave_paso(texto_paso: str, contexto_pasos: Optional[List[str]] = None) -> set:
    fuente = f"{texto_paso or ''} {' '.join(contexto_pasos or [])}"
    tokens = re.findall(r"[a-zñ]{3,}", _normalizar(fuente))
    return {t for t in tokens if t not in _STOPWORDS_ES}


def _extraer_frase_clave_paso(texto_paso: str) -> str:
    limpio = re.sub(r"¡?presiona.*?listo!?|cuando termines", "", (texto_paso or ""), flags=re.IGNORECASE).strip()
    limpio = re.sub(r"\s+", " ", limpio).strip(" .,:;¡!¿?")
    if len(limpio) <= 38:
        return limpio or "Trabajar el ejercicio del paso"
    palabras = limpio.split()
    acum = ""
    for pal in palabras:
        cand = f"{acum} {pal}".strip()
        if len(cand) > 36:
            break
        acum = cand
    return acum + "…" if len(acum) < len(limpio) else acum


_COLORES_CATALOGO = [
    ("Azul", "azul"),
    ("Amarillo", "amarillo"),
    ("Verde", "verde"),
    ("Rojo", "rojo"),
    ("Naranja", "naranja"),
    ("Morado", "morado"),
    ("Rosado", "rosado"),
    ("Café", "cafe"),
]

_UTILES_ESCOLARES = [
    (["cuaderno", "libreta"], "Mi cuaderno"),
    (["libro", "cuento"], "Mi libro de lectura"),
    (["lapiz", "lapices"], "Mi lápiz"),
    (["estuche", "cartuchera"], "Mi estuche"),
    (["mochila"], "Mi mochila"),
    (["borrador", "goma"], "Mi borrador"),
    (["regla"], "Mi regla"),
    (["hoja"], "Una hoja limpia"),
]


def generar_reto_paso(
    texto_paso: str,
    numero_paso: int = 1,
    nombre_tarea: str = "",
    contexto_pasos: Optional[List[str]] = None,
    total_pasos: Optional[int] = None,
) -> Dict:
    """
    Construye un reto de comprobación activa adaptado al contenido del paso y con
    dificultad progresiva según el avance del alumno (Paso 1 -> Paso final en cuaderno).
    """
    norm = _normalizar(texto_paso)
    norm_tarea = _normalizar(nombre_tarea)
    norm_contexto = _normalizar(" ".join(contexto_pasos or []))
    ops_paso = _extraer_operaciones_del_texto(texto_paso)
    es_paso_avanzado = numero_paso >= 3 or (total_pasos is not None and total_pasos >= 2 and numero_paso >= total_pasos)
    kws_contexto = _extraer_palabras_clave_paso(texto_paso, contexto_pasos)

    # Extraer operaciones de pasos previos de la misma misión escritas en el cuaderno
    ops_contexto: List[Tuple[str, int]] = []
    if contexto_pasos:
        for p_ant in contexto_pasos:
            ops_contexto.extend(_extraer_operaciones_del_texto(p_ant))

    tiene_verbo_calculo = any(
        v in norm for v in (
            "suma", "resta", "multiplica", "divide", "calcula", "resuelve",
            "cuanto", "resultado", "unidades", "decenas", "revisa", "comprueba", "respuesta",
        )
    )
    es_solo_copiar = any(
        fr in norm for fr in ("escribe la suma", "escribe la resta", "copia la operacion", "anota la operacion", "escribe la operacion")
    ) or (
        bool(ops_paso)
        and any(w in norm for w in ("copia", "anota", "escribe"))
        and not any(w in norm for w in ("resuelve", "calcula", "cuanto", "resultado", "decenas", "revisa", "comprueba"))
    )

    # 1. Paso avanzado matemático (Paso 3+ o cierre): verifica el resultado completo del cuaderno
    if es_paso_avanzado and ops_contexto and any(
        w in norm for w in ("decena", "resultado", "respuesta", "final", "comprueba", "revisa", "voz alta", "total")
    ):
        etiqueta_total, res_total = ops_contexto[0]
        numeros_ok = {res_total}
        for _e, rc in ops_paso + ops_contexto[1:]:
            numeros_ok.add(rc)
        opciones = _opciones_numericas(res_total, semilla=numero_paso + 13, dificil=True)
        return {
            "tipo": "matematica",
            "nivel": "avanzado",
            "pregunta": f"¡Reto final de cuaderno! Ya terminaste tu cálculo: ¿cuánto da en total {etiqueta_total}?",
            "opciones": opciones,
            "respuesta_principal": str(res_total),
            "respuestas_validas": {str(n) for n in numeros_ok},
            "numeros_validos": numeros_ok,
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": False,
        }

    # 1B. Paso de cálculo matemático directo (nivel intermedio o avanzado con operación propia)
    if ops_paso and tiene_verbo_calculo and not es_solo_copiar:
        etiqueta_op, resultado = ops_paso[0]
        numeros_ok = {resultado}
        for _etq_c, res_c in ops_paso[1:] + ops_contexto:
            numeros_ok.add(res_c)

        opciones = _opciones_numericas(resultado, semilla=numero_paso, dificil=es_paso_avanzado)
        pref = "¡Último cálculo de cuaderno!" if es_paso_avanzado else "¡Comprobación rápida!"
        return {
            "tipo": "matematica",
            "nivel": "avanzado" if es_paso_avanzado else "intermedio",
            "pregunta": f"{pref} Dime el resultado en voz alta o toca el botón: ¿cuánto es {etiqueta_op}?",
            "opciones": opciones,
            "respuesta_principal": str(resultado),
            "respuestas_validas": {str(n) for n in numeros_ok},
            "numeros_validos": numeros_ok,
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": False,
        }

    # 1C. Paso avanzado cuando no hay dígitos en el texto actual pero sí operación previa en la misión
    if es_paso_avanzado and ops_contexto:
        etiqueta_total, res_total = ops_contexto[-1]
        numeros_ok = {res_total} | {r for _e, r in ops_contexto}
        opciones = _opciones_numericas(res_total, semilla=numero_paso + 21, dificil=True)
        return {
            "tipo": "matematica",
            "nivel": "avanzado",
            "pregunta": f"¡Verificación de cuaderno! Según lo que resolviste antes, ¿qué resultado dio {etiqueta_total}?",
            "opciones": opciones,
            "respuesta_principal": str(res_total),
            "respuestas_validas": {str(n) for n in numeros_ok},
            "numeros_validos": numeros_ok,
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": False,
        }

    # 2. Paso de copiar/escribir la operación en el cuaderno (ej. "escribe la suma: 15 + 7")
    if ops_paso and es_solo_copiar:
        etiqueta_op, resultado = ops_paso[0]
        partes = re.findall(r"\d+", etiqueta_op)
        a_val = int(partes[0]) if partes else 10
        b_val = int(partes[1]) if len(partes) > 1 else 5
        simbolo = "+" if "+" in etiqueta_op else ("-" if "-" in etiqueta_op else "×")
        distractor_1 = f"{a_val} {simbolo} {max(1, b_val - 3)}"
        distractor_2 = f"{max(2, a_val - 4)} {simbolo} {b_val + 2}"
        opciones = [etiqueta_op, distractor_1, distractor_2]
        rng = random.Random(a_val + b_val + numero_paso)
        rng.shuffle(opciones)
        return {
            "tipo": "copia_operacion",
            "nivel": "intermedio" if numero_paso >= 2 else "inicial",
            "pregunta": "¡Comprobemos tu cuaderno! Toca o dime en voz alta qué operación acabas de escribir:",
            "opciones": opciones,
            "respuesta_principal": etiqueta_op,
            "respuestas_validas": {_normalizar(etiqueta_op), str(resultado)},
            "numeros_validos": {resultado},
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": False,
        }

    # 2.5. Paso de vocabulario de Inglés (colores, animales o conteo bilingüe)
    es_paso_ingles = (
        "en ingles" in norm
        or "ingles" in norm_tarea
        or any(re.search(rf"\b{w}\b", norm) for w in ("blue", "red", "yellow", "green", "cat", "dog", "one, two, three", "hello"))
    )
    if es_paso_ingles:
        if re.search(r"\bblue\b", norm):
            opciones = ["BLUE", "RED", "GREEN"]
            rng = random.Random(numero_paso + 19)
            rng.shuffle(opciones)
            return {
                "tipo": "ingles",
                "pregunta": "¡Reto de Inglés! Toca el botón o dime en voz alta cómo se dice azul en inglés:",
                "opciones": opciones,
                "respuesta_principal": "BLUE",
                "respuestas_validas": {"blue", "azul"},
                "numeros_validos": set(),
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            }
        if re.search(r"\bcat\b", norm):
            opciones = ["CAT", "DOG", "SUN"]
            rng = random.Random(numero_paso + 23)
            rng.shuffle(opciones)
            return {
                "tipo": "ingles",
                "pregunta": "¡Reto de Inglés! Toca el botón o dime en voz alta cómo se dice gatito en inglés:",
                "opciones": opciones,
                "respuesta_principal": "CAT",
                "respuestas_validas": {"cat", "gato", "gatito", "miau"},
                "numeros_validos": set(),
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            }
        if "one" in norm and "two" in norm and "three" in norm:
            opciones = ["One, Two, Three", "Red, Blue, Green", "Cat, Dog, Bird"]
            rng = random.Random(numero_paso + 29)
            rng.shuffle(opciones)
            return {
                "tipo": "ingles",
                "pregunta": "¡Reto de Inglés! Toca el botón o cuenta conmigo 1, 2 y 3 en inglés:",
                "opciones": opciones,
                "respuesta_principal": "One, Two, Three",
                "respuestas_validas": {"one, two, three", "one two three", "one", "two", "three", "uno dos tres"},
                "numeros_validos": {1, 2, 3},
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            }

    # 3. Conceptos temáticos curriculares específicos (Ciencias, Lenguaje, Fracciones) con mayor exigencia en pasos finales
    retos_tematicos = [
        (
            ("evaporacion", "condensacion", "precipitacion", "ciclo del agua"),
            "¡Reto de Ciencias! ¿Cuál es la fase del ciclo del agua en este paso?",
            "Evaporación / Lluvia en nubes" if "vapor" in norm or "lluvia" in norm else "El ciclo del agua en tu hoja",
            ["Fases de un volcán", "Partes de un televisor"],
            {"evaporacion", "condensacion", "precipitacion", "vapor", "nube", "nubes", "lluvia", "agua", "sol"},
        ),
        (
            ("planeta", "planetas", "sistema solar", "mercurio", "saturno", "orbitas"),
            "¡Reto de Ciencias! ¿Qué elementos dibujaste o ubicaste del Sistema Solar?",
            "El Sol y los planetas en órbita",
            ["Nubes de lluvia y ríos", "Partes de una bicicleta"],
            {"sol", "tierra", "planeta", "planetas", "mercurio", "venus", "marte", "jupiter", "saturno", "orbita", "orbitas"},
        ),
        (
            ("fotosintesis", "clorofila", "raices", "oxigeno"),
            "¡Reto de Ciencias! Según tu esquema, ¿qué producen o toman las plantas?",
            "Toman luz/agua y dan oxígeno",
            ["Fabrican plástico y metal", "Necesitan electricidad"],
            {"fotosintesis", "luz", "sol", "agua", "aire", "oxigeno", "hojas", "raices", "planta", "plantas"},
        ),
        (
            ("verbo", "verbos", "accion"),
            "¡Reto de Lenguaje! En este paso, ¿qué palabra funciona como VERBO (acción)?",
            "Correr / Leer / Dibujar (acción)",
            ["Cuaderno / Mesa / Azul", "Ninguna acción"],
            {"verbo", "verbos", "accion", "correr", "leer", "dibujar", "saltar", "escribir", "estudiar"},
        ),
        (
            ("sustantivo", "sustantivos"),
            "¡Reto de Lenguaje! En tu cuaderno, ¿qué nombra un SUSTANTIVO?",
            "Personas, cosas o lugares",
            ["Solo signos de suma y resta", "Números sin palabras"],
            {"sustantivo", "sustantivos", "persona", "personas", "cosas", "lugares", "bolivia", "cuaderno", "mesa"},
        ),
        (
            ("fraccion", "fracciones", "numerador", "denominador"),
            "¡Reto de Fracciones! En una fracción, ¿qué indica el número de abajo (denominador)?",
            "Partes iguales del entero",
            ["Solo el color del lápiz", "La fecha del cuaderno"],
            {"numerador", "denominador", "partes", "iguales", "mitad", "cuarto", "entero", "fraccion"},
        ),
    ]
    for triggers, preg_t, ok_t, dist_t, valid_kws in retos_tematicos:
        if any(tr in norm for tr in triggers):
            opciones = [ok_t] + dist_t
            rng = random.Random(len(texto_paso) + numero_paso * 7)
            rng.shuffle(opciones)
            return {
                "tipo": "conocimiento",
                "nivel": "avanzado" if es_paso_avanzado else "intermedio",
                "pregunta": preg_t,
                "opciones": opciones,
                "respuesta_principal": ok_t,
                "respuestas_validas": {_normalizar(ok_t)} | valid_kws,
                "numeros_validos": set(),
                "palabras_clave": kws_contexto | valid_kws,
                "acepta_voz_descriptiva": False,
            }

    # 3.5. Paso con colores específicos mencionados (ej. "azul, amarillo y verde")
    colores_en_paso = [(etq, tok) for etq, tok in _COLORES_CATALOGO if re.search(rf"\b{tok}\b", norm)]
    if colores_en_paso:
        principal_etq, _principal_tok = colores_en_paso[0]
        tokens_ok = {tok for _e, tok in colores_en_paso}
        distractores_col = [
            etq for etq, tok in [("Morado", "morado"), ("Gris", "gris"), ("Café", "cafe"), ("Rosado", "rosado")]
            if tok not in tokens_ok
        ][:2]
        opciones = [principal_etq] + distractores_col
        rng = random.Random(len(texto_paso) + numero_paso)
        rng.shuffle(opciones)
        return {
            "tipo": "color",
            "pregunta": "¡Muy bien! Toca o dime en voz alta uno de los colores que usaste o preparaste en este paso:",
            "opciones": opciones,
            "respuesta_principal": principal_etq,
            "respuestas_validas": tokens_ok,
            "numeros_validos": set(),
            "palabras_clave": tokens_ok,
            "acepta_voz_descriptiva": False,
        }

    # 4. Paso de dibujo libre o creativo (ej. "Haz un pequeño dibujo...", "Dibuja un sol brillante y un río...")
    if any(p in norm for p in ("dibuja", "dibujo", "colorea", "pinta")):
        if "sol" in norm and ("rio" in norm or "mar" in norm):
            opciones = ["El sol y el río", "Un auto de carreras", "Un televisor"]
            rng = random.Random(numero_paso + 7)
            rng.shuffle(opciones)
            return {
                "tipo": "dibujo",
                "pregunta": "¡Qué bonito! Toca o dime en voz alta qué elementos dibujaste en tu hoja:",
                "opciones": opciones,
                "respuesta_principal": "El sol y el río",
                "respuestas_validas": {"el sol y el rio", "sol", "rio", "mar", "agua"},
                "numeros_validos": set(),
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            }
        if "nube" in norm or "lluvia" in norm or "vapor" in norm:
            opciones = ["Nube, vapor y lluvia", "Un balón de fútbol", "Un cohete espacial"]
            rng = random.Random(numero_paso + 11)
            rng.shuffle(opciones)
            return {
                "tipo": "dibujo",
                "pregunta": "¡Súper! Toca o dime en voz alta qué dibujaste para explicar este paso:",
                "opciones": opciones,
                "respuesta_principal": "Nube, vapor y lluvia",
                "respuestas_validas": {"nube, vapor y lluvia", "nube", "nubes", "vapor", "lluvia", "flechas", "flechitas"},
                "numeros_validos": set(),
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            }

        opciones_col = ["Azul", "Rojo", "Amarillo", "Verde"]
        todos_colores = {tok for _e, tok in _COLORES_CATALOGO} | {"celeste", "turquesa", "violeta", "negro", "blanco", "cuento", "historia", "dibujo", "personaje"}
        return {
            "tipo": "color_libre",
            "pregunta": "¡Qué gran artista! Toca el color principal que usaste en tu dibujo o dime qué dibujaste:",
            "opciones": opciones_col,
            "respuesta_principal": opciones_col[0],
            "respuestas_validas": todos_colores | kws_contexto,
            "numeros_validos": set(),
            "palabras_clave": kws_contexto | todos_colores,
            "acepta_voz_descriptiva": False,
        }

    # 5. Paso de lectura activa, personaje o redacción comprensiva (sin botones vacíos)
    if re.search(r"\b(lee|leer|leiste|parrafo|personaje|oracion|cuento)\b", norm):
        if "personaje" in norm:
            etiqueta_ok = "El personaje principal del texto"
            distractores_lec = ["El control del televisor", "La tabla del 9"]
            preg_lec = "¡Comprensión lectora! ¿Qué identificaste o escribiste sobre el cuento en tu cuaderno?"
        elif "oracion" in norm:
            etiqueta_ok = "Mi oración corta sobre el texto"
            distractores_lec = ["Saltarme todo el texto", "Una lista de compras"]
            preg_lec = "¡Reto de cuaderno! ¿Qué anotaste en este paso después de leer?"
        else:
            etiqueta_ok = "Leí el párrafo respetando puntos"
            distractores_lec = ["Cerré el libro sin leer", "Me salté la lectura"]
            preg_lec = "¡Cuéntame en voz alta o escribe una idea de lo que leíste en tu texto!"
        opciones = [etiqueta_ok] + distractores_lec
        rng = random.Random(len(texto_paso) + numero_paso * 3)
        rng.shuffle(opciones)
        return {
            "tipo": "lectura",
            "nivel": "avanzado" if es_paso_avanzado else "intermedio",
            "pregunta": preg_lec,
            "opciones": opciones,
            "respuesta_principal": etiqueta_ok,
            "respuestas_validas": {_normalizar(etiqueta_ok)} | kws_contexto,
            "numeros_validos": set(),
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": True,
        }

    # 6. Paso de alistar materiales escolares u organización (cuaderno, lápiz, libro, mochila, estuche)
    utiles_detectados: List[Tuple[str, List[str]]] = []
    for palabras_clave, etiqueta_util in _UTILES_ESCOLARES:
        if any(re.search(rf"\b{k}\b", norm) for k in palabras_clave):
            utiles_detectados.append((etiqueta_util, palabras_clave))

    if utiles_detectados:
        etiqueta_correcta, _claves = utiles_detectados[0]
        vocab_valido = {_normalizar(etiqueta_correcta)}
        for etq_u, kws in utiles_detectados:
            vocab_valido.add(_normalizar(etq_u))
            vocab_valido.update(kws)

        distractores_mat = ["Un juguete de recreo", "El control de la tele"]
        opciones = [etiqueta_correcta] + distractores_mat
        rng = random.Random(len(texto_paso) + numero_paso)
        rng.shuffle(opciones)
        preg_mat = (
            "¡Última revisión de orden! ¿Qué útil dejaste listo en su lugar?"
            if es_paso_avanzado
            else "¡Comprobemos juntos! Toca o dime en voz alta qué material escolar usaste en este paso:"
        )
        return {
            "tipo": "material",
            "nivel": "avanzado" if es_paso_avanzado else "inicial",
            "pregunta": preg_mat,
            "opciones": opciones,
            "respuesta_principal": etiqueta_correcta,
            "respuestas_validas": vocab_valido | kws_contexto,
            "numeros_validos": set(),
            "palabras_clave": vocab_valido | kws_contexto,
            "acepta_voz_descriptiva": False,
        }

    # 7. Respaldo contextual real basado en el contenido del paso (NUNCA botones vacíos como "Sí, completé el paso")
    frase_clave = _extraer_frase_clave_paso(texto_paso)
    etiqueta_ctx = frase_clave[0].upper() + frase_clave[1:] if frase_clave else "Realizar el ejercicio del paso"
    distractores_ctx = (
        ["Dejar el cuaderno en blanco", "Cambiar a videojuegos"]
        if es_paso_avanzado
        else ["No hacer nada todavía", "Guardar todo sin avanzar"]
    )
    opciones = [etiqueta_ctx] + distractores_ctx
    rng = random.Random(len(texto_paso) + numero_paso * 11)
    rng.shuffle(opciones)
    pregunta_ctx = (
        f"¡Comprobación final de cuaderno (Paso {numero_paso})! ¿Qué acción clave dejaste hecha en tu trabajo?"
        if es_paso_avanzado
        else f"¡Comprobación de atención (Paso {numero_paso})! Selecciona o cuéntame qué realizaste exactamente:"
    )
    return {
        "tipo": "comprension_paso",
        "nivel": "avanzado" if es_paso_avanzado else "intermedio",
        "pregunta": pregunta_ctx,
        "opciones": opciones,
        "respuesta_principal": etiqueta_ctx,
        "respuestas_validas": {_normalizar(etiqueta_ctx)} | kws_contexto,
        "numeros_validos": set(),
        "palabras_clave": kws_contexto,
        "acepta_voz_descriptiva": False,
    }


_RESPUESTAS_NEGATIVAS = {
    "no", "nada", "no se", "nose", "todavia", "todavia no", "todavia no empece",
    "todavia me falta hacerlo", "quiero leer el paso otra vez", "me salte la lectura",
    "un juguete de recreo", "el control de la tele", "el control del televisor",
    "un auto de carreras", "un televisor", "un balon de futbol", "un cohete espacial",
    "dejar el cuaderno en blanco", "cambiar a videojuegos", "no hacer nada todavia",
    "guardar todo sin avanzar", "cerré el libro sin leer", "cerre el libro sin leer",
    "fases de un volcan", "partes de un televisor", "nubes de lluvia y rios",
    "partes de una bicicleta", "fabrican plastico y metal", "necesitan electricidad",
    "cuaderno / mesa / azul", "ninguna accion", "solo signos de suma y resta",
    "numeros sin palabras", "solo el color del lapiz", "la fecha del cuaderno",
    "saltarme todo el texto", "una lista de compras", "una lista de videojuegos",
    "guarde el libro sin abrir", "dibuje un televisor", "no lei ninguna oracion",
    "cerre mi cuaderno", "la hoja totalmente en blanco",
}

_RESPUESTAS_VACIAS_O_EVASIVAS = {
    "si", "ya", "listo", "ok", "oka", "okey", "okay", "bien", "bueno", "claro",
    "obvio", "perfecto", "genial", "hola", "holi", "jaja", "jajaja", "jeje",
    "asdf", "qwerty", "xxx", "zzz", "cualquier cosa", "no importa", "paso listo",
    "siguiente", "termine", "ya termine", "ya lo hice", "complete", "completado",
    "complete el paso", "complete el ejercicio", "ya complete el paso",
    "ya complete el ejercicio", "hice la tarea", "ya hice la tarea",
}


def _es_afirmacion_vacia(resp_norm: str) -> bool:
    if resp_norm in _RESPUESTAS_VACIAS_O_EVASIVAS:
        return True
    if re.match(
        r"^(?:si|ya|ok|listo|bien|bueno|complete|termine|acabe|hice)\s+(?:todo\s+)?(?:el\s+|la\s+|los\s+|las\s+|mi\s+)?(?:paso|ejercicio|todo|tarea|actividad)\b",
        resp_norm,
    ):
        return True
    return False


def _es_texto_real_descriptivo(resp_norm: str) -> bool:
    """Verifica que una frase libre de lectura tenga sentido real y no sea relleno o garabato."""
    if _es_afirmacion_vacia(resp_norm):
        return False
    palabras = re.findall(r"[a-zñ]+", resp_norm)
    reales = [
        p for p in palabras
        if len(p) >= 2 and re.search(r"[aeiou]", p) and not re.search(r"(.)\1\1\1", p)
    ]
    if len(reales) < 2:
        return False
    contenido = [p for p in reales if len(p) >= 4]
    return len(contenido) >= 1


def validar_respuesta_reto(reto: Dict, respuesta_usuario: str) -> Tuple[bool, str]:
    """
    Evalúa sin castigos la respuesta elegida, escrita o hablada por el estudiante,
    verificando que realmente corresponda al reto y rechazando confirmaciones vacías.
    """
    resp_norm = _normalizar(respuesta_usuario)
    if not resp_norm:
        return False, "Toca una de las opciones o dime tu respuesta con el micrófono."

    if resp_norm in _RESPUESTAS_NEGATIVAS:
        return (
            False,
            "¡Qué honesto eres! Tómate tu tiempo para terminar este pasito y vuelve a presionar ¡Paso Listo!.",
        )

    validas = {_normalizar(v) for v in reto.get("respuestas_validas", set()) if _normalizar(v)}
    principal_norm = _normalizar(reto.get("respuesta_principal", ""))
    if principal_norm:
        validas.add(principal_norm)

    # Coincidencia directa con opción válida del reto
    if resp_norm in validas and not _es_afirmacion_vacia(resp_norm):
        return True, "¡Excelente comprobación! Se nota que hiciste tu paso con mucha atención."

    # Rechazar afirmaciones vacías como "sí", "listo", "completé el ejercicio", "hola", "asdf"
    if _es_afirmacion_vacia(resp_norm):
        return (
            False,
            "Necesito verificar lo que hiciste: dime el dato, resultado o palabra clave del paso (no solo «listo» o «completé»).",
        )

    # Validación numérica (dígitos o números dichos en voz alta como "doce" o "me salió doce")
    numeros_validos = set(reto.get("numeros_validos") or set())
    if numeros_validos:
        nums_dichos = extraer_numeros_de_respuesta(resp_norm)
        if any(n in numeros_validos for n in nums_dichos):
            return True, "¡Súper bien calculado! ¡Respuesta correcta!"

    # Coincidencia por palabra clave real del paso o del reto (excluyendo botones distractores)
    opciones_norm = {_normalizar(op) for op in reto.get("opciones", [])}
    if resp_norm in opciones_norm and resp_norm != principal_norm:
        return (
            False,
            "¡Casi, casi! Esa opción no coincide con tu paso. Revisa tu cuaderno e inténtalo otra vez.",
        )

    palabras_resp = set(re.findall(r"[a-z0-9ñ]+", resp_norm))
    palabras_resp_limpias = palabras_resp - _STOPWORDS_ES - {"paso", "ejercicio", "tarea", "hice", "complete", "listo"}

    if len(palabras_resp_limpias) >= 1:
        for v in validas:
            if not v or v in _RESPUESTAS_VACIAS_O_EVASIVAS:
                continue
            if (len(v) >= 4 and v in palabras_resp_limpias) or (len(v) >= 5 and v in resp_norm):
                return True, "¡Muy bien explicado! Comprobación superada."

        # Coincidencia significativa con conceptos propios del paso (evita aceptar cualquier texto suelto)
        kws_paso = {_normalizar(k) for k in (reto.get("palabras_clave") or set()) if len(_normalizar(k)) >= 4}
        coincidencias = palabras_resp_limpias & kws_paso
        if len(coincidencias) >= 2 or (len(coincidencias) == 1 and len(palabras_resp_limpias) >= 2):
            return True, "¡Excelente! Se nota en tu respuesta lo que trabajaste en el paso."

    # Pasos puramente de lectura abierta: exigir frase real en español (no garabatos ni relleno vacío)
    if reto.get("acepta_voz_descriptiva") and _es_texto_real_descriptivo(resp_norm):
        return True, "¡Qué bien me lo contaste! Sigamos al siguiente paso."

    return (
        False,
        "Tu respuesta no coincide con lo trabajado en este paso. Elige la opción correcta o escribe lo que hiciste en tu cuaderno.",
    )

