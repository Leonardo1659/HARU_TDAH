"""
Motor de Voz Neuronal Expresiva con Subtítulos Karaoke en Vivo (`edge-tts` + MCI)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Características:
1. Voz neuronal natural gratuita `es-BO-SofiaNeural` (acento boliviano cálido).
2. Extracción real de tiempos por palabra (`WordBoundary`) para subtítulos karaoke
   y sincronización labial (lip-sync) del personaje Haru.
3. Doble caché en disco (`assets/voz_precargada/` incluida en el `.zip` +
   `data/cache_tts/` automática) para latencia 0 ms en frases repetidas.
4. Reproducción nativa en Windows vía `winmm.dll` (`mciSendStringW`) en el mismo
   hilo afinado, soportando rutas con espacios (`Windows 11`) e interrupción en <40 ms.
5. Respaldo 100% offline con `System.Speech.Synthesis` oculto (`CREATE_NO_WINDOW`).
"""

import asyncio
import ctypes
import hashlib
import inspect
import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import AUDIO_PRECARGADO_DIR, CACHE_TTS_DIR, VOZ_POR_DEFECTO
from core.eventos import BusEventosUI

try:
    import edge_tts
    EDGE_TTS_DISPONIBLE = True
except ImportError:
    EDGE_TTS_DISPONIBLE = False


_REGEX_EMOJIS = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002300-\U000023FF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)


def limpiar_texto_para_voz(texto: str) -> str:
    """Elimina emojis y símbolos decorativos para que la voz lea con fluidez natural."""
    sin_emojis = _REGEX_EMOJIS.sub(" ", texto or "")
    sin_simbolos = sin_emojis.replace("«", '"').replace("»", '"').replace("•", ",")
    return re.sub(r"\s+", " ", sin_simbolos).strip()


def estimar_marcas_proporcionales(texto_hablado: str, wpm: int = 148) -> List[Dict]:
    """Genera marcas de tiempo proporcionales cuando se usa voz local offline."""
    palabras = [p for p in texto_hablado.split() if p.strip()]
    if not palabras:
        return []
    ms_por_caracter = max(42.0, (60_000.0 / wpm) / 5.2)
    marcas: List[Dict] = []
    cursor_ms = 60
    for p in palabras:
        dur = int(max(130, len(p) * ms_por_caracter))
        pausa_extra = 190 if p.endswith((".", "!", "?", ":", ";")) else (90 if p.endswith(",") else 25)
        marcas.append({
            "word": p,
            "offset_ms": cursor_ms,
            "duration_ms": dur,
        })
        cursor_ms += dur + pausa_extra
    return marcas


def calcular_visema_fonetico(marcas: List[Dict], idx_actual: int, transcurrido_ms: int) -> int:
    """
    Calcula la forma exacta de la boca de Haru (0..3) según la palabra activa y el tiempo:
    - 0: Boca cerrada (sonrisa suave) en silencios, comas, puntos o antes de empezar.
    - 1: Vocal abierta ('a', 'e') -> abertura amplia alegre.
    - 2: Vocal redondeada ('o', 'u') -> óvalo redondeado.
    - 3: Vocal cerrada ('i') o articulación consonántica entre sílabas.
    """
    if idx_actual < 0 or idx_actual >= len(marcas):
        return 0

    m = marcas[idx_actual]
    ini = int(m.get("offset_ms", 0))
    dur = max(65, int(m.get("duration_ms", 120)))

    # Si estamos en una pausa de puntuación entre palabras, cerrar la boca con naturalidad
    if transcurrido_ms < ini or transcurrido_ms > (ini + dur + 38):
        return 0

    texto_pal = m.get("word") if m.get("word") is not None else m.get("palabra", "")
    palabra = re.sub(r"[^a-záéíóúüñ]", "", str(texto_pal).lower())
    if not palabra:
        return 3

    avance_ms = transcurrido_ms - ini
    progreso = max(0.0, min(0.999, avance_ms / float(dur)))

    # Micro-cierre articulatorio entre sílabas en palabras largas (ej. "ma-te-má-ti-cas")
    if dur >= 230 and (avance_ms % 145) >= 118:
        return 3
    if dur >= 180 and progreso > 0.90:
        return 3

    pos_letra = int(progreso * len(palabra))
    ventana = palabra[max(0, pos_letra - 1): min(len(palabra), pos_letra + 2)]
    for ch in (palabra[pos_letra], *ventana):
        if ch in "aáeé":
            return 1
        if ch in "oóuúü":
            return 2
        if ch in "ií":
            return 3
    return 3


