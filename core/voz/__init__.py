"""Paquete de Voz Neuronal (Edge-TTS + Karaoke) y Escucha sin Compiladores (`sounddevice`)."""

from core.voz.stt import EscuchaVozHaru
from core.voz.tts import MotorVozHaru, calcular_visema_fonetico, limpiar_texto_para_voz

__all__ = ["MotorVozHaru", "EscuchaVozHaru", "limpiar_texto_para_voz", "calcular_visema_fonetico"]

