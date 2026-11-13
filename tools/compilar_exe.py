"""
Compilador Automatizado de Ejecutable Portable (`Haru.exe`) con Ícono Oficial `HARU.jpeg`
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Uso:
    python tools/compilar_exe.py

Genera la carpeta portable `dist/Haru/` con:
- `Haru.exe` (Ejecutable GUI nativo de 64 bits sin consola y con ícono `HARU.jpeg`)
- `_internal/` (Motor Python embebido + librerías + código y recursos de Haru)
- `data/` (Carpetas limpias para base de datos y bitácoras del alumno)
- `.env.example` y `LEEME.txt`

Listo para abrir con doble clic en cualquier Windows de 64 bits sin requerir Python.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DIST_DIR = ROOT_DIR / "dist"
HARU_DIST = DIST_DIR / "Haru"
INTERNAL_DIR = HARU_DIST / "_internal"

CSHARP_LAUNCHER_CODE = r"""
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace HaruLauncher
{
    static class Program
    {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern int SetCurrentProcessExplicitAppUserModelID(string AppID);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool SetDllDirectory(string lpPathName);

        [DllImport("python314.dll", CallingConvention = CallingConvention.Cdecl)]
        private static extern int Py_Main(int argc, [MarshalAs(UnmanagedType.LPArray, ArraySubType = UnmanagedType.LPWStr)] string[] argv);

        [STAThread]
        static int Main(string[] args)
        {
            try
            {
                SetCurrentProcessExplicitAppUserModelID("UniversidadSalesiana.Haru.AsistenteTDAH.2.0");
            }
            catch { }

            string baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
            string internalDir = Path.Combine(baseDir, "_internal");
            string scriptPath = Path.Combine(internalDir, "haru.pyw");

            if (!Directory.Exists(internalDir) || !File.Exists(scriptPath))
            {
                MessageBox.Show(
                    "No se encontró la carpeta '_internal' junto a Haru.exe.\n\n" +
                    "Por favor, descomprime toda la carpeta Haru del archivo .zip antes de abrir Haru.exe.",
                    "Haru — Archivos incompletos",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return 1;
            }

            Directory.SetCurrentDirectory(baseDir);
            Environment.SetEnvironmentVariable("HARU_PORTABLE_ROOT", baseDir);
            Environment.SetEnvironmentVariable("HARU_APP_DIR", internalDir);
            Environment.SetEnvironmentVariable("PYTHONHOME", internalDir);
            Environment.SetEnvironmentVariable(
                "PYTHONPATH",
                string.Join(";", new string[] {
                    internalDir,
                    Path.Combine(internalDir, "Lib"),
                    Path.Combine(internalDir, "DLLs"),
                    Path.Combine(internalDir, "site-packages")
                })
            );
            Environment.SetEnvironmentVariable("TCL_LIBRARY", Path.Combine(internalDir, "tcl", "tcl8.6"));
            Environment.SetEnvironmentVariable("TK_LIBRARY", Path.Combine(internalDir, "tcl", "tk8.6"));
            Environment.SetEnvironmentVariable("PYTHONUTF8", "1");

            SetDllDirectory(internalDir);

            string exePath = Path.Combine(baseDir, "Haru.exe");
            string[] pyArgs = new string[2 + (args != null ? args.Length : 0)];
            pyArgs[0] = exePath;
            pyArgs[1] = scriptPath;
            if (args != null && args.Length > 0)
            {
                Array.Copy(args, 0, pyArgs, 2, args.Length);
            }
            try
            {
                return Py_Main(pyArgs.Length, pyArgs);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Error al iniciar el motor interno de Haru:\n" + ex.Message,
                    "Haru — Error de Inicio",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 1;
            }
        }
    }
}
"""

STDLIB_EXCLUIR = {
    "test",
    "tests",
    "idlelib",
    "turtledemo",
    "Ensurepip",
    "ensurepip",
    "pydoc_data",
    "venv",
    "lib2to3",
    "distutils",
    "site-packages",
    "__pycache__",
}

SITE_PACKAGES_INCLUIR = [
    "aifc",
    "aiohappyeyeballs",
    "aiohttp",
    "aiosignal",
    "attr",
    "attrs",
    "audioop",
    "certifi",
    "cffi",
    "charset_normalizer",
    "chunk",
    "colorama",
    "customtkinter",
    "darkdetect",
    "edge_tts",
    "frozenlist",
    "idna",
    "multidict",
    "packaging",
    "PIL",
    "propcache",
    "pycparser",
    "serial",
    "sounddevice.py",
    "_sounddevice.py",
    "_sounddevice_data",
    "speech_recognition",
    "typing_extensions.py",
    "yarl",
    "_cffi_backend.cp314-win_amd64.pyd",
]


def _copiar_sin_pycache(origen: Path, destino: Path, ignorar_extra=None) -> None:
    ignorar_set = {"__pycache__", ".pyc", ".pyo"}
    if ignorar_extra:
        ignorar_set.update(ignorar_extra)

    def _ignore(dirpath, names):
        ignorados = []
        for n in names:
            if n in ignorar_set or n.endswith((".pyc", ".pyo")):
                ignorados.append(n)
        return ignorados

    if origen.is_dir():
        shutil.copytree(origen, destino, dirs_exist_ok=True, ignore=_ignore)
    elif origen.is_file():
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)


def compilar_haru_exe() -> Path:
    from ui.iconos import asegurar_icono_haru_ico

    ruta_ico = asegurar_icono_haru_ico()
    if not ruta_ico or not ruta_ico.exists():
        raise RuntimeError("No se pudo generar assets/img/haru_icon.ico desde HARU.jpeg")

    print(f"[1/4] Ícono oficial verificado: {ruta_ico}")

    if HARU_DIST.exists():
        shutil.rmtree(HARU_DIST, ignore_errors=True)
    INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    (HARU_DIST / "data" / "logs").mkdir(parents=True, exist_ok=True)
    (HARU_DIST / "data" / "cache_tts").mkdir(parents=True, exist_ok=True)

    # 1. Compilar Haru.exe nativo sin consola y con ícono HARU.jpeg
    csc_path = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    if not csc_path.exists():
        raise RuntimeError(f"No se encontró el compilador nativo de Windows en {csc_path}")

    cs_file = DIST_DIR / "_HaruLauncher.cs"
    cs_file.write_text(CSHARP_LAUNCHER_CODE, encoding="utf-8")
    exe_path = HARU_DIST / "Haru.exe"

    cmd_csc = [
        str(csc_path),
        "/nologo",
        "/target:winexe",
        "/platform:x64",
        "/optimize+",
        f"/win32icon:{ruta_ico}",
        f"/out:{exe_path}",
        str(cs_file),
    ]
    print("[2/4] Compilando lanzador nativo Haru.exe (sin terminal, con ícono HARU.jpeg)...")
    subprocess.run(cmd_csc, cwd=str(ROOT_DIR), check=True)
    if cs_file.exists():
        cs_file.unlink()

    # 2. Empaquetar motor Python 3.14 y dependencias en dist/Haru/_internal
    print("[3/4] Empaquetando motor Python y librerías en dist/Haru/_internal...")
    base_py = Path(sys.base_prefix)

    for dll_file in base_py.glob("*.dll"):
        shutil.copy2(dll_file, INTERNAL_DIR / dll_file.name)

    _copiar_sin_pycache(base_py / "DLLs", INTERNAL_DIR / "DLLs")
    _copiar_sin_pycache(base_py / "tcl", INTERNAL_DIR / "tcl")
    _copiar_sin_pycache(base_py / "Lib", INTERNAL_DIR / "Lib", ignorar_extra=STDLIB_EXCLUIR)

    sp_origen = base_py / "Lib" / "site-packages"
    sp_destino = INTERNAL_DIR / "site-packages"
    sp_destino.mkdir(parents=True, exist_ok=True)

    for item_name in SITE_PACKAGES_INCLUIR:
        src = sp_origen / item_name
        if not src.exists():
            continue
        if item_name == "speech_recognition":
            _copiar_sin_pycache(
                src,
                sp_destino / item_name,
                ignorar_extra={"pocketsphinx-data", "flac-linux-x86", "flac-linux-x86_64", "flac-mac"},
            )
        elif src.is_dir():
            _copiar_sin_pycache(src, sp_destino / item_name)
        else:
            shutil.copy2(src, sp_destino / item_name)

    # 3. Copiar código y recursos de Haru dentro de _internal
    shutil.copy2(ROOT_DIR / "haru.pyw", INTERNAL_DIR / "haru.pyw")
    for carpeta_app in ("core", "ui", "hardware"):
        _copiar_sin_pycache(ROOT_DIR / carpeta_app, INTERNAL_DIR / carpeta_app)

    _copiar_sin_pycache(
        ROOT_DIR / "assets",
        INTERNAL_DIR / "assets",
        ignorar_extra={"UptownFunk.mp3", "juanita.gif", "screenshot-1.png"},
    )

    if (ROOT_DIR / ".env.example").exists():
        shutil.copy2(ROOT_DIR / ".env.example", HARU_DIST / ".env.example")

    leeme = HARU_DIST / "LEEME.txt"
    leeme.write_text(
        "HARU — ASISTENTE VIRTUAL EDUCATIVO TDAH (VERSIÓN PORTABLE)\n"
        "Universidad Salesiana de Bolivia\n"
        "==========================================================\n\n"
        "CÓMO ABRIR HARU:\n"
        "1. Extrae toda la carpeta 'Haru' del archivo .zip.\n"
        "2. Haz doble clic directamente sobre 'Haru.exe' (el ícono de Haru con corona).\n\n"
        "VENTAJAS DE ESTA VERSIÓN:\n"
        "- No necesitas instalar Python ni ejecutar archivos .bat.\n"
        "- No se abre ninguna ventana negra de consola/terminal.\n"
        "- Incluye barra de carga inicial, 5 módulos curriculares, soporte de voz y lectura de guías.\n\n"
        "IMPORTANTE:\n"
        "- No borres ni separes la carpeta '_internal': Haru.exe la usa internamente.\n"
        "- Tu progreso y misiones se guardan automáticamente en la carpeta 'data'.\n",
        encoding="utf-8",
    )

    print(f"[4/4] Ejecutable portable listo en: {exe_path}")
    return exe_path


if __name__ == "__main__":
    compilar_haru_exe()
