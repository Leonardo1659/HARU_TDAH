"""
Motor de Comprobación Activa (Opción B — Micro-Validación Interactiva de Haru)
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Previene el avance impulsivo ("clic automático" característico de la impulsividad
en el TDAH) sin recurrir a castigos ni vigilancia invasiva:
- Al presionar «¡Paso Listo!», Haru formula una micro-pregunta amable y contextual
  sobre el paso recién trabajado (operación matemática, color usado, material
  escolar, vocabulario en inglés o palabra leída).
- El niño puede responder tocando un botón grande o diciendo la respuesta en voz alta
  con el micrófono (ej. «doce», «ciento veinte», «azul», «BLUE», «mi cuaderno»).
"""

import math
import random
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.ia.calculadora_ast import evaluar_ast_seguro

Numero = Union[int, float]

# Registro en memoria de intentos fallidos por reto cuando `intentos` no se pasa explícitamente
_CONTADOR_INTENTOS_RETO: Dict[str, int] = {}


def _normalizar(texto: Any) -> str:
    if texto is None or isinstance(texto, bool):
        return ""
    if not isinstance(texto, str):
        texto = str(texto)
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip()


def _normalizar_num(valor: Numero) -> Numero:
    num = float(valor)
    if math.isnan(num) or math.isinf(num):
        return 0
    redondeado = round(num, 4)
    if abs(redondeado) < 1e-9:
        return 0
    if redondeado.is_integer():
        return int(round(redondeado))
    return redondeado


def _formatear_num_reto(valor: Numero, usar_coma: bool = False) -> str:
    norm_v = _normalizar_num(valor)
    if isinstance(norm_v, int):
        return str(norm_v)
    txt = f"{norm_v:.4f}".rstrip("0").rstrip(".")
    if txt in ("-0", ""):
        txt = "0"
    return txt.replace(".", ",") if usar_coma else txt


# Mapas de números hablados en español (0..1000+) para respuestas por micrófono o texto
_HASTA_29_ES: Dict[str, int] = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiun": 21, "veintiuna": 21, "veintidos": 22,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}

_UNIDADES_1_9_ES: Dict[str, int] = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}

_DECENAS_30_90_ES: Dict[str, int] = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}

