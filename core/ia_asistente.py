"""
Fachada de compatibilidad hacia `core.ia` para importaciones existentes.
"""

from core.ia.calculadora_ast import evaluar_ast_seguro, resolver_pregunta_matematica
from core.ia.motor_ia import MotorIAHaru, SYSTEM_INSTRUCTION_HARU

__all__ = [
    "MotorIAHaru",
    "SYSTEM_INSTRUCTION_HARU",
    "evaluar_ast_seguro",
    "resolver_pregunta_matematica",
]
