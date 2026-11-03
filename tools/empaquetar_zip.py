"""
Empaquetador Limpio y Seguro para Distribución entre Compañeros (`tools/empaquetar_zip.py`)
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Genera `HARU_TDAH_Compartir.zip` excluyendo automáticamente:
- `.env` (protege tu clave privada `GEMINI_API_KEY` para que nunca se filtre)
- Bases de datos personales (`data/*.db`, `*.db-wal`, `*.db-shm`)
- Cachés temporales y bitácoras (`data/cache_tts/`, `data/logs/`, `__pycache__/`)
- Carpetas de entorno o editor (`.git/`, `.vscode/`, `.venv/`, `venv/`)

Incluye `.env.example`, `assets/voz_precargada/` y lanzadores silenciosos listos
para descomprimir y usar en cualquier otra computadora Windows.
"""

import sys
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

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
    archivos_incluidos = 0
    with zipfile.ZipFile(ruta_salida, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for ruta in sorted(ROOT_DIR.rglob("*")):
            if ruta.is_dir():
                continue
            rel = ruta.relative_to(ROOT_DIR)
            if any(parte in DIRECTORIOS_EXCLUIDOS for parte in rel.parts):
                continue
            if rel.name in ARCHIVOS_EXCLUIDOS:
                continue
            if ruta.suffix.lower() in EXTENSIONES_EXCLUIDAS:
                continue
            # Excluir archivos sueltos antiguos de música pesada si no se usan
            if rel.as_posix() == "assets/audio/UptownFunk.mp3":
                continue

            zf.write(ruta, arcname=f"implementos2/{rel.as_posix()}")
            archivos_incluidos += 1

    tam_mb = ruta_salida.stat().st_size / (1024 * 1024)
    print(f"[OK] Paquete limpio creado: {ruta_salida}")
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