_CENTENAS_ES: Dict[str, int] = {
    "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400,
    "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600,
    "setecientos": 700, "setecientas": 700,
    "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}

# Compatibilidad con posibles referencias externas
_UNIDADES_ES = _HASTA_29_ES
_DECENAS_ES = {**_DECENAS_30_90_ES, **_CENTENAS_ES, "mil": 1000}


def _consumir_menor_1000_tokens(tokens: List[str], idx: int) -> Optional[Tuple[int, int]]:
    """Consume una secuencia de palabras numéricas entre 0 y 999 a partir de `tokens[idx]`."""
    n = len(tokens)
    if idx >= n:
        return None

    cur = idx
    total = 0
    consumio = False
    w = tokens[cur]

    if w in _CENTENAS_ES:
        if w == "ciento" and cur > 0 and tokens[cur - 1] == "por":
            return None
        total += _CENTENAS_ES[w]
        consumio = True
        cur += 1

    if cur < n:
        w_cur = tokens[cur]
        if w_cur in _DECENAS_30_90_ES:
            total += _DECENAS_30_90_ES[w_cur]
            consumio = True
            cur += 1
            if cur + 1 < n and tokens[cur] == "y" and tokens[cur + 1] in _UNIDADES_1_9_ES:
                total += _UNIDADES_1_9_ES[tokens[cur + 1]]
                cur += 2
            elif cur < n and tokens[cur] in _UNIDADES_1_9_ES:
                total += _UNIDADES_1_9_ES[tokens[cur]]
                cur += 1
        elif w_cur in _HASTA_29_ES:
            if not (consumio and w_cur == "cero"):
                total += _HASTA_29_ES[w_cur]
                consumio = True
                cur += 1

    if consumio:
        return total, cur
    return None


def _consumir_numero_hablado_tokens(tokens: List[str], idx: int) -> Optional[Tuple[Numero, int]]:
    """Consume un número en palabras en español (0..999999), incluyendo decimales hablados ('tres coma cinco')."""
    n = len(tokens)
    if idx >= n:
        return None

    cur = idx
    bloque1 = _consumir_menor_1000_tokens(tokens, cur)
    if bloque1 is not None:
        val, j = bloque1
        if j < n and tokens[j] == "mil" and val >= 1:
            val = val * 1000
            j += 1
            bloque2 = _consumir_menor_1000_tokens(tokens, j)
            if bloque2 is not None and bloque2[0] >= 1:
                val += bloque2[0]
                j = bloque2[1]
        cur = j
    elif tokens[cur] == "mil":
        if cur + 1 < n and tokens[cur + 1] in ("gracias", "perdon", "disculpas"):
            return None
        val = 1000
        cur += 1
        bloque2 = _consumir_menor_1000_tokens(tokens, cur)
        if bloque2 is not None and bloque2[0] >= 1:
            val += bloque2[0]
            cur = bloque2[1]
    else:
        return None

    # Soporte para decimales hablados: "tres coma cinco", "cero punto cinco"
    if cur + 1 < n and tokens[cur] in ("coma", "punto"):
        sub_dec = _consumir_menor_1000_tokens(tokens, cur + 1)
        if sub_dec is not None:
            dec_val, cur_dec = sub_dec
            val_float = float(f"{val}.{dec_val}")
            return _normalizar_num(val_float), cur_dec

    return _normalizar_num(val), cur


def _equivalencias_numericas(valor: Numero) -> Set[str]:
    """Devuelve representaciones equivalentes (decimal con punto/coma, fracción y porcentaje) de un número."""
    norm_v = _normalizar_num(valor)
    str_punto = _formatear_num_reto(norm_v, usar_coma=False)
    str_coma = _formatear_num_reto(norm_v, usar_coma=True)
    equiv: Set[str] = {str_punto, str_coma}

    mapa_fracciones: List[Tuple[float, Set[str]]] = [
        (0.5, {"1/2", "2/4", "50%", "50 %", "50 por ciento", "cincuenta por ciento", "un medio", "medio", "la mitad", "cero coma cinco", "cero punto cinco"}),
        (0.25, {"1/4", "25%", "25 %", "25 por ciento", "veinticinco por ciento", "un cuarto", "cero coma veinticinco", "cero punto veinticinco"}),
        (0.75, {"3/4", "75%", "75 %", "75 por ciento", "setenta y cinco por ciento", "tres cuartos", "cero coma setenta y cinco", "cero punto setenta y cinco"}),
        (0.2, {"1/5", "20%", "20 %", "20 por ciento", "veinte por ciento", "un quinto", "cero coma dos", "cero punto dos"}),
        (0.1, {"1/10", "10%", "10 %", "10 por ciento", "diez por ciento", "un decimo", "cero coma uno", "cero punto uno"}),
    ]
    for ref, textos in mapa_fracciones:
        if abs(float(norm_v) - ref) < 1e-6:
            equiv.update(textos)
    return equiv


def extraer_numeros_de_respuesta(texto: Any) -> List[Numero]:
    """
    Extrae números escritos en dígitos ('12', '1000', '-5', '0.5', '3,5'),
    fracciones/porcentajes ('1/2', '50%') y hablados en español ('doce',
    'ciento veinte', 'doscientos', 'mil', 'menos tres', 'un medio').
    """
    if isinstance(texto, (int, float)) and not isinstance(texto, bool):
        return [_normalizar_num(texto)]
    norm = _normalizar(texto)
    if not norm:
        return []

    encontrados: List[Numero] = []
    spans_ocupados: List[Tuple[int, int]] = []

    def _span_libre(ini: int, fin: int) -> bool:
        return all(fin <= s_ini or ini >= s_fin for s_ini, s_fin in spans_ocupados)

    # 1. Fracciones escritas como 'a/b' (ej. '1/2', '3/4', '-1/2')
    for m_frac in re.finditer(r"(?<![\d.,])(-?\d+)\s*/\s*(\d+)(?![\d.,])", norm):
        ini, fin = m_frac.span()
        num_i = int(m_frac.group(1))
        den_i = int(m_frac.group(2))
        spans_ocupados.append((ini, fin))
        if den_i != 0:
            encontrados.append(_normalizar_num(num_i / den_i))

    # 2. Porcentajes escritos como '50%' o '12,5%'
    for m_pct in re.finditer(r"(?<![\d.,])(-?\d+(?:[.,]\d+)?)\s*%", norm):
        ini, fin = m_pct.span()
        if not _span_libre(ini, fin):
            continue
        spans_ocupados.append((ini, fin))
        val_p = float(m_pct.group(1).replace(",", "."))
        encontrados.append(_normalizar_num(val_p / 100.0))
        encontrados.append(_normalizar_num(val_p))

    # 3. Números en dígitos (enteros, negativos y decimales con punto o coma)
    for m_num in re.finditer(r"(?<![\d.,])-\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", norm):
        ini, fin = m_num.span()
        if not _span_libre(ini, fin):
            continue
        raw = m_num.group(0).replace(",", ".")
        # Si comienza con '-' pero justo antes hay un dígito o ')' (ej. '15-7'), es resta binaria
        if raw.startswith("-") and ini > 0:
            prev_no_sp = norm[:ini].rstrip()
            if prev_no_sp and (prev_no_sp[-1].isdigit() or prev_no_sp[-1] == ")"):
                raw = raw[1:]
        try:
            encontrados.append(_normalizar_num(float(raw)))
        except ValueError:
            continue

    # 4. Expresiones fraccionarias habladas ('un medio', 'la mitad', 'un cuarto', 'tres cuartos')
    expresiones_frac_habladas: List[Tuple[str, float]] = [
        (r"\bun\s+medio\b", 0.5),
        (r"\bla\s+mitad\b", 0.5),
        (r"\bun\s+cuarto\b", 0.25),
        (r"\btres\s+cuartos\b", 0.75),
        (r"\bun\s+quinto\b", 0.2),
        (r"\bun\s+decimo\b", 0.1),
    ]
    tiene_frac_hablada = False
    for pat_f, val_f in expresiones_frac_habladas:
        if re.search(pat_f, norm):
            encontrados.append(_normalizar_num(val_f))
            tiene_frac_hablada = True

    # 5. Números hablados en palabras en español (0..999999, negativos y 'por ciento')
    tokens = re.findall(r"\d+(?:[.,]\d+)?|[a-zñ]+", norm)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # Evitar extraer '1' de 'un medio' o 'un cuarto' cuando ya se extrajo la fracción hablada
        if tiene_frac_hablada and tok == "un" and i + 1 < len(tokens) and tokens[i + 1] in ("medio", "cuarto", "quinto", "decimo"):
            i += 2
            continue

        signo = 1
        start_idx = i
        if tok in ("menos", "negativo") and i + 1 < len(tokens):
            prev_tok = tokens[i - 1] if i > 0 else ""
            es_prev_num = bool(
                re.fullmatch(r"\d+(?:[.,]\d+)?", prev_tok)
                or prev_tok in _HASTA_29_ES
                or prev_tok in _DECENAS_30_90_ES
                or prev_tok in _CENTENAS_ES
                or prev_tok == "mil"
            )
            if not es_prev_num:
                signo = -1
                start_idx = i + 1

        if signo == -1 and start_idx < len(tokens) and re.fullmatch(r"\d+(?:[.,]\d+)?", tokens[start_idx]):
            val_d = float(tokens[start_idx].replace(",", "."))
            encontrados.insert(0, _normalizar_num(-val_d))
            i = start_idx + 1
            continue

        consumido = _consumir_numero_hablado_tokens(tokens, start_idx)
        if consumido is not None:
            val_hab, next_i = consumido
            val_final = _normalizar_num(signo * val_hab)
            if next_i + 1 < len(tokens) and tokens[next_i] == "por" and tokens[next_i + 1] == "ciento":
                encontrados.append(_normalizar_num(float(val_final) / 100.0))
                encontrados.append(val_final)
                i = next_i + 2
                continue
            encontrados.append(val_final)
            i = next_i
            continue

        i += 1

    # Eliminar duplicados preservando orden (tratando 12 y 12.0 como el mismo número)
    vistos: List[Numero] = []
    unicos: List[Numero] = []
    for n_val in encontrados:
        if not any(
            (isinstance(n_val, int) and isinstance(v, int) and n_val == v)
            or abs(float(n_val) - float(v)) < 1e-6
            for v in vistos
        ):
            vistos.append(n_val)
            unicos.append(n_val)
    return unicos


def _convertir_palabras_numericas_en_operacion(texto_norm: str) -> str:
    """Convierte palabras numéricas en español a dígitos cuando forman parte de texto matemático."""
    matches = list(re.finditer(r"[a-zñ]+", texto_norm))
    if not matches:
        return texto_norm

    tokens = [m.group(0) for m in matches]
    spans = [(m.start(), m.end()) for m in matches]
    n = len(tokens)
    reemplazos: List[Tuple[int, int, str]] = []

    palabras_op = {
        "mas", "menos", "por", "entre", "dividido", "multiplicado",
        "suma", "resta", "multiplica", "divide", "calcula", "resuelve", "cuanto", "es", "da", "igual",
    }

    i = 0
    while i < n:
        # Verificar que todos los tokens consumidos sean contiguos (separados solo por espacios)
        consumido = _consumir_numero_hablado_tokens(tokens, i)
        if consumido is not None:
            val_num, j = consumido
            contiguo = all(
                texto_norm[spans[k][1]:spans[k + 1][0]].isspace()
                for k in range(i, j - 1)
            )
            if not contiguo:
                # Consumir solo el primer token si hubo signos entre palabras
                sub1 = _consumir_numero_hablado_tokens(tokens[: i + 1], i)
                if sub1 is None:
                    i += 1
                    continue
                val_num, j = sub1[0], i + 1

            # Proteger artículos 'un' / 'una' aislados cuando no están junto a operador matemático
            if j == i + 1 and tokens[i] in ("un", "una"):
                prev_w = tokens[i - 1] if i > 0 else ""
                next_w = tokens[j] if j < n else ""
                ctx_izq = texto_norm[max(0, spans[i][0] - 2):spans[i][0]].strip()
                ctx_der = texto_norm[spans[i][1]:min(len(texto_norm), spans[i][1] + 2)].strip()
                if (
                    prev_w not in palabras_op
                    and next_w not in palabras_op
                    and ctx_izq not in {"+", "-", "*", "/", "×", "÷", "="}
                    and ctx_der not in {"+", "-", "*", "/", "×", "÷", "="}
                ):
                    i += 1
                    continue

            reemplazos.append((spans[i][0], spans[j - 1][1], _formatear_num_reto(val_num)))
            i = j
        else:
            i += 1

    if not reemplazos:
        return texto_norm

    partes: List[str] = []
    ultimo = 0
    for ini, fin, num_s in reemplazos:
        partes.append(texto_norm[ultimo:ini])
        partes.append(num_s)
        ultimo = fin
    partes.append(texto_norm[ultimo:])
    return "".join(partes)


def _formatear_etiqueta_expresion(expr_py: str) -> str:
    """Convierte una expresión aritmética Python ('15 + 7 - 2', '8 * 4', '20 / 4') en etiqueta legible."""
    tokens = re.findall(r"\d+(?:\.\d+)?|[+\-*/()]", expr_py)
    if not tokens:
        return expr_py.strip()
    salida: List[str] = []
    for idx, tok in enumerate(tokens):
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            val = _normalizar_num(float(tok))
            salida.append(_formatear_num_reto(val))
        elif tok in ("+", "-", "*", "/"):
            es_unario = tok in ("+", "-") and (idx == 0 or tokens[idx - 1] in ("(", "+", "-", "*", "/"))
            if es_unario:
                salida.append(tok)
            else:
                op_vis = {"*": "×", "/": "÷"}.get(tok, tok)
                salida.append(f" {op_vis} ")
        else:
            salida.append(tok)
    etq = "".join(salida)
    return re.sub(r"\s+", " ", etq).strip()


def _extraer_operaciones_del_texto(texto: Any) -> List[Tuple[str, Numero]]:
    """
    Detecta expresiones aritméticas simples o compuestas como:
    '15 + 7', '(5 más 7)', '8 × 4', '20 ÷ 4', '0.5 + 0.25', '3,5 + 2,5',
    '1000 + 200', '15 + 7 - 2 = 20', '3 - 8', 'mil más doscientos'.
    Retorna lista de `(expresion_legible, resultado_numerico)`.
    """
    norm = _normalizar(texto)
    if not norm:
        return []

    # Ignorar fechas tipo 12-10-2026
    proc = re.sub(r"\b\d{1,2}-\d{1,2}-\d{2,4}\b", " ", norm)
    # Normalizar coma decimal entre dígitos (ej. 3,5 -> 3.5)
    proc = re.sub(r"(?<=\d),(?=\d)", ".", proc)
    # Convertir palabras numéricas en español a dígitos
    proc = _convertir_palabras_numericas_en_operacion(proc)

    reemplazos = [
        (r"×", " * "),
        (r"÷", " / "),
        (r"\bdividido\s+entre\b", " / "),
        (r"\bdividido\s+por\b", " / "),
        (r"(?<=\d)\s+entre\s+(?=-?\d)", " / "),
        (r"\bmultiplicado\s+por\b", " * "),
        (r"\bmas\b", " + "),
        (r"\bmenos\b", " - "),
        (r"(?<=\d)\s*x\s*(?=-?\d)", " * "),
        (r"\bpor\b(?!\s+ciento\b)", " * "),
    ]
    for pat, rep in reemplazos:
        proc = re.sub(pat, rep, proc)

    hallazgos: List[Tuple[str, Numero]] = []
    patron_expr = re.compile(
        r"(?<![\w.])(?:\(\s*)*-?\d+(?:\.\d+)?(?:\s*\))*(?:\s*[+\-*/]\s*(?:\(\s*)*-?\d+(?:\.\d+)?(?:\s*\))*)+"
    )
    for m in patron_expr.finditer(proc):
        expr_py = m.group(0).strip()
        # Balancear paréntesis sobrantes en bordes si la expresión estaba dentro de '(5 + 7)'
        while expr_py.startswith("(") and expr_py.endswith(")") and expr_py.count("(") == expr_py.count(")"):
            interno = expr_py[1:-1].strip()
            # Verificar que los paréntesis externos envuelvan toda la expresión
            prof = 0
            envuelve_todo = True
            for ch in interno:
                if ch == "(":
                    prof += 1
                elif ch == ")":
                    prof -= 1
                    if prof < 0:
                        envuelve_todo = False
                        break
            if envuelve_todo and prof == 0:
                expr_py = interno
            else:
                break
        if expr_py.count("(") != expr_py.count(")"):
            expr_py = expr_py.replace("(", "").replace(")", "").strip()

        try:
            res = evaluar_ast_seguro(expr_py)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError, SyntaxError):
            continue

        res_norm = _normalizar_num(res)
        etiqueta = _formatear_etiqueta_expresion(expr_py)
        hallazgos.append((etiqueta, res_norm))

    return hallazgos


