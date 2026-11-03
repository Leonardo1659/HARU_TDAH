"""
Punto de Entrada Silencioso sin Consola Negra (`pythonw.exe`) — Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Redirige `sys.stdout` y `sys.stderr` hacia `data/logs/haru.log` cuando se ejecuta
bajo `pythonw.exe` (evitando errores por flujos `None`), activa nitidez High-DPI
en Windows y muestra un aviso amigable si faltan dependencias por instalar.
"""

import ctypes
import os
import sys
import traceback
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

LOGS_DIR = ROOT_DIR / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "haru.log"


def _configurar_streams_seguros() -> None:
    if sys.stdout is None or sys.stderr is None:
         manejador = open(LOG_FILE, mode="a", encoding="utf-8", buffering=1)
         if sys.stdout is None:
             sys.stdout = manejador
         if sys.stderr is None:
             sys.stderr = manejador


def _activar_nitidez_dpi_windows() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _mostrar_error_amigable(titulo: str, detalle: str) -> None:
    try:
        with open(LOG_FILE, mode="a", encoding="utf-8") as f:
            f.write(f"\n=== {titulo} ===\n{detalle}\n")
    except Exception:
        pass
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, detalle, titulo, 0x10)


def _instalar_excepthook() -> None:
    def _hook(exc_type, exc_value, exc_tb):
        traza = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _mostrar_error_amigable(
            "Haru — Error Inesperado",
            f"Ocurrió un problema al ejecutar Haru.\nSe guardó el detalle en: data/logs/haru.log\n\n{exc_value}",
        )

    sys.excepthook = _hook


def iniciar_haru(silenciar_audio: bool = False) -> None:
    _configurar_streams_seguros()
    _activar_nitidez_dpi_windows()
    _instalar_excepthook()

    try:
        import customtkinter  # noqa: F401
    except ImportError:
        _mostrar_error_amigable(
            "Haru — Falta instalar librerías",
            "¡Bienvenido a Haru!\n\n"
            "Antes de abrir el asistente por primera vez en esta computadora, "
            "haz doble clic en:\n\n"
            "👉 INSTALAR_DEPENDENCIAS.bat\n\n"
            "Terminará en pocos segundos y luego podrás abrir Haru normalmente.",
        )
        return

    from ui.app import VentanaPrincipalHaru

    os.chdir(ROOT_DIR)
    app = VentanaPrincipalHaru(silenciar_audio_inicial=silenciar_audio)
    app.mainloop()


if __name__ == "__main__":
    iniciar_haru()

