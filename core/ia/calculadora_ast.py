"""
Calculadora Aritmética Segura con `ast` (Cero `eval`, Cero `SymPy`)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Resuelve operaciones escolares de primaria expresadas en lenguaje natural
("¿cuánto es 15 más 7?", "8 por 4", "la mitad de 24", "(12 + 8) entre 4")
evaluando únicamente nodos `ast` numéricos permitidos y bloqueando cualquier
ejecución arbitraria o exponentes gigantes.
"""

import ast
import math
import operator
import re
from typing import Dict, List, Optional, Tuple, Union

Numero = Union[int, float]

_OPERADORES_BINARIOS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_OPERADORES_UNARIOS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

MAX_ABS_OPERANDO = 1_000_000
MAX_BASE_POTENCIA = 10_000
MAX_EXPONENTE = 8

_MENSAJE_CERO = (
    "¡Ups! En matemáticas no podemos repartir ni dividir entre cero. ¡Prueba con otro número!"
)
_MENSAJE_RANGO_PRIMARIA = (
    "¡Uy, qué número tan enorme! Supera el rango seguro de primaria "
    "(números hasta 1000000 y exponentes hasta 8). ¡Prueba con números más pequeños!"
)
_MENSAJE_DOMINIO_REAL = (
    "¡Buen intento! Esa operación da un resultado fuera de los números reales que usamos "
    "en primaria, como las raíces de números negativos. ¡Probemos con números positivos!"
)

_TABLA_TILDES = str.maketrans("áéíóúüàèìòùâêîôû", "aeiouuaeiouaeiou")

_HASTA_29_ES = {
    "cero": 0,
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiun": 21,
    "veintiuno": 21,
    "veintiuna": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
}

_UNIDADES_1_9_ES = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
}

_DECENAS_ES = {
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
}

_CENTENAS_200_900_ES = {
    "doscientos": 200,
    "doscientas": 200,
    "trescientos": 300,
    "trescientas": 300,
    "cuatrocientos": 400,
    "cuatrocientas": 400,
    "quinientos": 500,
    "quinientas": 500,
    "seiscientos": 600,
    "seiscientas": 600,
    "setecientos": 700,
    "setecientas": 700,
    "ochocientos": 800,
    "ochocientas": 800,
    "novecientos": 900,
    "novecientas": 900,
}

_OPERADORES_PALABRA_ADJ = {
    "mas", "menos", "por", "entre", "veces", "elevado", "dividido", "multiplicado",
}

_FUNCIONES_MATH = {
    "sin", "cos", "tan", "sen", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "log", "log2", "log10", "ln",
    "exp", "sqrt", "abs", "pow", "round", "floor", "ceil", "max", "min",
}


class _ErrorRangoEscolar(ValueError):
    """Error de rango numérico o potencia fuera de los límites de primaria."""


class _ErrorDominioReal(ValueError):
    """Resultado fuera de los números reales (complejo, NaN o infinito)."""


def _quitar_tildes(texto: str) -> str:
    return texto.translate(_TABLA_TILDES)


def _formatear_numero(valor: Numero) -> str:
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor)
    num = float(valor)
    if math.isnan(num) or math.isinf(num):
        raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
    redondeado = round(num, 4)
    if abs(redondeado) < 1e-9:
        return "0"
    if redondeado.is_integer():
        return str(int(redondeado))
    texto = f"{redondeado:.4f}".rstrip("0").rstrip(".")
    return "0" if texto in ("-0", "") else texto