def _tiene_division_por_cero(texto: Any) -> bool:
    norm = _normalizar(texto)
    if not norm:
        return False
    proc = _convertir_palabras_numericas_en_operacion(norm)
    return bool(
        re.search(
            r"\b\d+(?:[.,]\d+)?\s*(?:/|÷|dividido\s+entre|dividido\s+por|entre)\s*0(?![.,]\d)\b",
            proc,
        )
    )


def _opciones_numericas(correcto: Numero, semilla: int = 0, dificil: bool = False) -> List[str]:
    """Genera siempre 3 opciones numéricas distintas, soportando positivos, cero, negativos y decimales."""
    corr_norm = _normalizar_num(correcto)
    corr_str = _formatear_num_reto(corr_norm)
    es_decimal = isinstance(corr_norm, float) and not corr_norm.is_integer()

    distractores: List[str] = []
    if es_decimal:
        deltas_dec = [0.5, -0.5, 1.0, -1.0, 0.25, -0.25, 1.5, 2.0, -1.5, 3.0]
        for d in deltas_dec:
            cand = _normalizar_num(float(corr_norm) + d)
            if corr_norm >= 0 and cand < 0:
                continue
            cand_s = _formatear_num_reto(cand)
            if cand_s != corr_str and cand_s not in distractores:
                distractores.append(cand_s)
            if len(distractores) == 2:
                break
        paso_extra = 1
        while len(distractores) < 2:
            cand = _normalizar_num(float(corr_norm) + paso_extra * 0.5)
            cand_s = _formatear_num_reto(cand)
            if cand_s != corr_str and cand_s not in distractores:
                distractores.append(cand_s)
            paso_extra += 1
    else:
        corr_int = int(round(float(corr_norm)))
        deltas_int = ([1, -1, 2, -2, 10, -10, 3, -3, 5, -5] if dificil else [2, -2, 3, -3, 1, 4, -1, 5, -4, 6])
        for d in deltas_int:
            cand = corr_int + d
            if corr_int >= 0 and cand < 0:
                continue
            cand_s = str(cand)
            if cand != corr_int and cand_s not in distractores:
                distractores.append(cand_s)
            if len(distractores) == 2:
                break
        paso_extra = 1
        while len(distractores) < 2:
            cand = corr_int + (paso_extra if corr_int >= 0 else -paso_extra)
            cand_s = str(cand)
            if cand_s != corr_str and cand_s not in distractores:
                distractores.append(cand_s)
            paso_extra += 1

    opciones = [corr_str] + distractores[:2]
    semilla_int = int(round(float(corr_norm) * 100)) * 31 + int(semilla)
    rng = random.Random(semilla_int)
    rng.shuffle(opciones)
    return opciones


_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "en", "con", "por", "para", "y", "o", "u", "su", "sus", "tu", "tus",
    "mi", "mis", "te", "se", "lo", "le", "que", "como", "sobre", "luego",
    "primero", "despues", "ahora", "solo", "cada", "mas", "muy", "bien",
    "paso", "presiona", "listo", "cuando", "termines", "calma", "hoja",
}


def _extraer_palabras_clave_paso(texto_paso: Any, contexto_pasos: Optional[List[Any]] = None) -> Set[str]:
    ctx_limpio = [str(x) for x in (contexto_pasos or []) if x is not None] if isinstance(contexto_pasos, (list, tuple, set)) else []
    fuente = f"{_normalizar(texto_paso)} {' '.join(ctx_limpio)}"
    tokens = re.findall(r"[a-zñ]{3,}", _normalizar(fuente))
    return {t for t in tokens if t not in _STOPWORDS_ES}


def _extraer_frase_clave_paso(texto_paso: Any) -> str:
    txt_str = "" if texto_paso is None or isinstance(texto_paso, bool) else str(texto_paso)
    limpio = re.sub(r"¡?presiona.*?listo!?|cuando termines", "", txt_str, flags=re.IGNORECASE).strip()
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

