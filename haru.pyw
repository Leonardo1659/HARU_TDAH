"""
Punto de Entrada Silencioso sin Consola Negra (`Haru.exe` / `pythonw.exe`) — Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Incluye pantalla de carga (Splash Screen) con barra de progreso e ícono oficial
`HARU.jpeg`, redirige `sys.stdout` y `sys.stderr` hacia `data/logs/haru.log`,
activa nitidez High-DPI y registra el AppUserModelID en la barra de tareas de Windows.
"""

import ctypes
import importlib
import importlib.util
import os
import site
import subprocess
import sys
import tkinter as tk
import traceback
from pathlib import Path
from typing import Optional

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
    APP_DIR = Path(getattr(sys, "_MEIPASS", ROOT_DIR)).resolve()
elif os.environ.get("HARU_PORTABLE_ROOT"):
    ROOT_DIR = Path(os.environ["HARU_PORTABLE_ROOT"]).resolve()
    APP_DIR = Path(os.environ.get("HARU_APP_DIR", str(ROOT_DIR))).resolve()
else:
    ROOT_DIR = Path(__file__).resolve().parent
    APP_DIR = ROOT_DIR

for _p in (str(ROOT_DIR), str(APP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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


def _activar_nitidez_dpi_y_appid_windows() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "UniversidadSalesiana.Haru.AsistenteTDAH.2.0"
            )
        except Exception:
            pass
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
        try:
            with open(LOG_FILE, mode="a", encoding="utf-8") as f:
                f.write(f"\n=== EXCEPCIÓN ===\n{traza}\n")
        except Exception:
            pass
        _mostrar_error_amigable(
            "Haru — Error Inesperado",
            f"Ocurrió un problema al ejecutar Haru.\nSe guardó el detalle en: data/logs/haru.log\n\n{exc_value}",
        )

    sys.excepthook = _hook


class _SplashCargaHaru:
    """Pantalla de bienvenida instantánea con barra de progreso mientras inicia Haru."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg="#0f172a")
        self.root.attributes("-topmost", True)

        ancho, alto = 440, 330
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - ancho) // 2)
        y = max(0, (sh - alto) // 2)
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

        marco = tk.Frame(self.root, bg="#1e293b", bd=2, relief="ridge")
        marco.pack(fill="both", expand=True, padx=4, pady=4)

        self._img_tk = None
        try:
            from PIL import Image, ImageDraw, ImageTk

            ruta_jpg = APP_DIR / "assets" / "img" / "HARU.jpeg"
            if ruta_jpg.exists():
                with Image.open(ruta_jpg) as im:
                    rgba = im.convert("RGBA").resize((136, 136), Image.Resampling.LANCZOS)
                    mask = Image.new("L", (136, 136), 0)
                    ImageDraw.Draw(mask).rounded_rectangle((2, 2, 134, 134), radius=26, fill=255)
                    out = Image.new("RGBA", (136, 136), (30, 41, 59, 255))
                    out.paste(rgba, (0, 0), mask)
                    self._img_tk = ImageTk.PhotoImage(out, master=self.root)
                    tk.Label(marco, image=self._img_tk, bg="#1e293b", bd=0).pack(pady=(18, 6))
        except Exception:
            pass

        tk.Label(
            marco,
            text="HARU — IA DE APRENDIZAJE",
            font=("Segoe UI", 15, "bold"),
            fg="#f8fafc",
            bg="#1e293b",
        ).pack(pady=(4, 2))

        self.lbl_estado = tk.Label(
            marco,
            text="Iniciando asistente educativo TDAH...",
            font=("Segoe UI", 10),
            fg="#94a3b8",
            bg="#1e293b",
        )
        self.lbl_estado.pack(pady=(0, 12))

        self.canvas_barra = tk.Canvas(
            marco, width=350, height=14, bg="#0f172a", highlightthickness=0
        )
        self.canvas_barra.pack(pady=(2, 8))
        self._rect_progreso = self.canvas_barra.create_rectangle(
            0, 0, 25, 14, fill="#22c55e", width=0
        )

        self.lbl_pct = tk.Label(
            marco,
            text="10%",
            font=("Segoe UI", 9, "bold"),
            fg="#4ade80",
            bg="#1e293b",
        )
        self.lbl_pct.pack()
        self.root.update()

    def avanzar(self, porcentaje: int, texto: str) -> None:
        try:
            pct = max(5, min(100, int(porcentaje)))
            ancho_px = int(350 * (pct / 100.0))
            self.canvas_barra.coords(self._rect_progreso, 0, 0, ancho_px, 14)
            self.lbl_estado.configure(text=texto)
            self.lbl_pct.configure(text=f"{pct}%")
            self.root.update()
        except Exception:
            pass

    def cerrar(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass


def _asegurar_dependencias_repositorio(splash: Optional[_SplashCargaHaru] = None) -> None:
    """Si se ejecuta desde código fuente y falta alguna librería, instala `requirements.txt`."""
    if getattr(sys, "frozen", False) or os.environ.get("HARU_PORTABLE_ROOT"):
        return

    req_path = ROOT_DIR / "requirements.txt"
    if not req_path.exists():
        return

    modulos_req = (
        "customtkinter",
        "PIL",
        "edge_tts",
        "cv2",
        "numpy",
        "sounddevice",
        "speech_recognition",
        "serial",
    )
    if all(importlib.util.find_spec(mod) is not None for mod in modulos_req):
        return

    if splash is not None:
        splash.avanzar(18, "Instalando librerías necesarias por primera vez...")

    exe_py = Path(sys.executable)
    if exe_py.name.lower() == "pythonw.exe" and exe_py.with_name("python.exe").exists():
        py_cmd = str(exe_py.with_name("python.exe"))
    else:
        py_cmd = sys.executable

    flags_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd_base = [py_cmd, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req_path)]
    try:
        res = subprocess.run(
            cmd_base,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=240,
            creationflags=flags_win,
        )
        if res.returncode != 0:
            subprocess.run(
                [py_cmd, "-m", "pip", "install", "--user", "--disable-pip-version-check", "-r", str(req_path)],
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=240,
                creationflags=flags_win,
            )
    except Exception:
        pass

    try:
        user_site = site.getusersitepackages()
        if user_site and os.path.isdir(user_site) and user_site not in sys.path:
            site.addsitedir(user_site)
    except Exception:
        pass
    importlib.invalidate_caches()


def iniciar_haru(silenciar_audio: bool = False) -> None:
    _configurar_streams_seguros()
    _activar_nitidez_dpi_y_appid_windows()
    _instalar_excepthook()

    splash = None
    try:
        splash = _SplashCargaHaru()
        _asegurar_dependencias_repositorio(splash)
        splash.avanzar(25, "Verificando componentes gráficos y de audio...")
        import customtkinter  # noqa: F401

        splash.avanzar(55, "Cargando módulos curriculares y base de datos local...")
        from ui.iconos import asegurar_icono_haru_ico
        asegurar_icono_haru_ico()

        splash.avanzar(85, "Preparando escenario interactivo de Haru...")
        from ui.app import VentanaPrincipalHaru

        splash.avanzar(100, "¡Listo! Abriendo Haru...")
        splash.cerrar()
        splash = None
    except ImportError as exc:
        if splash is not None:
            splash.cerrar()
        _mostrar_error_amigable(
            "Haru — Falta instalar librerías",
            f"Falta un componente de Python para iniciar Haru:\n{exc}\n\n"
            "Instala las dependencias con: pip install -r requirements.txt",
        )
        return
    except Exception:
        if splash is not None:
            splash.cerrar()
        raise

    os.chdir(ROOT_DIR)
    es_autoprueba = "--self-test" in sys.argv
    app = VentanaPrincipalHaru(silenciar_audio_inicial=silenciar_audio or es_autoprueba)
    if es_autoprueba:
        app.after(600, app.cerrar_aplicacion)
    app.mainloop()


if __name__ == "__main__":
    iniciar_haru()


