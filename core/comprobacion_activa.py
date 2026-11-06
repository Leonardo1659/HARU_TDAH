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


def _opciones_numericas(correcto: int, semilla: int = 0) -> List[str]:
    deltas = [2, -2, 1, -1, 3, 4]
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
) -> Dict:
    """
    Construye un reto breve y amigable de comprobación activa adaptado al contenido del paso.
    Retorna un diccionario con:
      - `tipo`: 'matematica' | 'copia_operacion' | 'color' | 'dibujo' | 'material' | 'lectura'
      - `pregunta`: texto claro que Haru muestra y pronuncia en voz alta
      - `opciones`: 3 o 4 botones grandes para respuesta táctil rápida
      - `respuestas_validas`: conjunto normalizado de respuestas válidas (botones o voz)
      - `numeros_validos`: conjunto opcional de enteros aceptados por voz
      - `acepta_voz_descriptiva`: bool para pasos de lectura/redacción abierta
    """
    norm = _normalizar(texto_paso)
    ops_paso = _extraer_operaciones_del_texto(texto_paso)

    # Extraer también operaciones de pasos previos de la misma misión por si el niño dice el total final
    ops_contexto: List[Tuple[str, int]] = []
    if contexto_pasos:
        for p_ant in contexto_pasos:
            ops_contexto.extend(_extraer_operaciones_del_texto(p_ant))

    es_solo_copiar = any(
        fr in norm for fr in ("escribe la suma", "escribe la resta", "copia la operacion", "anota la operacion", "escribe la operacion")
    )
    tiene_verbo_calculo = any(
        v in norm for v in ("suma", "resta", "multiplica", "divide", "calcula", "resuelve", "cuanto", "resultado", "unidades")
    )

    # 1. Paso de cálculo matemático (ej. "Suma primero las unidades (5 más 7)...")
    if ops_paso and tiene_verbo_calculo and not es_solo_copiar:
        etiqueta_op, resultado = ops_paso[0]
        numeros_ok = {resultado}
        for _etq_c, res_c in ops_paso[1:] + ops_contexto:
            numeros_ok.add(res_c)

        opciones = _opciones_numericas(resultado, semilla=numero_paso)
        return {
            "tipo": "matematica",
            "pregunta": f"¡Comprobación rápida! Dime el resultado en voz alta o toca el botón: ¿cuánto es {etiqueta_op}?",
            "opciones": opciones,
            "respuesta_principal": str(resultado),
            "respuestas_validas": {str(n) for n in numeros_ok},
            "numeros_validos": numeros_ok,
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
            "pregunta": "¡Comprobemos tu cuaderno! Toca o dime en voz alta qué operación acabas de escribir:",
            "opciones": opciones,
            "respuesta_principal": etiqueta_op,
            "respuestas_validas": {_normalizar(etiqueta_op), str(resultado)},
            "numeros_validos": {resultado, a_val},
            "acepta_voz_descriptiva": False,
        }

    # 3. Paso con colores específicos mencionados (ej. "azul, amarillo y verde")
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
            "acepta_voz_descriptiva": False,
        }

    # 4. Paso de dibujo libre o creativo (ej. "Haz un pequeño dibujo...", "Dibuja un sol brillante y un río...")
    if any(p in norm for p in ("dibuja", "dibujo", "colorea", "pinta")):
        # Si menciona elementos concretos como sol, río, nube o lluvia, preguntar por ellos
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
                "acepta_voz_descriptiva": False,
            }

        # Dibujo libre: el niño elige o dice el color que usó
        opciones_col = ["Azul", "Rojo", "Amarillo", "Verde"]
        todos_colores = {tok for _e, tok in _COLORES_CATALOGO} | {"celeste", "turquesa", "violeta", "negro", "blanco"}
        return {
            "tipo": "color_libre",
            "pregunta": "¡Qué gran artista! Presiona el botón o dime en voz alta el color que usaste para dibujar:",
            "opciones": opciones_col,
            "respuesta_principal": opciones_col[0],
            "respuestas_validas": todos_colores,
            "numeros_validos": set(),
            "acepta_voz_descriptiva": True,
        }

    # 5. Paso de lectura activa, personaje o redacción comprensiva
    if re.search(r"\b(lee|leer|leiste|parrafo|personaje|oracion)\b", norm):
        etiqueta_ok = "Ya lo leí y respondí"
        opciones = [etiqueta_ok, "Todavía no empecé", "Me salté la lectura"]
        return {
            "tipo": "lectura",
            "pregunta": "¡Cuéntame en voz alta una palabrita de lo que leíste/escribiste o confirma tu avance!",
            "opciones": opciones,
            "respuesta_principal": etiqueta_ok,
            "respuestas_validas": {_normalizar(etiqueta_ok), "ya lo lei", "listo", "personaje", "parrafo"},
            "numeros_validos": set(),
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
        return {
            "tipo": "material",
            "pregunta": "¡Comprobemos juntos! Toca o dime en voz alta qué material escolar usaste en este paso:",
            "opciones": opciones,
            "respuesta_principal": etiqueta_correcta,
            "respuestas_validas": vocab_valido,
            "numeros_validos": set(),
            "acepta_voz_descriptiva": False,
        }

    # Respaldo universal para cualquier paso personalizado escrito por el docente
    etiqueta_gen = f"Sí, completé el paso {numero_paso}"
    opciones = [etiqueta_gen, "Todavía me falta hacerlo", "Quiero leer el paso otra vez"]
    return {
        "tipo": "general",
        "pregunta": f"¡Antes de avanzar! Cuéntame en voz alta qué hiciste en el paso {numero_paso} o confirma aquí:",
        "opciones": opciones,
        "respuesta_principal": etiqueta_gen,
        "respuestas_validas": {_normalizar(etiqueta_gen), "si", "ya lo hice", "completado", "termine"},
        "numeros_validos": set(),
        "acepta_voz_descriptiva": True,
    }


_RESPUESTAS_NEGATIVAS = {
    "no", "nada", "no se", "nose", "todavia", "todavia no", "todavia no empece",
    "todavia me falta hacerlo", "quiero leer el paso otra vez", "me salte la lectura",
    "un juguete de recreo", "el control de la tele", "un auto de carreras", "un televisor",
    "un balon de futbol", "un cohete espacial",
}


def validar_respuesta_reto(reto: Dict, respuesta_usuario: str) -> Tuple[bool, str]:
    """
    Evalúa sin castigos la respuesta elegida o hablada por el estudiante.
    Retorna `(es_correcta, mensaje_retroalimentacion)`.
    """
    resp_norm = _normalizar(respuesta_usuario)
    if not resp_norm:
        return False, "Toca una de las opciones o dime tu respuesta con el micrófono."

    if resp_norm in _RESPUESTAS_NEGATIVAS:
        return (
            False,
            "¡Qué honesto eres! Tómate tu tiempo para terminar este pasito y vuelve a presionar ¡Paso Listo!.",
        )

    validas = {_normalizar(v) for v in reto.get("respuestas_validas", set())}
    principal_norm = _normalizar(reto.get("respuesta_principal", ""))
    if principal_norm:
        validas.add(principal_norm)

    # Coincidencia directa con botón u opción válida
    if resp_norm in validas:
        return True, "¡Excelente comprobación! Se nota que hiciste tu paso con mucha atención."

    # Validación numérica (dígitos o números dichos en voz alta como "doce" o "me salió doce")
    numeros_validos = set(reto.get("numeros_validos") or set())
    if numeros_validos:
        nums_dichos = extraer_numeros_de_respuesta(resp_norm)
        if any(n in numeros_validos for n in nums_dichos):
            return True, "¡Súper bien calculado! ¡Respuesta correcta!"

    # Coincidencia por palabra clave contenida en una frase hablada (ej. "usé el color azul", "saqué mi cuaderno")
    palabras_resp = set(re.findall(r"[a-z0-9ñ]+", resp_norm))
    for v in validas:
        if v and (v in palabras_resp or (len(v) >= 4 and v in resp_norm)):
            return True, "¡Muy bien dicho! Comprobación superada."

    # En pasos abiertos de lectura/redacción, aceptar si el niño expresa una idea real con su voz/texto
    if reto.get("acepta_voz_descriptiva") and len(resp_norm) >= 3 and len(palabras_resp) >= 1:
        # Verificar que no haya tocado uno de los botones distractores del propio reto
        opciones_norm = {_normalizar(op) for op in reto.get("opciones", [])}
        if resp_norm not in opciones_norm:
            return True, "¡Qué bien me lo contaste! Sigamos al siguiente paso."

    return (
        False,
        "¡Casi, casi! Revisa tu cuaderno o lee el paso con calma e inténtalo otra vez.",
    )

