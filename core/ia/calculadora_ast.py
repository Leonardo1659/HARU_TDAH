"""
Calculadora Aritmética Segura con `ast` (Cero `eval`, Cero `SymPy`)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Resuelve operaciones escolares de primaria expresadas en lenguaje natural
("¿cuánto es 15 más 7?", "8 por 4", "la mitad de 24", "(12 + 8) entre 4")
evaluando únicamente nodos `ast` numéricos permitidos y bloqueando cualquier
ejecución arbitraria o exponentes gigantes.
"""

import ast
import operator
import re
from typing import Optional, Union

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


def evaluar_ast_seguro(expresion: str) -> Numero:
    """Evalúa de forma estrictamente segura una expresión aritmética."""
    if not expresion or len(expresion) > 120:
        raise ValueError("Expresión inválida o demasiado larga.")

    arbol = ast.parse(expresion.strip(), mode="eval")

    def _eval_nodo(nodo: ast.AST, profundidad: int = 0) -> Numero:
        if profundidad > 16:
            raise ValueError("Expresión demasiado anidada.")
        if isinstance(nodo, ast.Expression):
            return _eval_nodo(nodo.body, profundidad + 1)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)) and not isinstance(nodo.value, bool):
            if abs(nodo.value) > MAX_ABS_OPERANDO:
                raise ValueError("Número fuera del rango escolar permitido.")
            return nodo.value
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES_UNARIOS:
            return _OPERADORES_UNARIOS[type(nodo.op)](_eval_nodo(nodo.operand, profundidad + 1))
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES_BINARIOS:
            izq = _eval_nodo(nodo.left, profundidad + 1)
            der = _eval_nodo(nodo.right, profundidad + 1)
            if isinstance(nodo.op, ast.Pow):
                if abs(izq) > MAX_BASE_POTENCIA or abs(der) > MAX_EXPONENTE:
                    raise ValueError("Potencia fuera del rango escolar seguro.")
            if isinstance(nodo.op, (ast.Div, ast.FloorDiv, ast.Mod)) and der == 0:
                raise ZeroDivisionError("División entre cero.")
            res = _OPERADORES_BINARIOS[type(nodo.op)](izq, der)
            if abs(res) > MAX_ABS_OPERANDO * 100:
                raise ValueError("Resultado demasiado grande.")
            return res
        raise ValueError(f"Operación no permitida: {type(nodo).__name__}")

    return _eval_nodo(arbol)


def resolver_pregunta_matematica(texto: str) -> Optional[str]:
    """
    Detecta preguntas matemáticas infantiles en español y devuelve una explicación
    breve, cálida y pedagógica paso a paso.
    """
    if not texto:
        return None

    t = texto.lower().strip()

    # Casos verbales frecuentes en primaria: "la mitad de X", "el doble de X", "el triple de X"
    m_mitad = re.search(r"\bmitad\s+de\s+(\d+(?:\.\d+)?)\b", t)
    if m_mitad:
        n = float(m_mitad.group(1))
        res = n / 2.0
        val = int(res) if res == int(res) else round(res, 2)
        n_txt = int(n) if n == int(n) else n
        return f"¡Calculemos juntos! La mitad de {n_txt} es repartir {n_txt} en 2 partes iguales: ¡da {val}!"

    m_doble = re.search(r"\bdoble\s+de\s+(\d+(?:\.\d+)?)\b", t)
    if m_doble:
        n = float(m_doble.group(1))
        res = n * 2.0
        val = int(res) if res == int(res) else round(res, 2)
        n_txt = int(n) if n == int(n) else n
        return f"¡Súper fácil! El doble de {n_txt} es sumar {n_txt} + {n_txt}, ¡que nos da {val}!"

    m_triple = re.search(r"\btriple\s+de\s+(\d+(?:\.\d+)?)\b", t)
    if m_triple:
        n = float(m_triple.group(1))
        res = n * 3.0
        val = int(res) if res == int(res) else round(res, 2)
        n_txt = int(n) if n == int(n) else n
        return f"¡Vamos a verlo! El triple de {n_txt} es {n_txt} × 3, ¡y el resultado es {val}!"

    # Evitar falsos positivos si es una pregunta narrativa/histórica sin intención de cálculo
    tiene_intencion_mate = any(
        w in t for w in (
            "cuánto", "cuanto", "calcula", "resuelve", "suma", "resta",
            "multiplica", "divide", "resultado", "+", "*", "×", "÷", "/", "="
        )
    )
    es_pregunta_narrativa = any(
        w in t for w in ("por qué", "porque", "quién", "quien", "dónde", "donde", "cuándo", "cuando", "historia", "cuento", "significa")
    )
    if es_pregunta_narrativa and not tiene_intencion_mate:
        return None

    t = re.sub(r"[¿?¡!=]", " ", t)
    reemplazos_regex = [
        (r"\bcu[aá]nto\s+(?:es|da)\b", " "),
        (r"\b(?:calcula|resuelve)\b", " "),
        (r"\bmultiplicado\s+por\b", " * "),
        (r"\bdividido\s+(?:entre|por)\b", " / "),
        (r"\bal\s+cuadrado\b", " ** 2 "),
        (r"\bal\s+cubo\b", " ** 3 "),
        (r"\belevado\s+a\b", " ** "),
        (r"\bm[aá]s\b", " + "),
        (r"\bmenos\b", " - "),
        (r"\b(?:por|veces)\b", " * "),
        (r"(?<=\d)\s*[x×]\s*(?=\d)", " * "),
        (r"×", " * "),
        (r"\bentre\b", " / "),
        (r"÷", " / "),
    ]
    for patron, simbolo in reemplazos_regex:
        t = re.sub(patron, simbolo, t)

    # Extraer expresión aritmética válida con paréntesis opcionales
    coincidencia = re.search(
        r"(\(?\s*\d+(?:\.\d+)?\s*\)?(?:\s*(?:\*\*|[\+\-\*\/])\s*\(?\s*\d+(?:\.\d+)?\s*\)?)+)",
        t,
    )
    if not coincidencia:
        return None

    expresion = coincidencia.group(1).strip()
    try:
        resultado = evaluar_ast_seguro(expresion)
    except ZeroDivisionError:
        return "¡Ups! En matemáticas no podemos repartir ni dividir entre cero. ¡Prueba con otro número!"
    except Exception:
        return None

    val = int(resultado) if resultado == int(resultado) else round(float(resultado), 2)
    expresion_bonita = (
        re.sub(r"\s+", " ", expresion)
        .replace("**", "^")
        .replace("*", "×")
        .replace("/", "÷")
    )
    return (
        f"¡Vamos a calcularlo juntos! La operación {expresion_bonita} da como resultado {val}. "
        f"¡Anota el {val} en tu cuaderno revisando bien tus números!"
    )