# Catálogo ampliado de vocabulario en Inglés para Primaria
# (palabra_en_upper, tokens_en, traduccion_es, distractores_en, variantes_validas_en)
_VOCABULARIO_INGLES: List[Tuple[str, Tuple[str, ...], str, List[str], Set[str]]] = [
    ("BLUE", ("blue",), "azul", ["RED", "GREEN"], {"blue", "blu"}),
    ("RED", ("red",), "rojo", ["BLUE", "YELLOW"], {"red"}),
    ("GREEN", ("green",), "verde", ["RED", "BLUE"], {"green", "grin"}),
    ("YELLOW", ("yellow",), "amarillo", ["BLUE", "RED"], {"yellow", "yelou"}),
    ("ORANGE", ("orange",), "naranja", ["GREEN", "BLUE"], {"orange"}),
    ("PURPLE", ("purple",), "morado", ["YELLOW", "RED"], {"purple"}),
    ("PINK", ("pink",), "rosado", ["BLUE", "GREEN"], {"pink"}),
    ("BLACK", ("black",), "negro", ["WHITE", "RED"], {"black"}),
    ("WHITE", ("white",), "blanco", ["BLACK", "BLUE"], {"white"}),
    ("BROWN", ("brown",), "café", ["GREEN", "YELLOW"], {"brown"}),
    ("CAT", ("cat",), "gatito", ["DOG", "SUN"], {"cat"}),
    ("DOG", ("dog",), "perro", ["CAT", "BIRD"], {"dog"}),
    ("BIRD", ("bird",), "pájaro", ["DOG", "CAT"], {"bird"}),
    ("FISH", ("fish",), "pez", ["CAT", "DOG"], {"fish"}),
    ("LION", ("lion",), "león", ["DOG", "BIRD"], {"lion"}),
    ("RABBIT", ("rabbit",), "conejo", ["CAT", "DOG"], {"rabbit"}),
    ("HOUSE", ("house",), "casa", ["BOOK", "WATER"], {"house"}),
    ("BOOK", ("book",), "libro", ["HOUSE", "APPLE"], {"book"}),
    ("WATER", ("water",), "agua", ["SUN", "BOOK"], {"water"}),
    ("SUN", ("sun",), "sol", ["MOON", "WATER"], {"sun"}),
    ("MOON", ("moon",), "luna", ["SUN", "BOOK"], {"moon"}),
    ("STAR", ("star",), "estrella", ["MOON", "SUN"], {"star"}),
    ("APPLE", ("apple",), "manzana", ["BOOK", "HOUSE"], {"apple"}),
    ("TREE", ("tree",), "árbol", ["HOUSE", "SUN"], {"tree"}),
    ("FLOWER", ("flower",), "flor", ["TREE", "WATER"], {"flower"}),
    ("PENCIL", ("pencil",), "lápiz", ["BOOK", "HOUSE"], {"pencil"}),
    ("TABLE", ("table",), "mesa", ["CHAIR", "BOOK"], {"table"}),
    ("CHAIR", ("chair",), "silla", ["TABLE", "HOUSE"], {"chair"}),
    ("SCHOOL", ("school",), "escuela", ["HOUSE", "BOOK"], {"school"}),
    ("FAMILY", ("family",), "familia", ["SCHOOL", "HOUSE"], {"family"}),
    ("MOTHER", ("mother", "mom"), "mamá", ["FATHER", "BOOK"], {"mother", "mom"}),
    ("FATHER", ("father", "dad"), "papá", ["MOTHER", "HOUSE"], {"father", "dad"}),
    ("HELLO", ("hello", "hi"), "hola", ["GOODBYE", "BOOK"], {"hello", "hi"}),
    ("GOODBYE", ("goodbye", "bye"), "adiós", ["HELLO", "SUN"], {"goodbye", "bye"}),
]


def _clave_reto(reto: Dict) -> str:
    if not isinstance(reto, dict):
        return "reto_generico"
    return f"{reto.get('tipo', '')}|{reto.get('pregunta', '')}|{reto.get('respuesta_principal', '')}"


def _registrar_reto_nuevo(reto: Dict) -> Dict:
    if isinstance(reto, dict):
        reto["_intentos_fallidos"] = 0
        _CONTADOR_INTENTOS_RETO[_clave_reto(reto)] = 0
    return reto


