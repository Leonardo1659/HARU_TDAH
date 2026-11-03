"""
Reconocimiento de Voz Infantil sin Compiladores C++ (`sounddevice` + `SpeechRecognition`)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Reemplaza por completo a `PyAudio` utilizando `sounddevice.RawInputStream` (binarios
PortAudio precompilados incluidos en el wheel). Emite niveles de volumen en tiempo
real para animar el botón `🎤 Hablar` y cae limpiamente a diálogo escrito si no hay
micrófono o internet.
"""

import array
import math
import threading
import time
from typing import Optional

from core.eventos import BusEventosUI

try:
    import sounddevice as sd
    SOUNDDEVICE_DISPONIBLE = True
except Exception:
    SOUNDDEVICE_DISPONIBLE = False

try:
    import speech_recognition as sr
    SR_DISPONIBLE = True
except Exception:
    SR_DISPONIBLE = False


class EscuchaVozHaru:
    SAMPLE_RATE = 16_000
    DURACION_MAX_SEG = 4.2
    BLOQUE_MUESTRAS = 1600  # 100 ms por bloque

    def __init__(self, bus_eventos: Optional[BusEventosUI] = None,
                 forzar_modo_privado: bool = False):
        self.bus = bus_eventos
        self.escuchando = False
        self.forzar_modo_privado = forzar_modo_privado

    def hay_microfono_disponible(self) -> bool:
        if not SOUNDDEVICE_DISPONIBLE:
            return False
        try:
            disp = sd.query_devices(kind="input")
            return bool(disp and int(disp.get("max_input_channels", 0)) > 0)
        except Exception:
            return False

    def escuchar_en_hilo(self) -> None:
        if self.escuchando:
            return
        threading.Thread(target=self._capturar_y_transcribir, daemon=True, name="HaruSTTWorker").start()

    def _emitir(self, tipo: str, **datos) -> None:
        if self.bus:
            self.bus.emitir(tipo, **datos)

    def _capturar_y_transcribir(self) -> None:
        if self.forzar_modo_privado:
            # Cumplimiento estricto Ley N.º 548: en Modo Privado no se envía audio a servidores externos
            self._emitir(
                "stt_fallback_texto",
                motivo="🔒 Modo Privado Estricto activo (Ley N.º 548): el micrófono en la nube está desactivado.",
            )
            return

        if not SOUNDDEVICE_DISPONIBLE or not SR_DISPONIBLE or not self.hay_microfono_disponible():
            self._emitir(
                "stt_fallback_texto",
                motivo="No se detectó un micrófono activo en esta computadora.",
            )
            return

        self.escuchando = True
        self._emitir("stt_inicio")
        buffer_pcm = bytearray()
        hubo_voz = False
        bloques_silencio_tras_voz = 0

        try:
            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOQUE_MUESTRAS,
                channels=1,
                dtype="int16",
            ) as stream:
                inicio = time.perf_counter()
                while (time.perf_counter() - inicio) < self.DURACION_MAX_SEG:
                    fragmento, _ = stream.read(self.BLOQUE_MUESTRAS)
                    raw = bytes(fragmento)
                    buffer_pcm.extend(raw)

                    # Calcular RMS rápido para animar el indicador visual del micrófono
                    muestras = array.array("h")
                    muestras.frombytes(raw)
                    if muestras:
                        suma_cuad = sum(m * m for m in muestras)
                        rms = math.sqrt(suma_cuad / len(muestras))
                    else:
                        rms = 0.0

                    nivel = min(1.0, rms / 3200.0)
                    self._emitir("stt_nivel", nivel=nivel)

                    if rms > 420:
                        hubo_voz = True
                        bloques_silencio_tras_voz = 0
                    elif hubo_voz:
                        bloques_silencio_tras_voz += 1
                        # Cortar rápido si el niño ya terminó de decir su frase (0.8s de silencio)
                        if bloques_silencio_tras_voz >= 8 and (time.perf_counter() - inicio) > 1.4:
                            break
        except Exception as e:
            self.escuchando = False
            self._emitir("stt_fallback_texto", motivo=f"Micrófono ocupado o no disponible ({e}).")
            return

        self.escuchando = False
        self._emitir("stt_procesando")

        if not buffer_pcm or not hubo_voz:
            self._emitir("stt_vacio", mensaje="No escuché tu voz. ¡Puedes intentar otra vez o tocar los botones!")
            return

        try:
            recognizer = sr.Recognizer()
            audio_data = sr.AudioData(bytes(buffer_pcm), self.SAMPLE_RATE, 2)
            texto = recognizer.recognize_google(audio_data, language="es-BO")
            self._emitir("stt_resultado", texto=texto.strip())
        except sr.UnknownValueError:
            self._emitir("stt_vacio", mensaje="No logré entender bien. ¡Dímelo un poquito más cerca o usa los botones!")
        except Exception:
            self._emitir(
                "stt_fallback_texto",
                motivo="Sin conexión al servicio de transcripción por voz; escribe aquí tu mensaje para Haru:",
            )

