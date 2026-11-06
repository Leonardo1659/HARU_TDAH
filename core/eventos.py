"""
Bus Seguro de Eventos entre Hilos (`queue.Queue`)
Garantiza que ningún hilo secundario (Voz, Micrófono, Temporizador o IA)
modifique widgets de CustomTkinter/Tkinter fuera del hilo principal.
"""

import queue
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class EventoUI:
    tipo: str
    datos: Dict[str, Any] = field(default_factory=dict)


class BusEventosUI:
    def __init__(self):
        self._cola: "queue.Queue[EventoUI]" = queue.Queue()

    def emitir(self, tipo: str, **datos: Any) -> None:
        self._cola.put(EventoUI(tipo=tipo, datos=datos))

    def extraer_pendientes(self, max_items: int = 40):
        eventos = []
        for _ in range(max_items):
            try:
                eventos.append(self._cola.get_nowait())
            except queue.Empty:
                break
        return eventos

