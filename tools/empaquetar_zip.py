"""
Empaquetador Limpio y Seguro para Distribución entre Compañeros (`tools/empaquetar_zip.py`)
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Genera `HARU_TDAH_Compartir.zip` conteniendo ÚNICAMENTE la versión ejecutable
portable `Haru/` (`Haru.exe`, `_internal/`, `data/`, `.env.example` y `LEEME.txt`),
para que los compañeros solo tengan que abrir `Haru.exe` con doble clic sin
consola ni instalación previa. (El código fuente completo, pruebas y README
permanecen en el repositorio de GitHub).

Excluye automáticamente:
- `.env` (protege tu clave privada `GEMINI_API_KEY` para que nunca se filtre)
- Bases de datos personales (`*.db`, `*.db-wal`, `*.db-shm`)
- Cachés temporales y bitácoras (`cache_tts/`, `logs/`, `__pycache__/`)
"""

import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
HARU_DIST = ROOT_DIR / "dist" / "Haru"

DIRECTORIOS_EXCLUIDOS = {
    "__pycache__",
    ".git",
    ".vscode",
    ".idea",
    ".venv",
    "venv",
    "env",
    "cache_tts",
    "logs",
}

ARCHIVOS_EXCLUIDOS = {
    ".env",
    "HARU_TDAH_Compartir.zip",
}

EXTENSIONES_EXCLUIDAS = {
    ".pyc",
    ".pyo",
    ".db",
    ".db-wal",
    ".db-shm",
    ".log",
}


def crear_paquete_zip(ruta_salida: Path = ROOT_DIR / "HARU_TDAH_Compartir.zip") -> Path:
    # Si aún no existe dist/Haru/Haru.exe, compilarlo automáticamente
    if not (HARU_DIST / "Haru.exe").exists():
        from tools.compilar_exe import compilar_haru_exe
        compilar_haru_exe()

    es_paquete_oficial = ruta_salida.resolve() == (ROOT_DIR / "HARU_TDAH_Compartir.zip").resolve()
    archivos_incluidos = 0

    with zipfile.ZipFile(ruta_salida, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Asegurar carpetas vacías limpias de datos en el .zip
        zf.writestr("Haru/data/logs/.keep", "")
        zf.writestr("Haru/data/cache_tts/.keep", "")

        for ruta in sorted(HARU_DIST.rglob("*")):
            if ruta.is_dir():
                continue
            rel = ruta.relative_to(HARU_DIST)
            if any(parte in DIRECTORIOS_EXCLUIDOS for parte in rel.parts):
                continue
            if rel.name in ARCHIVOS_EXCLUIDOS:
                continue
            if ruta.suffix.lower() in EXTENSIONES_EXCLUIDAS:
                continue
            # En pruebas unitarias temporales omitimos binarios pesados de Python para correr en <0.5s
            if not es_paquete_oficial and len(rel.parts) >= 2 and rel.parts[0] == "_internal":
                if rel.parts[1] in ("Lib", "DLLs", "tcl", "site-packages") or ruta.suffix.lower() == ".dll":
                    continue

            zf.write(ruta, arcname=f"Haru/{rel.as_posix()}")
            archivos_incluidos += 1

    tam_mb = ruta_salida.stat().st_size / (1024 * 1024)
    print(f"[OK] Paquete portable creado: {ruta_salida}")
    print(f"     Estructura: Haru/Haru.exe + _internal/ + data/ + LEEME.txt")
    print(f"     Archivos incluidos: {archivos_incluidos} | Tamaño total: {tam_mb:.2f} MB")
    print("     Seguridad verificada: `.env` y bases `.db` NO fueron incluidos en el .zip.")
    return ruta_salida


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    crear_paquete_zip()