def generar_reto_paso(
    texto_paso: Any,
    numero_paso: Any = 1,
    nombre_tarea: Any = "",
    contexto_pasos: Optional[List[Any]] = None,
    total_pasos: Optional[Any] = None,
) -> Dict:
    """
    Construye un reto de comprobación activa adaptado al contenido del paso y con
    dificultad progresiva según el avance del alumno (Paso 1 -> Paso final en cuaderno).
    Maneja de forma segura entradas `None`, `int` o divisiones por cero.
    """
    texto_paso_str = "" if texto_paso is None or isinstance(texto_paso, bool) else str(texto_paso)
    nombre_tarea_str = "" if nombre_tarea is None or isinstance(nombre_tarea, bool) else str(nombre_tarea)

    try:
        numero_paso_int = max(1, int(numero_paso)) if numero_paso is not None and not isinstance(numero_paso, bool) else 1
    except (ValueError, TypeError):
        numero_paso_int = 1

    try:
        total_pasos_int = int(total_pasos) if total_pasos is not None and not isinstance(total_pasos, bool) else None
    except (ValueError, TypeError):
        total_pasos_int = None

    if isinstance(contexto_pasos, (list, tuple, set)):
        contexto_limpio = [str(p) for p in contexto_pasos if p is not None and not isinstance(p, bool)]
    elif isinstance(contexto_pasos, str):
        contexto_limpio = [contexto_pasos]
    else:
        contexto_limpio = []

    norm = _normalizar(texto_paso_str)
    norm_tarea = _normalizar(nombre_tarea_str)
    ops_paso = _extraer_operaciones_del_texto(texto_paso_str)
    es_paso_avanzado = numero_paso_int >= 3 or (
        total_pasos_int is not None and total_pasos_int >= 2 and numero_paso_int >= total_pasos_int
    )
    kws_contexto = _extraer_palabras_clave_paso(texto_paso_str, contexto_limpio)

    # Detectar pasos de equivalencia decimal/fracción/porcentaje cuando no hay operador binario explícito
    if not ops_paso and any(
        w in norm for w in ("equivalencia", "equivale", "equivalente", "decimal", "porcentaje")
    ):
        nums_eq = extraer_numeros_de_respuesta(texto_paso_str)
        if nums_eq:
            val_eq = nums_eq[0]
            ops_paso = [(_formatear_num_reto(val_eq), val_eq)]

    # Si el paso contiene una división entre cero y ninguna otra operación válida, manejar sin caer
    if not ops_paso and _tiene_division_por_cero(texto_paso_str):
        opciones_div0 = [
            "No se puede dividir entre cero",
            "El resultado es 100",
            "El resultado es 1",
        ]
        rng = random.Random(numero_paso_int + 17)
        rng.shuffle(opciones_div0)
        return _registrar_reto_nuevo({
            "tipo": "conocimiento",
            "nivel": "avanzado" if es_paso_avanzado else "intermedio",
            "pregunta": "¡Atención matemática! ¿Qué ocurre cuando intentamos dividir un número entre cero?",
            "opciones": opciones_div0,
            "respuesta_principal": "No se puede dividir entre cero",
            "respuestas_validas": {
                "no se puede dividir entre cero",
                "indefinido",
                "no existe",
                "imposible dividir entre cero",
                "error",
            },
            "numeros_validos": set(),
            "palabras_clave": {"dividir", "cero", "indefinido"},
            "acepta_voz_descriptiva": False,
        })

    # Extraer operaciones de pasos previos de la misma misión escritas en el cuaderno
    ops_contexto: List[Tuple[str, Numero]] = []
    ops_contexto_principales: List[Tuple[str, Numero]] = []
    for p_ant in contexto_limpio:
        extraidas_ant = _extraer_operaciones_del_texto(p_ant)
        ops_contexto.extend(extraidas_ant)
        norm_ant = _normalizar(p_ant)
        if "unidades" not in norm_ant:
            ops_contexto_principales.extend(extraidas_ant)

    es_solo_copiar = any(
        fr in norm for fr in (
            "escribe la suma", "escribe la resta", "copia la operacion",
            "anota la operacion", "escribe la operacion",
        )
    ) or (
        bool(ops_paso)
        and any(w in norm for w in ("copia", "anota", "escribe"))
        and not any(
            w in norm for w in (
                "resuelve", "calcula", "cuanto", "resultado", "unidades",
                "decenas", "revisa", "comprueba", "suma primero", "resta primero",
            )
        )
    )

    # 1A. Paso de cálculo matemático directo (con operación explícita en el propio paso)
    if ops_paso and not es_solo_copiar:
        # Si el paso es final/avanzado y menciona varias operaciones en el mismo paso, preguntar por la última
        etiqueta_op, resultado = ops_paso[-1] if (es_paso_avanzado and len(ops_paso) > 1) else ops_paso[0]
        numeros_ok: Set[Numero] = {resultado}
        if es_paso_avanzado and len(ops_paso) > 1:
            for _etq_p, res_p in ops_paso:
                numeros_ok.add(res_p)

        # Si este paso resuelve las unidades de una suma copiada en el paso 1 (ej. 'Escribe la suma: 15 + 7' -> 'unidades (5 más 7)'),
        # aceptar también el total de la suma principal de la misión.
        if "unidades" in norm and ops_contexto_principales and contexto_limpio:
            norm_primero = _normalizar(contexto_limpio[0])
            if any(fr in norm_primero for fr in ("escribe la suma", "escribe la resta", "copia la operacion", "escribe la operacion")):
                numeros_ok.add(ops_contexto_principales[0][1])

        respuestas_validas_str: Set[str] = set()
        for num_v in numeros_ok:
            respuestas_validas_str.update(_equivalencias_numericas(num_v))

        opciones = _opciones_numericas(resultado, semilla=numero_paso_int, dificil=es_paso_avanzado)
        pref = "¡Último cálculo de cuaderno!" if es_paso_avanzado else "¡Comprobación rápida!"
        return _registrar_reto_nuevo({
            "tipo": "matematica",
            "nivel": "avanzado" if es_paso_avanzado else "intermedio",
            "pregunta": f"{pref} Dime el resultado en voz alta o toca el botón: ¿cuánto es {etiqueta_op}?",
            "opciones": opciones,
            "respuesta_principal": _formatear_num_reto(resultado),
            "respuestas_validas": respuestas_validas_str,
            "numeros_validos": numeros_ok,
            "palabras_clave": set(),
            "acepta_voz_descriptiva": False,
        })

    # 1B. Paso avanzado/final matemático sin operación propia pero con operaciones previas en el contexto
    if es_paso_avanzado and ops_contexto:
        # Si el paso cierra la suma de la decena de una operación copiada al inicio, usar la operación principal;
        # de lo contrario, preguntar claramente por la última operación resuelta.
        if "decena" in norm and ops_contexto_principales:
            etiqueta_total, res_total = ops_contexto_principales[-1]
        else:
            etiqueta_total, res_total = ops_contexto[-1]

        numeros_ok = {res_total} | {r for _e, r in ops_contexto}
        respuestas_validas_str = set()
        for num_v in numeros_ok:
            respuestas_validas_str.update(_equivalencias_numericas(num_v))

        opciones = _opciones_numericas(res_total, semilla=numero_paso_int + 13, dificil=True)
        return _registrar_reto_nuevo({
            "tipo": "matematica",
            "nivel": "avanzado",
            "pregunta": f"¡Reto final de cuaderno! Ya terminaste tu cálculo: ¿cuánto da en total {etiqueta_total}?",
            "opciones": opciones,
            "respuesta_principal": _formatear_num_reto(res_total),
            "respuestas_validas": respuestas_validas_str,
            "numeros_validos": numeros_ok,
            "palabras_clave": set(),
            "acepta_voz_descriptiva": False,
        })

    # 2. Paso de copiar/escribir la operación en el cuaderno (ej. "escribe la suma: 15 + 7")
    if ops_paso and es_solo_copiar:
        etiqueta_op, resultado = ops_paso[0]
        partes = re.findall(r"\d+", etiqueta_op)
        a_val = int(partes[0]) if partes else 10
        b_val = int(partes[1]) if len(partes) > 1 else 5
        simbolo = "+" if "+" in etiqueta_op else ("-" if "-" in etiqueta_op else ("÷" if "÷" in etiqueta_op else "×"))
        b_d1 = b_val - 3 if b_val > 3 else b_val + 3
        a_d2 = a_val - 4 if a_val > 5 else a_val + 4
        distractor_1 = f"{a_val} {simbolo} {b_d1}"
        distractor_2 = f"{a_d2} {simbolo} {b_val + 2}"
        if distractor_1 == etiqueta_op:
            distractor_1 = f"{a_val + 1} {simbolo} {b_val + 2}"
        if distractor_2 in (etiqueta_op, distractor_1):
            distractor_2 = f"{a_val + 3} {simbolo} {b_val + 1}"
        opciones = [etiqueta_op, distractor_1, distractor_2]
        rng = random.Random(a_val + b_val + numero_paso_int)
        rng.shuffle(opciones)
        return _registrar_reto_nuevo({
            "tipo": "copia_operacion",
            "nivel": "intermedio" if numero_paso_int >= 2 else "inicial",
            "pregunta": "¡Comprobemos tu cuaderno! Toca o dime en voz alta qué operación acabas de escribir:",
            "opciones": opciones,
            "respuesta_principal": etiqueta_op,
            "respuestas_validas": {_normalizar(etiqueta_op), _formatear_num_reto(resultado)},
            "numeros_validos": {resultado},
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": False,
        })

    # 2.5. Paso de vocabulario de Inglés (colores, animales, objetos, naturaleza o conteo bilingüe)
    tiene_contexto_ingles = (
        "en ingles" in norm
        or "in english" in norm
        or "english" in norm
        or "ingles" in norm_tarea
        or "english" in norm_tarea
    )
    # Detectar palabras del catálogo de inglés presentes en el paso
    hallazgos_vocab_ing: List[Tuple[int, Tuple[str, Tuple[str, ...], str, List[str], Set[str]]]] = []
    for entrada_ing in _VOCABULARIO_INGLES:
        en_upper, tokens_en, es_trad, _dist_en, _var_en = entrada_ing
        for tok_en in tokens_en:
            # 'red' en minúscula en español puede ser 'red de pesca' si no hay contexto de inglés ni mayúsculas
            if tok_en == "red" and not tiene_contexto_ingles and "RED" not in texto_paso_str and "rojo" not in norm:
                continue
            # 'hello' al inicio de una instrucción de organizar cuaderno no debe eclipsar el material
            if tok_en in ("hello", "hi") and "cuaderno" in norm and not re.search(r"\b(saluda|repite|dice|say)\b", norm):
                continue
            m_tok = re.search(rf"\b{re.escape(tok_en)}\b", norm)
            if m_tok:
                hallazgos_vocab_ing.append((m_tok.start(), entrada_ing))
                break

    # Si el paso pide traducir al inglés usando solo la palabra en español (ej. "¿Cómo se dice perro en inglés?")
    if not hallazgos_vocab_ing and tiene_contexto_ingles:
        for entrada_ing in _VOCABULARIO_INGLES:
            _en_u, _toks_e, es_trad, _dist_e, _var_e = entrada_ing
            es_norm = _normalizar(es_trad)
            variantes_es = {es_norm}
            if es_norm == "gatito":
                variantes_es.add("gato")
            elif es_norm == "pajaro":
                variantes_es.add("ave")
            for v_es in variantes_es:
                m_es = re.search(rf"\b{re.escape(v_es)}\b", norm)
                if m_es:
                    hallazgos_vocab_ing.append((m_es.start(), entrada_ing))
                    break

    es_conteo_ingles = bool(
        re.search(r"\bone\b", norm) and re.search(r"\btwo\b", norm) and re.search(r"\bthree\b", norm)
    )

    if es_conteo_ingles:
        opciones = ["One, Two, Three", "Red, Blue, Green", "Cat, Dog, Bird"]
        rng = random.Random(numero_paso_int + 29)
        rng.shuffle(opciones)
        return _registrar_reto_nuevo({
            "tipo": "ingles",
            "pregunta": "¡Reto de Inglés! Toca el botón o cuenta conmigo 1, 2 y 3 en inglés:",
            "opciones": opciones,
            "respuesta_principal": "One, Two, Three",
            "respuestas_validas": {"one, two, three", "one two three", "one", "two", "three"},
            "numeros_validos": set(),
            "palabras_clave": set(),
            "acepta_voz_descriptiva": False,
        })

    if hallazgos_vocab_ing and (tiene_contexto_ingles or any(
        en_u in texto_paso_str or tok_e != "red"
        for _, (en_u, (tok_e, *_), *_) in hallazgos_vocab_ing
    )):
        hallazgos_vocab_ing.sort(key=lambda x: x[0])
        en_upper, _tokens_en, es_trad, dist_base, var_validas = hallazgos_vocab_ing[0][1]

        # Evitar que los distractores incluyan otra palabra en inglés que también aparezca en el mismo paso
        presentes_upper = {e[1][0] for e in hallazgos_vocab_ing}
        pool_distractores = [d for d in dist_base if d not in presentes_upper]
        for cand_d in ("DOG", "CAT", "BLUE", "RED", "GREEN", "SUN", "BOOK", "HOUSE", "APPLE", "BIRD"):
            if len(pool_distractores) >= 2:
                break
            if cand_d != en_upper and cand_d not in presentes_upper and cand_d not in pool_distractores:
                pool_distractores.append(cand_d)

        opciones = [en_upper] + pool_distractores[:2]
        rng = random.Random(numero_paso_int + sum(ord(c) for c in en_upper))
        rng.shuffle(opciones)

        validas_ing: Set[str] = set(var_validas) | {en_upper.lower()}
        for _pos, (_eu, _te, _est, _db, vv) in hallazgos_vocab_ing[1:]:
            validas_ing.update(vv)

        # Compatibilidad con el paso predeterminado "Busca algo de color azul cerca de ti y tócalo..."
        if "busca algo de color azul cerca de ti" in norm and en_upper == "BLUE":
            validas_ing.add("azul")

        return _registrar_reto_nuevo({
            "tipo": "ingles",
            "pregunta": f"¡Reto de Inglés! Toca el botón o dime en voz alta cómo se dice {es_trad} en inglés:",
            "opciones": opciones,
            "respuesta_principal": en_upper,
            "respuestas_validas": validas_ing,
            "numeros_validos": set(),
            "palabras_clave": set(),
            "acepta_voz_descriptiva": False,
        })

    # 3. Conceptos temáticos curriculares específicos (Ciencias, Lenguaje, Fracciones) con límites de palabra \b
    retos_tematicos = [
        (
            ("evaporacion", "condensacion", "precipitacion", "ciclo del agua"),
            "¡Reto de Ciencias! ¿Cuál es la fase del ciclo del agua en este paso?",
            "Evaporación / Lluvia en nubes" if re.search(r"\b(vapor|lluvia)\b", norm) else "El ciclo del agua en tu hoja",
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
            ("fraccion", "fracciones", "numerador", "denominador"),
            "¡Reto de Fracciones! En una fracción, ¿qué indica el número de abajo (denominador)?",
            "Partes iguales del entero",
            ["Solo el color del lápiz", "La fecha del cuaderno"],
            {"numerador", "denominador", "partes", "iguales", "mitad", "cuarto", "entero", "fraccion"},
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
    ]
    for triggers, preg_t, ok_t, dist_t, valid_kws in retos_tematicos:
        if any(re.search(rf"\b{re.escape(tr)}\b", norm) for tr in triggers):
            opciones = [ok_t] + dist_t
            rng = random.Random(len(texto_paso_str) + numero_paso_int * 7)
            rng.shuffle(opciones)
            return _registrar_reto_nuevo({
                "tipo": "conocimiento",
                "nivel": "avanzado" if es_paso_avanzado else "intermedio",
                "pregunta": preg_t,
                "opciones": opciones,
                "respuesta_principal": ok_t,
                "respuestas_validas": {_normalizar(ok_t)} | valid_kws,
                "numeros_validos": set(),
                "palabras_clave": kws_contexto | valid_kws,
                "acepta_voz_descriptiva": False,
            })

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
        rng = random.Random(len(texto_paso_str) + numero_paso_int)
        rng.shuffle(opciones)
        return _registrar_reto_nuevo({
            "tipo": "color",
            "pregunta": "¡Muy bien! Toca o dime en voz alta uno de los colores que usaste o preparaste en este paso:",
            "opciones": opciones,
            "respuesta_principal": principal_etq,
            "respuestas_validas": tokens_ok,
            "numeros_validos": set(),
            "palabras_clave": tokens_ok,
            "acepta_voz_descriptiva": False,
        })

    # 4. Paso de dibujo libre o creativo (ej. "Haz un pequeño dibujo...", "Dibuja un sol brillante y un río...")
    if re.search(r"\b(dibuja|dibujo|colorea|pinta)\b", norm):
        if re.search(r"\bsol\b", norm) and re.search(r"\b(rio|mar)\b", norm):
            opciones = ["El sol y el río", "Un auto de carreras", "Un televisor"]
            rng = random.Random(numero_paso_int + 7)
            rng.shuffle(opciones)
            return _registrar_reto_nuevo({
                "tipo": "dibujo",
                "pregunta": "¡Qué bonito! Toca o dime en voz alta qué elementos dibujaste en tu hoja:",
                "opciones": opciones,
                "respuesta_principal": "El sol y el río",
                "respuestas_validas": {"el sol y el rio", "sol", "rio", "mar", "agua"},
                "numeros_validos": set(),
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            })
        if re.search(r"\b(nube|nubes|lluvia|vapor)\b", norm):
            opciones = ["Nube, vapor y lluvia", "Un balón de fútbol", "Un cohete espacial"]
            rng = random.Random(numero_paso_int + 11)
            rng.shuffle(opciones)
            return _registrar_reto_nuevo({
                "tipo": "dibujo",
                "pregunta": "¡Súper! Toca o dime en voz alta qué dibujaste para explicar este paso:",
                "opciones": opciones,
                "respuesta_principal": "Nube, vapor y lluvia",
                "respuestas_validas": {"nube, vapor y lluvia", "nube", "nubes", "vapor", "lluvia", "flechas", "flechitas"},
                "numeros_validos": set(),
                "palabras_clave": kws_contexto,
                "acepta_voz_descriptiva": False,
            })

        opciones_col = ["Azul", "Rojo", "Amarillo", "Verde"]
        todos_colores = {tok for _e, tok in _COLORES_CATALOGO} | {
            "celeste", "turquesa", "violeta", "negro", "blanco", "cuento", "historia", "dibujo", "personaje",
        }
        return _registrar_reto_nuevo({
            "tipo": "color_libre",
            "pregunta": "¡Qué gran artista! Toca el color principal que usaste en tu dibujo o dime qué dibujaste:",
            "opciones": opciones_col,
            "respuesta_principal": opciones_col[0],
            "respuestas_validas": todos_colores | kws_contexto,
            "numeros_validos": set(),
            "palabras_clave": kws_contexto | todos_colores,
            "acepta_voz_descriptiva": False,
        })

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
        rng = random.Random(len(texto_paso_str) + numero_paso_int * 3)
        rng.shuffle(opciones)
        return _registrar_reto_nuevo({
            "tipo": "lectura",
            "nivel": "avanzado" if es_paso_avanzado else "intermedio",
            "pregunta": preg_lec,
            "opciones": opciones,
            "respuesta_principal": etiqueta_ok,
            "respuestas_validas": {_normalizar(etiqueta_ok)} | kws_contexto,
            "numeros_validos": set(),
            "palabras_clave": kws_contexto,
            "acepta_voz_descriptiva": True,
        })

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
        rng = random.Random(len(texto_paso_str) + numero_paso_int)
        rng.shuffle(opciones)
        preg_mat = (
            "¡Última revisión de orden! ¿Qué útil dejaste listo en su lugar?"
            if es_paso_avanzado
            else "¡Comprobemos juntos! Toca o dime en voz alta qué material escolar usaste en este paso:"
        )
        return _registrar_reto_nuevo({
            "tipo": "material",
            "nivel": "avanzado" if es_paso_avanzado else "inicial",
            "pregunta": preg_mat,
            "opciones": opciones,
            "respuesta_principal": etiqueta_correcta,
            "respuestas_validas": vocab_valido | kws_contexto,
            "numeros_validos": set(),
            "palabras_clave": vocab_valido | kws_contexto,
            "acepta_voz_descriptiva": False,
        })

    # 7. Respaldo contextual real basado en el contenido del paso (NUNCA botones vacíos como "Sí, completé el paso")
    frase_clave = _extraer_frase_clave_paso(texto_paso_str)
    etiqueta_ctx = frase_clave[0].upper() + frase_clave[1:] if frase_clave else "Realizar el ejercicio del paso"
    distractores_ctx = (
        ["Dejar el cuaderno en blanco", "Cambiar a videojuegos"]
        if es_paso_avanzado
        else ["No hacer nada todavía", "Guardar todo sin avanzar"]
    )
    opciones = [etiqueta_ctx] + distractores_ctx
    rng = random.Random(len(texto_paso_str) + numero_paso_int * 11)
    rng.shuffle(opciones)
    pregunta_ctx = (
        f"¡Comprobación final de cuaderno (Paso {numero_paso_int})! ¿Qué acción clave dejaste hecha en tu trabajo?"
        if es_paso_avanzado
        else f"¡Comprobación de atención (Paso {numero_paso_int})! Selecciona o cuéntame qué realizaste exactamente:"
    )
    return _registrar_reto_nuevo({
        "tipo": "comprension_paso",
        "nivel": "avanzado" if es_paso_avanzado else "intermedio",
        "pregunta": pregunta_ctx,
        "opciones": opciones,
        "respuesta_principal": etiqueta_ctx,
        "respuestas_validas": {_normalizar(etiqueta_ctx)} | kws_contexto,
        "numeros_validos": set(),
        "palabras_clave": kws_contexto,
        "acepta_voz_descriptiva": False,
    })


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
    "cerre mi cuaderno", "la hoja totalmente en blanco", "no lo hice", "no entiendo",
    "no se como hacerlo", "no saque mi cuaderno", "no lei el cuento", "aun no",
}