class MotorVozHaru:
    def __init__(self, bus_eventos: Optional[BusEventosUI] = None,
                 voz: str = VOZ_POR_DEFECTO,
                 velocidad: str = "+0%",
                 silenciado: bool = False):
        self.bus = bus_eventos
        self.voz = voz or VOZ_POR_DEFECTO
        self.velocidad = velocidad or "+0%"
        self.silenciado = silenciado
        self.forzar_offline = False

        self._cola_peticiones: "queue.Queue[Optional[Tuple[int, str]]]" = queue.Queue()
        self._generacion_actual = 0
        self._lock_gen = threading.Lock()
        self._proceso_offline: Optional[subprocess.Popen] = None
        self._activo = True

        self._hilo_worker = threading.Thread(target=self._bucle_worker, daemon=True, name="HaruTTSWorker")
        self._hilo_worker.start()

    @staticmethod
    def clave_cache(texto_hablado: str, voz: str, velocidad: str) -> str:
        base = f"{voz.strip()}|{velocidad.strip()}|{texto_hablado.strip()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    def configurar_voz(self, voz: Optional[str] = None, velocidad: Optional[str] = None) -> None:
        if voz:
            self.voz = voz
        if velocidad:
            self.velocidad = velocidad

    def hablar(self, texto: str) -> None:
        """Encola una locución interrumpiendo cualquier audio anterior de inmediato."""
        if not texto or not texto.strip():
            return
        with self._lock_gen:
            self._generacion_actual += 1
            gen_id = self._generacion_actual
            self._terminar_proceso_offline()
        # Vaciar locuciones obsoletas pendientes en la cola
        while not self._cola_peticiones.empty():
            try:
                self._cola_peticiones.get_nowait()
            except queue.Empty:
                break
        self._cola_peticiones.put((gen_id, texto.strip()))

    def detener(self) -> None:
        """Detiene al instante la voz actual y limpia subtítulos activos."""
        with self._lock_gen:
            self._generacion_actual += 1
            self._terminar_proceso_offline()
        self._emitir("tts_fin", interrumpido=True)

    def cerrar(self) -> None:
        self._activo = False
        self.detener()
        self._cola_peticiones.put(None)

    def _es_vigente(self, gen_id: int) -> bool:
        return self._activo and gen_id == self._generacion_actual

    def _emitir(self, tipo: str, **datos) -> None:
        if self.bus:
            self.bus.emitir(tipo, **datos)

    def _terminar_proceso_offline(self) -> None:
        proc = self._proceso_offline
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        self._proceso_offline = None

    # =========================================================================
    # SÍNTESIS NEURONAL + CACHÉ EN DISCO
    # =========================================================================
    def obtener_o_sintetizar_mp3(self, texto_hablado: str,
                                 directorio_destino: Optional[Path] = None) -> Optional[Tuple[Path, List[Dict]]]:
        """
        Busca primero en `assets/voz_precargada/`, luego en `data/cache_tts/`,
        y si no existe sintetiza con `edge-tts` guardando `.mp3` + `.json`.
        """
        if not texto_hablado:
            return None

        clave = self.clave_cache(texto_hablado, self.voz, self.velocidad)

        for carpeta in (AUDIO_PRECARGADO_DIR, CACHE_TTS_DIR):
            mp3_p = carpeta / f"{clave}.mp3"
            json_p = carpeta / f"{clave}.json"
            if mp3_p.exists() and mp3_p.stat().st_size > 200:
                marcas = []
                if json_p.exists():
                    try:
                        marcas = json.loads(json_p.read_text(encoding="utf-8")).get("marcas", [])
                    except Exception:
                        marcas = []
                if not marcas:
                    marcas = estimar_marcas_proporcionales(texto_hablado)
                return mp3_p, marcas

        if self.forzar_offline or not EDGE_TTS_DISPONIBLE:
            return None

        carpeta_out = directorio_destino or CACHE_TTS_DIR
        carpeta_out.mkdir(parents=True, exist_ok=True)
        mp3_destino = carpeta_out / f"{clave}.mp3"
        json_destino = carpeta_out / f"{clave}.json"

        try:
            marcas = asyncio.run(self._corutina_edge_tts(texto_hablado, mp3_destino))
            if not mp3_destino.exists() or mp3_destino.stat().st_size < 200:
                return None
            if not marcas:
                marcas = estimar_marcas_proporcionales(texto_hablado)
            json_destino.write_text(
                json.dumps(
                    {"texto": texto_hablado, "voz": self.voz, "velocidad": self.velocidad, "marcas": marcas},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return mp3_destino, marcas
        except Exception:
            try:
                if mp3_destino.exists() and mp3_destino.stat().st_size < 200:
                    mp3_destino.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    async def _corutina_edge_tts(self, texto_hablado: str, mp3_destino: Path) -> List[Dict]:
        sig = inspect.signature(edge_tts.Communicate.__init__)
        kwargs = {"rate": self.velocidad}
        if "boundary" in sig.parameters:
            kwargs["boundary"] = "WordBoundary"

        comunicador = edge_tts.Communicate(texto_hablado, self.voz, **kwargs)
        marcas: List[Dict] = []
        audio_bytes = bytearray()

        async for chunk in comunicador.stream():
            tipo = chunk.get("type")
            if tipo == "audio":
                audio_bytes.extend(chunk.get("data", b""))
            elif tipo == "WordBoundary":
                offset_ms = int(chunk.get("offset", 0) / 10_000)
                dur_ms = max(60, int(chunk.get("duration", 0) / 10_000))
                palabra = str(chunk.get("text", "")).strip()
                if palabra:
                    marcas.append({
                        "word": palabra,
                        "offset_ms": offset_ms,
                        "duration_ms": dur_ms,
                    })

        if audio_bytes:
            mp3_destino.write_bytes(bytes(audio_bytes))
        return marcas

    # =========================================================================
    # REPRODUCCIÓN EN HILO DEDICADO (MCI + FALLBACK SAPI5)
    # =========================================================================
    def _bucle_worker(self) -> None:
        while self._activo:
            try:
                item = self._cola_peticiones.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break

            gen_id, texto_original = item
            if not self._es_vigente(gen_id):
                continue

            texto_hablado = limpiar_texto_para_voz(texto_original)
            if not texto_hablado:
                continue

            if self.silenciado:
                marcas = estimar_marcas_proporcionales(texto_hablado)
                self._simular_karaoke_sin_audio(gen_id, texto_original, marcas)
                continue

            resultado_neuronal = self.obtener_o_sintetizar_mp3(texto_hablado)
            if not self._es_vigente(gen_id):
                continue

            if resultado_neuronal and sys.platform == "win32":
                mp3_path, marcas = resultado_neuronal
                exito_mci = self._reproducir_mp3_mci(gen_id, texto_original, mp3_path, marcas)
                if exito_mci:
                    continue

            # Respaldo 100% offline con SAPI5 nativo de Windows
            marcas_est = estimar_marcas_proporcionales(texto_hablado)
            self._reproducir_fallback_windows(gen_id, texto_original, texto_hablado, marcas_est)

    def _reproducir_mp3_mci(self, gen_id: int, texto_visual: str,
                            mp3_path: Path, marcas: List[Dict]) -> bool:
        winmm = ctypes.windll.winmm
        alias = f"haru_tts_{gen_id}"
        buf = ctypes.create_unicode_buffer(256)

        def mci(cmd: str) -> int:
            return winmm.mciSendStringW(cmd, buf, 255, 0)

        ruta_str = str(mp3_path.resolve())
        if mci(f'open "{ruta_str}" type mpegvideo alias {alias}') != 0:
            return False

        try:
            mci(f"play {alias} from 0")
            self._emitir(
                "tts_inicio",
                texto=texto_visual,
                marcas=marcas,
                modo="neuronal",
                voz=self.voz,
            )
            t0 = time.perf_counter()
            ultimo_idx = -1
            ultima_boca = -1

            while self._es_vigente(gen_id):
                transcurrido_ms = int((time.perf_counter() - t0) * 1000)
                idx_actual = self._buscar_indice_palabra(marcas, transcurrido_ms)
                boca = calcular_visema_fonetico(marcas, idx_actual, transcurrido_ms)

                if idx_actual != ultimo_idx and 0 <= idx_actual < len(marcas):
                    ultimo_idx = idx_actual
                    ultima_boca = boca
                    self._emitir(
                        "tts_palabra",
                        indice=idx_actual,
                        total=len(marcas),
                        palabra=marcas[idx_actual]["word"],
                        boca=boca,
                    )
                elif boca != ultima_boca:
                    ultima_boca = boca
                    self._emitir("tts_boca", boca=boca)

                mci(f"status {alias} mode")
                modo_mci = buf.value.strip().lower()
                if modo_mci not in ("playing", "seeking") and transcurrido_ms > 180:
                    break

                time.sleep(0.032)
        finally:
            mci(f"stop {alias}")
            mci(f"close {alias}")
            if self._es_vigente(gen_id):
                self._emitir("tts_fin", interrumpido=False)
        return True

    def _reproducir_fallback_windows(self, gen_id: int, texto_visual: str,
                                     texto_hablado: str, marcas: List[Dict]) -> None:
        self._emitir(
            "tts_inicio",
            texto=texto_visual,
            marcas=marcas,
            modo="local_windows",
            voz="Windows SAPI5",
        )
        proc = None
        if sys.platform == "win32":
            script_ps = (
                "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                "$txt = [Console]::In.ReadToEnd(); "
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "foreach ($v in $s.GetInstalledVoices()) { "
                "  if ($v.VoiceInfo.Culture.Name -like 'es-*') { $s.SelectVoice($v.VoiceInfo.Name); break } "
                "}; "
                "$s.Rate = 0; "
                "$s.Speak($txt)"
            )
            try:
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script_ps],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self._proceso_offline = proc
                if proc.stdin:
                    proc.stdin.write(texto_hablado.encode("utf-8"))
                    proc.stdin.close()
            except Exception:
                proc = None

        t0 = time.perf_counter()
        ultimo_idx = -1
        ultima_boca = -1
        duracion_estimada_ms = (
            (marcas[-1]["offset_ms"] + marcas[-1]["duration_ms"] + 350) if marcas else 1200
        )

        while self._es_vigente(gen_id):
            transcurrido_ms = int((time.perf_counter() - t0) * 1000)
            idx_actual = self._buscar_indice_palabra(marcas, transcurrido_ms)
            boca = calcular_visema_fonetico(marcas, idx_actual, transcurrido_ms)
            if idx_actual != ultimo_idx and 0 <= idx_actual < len(marcas):
                ultimo_idx = idx_actual
                ultima_boca = boca
                self._emitir(
                    "tts_palabra",
                    indice=idx_actual,
                    total=len(marcas),
                    palabra=marcas[idx_actual]["word"],
                    boca=boca,
                )
            elif boca != ultima_boca:
                ultima_boca = boca
                self._emitir("tts_boca", boca=boca)
            if proc is not None:
                if proc.poll() is not None:
                    break
            elif transcurrido_ms >= duracion_estimada_ms:
                break
            time.sleep(0.035)

        self._terminar_proceso_offline()
        if self._es_vigente(gen_id):
            self._emitir("tts_fin", interrumpido=False)

    def _simular_karaoke_sin_audio(self, gen_id: int, texto_visual: str, marcas: List[Dict]) -> None:
        self._emitir("tts_inicio", texto=texto_visual, marcas=marcas, modo="silencio", voz="Silencio")
        t0 = time.perf_counter()
        dur_total = (marcas[-1]["offset_ms"] + marcas[-1]["duration_ms"]) if marcas else 600
        ultimo_idx = -1
        ultima_boca = -1
        while self._es_vigente(gen_id):
            ms = int((time.perf_counter() - t0) * 1000)
            idx = self._buscar_indice_palabra(marcas, ms)
            boca = calcular_visema_fonetico(marcas, idx, ms)
            if idx != ultimo_idx and 0 <= idx < len(marcas):
                ultimo_idx = idx
                ultima_boca = boca
                self._emitir("tts_palabra", indice=idx, total=len(marcas), palabra=marcas[idx]["word"], boca=boca)
            elif boca != ultima_boca:
                ultima_boca = boca
                self._emitir("tts_boca", boca=boca)
            if ms >= dur_total:
                break
            time.sleep(0.035)
        if self._es_vigente(gen_id):
            self._emitir("tts_fin", interrumpido=False)

    @staticmethod
    def _buscar_indice_palabra(marcas: List[Dict], transcurrido_ms: int) -> int:
        idx_encontrado = -1
        for i, m in enumerate(marcas):
            if transcurrido_ms >= m.get("offset_ms", 0):
                idx_encontrado = i
            else:
                break
        return idx_encontrado
