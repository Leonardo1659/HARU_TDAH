"""
Módulo de Control del Semáforo Visual Nativo para Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Gestiona la guía visual de 3 luces (Inicio, Avance, Meta) integrada en la
interfaz del estudiante, 100% nativa y sin dependencias de puertos seriales
ni hardware externo.
"""

import math
import threading
from typing import Callable, List, Optional


class ControladorSemaforoVisual:
    """Controlador 100% nativo del Semáforo Visual Pedagógico (Inicio, Avance, Meta)."""

    def __init__(
        self,
        puerto_default: str = "Guía Visual",
        baudrate: int = 9600,
        callback_gui: Optional[Callable[[List[bool], str], None]] = None,
    ):
        self.puerto_default = puerto_default or "Guía Visual"
        self.puerto_actual = "Guía Visual"
        self.baudrate = baudrate
        self.conexion = None
        self.en_simulacion = True
        self.callback_gui = callback_gui
        self.estado_leds: List[bool] = [False, False, False]
        self.ultimo_comando: str = "OFF"
        self._lock = threading.Lock()

        self.conectar()

    def listar_puertos_disponibles(self) -> List[str]:
        """Devuelve lista vacía al operar como Semáforo Visual nativo sin escaneo COM."""
        return []

    def conectar(self, puerto_especifico: Optional[str] = None) -> bool:
        """Activa de inmediato el modo de Guía Visual nativa sin abrir puertos seriales."""
        with self._lock:
            self.en_simulacion = True
            self.puerto_actual = "Guía Visual"
            self.conexion = None
        return True

    def enviar_comando(self, comando: str) -> None:
        """Registra internamente el comando visual actual con seguridad multihilo."""
        with self._lock:
            self.ultimo_comando = (comando or "").strip()

    def actualizar_progreso(self, paso_actual: int, total_pasos: int = 3) -> None:
        """
        Mapea proporcionalmente el paso actual (de 1 a N) hacia las 3 luces
        del Semáforo Visual (P1: Inicio, P2: Avance, P3: Meta).
        """
        if paso_actual <= 0 or total_pasos <= 0:
            leds_encendidos = 0
        elif total_pasos <= 3:
            leds_encendidos = min(3, paso_actual)
        else:
            proporcion = paso_actual / float(total_pasos)
            leds_encendidos = max(1, min(3, math.ceil(proporcion * 3)))

        self.estado_leds = [i < leds_encendidos for i in range(3)]

        if leds_encendidos <= 0:
            self.enviar_comando("OFF")
        elif leds_encendidos == 1:
            self.enviar_comando("P1")
        elif leds_encendidos == 2:
            self.enviar_comando("P2")
        else:
            self.enviar_comando("P3")

        self._notificar_gui("PROGRESO")

    def celebrar_victoria(self) -> None:
        """Enciende las 3 luces para festejar la meta alcanzada."""
        self.estado_leds = [True, True, True]
        self.enviar_comando("WIN")
        self._notificar_gui("WIN")

    def activar_pausa(self) -> None:
        """Enciende la luz central (Avance) para indicar pausa activa saludable."""
        self.estado_leds = [False, True, False]
        self.enviar_comando("PAUSA")
        self._notificar_gui("PAUSA")

    def apagar_todo(self) -> None:
        """Apaga todas las luces del Semáforo Visual."""
        self.estado_leds = [False, False, False]
        self.enviar_comando("OFF")
        self._notificar_gui("OFF")

    def _notificar_gui(self, evento: str) -> None:
        if self.callback_gui:
            try:
                self.callback_gui(list(self.estado_leds), evento)
            except Exception:
                pass

    def cerrar(self) -> None:
        """Apaga las luces al finalizar la sesión."""
        self.apagar_todo()


# Alias retrocompatible
ControladorHardwareLEDs = ControladorSemaforoVisual

__all__ = ["ControladorSemaforoVisual", "ControladorHardwareLEDs"]