_RESPUESTAS_VACIAS_O_EVASIVAS = {
    "si", "ya", "listo", "ok", "oka", "okey", "okay", "bien", "bueno", "claro",
    "obvio", "perfecto", "genial", "hola", "holi", "jaja", "jajaja", "jeje",
    "asdf", "qwerty", "xxx", "zzz", "cualquier cosa", "no importa", "paso listo",
    "siguiente", "termine", "ya termine", "ya lo hice", "complete", "completado",
    "complete el paso", "complete el ejercicio", "ya complete el paso",
    "ya complete el ejercicio", "hice la tarea", "ya hice la tarea",
}

_PATRON_NEGACION = re.compile(
    r"\b("
    r"no|nada|nunca|jamas|tampoco|ningun|ninguna|ninguno|todavia|nose|"
    r"aun\s+no|sin\s+leer|sin\s+hacer|sin\s+escribir|sin\s+abrir|me\s+falta|me\s+salte"
    r")\b"
)

_PATRON_FRASE_AJENA = re.compile(
    r"\b("
    r"bano|hambre|sueno|dormir|aburrido|aburrida|aburro|cansado|cansada|"
    r"comida|comer|almuerzo|desayuno|cena|pizza|helado|galleta|"
    r"videojuego|videojuegos|tiktok|roblox|freefire|minecraft|fortnite|youtube|"
    r"televisor|television|tele|celular|recreo|"
    r"fui\s+al|me\s+fui|quiero\s+ir|quiero\s+jugar|me\s+duele|tengo\s+sed|tengo\s+frio|tengo\s+calor|"
    r"que\s+hora\s+es|cuanto\s+falta|me\s+olvide"
    r")\b"
)