def evaluar_ast_seguro(expresion: str) -> Numero:
    """Evalúa de forma estrictamente segura una expresión aritmética."""
    if not isinstance(expresion, str) or not expresion.strip() or len(expresion) > 120:
        raise ValueError("Expresión inválida o demasiado larga.")

    try:
        arbol = ast.parse(expresion.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError("Expresión aritmética inválida.") from exc

    def _eval_nodo(nodo: ast.AST, profundidad: int = 0) -> Numero:
        if profundidad > 16:
            raise ValueError("Expresión demasiado anidada.")
        if isinstance(nodo, ast.Expression):
            return _eval_nodo(nodo.body, profundidad + 1)
        if isinstance(nodo, ast.Constant):
            if isinstance(nodo.value, complex):
                raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
            if isinstance(nodo.value, (int, float)) and not isinstance(nodo.value, bool):
                if isinstance(nodo.value, float) and (math.isnan(nodo.value) or math.isinf(nodo.value)):
                    raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
                if abs(nodo.value) > MAX_ABS_OPERANDO:
                    raise _ErrorRangoEscolar("Número fuera del rango escolar permitido.")
                return nodo.value
            raise ValueError(f"Constante no permitida: {type(nodo.value).__name__}")
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES_UNARIOS:
            res = _OPERADORES_UNARIOS[type(nodo.op)](_eval_nodo(nodo.operand, profundidad + 1))
            if isinstance(res, complex):
                raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
            if isinstance(res, float) and (math.isnan(res) or math.isinf(res)):
                raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
            if abs(res) > MAX_ABS_OPERANDO * 100:
                raise _ErrorRangoEscolar("Resultado demasiado grande.")
            return res
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES_BINARIOS:
            izq = _eval_nodo(nodo.left, profundidad + 1)
            der = _eval_nodo(nodo.right, profundidad + 1)
            if isinstance(nodo.op, ast.Pow):
                if abs(izq) > MAX_BASE_POTENCIA or abs(der) > MAX_EXPONENTE:
                    raise _ErrorRangoEscolar("Potencia fuera del rango escolar seguro.")
            if isinstance(nodo.op, (ast.Div, ast.FloorDiv, ast.Mod)) and der == 0:
                raise ZeroDivisionError("División entre cero.")
            try:
                res = _OPERADORES_BINARIOS[type(nodo.op)](izq, der)
            except OverflowError as exc:
                raise _ErrorRangoEscolar("Resultado fuera del rango escolar permitido.") from exc
            if isinstance(res, complex):
                raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
            if isinstance(res, float) and (math.isnan(res) or math.isinf(res)):
                raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
            if abs(res) > MAX_ABS_OPERANDO * 100:
                raise _ErrorRangoEscolar("Resultado demasiado grande.")
            return res
        raise ValueError(f"Operación no permitida: {type(nodo).__name__}")

    resultado = _eval_nodo(arbol)
    if isinstance(resultado, complex) or (
        isinstance(resultado, float) and (math.isnan(resultado) or math.isinf(resultado))
    ):
        raise _ErrorDominioReal("Resultado fuera de los números reales de primaria.")
    return resultado


def _consumir_bloque_menor_1000(
    palabras: List[Tuple[int, int, str, str]],
    idx: int,
) -> Optional[Tuple[int, int]]:
    """Consume una secuencia de palabras numéricas entre 0 y 999."""
    n = len(palabras)
    if idx >= n:
        return None

    def _contiguo(a: int, b: int) -> bool:
        return palabras[a][1] < palabras[b][0] and palabras[a][1] == palabras[b][0] - 1 or (
            # Permita uno o más espacios únicamente (ya normalizados a 1 espacio)
            palabras[b][0] > palabras[a][1]
        )

    cur = idx
    total = 0
    tiene_centena = False
    w = palabras[cur][3]

    if w == "cien":
        return (100, cur + 1)
    if w == "ciento":
        prev_w = palabras[cur - 1][3] if cur > 0 else ""
        if prev_w == "por":
            return None
        # "ciento" válido solo si continúa con <1..99>
        if cur + 1 >= n:
            return None
        siguiente = palabras[cur + 1][3]
        if (
            siguiente not in _DECENAS_ES
            and siguiente not in _HASTA_29_ES
        ) or siguiente == "cero":
            return None
        total += 100
        tiene_centena = True
        cur += 1
    elif w in _CENTENAS_200_900_ES:
        total += _CENTENAS_200_900_ES[w]
        tiene_centena = True
        cur += 1

    if cur < n and (not tiene_centena or _contiguo(cur - 1, cur)):
        w_cur = palabras[cur][3]
        if w_cur in _DECENAS_ES:
            total += _DECENAS_ES[w_cur]
            cur += 1
            if (
                cur + 1 < n
                and palabras[cur][3] == "y"
                and palabras[cur + 1][3] in _UNIDADES_1_9_ES
            ):
                total += _UNIDADES_1_9_ES[palabras[cur + 1][3]]
                cur += 2
            return (total, cur)
        if w_cur in _HASTA_29_ES:
            if w_cur == "cero" and tiene_centena:
                return (total, cur)
            total += _HASTA_29_ES[w_cur]
            cur += 1
            return (total, cur)

    if tiene_centena:
        return (total, cur)
    return None


def _reemplazar_palabras_numericas(texto: str) -> str:
    """Convierte palabras numéricas en español (0..999999) a dígitos sin corromper artículos."""
    # Tokenizar palabras junto con espacios exactos entre ellas para verificar adyacencia pura
    matches = list(re.finditer(r"[a-zA-ZñÑáéíóúü]+", texto))
    if not matches:
        return texto

    # Agrupar palabras separadas únicamente por espacios horizontales
    grupos: List[List[Tuple[int, int, str, str]]] = []
    grupo_actual: List[Tuple[int, int, str, str]] = []
    for m in matches:
        item = (m.start(), m.end(), m.group(0), _quitar_tildes(m.group(0).lower()))
        if not grupo_actual:
            grupo_actual.append(item)
        else:
            hueco = texto[grupo_actual[-1][1]:m.start()]
            if hueco and hueco.isspace():
                grupo_actual.append(item)
            else:
                grupos.append(grupo_actual)
                grupo_actual = [item]
    if grupo_actual:
        grupos.append(grupo_actual)

    reemplazos: List[Tuple[int, int, str]] = []
    for palabras in grupos:
        i = 0
        n = len(palabras)
        while i < n:
            w = palabras[i][3]
            start_pos = palabras[i][0]
            end_pos = None
            valor_num: Optional[int] = None

            bloque = _consumir_bloque_menor_1000(palabras, i)
            if bloque is not None:
                v1, j = bloque
                if j < n and palabras[j][3] == "mil" and v1 >= 1:
                    valor_num = v1 * 1000
                    end_idx = j + 1
                    bloque2 = _consumir_bloque_menor_1000(palabras, j + 1)
                    if bloque2 is not None and bloque2[0] >= 1:
                        valor_num += bloque2[0]
                        end_idx = bloque2[1]
                    end_pos = palabras[end_idx - 1][1]
                    i = end_idx
                else:
                    # Proteger artículos "un" / "una" / "uno" cuando no forman número compuesto
                    es_un_simple = (j == i + 1 and v1 == 1)
                    es_un_compuesto = (j > i + 1 and palabras[j - 1][3] == "un")
                    if es_un_compuesto:
                        # "treinta y un", "ciento un" sin "mil": no convertir para no dañar "treinta y un días"
                        i += 1
                        continue
                    if es_un_simple:
                        prev_w = palabras[i - 1][3] if i > 0 else ""
                        next_w = palabras[i + 1][3] if i + 1 < n else ""
                        ctx_antes = texto[max(0, start_pos - 2):start_pos].strip()
                        ctx_despues = texto[palabras[i][1]:min(len(texto), palabras[i][1] + 2)].strip()
                        op_sym = {"+", "-", "*", "/", "^", "=", "×", "÷"}

                        if w in ("uno", "una") and (
                            (next_w in ("por", "a", "en") and i + 2 < n and palabras[i + 2][3] == w)
                            or (prev_w in ("por", "a", "en") and i >= 2 and palabras[i - 2][3] == w)
                        ):
                            i += 1
                            continue
                        if w == "un":
                            i += 1
                            continue
                        if prev_w == "cada" or next_w in ("de", "que", "se", "no", "solo"):
                            i += 1
                            continue
                        if w == "una":
                            es_contexto_mate = (
                                next_w in _OPERADORES_PALABRA_ADJ
                                or prev_w in _OPERADORES_PALABRA_ADJ
                                or prev_w == "de" and i >= 2 and palabras[i - 2][3] in ("mitad", "doble", "triple")
                                or ctx_antes in op_sym
                                or ctx_despues in op_sym
                            )
                            if not es_contexto_mate:
                                i += 1
                                continue
                    valor_num = v1
                    end_pos = palabras[j - 1][1]
                    i = j
            elif w == "mil":
                prev_w = palabras[i - 1][3] if i > 0 else ""
                next_w = palabras[i + 1][3] if i + 1 < n else ""
                if next_w in ("gracias", "perdon", "disculpas", "amores"):
                    i += 1
                    continue
                valor_num = 1000
                end_idx = i + 1
                bloque2 = _consumir_bloque_menor_1000(palabras, i + 1)
                if bloque2 is not None and bloque2[0] >= 1:
                    valor_num += bloque2[0]
                    end_idx = bloque2[1]
                else:
                    # Exigir algún indicador contextual/operador para "mil" aislado
                    ctx_antes = texto[max(0, start_pos - 2):start_pos].strip()
                    ctx_despues = texto[palabras[i][1]:min(len(texto), palabras[i][1] + 2)].strip()
                    op_sym = {"+", "-", "*", "/", "^", "=", "×", "÷", "%"}
                    es_ctx_mil = (
                        prev_w in _OPERADORES_PALABRA_ADJ
                        or next_w in _OPERADORES_PALABRA_ADJ
                        or prev_w in ("de", "es", "son", "da", "calcula", "resuelve", "entre")
                        or next_w in ("entre", "por", "al", "elevado", "veces")
                        or ctx_antes in op_sym
                        or ctx_despues in op_sym
                    )
                    if not es_ctx_mil and prev_w == "" and next_w == "":
                        es_ctx_mil = True
                    if not es_ctx_mil:
                        i += 1
                        continue
                end_pos = palabras[end_idx - 1][1]
                i = end_idx
            else:
                i += 1
                continue

            if valor_num is not None and end_pos is not None:
                reemplazos.append((start_pos, end_pos, str(valor_num)))

    if not reemplazos:
        return texto

    partes: List[str] = []
    ultimo = 0
    for ini, fin, num_str in reemplazos:
        partes.append(texto[ultimo:ini])
        partes.append(num_str)
        ultimo = fin
    partes.append(texto[ultimo:])
    return "".join(partes)


def _precomputar_cierres_paren(texto: str) -> Dict[int, int]:
    """Precomputa índices de cierre `)` para cada `(` en una sola pasada O(n)."""
    cierre_paren: Dict[int, int] = {}
    pila_paren: List[int] = []
    for idx_ch, ch_p in enumerate(texto):
        if ch_p == "(":
            pila_paren.append(idx_ch)
        elif ch_p == ")" and pila_paren:
            cierre_paren[pila_paren.pop()] = idx_ch
    return cierre_paren


def _extraer_expresiones_matematicas(texto: str) -> List[str]:
    """
    Escáner lineal O(n) con balanceo de paréntesis, negativos unarios y
    multiplicación implícita. Protege guiones en prosa (covid-19, A-12-3) y
    llamadas a funciones (sin(3+4), sin (3+4), log2(8)).
    """
    tokens_runs: List[List[Tuple[str, str, bool]]] = []
    run_actual: List[Tuple[str, str, bool]] = []
    run_tainted = False
    had_space = False
    unclosed_lp = 0
    i = 0
    n = len(texto)

    # Precomputar cierres de paréntesis en una única pasada O(n)
    cierre_paren = _precomputar_cierres_paren(texto)

    def _cerrar_run() -> None:
        nonlocal run_actual, run_tainted, unclosed_lp
        if run_actual and not run_tainted:
            tokens_runs.append(run_actual)
        run_actual = []
        run_tainted = False
        unclosed_lp = 0

    def _saltar_parentesis_desde(pos_lp: int) -> int:
        if pos_lp in cierre_paren:
            return cierre_paren[pos_lp] + 1
        return pos_lp + 1

    def _ultimo_no_lp() -> Tuple[Optional[str], bool]:
        """Devuelve (kind, lp_tuvo_espacio) del último token distinto de LP."""
        lp_sp = had_space
        for tok_k, _, tok_sp in reversed(run_actual):
            if tok_k == "LP":
                lp_sp = tok_sp
                continue
            return tok_k, lp_sp
        return None, False

    def _sigue_op_tras_rp(pos: int) -> bool:
        """Comprueba si tras cerrar paréntesis pendientes sigue un operador o '('."""
        p = pos
        while p < n and (texto[p] == ")" or texto[p].isspace()):
            p += 1
        return (
            p < n
            and texto[p] in "+-*/("
            and texto[p:p + 2] != "--"
        )

    while i < n:
        ch = texto[i]
        if ch.isspace():
            had_space = True
            i += 1
            continue

        # Identificador: cierra o contamina run; protege fn(...) y códigos A-12-3
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (texto[j].isalnum() or texto[j] == "_"):
                j += 1
            ident_lower = texto[i:j].lower()
            k_sp = j
            while k_sp < n and texto[k_sp].isspace():
                k_sp += 1

            # 1) Llamada a función: fn(...) o fn (...) para funciones matemáticas conocidas
            if k_sp < n and texto[k_sp] == "(" and (k_sp == j or ident_lower in _FUNCIONES_MATH):
                fin_fn = _saltar_parentesis_desde(k_sp)
                k_after = fin_fn
                while k_after < n and texto[k_after].isspace():
                    k_after += 1
                last_k, _ = _ultimo_no_lp()
                conectado_izq = bool(
                    (run_actual and run_actual[-1][0] == "OP")
                    or last_k in ("OP", "NUM")
                    or (last_k == "RP" and not had_space)
                    or unclosed_lp > 0
                )
                conectado_der = (
                    (
                        k_after < n
                        and texto[k_after] in "+-*/("
                        and texto[k_after:k_after + 2] != "--"
                    )
                    or (unclosed_lp > 0 and k_after < n and texto[k_after] == ")" and _sigue_op_tras_rp(k_after))
                )
                if conectado_izq or conectado_der:
                    run_tainted = True
                else:
                    _cerrar_run()
                i = fin_fn
                had_space = False
                continue

            # 2) Código alfanumérico con guiones encadenados: covid-19, A-12-3
            if j < n and texto[j] == "-" and j + 1 < n and texto[j + 1].isalnum():
                k = j
                while k < n and texto[k] == "-" and k + 1 < n and texto[k + 1].isalnum():
                    k += 1
                    while k < n and (texto[k].isalnum() or texto[k] in "._"):
                        k += 1
                k_after = k
                while k_after < n and texto[k_after].isspace():
                    k_after += 1
                last_k, _ = _ultimo_no_lp()
                conectado_izq = bool(
                    (run_actual and run_actual[-1][0] == "OP")
                    or last_k == "OP"
                    or (last_k == "RP" and not had_space)
                    or unclosed_lp > 0
                )
                conectado_der = (
                    (k < n and texto[k] in "+-*/(" and texto[k:k + 2] != "--")
                    or (k_after < n and texto[k_after] in "+-*/(" and texto[k_after:k_after + 2] != "--")
                    or (unclosed_lp > 0 and k_after < n and texto[k_after] == ")" and _sigue_op_tras_rp(k_after))
                )
                if conectado_izq or conectado_der:
                    run_tainted = True
                else:
                    _cerrar_run()
                i = k
                had_space = False
                continue

            # 3) Identificador / variable suelta (ej. "(1 + 2) * (a + 3)", "1 + 2 + x")
            last_k, lp_sp = _ultimo_no_lp()
            conectado_izq = bool(
                (run_actual and run_actual[-1][0] == "OP")
                or last_k == "OP"
                or (unclosed_lp > 0 and last_k in ("NUM", "RP") and not lp_sp)
            )
            conectado_der = False
            if k_sp < n:
                ch_after = texto[k_sp]
                if ch_after in "+*/":
                    conectado_der = True
                elif ch_after == "-" and texto[k_sp:k_sp + 2] != "--":
                    # Distinguir operador binario/parentético ("a - 3", "a-3", "(a -3)") de "-5" tras palabra en prosa ("dime -5 + 3")
                    if k_sp == j or (k_sp + 1 < n and texto[k_sp + 1].isspace()) or unclosed_lp > 0:
                        conectado_der = True
                elif ch_after == ")" and unclosed_lp > 0 and _sigue_op_tras_rp(k_sp):
                    conectado_der = True
            if conectado_izq or conectado_der:
                run_tainted = True
            else:
                _cerrar_run()
            i = j
            had_space = False
            continue

        # Guion largo "--" en prosa
        if texto[i:i + 2] == "--":
            _cerrar_run()
            while i < n and texto[i] == "-":
                i += 1
            had_space = False
            continue

        # Números (enteros o decimales con '.')
        if ch.isdigit():
            j = i
            while j < n and texto[j].isdigit():
                j += 1
            if j + 1 < n and texto[j] == "." and texto[j + 1].isdigit():
                j += 1
                while j < n and texto[j].isdigit():
                    j += 1
            if j < n and (texto[j].isalpha() or texto[j] == "_"):
                # Pegado a letras (ej. "2da", "3x", "3sin(4)"): contaminar si está ligado a operación
                last_k, lp_sp = _ultimo_no_lp()
                conectado_izq = bool(
                    (run_actual and run_actual[-1][0] == "OP")
                    or last_k == "OP"
                    or (unclosed_lp > 0 and last_k in ("NUM", "RP") and not lp_sp)
                )
                if conectado_izq:
                    run_tainted = True
                else:
                    _cerrar_run()
                i = j
                had_space = False
                continue
            if run_actual and run_actual[-1][0] == "NUM":
                # Nunca concatenar dos números adyacentes separados por espacios ("2 3 + 4")
                run_tainted = True
            run_actual.append(("NUM", texto[i:j], had_space))
            i = j
            had_space = False
            continue

        # Operadores
        if texto[i:i + 2] == "**":
            run_actual.append(("OP", "**", had_space))
            i += 2
            had_space = False
            continue

        if ch in "+-*/":
            run_actual.append(("OP", ch, had_space))
            i += 1
            had_space = False
            continue

        if ch == "(":
            run_actual.append(("LP", "(", had_space))
            unclosed_lp += 1
            i += 1
            had_space = False
            continue

        if ch == ")":
            run_actual.append(("RP", ")", had_space))
            if unclosed_lp > 0:
                unclosed_lp -= 1
            i += 1
            had_space = False
            continue

        _cerrar_run()
        i += 1
        had_space = True

    _cerrar_run()

    # Dividir por paréntesis desbalanceados
    sub_runs: List[List[Tuple[str, str, bool]]] = []
    for run in tokens_runs:
        pila_lp: List[int] = []
        actual: List[Tuple[str, str, bool]] = []
        for tok in run:
            if tok[0] == "LP":
                pila_lp.append(len(actual))
                actual.append(tok)
            elif tok[0] == "RP":
                if pila_lp:
                    pila_lp.pop()
                    actual.append(tok)
                else:
                    if actual:
                        sub_runs.append(actual)
                        actual = []
            else:
                actual.append(tok)
        if actual:
            if pila_lp:
                # Dividir en los LP sin cerrar para rescatar sub-expresiones internas válidas
                cortes = set(pila_lp)
                segmento: List[Tuple[str, str, bool]] = []
                for idx_tok, tok in enumerate(actual):
                    if idx_tok in cortes:
                        if segmento:
                            sub_runs.append(segmento)
                            segmento = []
                    else:
                        segmento.append(tok)
                if segmento:
                    sub_runs.append(segmento)
            else:
                sub_runs.append(actual)

    candidatas: List[Tuple[int, str]] = []
    for sub in sub_runs:
        # Recortar operadores inválidos al inicio y al final
        while sub and sub[0][0] == "OP":
            if sub[0][1] in ("+", "-") and len(sub) > 1 and sub[1][0] in ("NUM", "LP"):
                break
            sub.pop(0)
        while sub and sub[-1][0] == "OP":
            sub.pop()
        if not sub:
            continue

        # Calcular si cada ')' pertenece a un grupo '(...)' con al menos un OP interno
        pila_info: List[bool] = []
        rp_tiene_op = {}
        for idx_tok, (kind, _, _) in enumerate(sub):
            if kind == "LP":
                pila_info.append(False)
            elif kind == "OP":
                if pila_info:
                    pila_info[-1] = True
            elif kind == "RP":
                tiene = pila_info.pop() if pila_info else False
                rp_tiene_op[idx_tok] = tiene
                if tiene and pila_info:
                    pila_info[-1] = True

        # Insertar multiplicación implícita: 2(3+4), (2+3)(4+1), (3+4)2
        segmentos_expandidos: List[List[Tuple[str, str]]] = []
        expandida: List[Tuple[str, str]] = []
        segmento_invalido = False
        for idx_tok, (kind, lex, sp) in enumerate(sub):
            if expandida:
                prev_kind = expandida[-1][0]
                if prev_kind == "NUM" and kind == "NUM":
                    segmento_invalido = True
                    break
                if prev_kind == "NUM" and kind == "LP":
                    expandida.append(("OP", "*"))
                elif prev_kind == "RP" and kind == "LP":
                    expandida.append(("OP", "*"))
                elif prev_kind == "RP" and kind == "NUM":
                    prev_orig_idx = idx_tok - 1
                    if not sp or rp_tiene_op.get(prev_orig_idx, False):
                        expandida.append(("OP", "*"))
                    else:
                        # Ej: "Ejercicio (2) 5 + 3" -> preservar segmento previo y reiniciar
                        segmentos_expandidos.append(expandida)
                        expandida = []
            expandida.append((kind, lex))
        if segmento_invalido:
            continue
        if expandida:
            segmentos_expandidos.append(expandida)

        for seg_exp in segmentos_expandidos:
            # Verificar al menos un operador binario real y paréntesis balanceados
            prof = 0
            ops_binarios = 0
            secuencia_valida = True
            for idx_tok, (kind, lex) in enumerate(seg_exp):
                if kind == "LP":
                    prof += 1
                elif kind == "RP":
                    prof -= 1
                    if prof < 0:
                        secuencia_valida = False
                        break
                elif kind == "OP":
                    prev_k = seg_exp[idx_tok - 1][0] if idx_tok > 0 else None
                    next_k = seg_exp[idx_tok + 1][0] if idx_tok + 1 < len(seg_exp) else None
                    if prev_k in ("NUM", "RP"):
                        ops_binarios += 1
                        if next_k not in ("NUM", "LP", "OP"):
                            secuencia_valida = False
                            break
                    else:
                        # Operador unario: solo '+' o '-' delante de NUM o LP
                        if lex not in ("+", "-") or next_k not in ("NUM", "LP"):
                            secuencia_valida = False
                            break
            if not secuencia_valida or prof != 0 or ops_binarios == 0:
                continue

            # Reconstruir expresión Python limpia
            partes: List[str] = []
            for idx_tok, (kind, lex) in enumerate(seg_exp):
                if kind == "OP":
                    prev_k = seg_exp[idx_tok - 1][0] if idx_tok > 0 else None
                    if prev_k in ("NUM", "RP"):
                        partes.append(f" {lex} ")
                    else:
                        partes.append(lex)
                else:
                    partes.append(lex)
            expr_str = "".join(partes).strip()
            try:
                ast.parse(expr_str, mode="eval")
            except SyntaxError:
                continue
            candidatas.append((ops_binarios * 10 + len(seg_exp), expr_str))

    candidatas.sort(key=lambda item: item[0], reverse=True)
    return [expr for _, expr in candidatas]


def _resolver_problema_verbal(texto_norm: str, texto_sin_tildes: str) -> Optional[str]:
    """
    Resuelve problemas verbales simples de primaria (suma, resta, multiplicación, reparto)
    evaluando la operación mediante `evaluar_ast_seguro` y evitando falsos positivos narrativos.
    """
    # 1. División / reparto ("para compartir" sin divisor numérico no es división)
    if (
        re.search(r"\b(?:repart\w*|divid\w*|distribu\w*|compart\w*)\b", texto_sin_tildes)
        and re.search(
            r"\b(?:entre|para\s+(?:\d+(?:\.\d+)?|cada\s+un[oa])|en\s+\d+|en\s+partes\s+iguales|grupos\s+iguales|cada\s+un[oa]|a\s+cada)\b",
            texto_sin_tildes,
        )
    ):
        op = "/"
        desc = "repartir"
    # 2. Multiplicación / agrupamiento (incluye "cada <sustantivo> cuesta/vale/...")
    elif (
        (
            re.search(
                r"\b(?:cajas?|bolsas?|paquetes?|filas?|grupos?|cestas?|frascos?|equipos?|mesas?|platos?|cuest\w*|valen?)\b",
                texto_sin_tildes,
            )
            and re.search(
                r"\b(?:cada\s+(?:un[oa]|caja|bolsa|paquete|fila|grupo|cesta|frasco|equipo|mesa|plato)|por\s+cada|con\s+\d+(?:\.\d+)?\s+\w+\s+cada)\b",
                texto_sin_tildes,
            )
        )
        or re.search(
            r"\bcada\s+[a-zñ]+\s+(?:cuesta|cuestan|vale|valen|pesa|pesan|mide|miden|trae|traen|tiene|tienen|contiene|contienen)\b"
            r"|\ba\s+\d+(?:\.\d+)?\s+(?:\w+\s+)?cada\b",
            texto_sin_tildes,
        )
    ):
        op = "*"
        desc = "multiplicar"
    # 3. Resta / pérdida (exige "(?:me|te|se) como", distingue sustantivo "regalo" y trata "le regalo"/"le di" como resta)
    elif (
        re.search(
            r"\b(?:comi|comio|comimos|(?:me|te|se)\s+como|gaste|gasto|gastamos|perdi|perdio|perdimos|"
            r"quite|quito|quitamos|saque|saco|sacamos|rompi|rompio|rompieron|pincharon|"
            r"volaron|se\s+fueron|quedan|sobran|faltan)\b",
            texto_sin_tildes,
        )
        or re.search(r"\ble\s+(?:regal[eoó]|regal[eé]|di|dio)\b", texto_norm)
        or re.search(
            r"(?<!\bme\s)(?<!\bnos\s)(?<!\bte\s)\b(?:regal[eé]|regaló|regalamos|di|dimos|vend[ií]|vendi[oó]|vendimos)\b",
            texto_norm,
        )
        or re.search(
            r"(?<!\bme\s)(?<!\bnos\s)(?<!\bte\s)(?<!\bel\s)(?<!\bun\s)(?<!\bmi\s)(?<!\bsu\s)(?<!\beste\s)(?<!\bese\s)(?<!\bdel\s)(?<!\bal\s)\bregalo(?=\s+(?:\d|un[oa]?\b))",
            texto_norm,
        )
    ):
        op = "-"
        desc = "restar"
    # 4. Suma / ganancia
    elif re.search(
        r"\b(?:(?:me|nos|te)\s+(?:regalan|regalaron|regalo|dan|dieron|dio)|regalan|regalaron|dieron|"
        r"compre|compro|compramos|encontre|encontro|gano|gane|recibi|recibio|"
        r"agregue|agrego|anadi|anado|llegan|llegaron(?!\s+(?:\d+(?:\.\d+)?\s+)?tarde\b)|suben|subieron|junte|junto|reuni|"
        r"en\s+total)\b",
        texto_sin_tildes,
    ):
        op = "+"
        desc = "sumar"
    else:
        return None

    # Proteger años históricos, ordinales ("en 2024", "2.°") y códigos con guiones ("A-12-3")
    t_limpio = re.sub(r"\b(?:en|del|ano|año|desde|hasta)\s+(?:1[5-9]\d{2}|20\d{2})\b", " ", texto_norm)
    t_limpio = re.sub(r"\b\d+\s*[°ºª]\b", " ", t_limpio)
    t_limpio = re.sub(r"\b[a-zA-ZñÑáéíóúü_]+(?:-[a-zA-ZñÑáéíóúü_\d]+)+\b", " ", t_limpio)

    patron_num = re.compile(r"(?<![a-zA-ZñÑáéíóúü_])-?\d+(?:\.\d+)?(?![a-zA-ZñÑáéíóúü_])")
    nums_con_pos: List[Tuple[int, str, bool]] = [
        (m.start(), m.group(0), False) for m in patron_num.finditer(t_limpio)
    ]
    if len(nums_con_pos) < 2:
        # Recuperar "un" / "una" singular como cantidad = 1 solo si falta operando,
        # evitando locuciones/artículos y compras no monetarias frente a gastos ("Compré una mochila y gasté 20 soles")
        palabras_t = list(re.finditer(r"[a-zA-ZñÑáéíóúü]+", t_limpio))
        prev_bloqueadas = {
            "cada", "por", "para", "a", "de", "en", "con", "sin",
            "sobre", "entre", "hacia", "el", "la", "los", "las",
        }
        next_bloqueadas = {
            "vez", "veces", "poco", "rato", "momento", "dia", "dias",
            "semana", "mes", "ano", "par", "total", "amigo", "amiga",
            "companero", "companera", "nino", "nina", "problema",
            "ejemplo", "historia", "cuento", "pregunta", "duda", "idea",
            "cosa", "respuesta", "clase", "nota", "tarea", "prueba",
            "examen", "leccion", "de", "que", "se", "no", "solo",
        }
        unidades_moneda = {
            "sol", "soles", "peso", "pesos", "euro", "euros", "dolar", "dolares",
            "boliviano", "bolivianos", "centavo", "centavos", "moneda", "monedas",
            "billete", "billetes",
        }
        tiene_gasto_monetario = bool(re.search(
            r"\b(?:gast[eo]|gaste|gastamos|pagu[eo]|pag[eo]|pagamos|cost[eo]|cuest[ae]|val[e])\b",
            texto_sin_tildes,
        ))
        for idx_p, mp in enumerate(palabras_t):
            w_norm = _quitar_tildes(mp.group(0).lower())
            if w_norm not in ("un", "una"):
                continue
            prev_w = _quitar_tildes(palabras_t[idx_p - 1].group(0).lower()) if idx_p > 0 else ""
            next_w = _quitar_tildes(palabras_t[idx_p + 1].group(0).lower()) if idx_p + 1 < len(palabras_t) else ""
            if prev_w in prev_bloqueadas or next_w in next_bloqueadas:
                continue
            if tiene_gasto_monetario and next_w not in unidades_moneda:
                continue
            nums_con_pos.append((mp.start(), "1", True))
        nums_con_pos.sort(key=lambda item: item[0])

    if len(nums_con_pos) != 2:
        return None

    (pos1, n1_str, n1_inf), (pos2, n2_str, n2_inf) = nums_con_pos[0], nums_con_pos[1]
    if op == "-":
        pref_n2 = _quitar_tildes(t_limpio[:pos2])
        if re.search(r"\b(?:de\s+(?:mis|tus|sus|los|las|estos|estas|esos|esas)|tenia)\s*$", pref_n2):
            n1_str, n2_str = n2_str, n1_str
            n1_inf, n2_inf = n2_inf, n1_inf
        if n1_inf and float(n1_str) < float(n2_str):
            return None

    try:
        resultado = evaluar_ast_seguro(f"{n1_str} {op} {n2_str}")
    except ZeroDivisionError:
        return _MENSAJE_CERO
    except _ErrorDominioReal:
        return _MENSAJE_DOMINIO_REAL
    except _ErrorRangoEscolar:
        return _MENSAJE_RANGO_PRIMARIA
    except ValueError:
        return None

    val = _formatear_numero(resultado)
    n1_bonito = _formatear_numero(float(n1_str))
    n2_bonito = _formatear_numero(float(n2_str))
    simbolo = {"+": "+", "-": "-", "*": "×", "/": "÷"}[op]
    return (
        f"¡Resolvamos el problema juntos! Al {desc} hacemos {n1_bonito} {simbolo} {n2_bonito}, "
        f"lo que nos da como resultado {val}. ¡Anota el {val} en tu cuaderno!"
    )


_RE_NUM_PREFIJO = re.compile(r"(-\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d.])(?!\s*%)")
_RE_NUM_EXP = re.compile(r"(-\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d.])")
_RE_POW_SEP = re.compile(r"\s*\*\*\s*")


def _reescribir_operadores_prefijo(
    texto: str,
    incluir_pct: bool = True,
    incluir_unarios: bool = True,
) -> str:
    """
    Reescribe en una sola pasada O(n) y de adentro hacia afuera operadores prefijo
    (`X% de <arg>` y `(la/el) mitad/doble/triple de <arg>`), soportando
    encadenamientos, paréntesis anidados, operandos negativos `-(...)` y potencias `**`.
    """
    if incluir_pct and "%" not in texto:
        incluir_pct = False
    if incluir_unarios and "mitad" not in texto and "doble" not in texto and "triple" not in texto:
        incluir_unarios = False
    if not incluir_pct and not incluir_unarios:
        return texto

    partes_pat: List[str] = []
    if incluir_pct:
        partes_pat.append(r"(?P<pct>(?<![a-zA-ZñÑáéíóúü_])\d+(?:\.\d+)?)\s*%\s*de\b(?:\s+(?:la|el)\b)?")
    if incluir_unarios:
        partes_pat.append(r"\b(?:(?:la|el)\s+)?(?P<unario>mitad|doble|triple)\s+de\b(?:\s+(?:la|el)\b)?")
    patron = re.compile("|".join(partes_pat))

    matches = list(patron.finditer(texto))
    if not matches:
        return texto

    n = len(texto)
    cierre_paren = _precomputar_cierres_paren(texto)
    op_map = {"mitad": "/ 2", "doble": "* 2", "triple": "* 3"}

    out: List[str] = []
    pending: List[Tuple[str, str, str]] = []
    paren_stack: List[Tuple[List[str], List[Tuple[str, str, str]], str, int]] = []

    def _flush_pending() -> None:
        for _, _, raw_txt in pending:
            out.append(raw_txt)
        pending.clear()

    def _aplicar_arg(arg: str, pos_fin: int) -> int:
        nonlocal out, pending
        while pos_fin < n:
            m_pow = _RE_POW_SEP.match(texto, pos_fin)
            if not m_pow:
                break
            pos_exp = m_pow.end()
            if pos_exp < n and texto[pos_exp] == "(" and pos_exp in cierre_paren:
                paren_stack.append((out, pending, f"{arg} ** ", cierre_paren[pos_exp]))
                out = []
                pending = []
                return pos_exp + 1
            m_enum = _RE_NUM_EXP.match(texto, pos_exp)
            if not m_enum:
                break
            arg = f"{arg} ** {m_enum.group(1).replace(' ', '')}"
            pos_fin = m_enum.end()

        while pending:
            kind, payload, _ = pending.pop()
            if kind == "pct":
                if " ** " in arg and not (arg.startswith("(") and arg.endswith(")")):
                    arg = f"({arg})"
                arg = f"(({payload} / 100) * {arg})"
            else:
                arg = f"({arg} {payload})"
        out.append(arg)
        return pos_fin

    i = 0
    match_idx = 0
    num_matches = len(matches)
    while i < n:
        if paren_stack and i == paren_stack[-1][3]:
            if pending:
                _flush_pending()
            saved_out, saved_pending, prefix_str, _ = paren_stack.pop()
            inner = "".join(out)
            out = saved_out
            pending = saved_pending
            arg = f"{prefix_str}({inner})"
            if pending:
                i = _aplicar_arg(arg, i + 1)
            else:
                out.append(arg)
                i += 1
            continue

        while match_idx < num_matches and matches[match_idx].start() < i:
            match_idx += 1

        if match_idx < num_matches and matches[match_idx].start() == i:
            m = matches[match_idx]
            match_idx += 1
            k = m.end()
            while k < n and texto[k].isspace():
                k += 1
            raw_txt = texto[i:k]
            pct_val = m.group("pct") if incluir_pct else None
            if pct_val is not None:
                pending.append(("pct", pct_val, raw_txt))
            else:
                tipo = m.group("unario")
                pending.append(("op", op_map[tipo], raw_txt))
            i = k
            continue

        if pending:
            if texto[i] == "(" and i in cierre_paren:
                paren_stack.append((out, pending, "", cierre_paren[i]))
                out = []
                pending = []
                i += 1
                continue
            if texto[i] in "+-":
                p_lp = i + 1
                while p_lp < n and texto[p_lp].isspace():
                    p_lp += 1
                if p_lp < n and texto[p_lp] == "(" and p_lp in cierre_paren:
                    paren_stack.append((out, pending, texto[i], cierre_paren[p_lp]))
                    out = []
                    pending = []
                    i = p_lp + 1
                    continue
            m_num = _RE_NUM_PREFIJO.match(texto, i)
            if m_num:
                arg = m_num.group(1).replace(" ", "")
                i = _aplicar_arg(arg, m_num.end())
                continue
            _flush_pending()
            out.append(texto[i])
            i += 1
            continue

        salto = n
        if match_idx < num_matches and matches[match_idx].start() < salto:
            salto = matches[match_idx].start()
        if paren_stack and paren_stack[-1][3] < salto:
            salto = paren_stack[-1][3]
        if salto == i:
            out.append(texto[i])
            i += 1
        else:
            out.append(texto[i:salto])
            i = salto

    if pending:
        _flush_pending()
    while paren_stack:
        saved_out, saved_pending, prefix_str, _ = paren_stack.pop()
        inner = "".join(out)
        out = saved_out
        pending = saved_pending
        out.append(f"{prefix_str}({inner})")
        if pending:
            _flush_pending()

    return "".join(out)


def _aplicar_porcentaje_aislado(t: str) -> str:
    """Convierte porcentajes aislados (`20% + 30%`) evitando falsos positivos (`15% de descuento`)."""
    t_sin_pct = _quitar_tildes(re.sub(r"(?<![a-zA-ZñÑáéíóúü_])\d+(?:\.\d+)?\s*%", " ", t))
    t_sin_pct = re.sub(r"\bpor\s+favor\b", " ", t_sin_pct)
    tiene_otro_op = bool(re.search(
        r"[+*/^×÷]|(?<!\w)-(?!\w)|\s-\s|\b(?:mas|menos|por|entre|veces|dividido|multiplicado|elevado|cuadrado|cubo|mitad|doble|triple)\b",
        t_sin_pct,
    ))
    if tiene_otro_op:
        t = re.sub(r"(?<![a-zA-ZñÑáéíóúü_])(\d+(?:\.\d+)?)\s*%(?!\s*(?:\d|de\b))", r"(\1 / 100)", t)
    return t


def _reescribir_porcentajes(texto: str) -> str:
    """Convierte `por ciento` / `%` evitando falsos positivos como `15% de descuento`."""
    t = re.sub(r"\bpor\s+ciento\b", "%", texto)
    t = _reescribir_operadores_prefijo(t, incluir_pct=True, incluir_unarios=False)
    return _aplicar_porcentaje_aislado(t)


def _reescribir_mitad_doble_triple(texto: str) -> str:
    """
    Reescribe de adentro hacia afuera `(la/el) mitad/doble/triple de <arg>`
    soportando paréntesis anidados, encadenamientos (`la mitad de la mitad de 8`),
    negativos parentéticos (`-(2+3)`) y potencias sobre el operando (`el doble de 10 ** 2`).
    """
    return _reescribir_operadores_prefijo(texto, incluir_pct=False, incluir_unarios=True)


def resolver_pregunta_matematica(texto: str) -> Optional[str]:
    """
    Detecta preguntas matemáticas infantiles en español y devuelve una explicación
    breve, cálida y pedagógica paso a paso.
    """
    if not isinstance(texto, str) or not texto.strip():
        return None

    t_norm = re.sub(r"\s+", " ", texto.lower().strip())
    t_sin_tildes = _quitar_tildes(t_norm)

    # 1. Guarda conceptual/narrativa PRIMERO (con límites de palabra, sin contar '/' como cálculo)
    pide_calcular = bool(re.search(
        r"\b(?:cuant[oa]s?|calcul\w*|resuelv\w*|resolver|hall\w*|evalu\w*|"
        r"resultado\s+de|dime\s+el\s+resultado|haz\s+la\s+cuenta)\b",
        t_sin_tildes,
    ))
    es_conceptual = bool(re.search(
        r"\b(?:por\s+que|porque|que\s+es|que\s+son|que\s+significa|significa\w*|"
        r"quiere\s+decir|explica\w*|defin\w*|concepto|para\s+que\s+sirve|"
        r"diferencia\s+entre|mayor\s+que|menor\s+que|igual\s+(?:a|que)|equivalente\w*|compar(?:a|ar|ando|ado|acion|aciones|ativa|ativo)?|"
        r"como\s+se\s+(?:lee|llama|escribe|representa|suma|resta|multiplica|divide|simplifica|amplifica|hace|opera)|"
        r"quien(?:es)?|donde|cuando|historia|cuento)\b",
        t_sin_tildes,
    ))
    if es_conceptual and not pide_calcular:
        return None

    # Proteger preguntas de equivalencia/subdivisión ("¿Cuántos cuartos hay en 1/2?")
    if (
        re.search(r"\bcuant[oa]s\s+[a-zñ]+\s+(?:hay|caben|entran)\s+en\b", t_sin_tildes)
        and re.search(r"\d+\s*/\s*\d+", t_sin_tildes)
        and not re.search(r"\b(?:calcul\w*|resuelv\w*|resolver|hall\w*|evalu\w*)\b", t_sin_tildes)
    ):
        return None

    # Proteger menciones narrativas / recetas / dibujo con fracción aislada ("Necesito 3/4 de taza...", "Dibuja 1/2 de un círculo")
    if re.search(r"\d+\s*/\s*\d+", t_sin_tildes) and not pide_calcular:
        t_sin_frac = re.sub(r"\d+\s*/\s*\d+", " ", t_sin_tildes)
        tiene_otro_op = bool(re.search(
            r"[+\-*^×÷%]|\b(?:mas|menos|por(?!\s+favor\b)|entre|veces|dividido|multiplicado|elevado|cuadrado|cubo|mitad|doble|triple)\b",
            t_sin_frac,
        ))
        es_mencion_narrativa = bool(re.search(
            r"\b(?:necesit\w*|dibuj\w*|pint\w*|colore\w*|recort\w*|cort\w*|traz\w*|receta|taza|cucharad\w*|"
            r"harina|azucar|leche|agua|aceite|circulo|triangulo|rectangulo|cuadrado|pastel|pizza|torta|hoja|"
            r"de\s+un[oa]?\s+[a-zñ]+)\b",
            t_sin_frac,
        ))
        if not tiene_otro_op and es_mencion_narrativa:
            return None

    # 2. Normalización de comas decimales y protección de fechas / rangos en prosa / teléfonos
    t = re.sub(r"(\d),(\d)", r"\1.\2", t_norm)
    t = re.sub(r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b", " ", t)
    if not pide_calcular:
        t = re.sub(r"\b(?:19|20)\d{2}[-–](?:19|20)\d{2}\b", " ", t)
        t = re.sub(
            r"\b(?:p[aá]ginas?|p[aá]gs?\.?|cap[ií]tulos?|caps?\.?|de\s+las?|entre\s+las?)\s+\d{1,4}\s*[-–]\s*\d{1,4}\b",
            " ",
            t,
        )
        t = re.sub(r"\bhorario(?:\s+es)?(?:\s+de)?\s+\d{1,2}\s*[-–]\s*\d{1,2}\b", " ", t)

        def _quitar_rango_de(m_rango: re.Match) -> str:
            pref_r = _quitar_tildes(t[:m_rango.start()].rstrip())
            if re.search(
                r"(?:%|por\s+ciento|\b(?:calculo|resta|diferencia|operacion|valor|mitad|doble|triple))$",
                pref_r,
            ):
                return m_rango.group(0)
            return " "

        t = re.sub(r"\bde\s+\d{1,2}\s*[-–]\s*\d{1,2}\b", _quitar_rango_de, t)
        t = re.sub(r"\b\d{3,4}-\d{4}\b", " ", t)
        t = re.sub(
            r"\b(?:hoy\s+es|fecha(?:\s+es)?|el\s+d[ií]a|desde\s+el|hasta\s+el|el|del|al)\s+\d{1,2}/\d{1,2}\b",
            " ",
            t,
        )

    # 3. Conversión de palabras numéricas en español (0..999999)
    t = _reemplazar_palabras_numericas(t)

    # 4. Casos verbales simples en primaria: "la mitad de X", "el doble de X", "el triple de X"
    #    Solo tomar el atajo pedagógico si NO hay otras operaciones o términos aritméticos fuera del match.
    m_unaria = re.search(
        r"\b(mitad|doble|triple)\s+de\s+(?:la\s+|el\s+)?(?:\(\s*(-\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?)\s*\)|(-\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d.]))"
        r"(?!\s*(?:[+\-*/^%(]|\*\*|[x×÷]|\b(?:m[aá]s|menos|por|entre|veces|dividido|multiplicado|elevado|al\s+cuadrado|al\s+cubo)\b))",
        t,
    )
    es_unaria_aislada = False
    if m_unaria:
        fuera_unaria = _quitar_tildes(t[:m_unaria.start()] + " " + t[m_unaria.end():])
        fuera_unaria = re.sub(r"\bpor\s+favor\b", " ", fuera_unaria)
        es_unaria_aislada = not bool(re.search(
            r"\d|[+\-*/^%×÷()]|\b(?:mas|menos|por|entre|veces|dividido|multiplicado|elevado|cuadrado|cubo|mitad|doble|triple)\b",
            fuera_unaria,
        ))
    if m_unaria and es_unaria_aislada:
        tipo = m_unaria.group(1)
        raw_num = (m_unaria.group(2) or m_unaria.group(3)).replace(" ", "")
        n = float(raw_num)
        if abs(n) > MAX_ABS_OPERANDO:
            return _MENSAJE_RANGO_PRIMARIA
        if tipo == "mitad":
            res = n / 2.0
            if abs(res) > MAX_ABS_OPERANDO * 100:
                return _MENSAJE_RANGO_PRIMARIA
            n_txt = _formatear_numero(n)
            val = _formatear_numero(res)
            return f"¡Calculemos juntos! La mitad de {n_txt} es repartir {n_txt} en 2 partes iguales: ¡da {val}!"
        if tipo == "doble":
            res = n * 2.0
            if abs(res) > MAX_ABS_OPERANDO * 100:
                return _MENSAJE_RANGO_PRIMARIA
            n_txt = _formatear_numero(n)
            val = _formatear_numero(res)
            return f"¡Súper fácil! El doble de {n_txt} es sumar {n_txt} + {n_txt}, ¡que nos da {val}!"
        res = n * 3.0
        if abs(res) > MAX_ABS_OPERANDO * 100:
            return _MENSAJE_RANGO_PRIMARIA
        n_txt = _formatear_numero(n)
        val = _formatear_numero(res)
        return f"¡Vamos a verlo! El triple de {n_txt} es {n_txt} × 3, ¡y el resultado es {val}!"

    # Guardar copia antes de reescribir operadores verbales para el fallback de problemas verbales
    t_para_problema = t

    # 5. Normalización de expresiones compuestas, potencias, porcentajes, unarios y operadores
    t = t.replace("\u2212", "-")
    t = re.sub(r"[¿?¡!]", " ", t)
    t = re.sub(r"\bpor\s+favor\b", " ", t)
    t = re.sub(r"\bcu[aá]nto\s+(?:es|da|son|vale|sale)\b", " ", t)
    t = re.sub(r"\b(?:calcul\w*|resuelv\w*|resolver|hall\w*|evalu\w*)\b", " ", t)

    # Potencias PRIMERO (para que "20% de 2^3" y "el doble de 10^2" absorban la potencia completa)
    reemplazos_potencias = [
        (r"\belevado\s+al\s+cuadrado\b", " ** 2 "),
        (r"\belevado\s+al\s+cubo\b", " ** 3 "),
        (r"\bal\s+cuadrado\b", " ** 2 "),
        (r"\bal\s+cubo\b", " ** 3 "),
        (r"\belevado\s+a\s+la\s+potencia\b", " ** "),
        (r"\belevado\s+a\s+la\b", " ** "),
        (r"\belevado\s+a\b", " ** "),
        (r"\^", " ** "),
    ]
    for patron, simbolo in reemplazos_potencias:
        t = re.sub(patron, simbolo, t)

    # Porcentajes y mitad/doble/triple en pasada unificada O(n) de adentro hacia afuera
    t = re.sub(r"\bpor\s+ciento\b", "%", t)
    t = _reescribir_operadores_prefijo(t, incluir_pct=True, incluir_unarios=True)
    t_aislado = _aplicar_porcentaje_aislado(t)
    if t_aislado != t:
        t = _reescribir_operadores_prefijo(t_aislado, incluir_pct=True, incluir_unarios=True)

    # Ecuaciones/afirmaciones con resultado numérico a la derecha ("1 + 2 = 3", "¿Es verdad que 2 + 2 = 4?"):
    # devolver None para que responda el tutor sin concatenar LHS y RHS.
    if re.search(r"=\s*(?:[-+(]|\d)", t):
        return None

    # Operadores aritméticos verbales y símbolos
    reemplazos_operadores = [
        (r"\bmultiplicado\s+por\b", " * "),
        (r"\bdividido\s+(?:entre|por|para)\b", " / "),
        (r"\bm[aá]s\b", " + "),
        (r"\bmenos\b", " - "),
        (r"\b(?:por|veces)\b", " * "),
        (r"(?<=[\d\)])\s*[x×]\s*(?=[\d\(\-])", " * "),
        (r"×", " * "),
        (r"\bentre\b", " / "),
        (r"÷", " / "),
    ]
    for patron, simbolo in reemplazos_operadores:
        t = re.sub(patron, simbolo, t)

    # 6. Extracción balanceada de expresiones y evaluación AST
    candidatas = _extraer_expresiones_matematicas(t)
    for expresion in candidatas:
        try:
            resultado = evaluar_ast_seguro(expresion)
        except ZeroDivisionError:
            return _MENSAJE_CERO
        except _ErrorDominioReal:
            return _MENSAJE_DOMINIO_REAL
        except _ErrorRangoEscolar:
            return _MENSAJE_RANGO_PRIMARIA
        except ValueError:
            continue

        val = _formatear_numero(resultado)
        expresion_bonita = (
            re.sub(r"\s+", " ", expresion)
            .replace("**", "^")
            .replace("//", "÷")
            .replace("*", "×")
            .replace("/", "÷")
        )
        return (
            f"¡Vamos a calcularlo juntos! La operación {expresion_bonita} da como resultado {val}. "
            f"¡Anota el {val} en tu cuaderno revisando bien tus números!"
        )

    # 7. Respaldo para problemas verbales simples de primaria
    return _resolver_problema_verbal(t_para_problema, _quitar_tildes(t_para_problema))

