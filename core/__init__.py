"""Módulos centrales del Asistente Educativo TDAH Haru."""

import sys

from core import semaforo_visual as _semaforo_visual

# Compatibilidad retroactiva para importaciones legado `from hardware.control_leds import ...`
setattr(_semaforo_visual, "control_leds", _semaforo_visual)
setattr(_semaforo_visual, "__path__", [])
sys.modules.setdefault("hardware", _semaforo_visual)
sys.modules.setdefault("hardware.control_leds", _semaforo_visual)