def _contiene_negacion(resp_norm: str, principal_norm: str = "") -> bool:
    if not resp_norm:
        return False
    if principal_norm and resp_norm == principal_norm:
        return False
    if resp_norm in _RESPUESTAS_NEGATIVAS:
        return True
    return bool(_PATRON_NEGACION.search(resp_norm))


def _es_frase_ajena(resp_norm: str, kws_permitidas: Set[str]) -> bool:
    if not resp_norm:
        return False
    m = _PATRON_FRASE_AJENA.search(resp_norm)
    if m and m.group(1) not in kws_permitidas:
        return True
    # Frases en primera persona sobre estados o acciones desconectadas de la lectura/estudio
    if re.match(r"^(?:fui|tengo|quiero|voy\s+a|estoy|me\s+voy|me\s+da)\b", resp_norm):
        palabras = set(re.findall(r"[a-zñ]+", resp_norm))
        verbos_estudio = {"lei", "leido", "escribi", "dibuje", "aprendi", "entendi", "hice", "resolvi", "sume", "reste"}
        if not (palabras & kws_permitidas) and not (palabras & verbos_estudio):
            return True
    return False


def _es_afirmacion_vacia(resp_norm: str) -> bool:
    if resp_norm in _RESPUESTAS_VACIAS_O_EVASIVAS:
        return True
    if re.match(
        r"^(?:si|ya|ok|listo|bien|bueno|complete|termine|acabe|hice)\s+(?:todo\s+)?(?:el\s+|la\s+|los\s+|las\s+|mi\s+)?(?:paso|ejercicio|todo|tarea|actividad)\b",
        resp_norm,
    ):
        return True
    return False


def _es_texto_real_descriptivo(resp_norm: str, kws_permitidas: Set[str]) -> bool:
    """Verifica que una frase libre de lectura tenga sentido real y no sea negación, frase ajena o garabato."""
    if _es_afirmacion_vacia(resp_norm) or _contiene_negacion(resp_norm) or _es_frase_ajena(resp_norm, kws_permitidas):
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


def _Incrementar_y_obtener_intento(reto: Dict, intentos_explicito: Optional[int]) -> int:
    if intentos_explicito is not None and not isinstance(intentos_explicito, bool):
        try:
            val = max(1, int(intentos_explicito))
            if isinstance(reto, dict):
                reto["_intentos_fallidos"] = val
                _CONTADOR_INTENTOS_RETO[_clave_reto(reto)] = val
            return val
        except (ValueError, TypeError):
            pass

    if not isinstance(reto, dict):
        return 1

    clave = _clave_reto(reto)
    prev = max(int(reto.get("_intentos_fallidos", 0)), _CONTADOR_INTENTOS_RETO.get(clave, 0))
    actual = prev + 1
    reto["_intentos_fallidos"] = actual
    _CONTADOR_INTENTOS_RETO[clave] = actual
    return actual


def _reiniciar_intentos(reto: Dict) -> None:
    if isinstance(reto, dict):
        reto["_intentos_fallidos"] = 0
        _CONTADOR_INTENTOS_RETO[_clave_reto(reto)] = 0


def _mensaje_diagnostico_progresivo(reto: Dict, motivo_base: str, num_intento: int) -> str:
    """
    Construye retroalimentación diagnóstica graduada según el número de intento fallido:
    - Intento 1: orientación amable específica al tipo de error.
    - Intento 2: pista diagnóstica concreta sobre la estrategia o inicio de la respuesta.
    - Intento 3+: guía paso a paso explícita que conduce a la respuesta correcta sin frustración.
    """
    if not isinstance(reto, dict):
        return motivo_base

    tipo = str(reto.get("tipo", ""))
    principal = str(reto.get("respuesta_principal", "")).strip()
    pregunta = str(reto.get("pregunta", "")).strip()
    opciones = [str(op) for op in (reto.get("opciones") or []) if op is not None]
    opciones_txt = ", ".join(opciones) if opciones else principal

    if num_intento <= 1:
        return motivo_base

    if num_intento == 2:
        if tipo == "matematica":
            if "+" in pregunta:
                return (
                    f"Pista diagnóstica (intento 2): revisa la suma con calma en tu cuaderno "
                    f"(puedes apoyarte contando unidades y decenas). El resultado correcto está entre: {opciones_txt}."
                )
            if "-" in pregunta:
                return (
                    f"Pista diagnóstica (intento 2): revisa la resta descontando paso a paso. "
                    f"Elige o di el resultado exacto entre las opciones: {opciones_txt}."
                )
            if "×" in pregunta or "*" in pregunta:
                return (
                    f"Pista diagnóstica (intento 2): recuerda que multiplicar es sumar el mismo número varias veces. "
                    f"Busca el resultado entre: {opciones_txt}."
                )
            if "÷" in pregunta or "/" in pregunta:
                return (
                    f"Pista diagnóstica (intento 2): reparte en partes iguales para hallar el cociente. "
                    f"Las opciones son: {opciones_txt}."
                )
            return f"Pista diagnóstica (intento 2): verifica el cálculo numérico exacto de tu cuaderno entre las opciones: {opciones_txt}."

        if tipo == "ingles":
            pref = principal[:2].upper() if len(principal) >= 2 else principal.upper()
            return (
                f"Pista diagnóstica (intento 2): recuerda responder en inglés. "
                f"La palabra correcta empieza con «{pref}...» entre las opciones ({opciones_txt})."
            )

        pref_gen = principal[:4] if len(principal) >= 4 else principal
        return (
            f"Pista diagnóstica (intento 2): fíjate en lo que hiciste en este paso. "
            f"La opción correcta empieza con «{pref_gen}...» ({opciones_txt})."
        )

    # Intento 3 o superior: guía paso a paso explícita hacia la respuesta correcta
    if tipo == "matematica":
        return (
            f"Guía paso a paso (intento {num_intento}): ¡hagámoslo juntos sin prisa! "
            f"Al resolver la operación del paso, el resultado exacto es {principal}. "
            f"Anota {principal} en tu cuaderno y selecciónalo o dilo en voz alta."
        )
    if tipo == "ingles":
        return (
            f"Guía paso a paso (intento {num_intento}): ¡repitamos juntos en inglés! "
            f"La palabra correcta en inglés es «{principal}». Toca el botón «{principal}» o dila en voz alta."
        )
    return (
        f"Guía paso a paso (intento {num_intento}): ¡revisemos juntos tu paso! "
        f"La respuesta correcta para avanzar es «{principal}». Selecciónala o escríbela con calma."
    )


def validar_respuesta_reto(
    reto: Dict,
    respuesta_usuario: Any,
    intentos: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Evalúa sin castigos la respuesta elegida, escrita o hablada por el estudiante,
    verificando que realmente corresponda al reto, rechazando negaciones/frases ajenas
    y entregando retroalimentación diagnóstica progresiva si falla varias veces.
    """
    if not isinstance(reto, dict):
        return False, "No hay un reto activo válido para comprobar."

    if respuesta_usuario is None or isinstance(respuesta_usuario, bool):
        return False, "Toca una de las opciones o dime tu respuesta con el micrófono."

    resp_norm = _normalizar(respuesta_usuario)
    if not resp_norm:
        return False, "Toca una de las opciones o dime tu respuesta con el micrófono."

    tipo_reto = str(reto.get("tipo", ""))
    principal_norm = _normalizar(reto.get("respuesta_principal", ""))
    validas = {_normalizar(v) for v in (reto.get("respuestas_validas") or set()) if _normalizar(v)}
    if principal_norm:
        validas.add(principal_norm)

    kws_paso = {_normalizar(k) for k in (reto.get("palabras_clave") or set()) if len(_normalizar(k)) >= 3}
    kws_permitidas = validas | kws_paso

    # 1. Coincidencia exacta directa con la respuesta principal (ej. "No se puede dividir entre cero")
    if resp_norm == principal_norm and not _es_afirmacion_vacia(resp_norm):
        _reiniciar_intentos(reto)
        return True, "¡Excelente comprobación! Se nota que hiciste tu paso con mucha atención."

    # 2. Rechazar negaciones ("no saqué mi cuaderno", "no leí el cuento", "no entiendo", "no lo hice", "todavía no")
    if _contiene_negacion(resp_norm, principal_norm=principal_norm):
        num_int = _Incrementar_y_obtener_intento(reto, intentos)
        base_neg = "¡Qué honesto eres! Tómate tu tiempo para terminar este pasito y vuelve a presionar ¡Paso Listo!."
        return False, _mensaje_diagnostico_progresivo(reto, base_neg, num_int)

    # 3. Rechazar frases ajenas ("fui al baño", "tengo hambre", etc.)
    if _es_frase_ajena(resp_norm, kws_permitidas):
        num_int = _Incrementar_y_obtener_intento(reto, intentos)
        base_ajena = "Esa frase no corresponde a la actividad del paso. Concéntrate un momento en tu cuaderno y dime lo que trabajaste."
        return False, _mensaje_diagnostico_progresivo(reto, base_ajena, num_int)

    # 4. Rechazar afirmaciones vacías ("sí", "listo", "completé el ejercicio", "hola", "asdf")
    if _es_afirmacion_vacia(resp_norm):
        num_int = _Incrementar_y_obtener_intento(reto, intentos)
        base_vacia = "Necesito verificar lo que hiciste: dime el dato, resultado o palabra clave del paso (no solo «listo» o «completé»)."
        return False, _mensaje_diagnostico_progresivo(reto, base_vacia, num_int)

    # 5. Coincidencia directa con opción válida del reto
    if resp_norm in validas:
        _reiniciar_intentos(reto)
        return True, "¡Excelente comprobación! Se nota que hiciste tu paso con mucha atención."

    # 6. Validación específica por tipo de reto
    numeros_validos = {_normalizar_num(n) for n in (reto.get("numeros_validos") or set())}

    if tipo_reto == "matematica":
        # En retos matemáticos se exige el resultado numérico exacto de la operación preguntada
        # Si el usuario escribió una operación con '=' (ej. '15 + 7 = 22'), evaluar el número tras '='
        texto_eval_num = resp_norm.split("=")[-1] if "=" in resp_norm else str(respuesta_usuario)
        # Si solo copió la expresión con operador ('+', '*', '×', '÷') sin resolverla, no aprobar
        if "=" not in resp_norm and re.search(r"\d\s*[+*×÷]\s*\d", resp_norm):
            nums_dichos: List[Numero] = []
        else:
            nums_dichos = extraer_numeros_de_respuesta(texto_eval_num)

        for n_dicho in nums_dichos:
            if any(abs(float(n_dicho) - float(n_ok)) < 1e-6 for n_ok in numeros_validos):
                _reiniciar_intentos(reto)
                return True, "¡Súper bien calculado! ¡Respuesta correcta!"

        num_int = _Incrementar_y_obtener_intento(reto, intentos)
        if nums_dichos:
            base_mate = "Ese número no coincide con el resultado de la operación preguntada. Revisa tu cálculo e inténtalo de nuevo."
        else:
            base_mate = "En este reto matemático necesito que me digas o elijas el resultado numérico exacto de la operación."
        return False, _mensaje_diagnostico_progresivo(reto, base_mate, num_int)

    if tipo_reto == "ingles":
        # En retos de inglés se exige la palabra en inglés dentro de `validas`
        palabras_ing = set(re.findall(r"[a-z]+", resp_norm))
        if any(v in palabras_ing or (len(v) >= 4 and v in resp_norm) for v in validas):
            _reiniciar_intentos(reto)
            return True, "¡Very good! ¡Excelente pronunciación en inglés!"

        num_int = _Incrementar_y_obtener_intento(reto, intentos)
        base_ing = "¡Buen intento! En este reto de inglés debes decir o seleccionar cómo se dice la palabra en inglés."
        return False, _mensaje_diagnostico_progresivo(reto, base_ing, num_int)

    # Para otros tipos con números válidos (ej. copia_operacion)
    if numeros_validos:
        nums_dichos = extraer_numeros_de_respuesta(respuesta_usuario)
        if any(any(abs(float(nd) - float(nok)) < 1e-6 for nok in numeros_validos) for nd in nums_dichos):
            _reiniciar_intentos(reto)
            return True, "¡Súper bien calculado! ¡Respuesta correcta!"

    # Excluir botones distractores explícitos
    opciones_norm = {_normalizar(op) for op in (reto.get("opciones") or [])}
    if resp_norm in opciones_norm and resp_norm != principal_norm:
        num_int = _Incrementar_y_obtener_intento(reto, intentos)
        base_dist = "¡Casi, casi! Esa opción no coincide con tu paso. Revisa tu cuaderno e inténtalo otra vez."
        return False, _mensaje_diagnostico_progresivo(reto, base_dist, num_int)

    palabras_resp = set(re.findall(r"[a-z0-9ñ]+", resp_norm))
    palabras_resp_limpias = palabras_resp - _STOPWORDS_ES - {"paso", "ejercicio", "tarea", "hice", "complete", "listo"}

    if len(palabras_resp_limpias) >= 1:
        for v in validas:
            if not v or v in _RESPUESTAS_VACIAS_O_EVASIVAS:
                continue
            if (len(v) >= 4 and v in palabras_resp_limpias) or (len(v) >= 5 and v in resp_norm):
                _reiniciar_intentos(reto)
                return True, "¡Muy bien explicado! Comprobación superada."

        # Coincidencia significativa con conceptos propios del paso
        kws_paso_4 = {k for k in kws_paso if len(k) >= 4}
        coincidencias = palabras_resp_limpias & kws_paso_4
        if len(coincidencias) >= 2 or (len(coincidencias) == 1 and len(palabras_resp_limpias) >= 2):
            _reiniciar_intentos(reto)
            return True, "¡Excelente! Se nota en tu respuesta lo que trabajaste en el paso."

    # Pasos de lectura abierta: exigir frase descriptiva real (sin negaciones ni frases ajenas)
    if reto.get("acepta_voz_descriptiva") and _es_texto_real_descriptivo(resp_norm, kws_permitidas):
        _reiniciar_intentos(reto)
        return True, "¡Qué bien me lo contaste! Sigamos al siguiente paso."

    num_int = _Incrementar_y_obtener_intento(reto, intentos)
    base_gen = "Tu respuesta no coincide con lo trabajado en este paso. Elige la opción correcta o escribe lo que hiciste en tu cuaderno."
    return False, _mensaje_diagnostico_progresivo(reto, base_gen, num_int)
