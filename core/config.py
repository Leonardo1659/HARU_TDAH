"""
Configuración Centralizada y Lector Ligero de Variables (.env)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Centraliza todas las rutas con `pathlib.Path` para garantizar portabilidad 100%
al compartir el proyecto en `.zip` en cualquier carpeta o computadora Windows.
"""

import os
from pathlib import Path
from typing import Dict

# Directorios principales del proyecto
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
LOGS_DIR: Path = DATA_DIR / "logs"
CACHE_TTS_DIR: Path = DATA_DIR / "cache_tts"
ASSETS_DIR: Path = ROOT_DIR / "assets"
SPRITES_DIR: Path = ASSETS_DIR / "sprites"
AUDIO_PRECARGADO_DIR: Path = ASSETS_DIR / "voz_precargada"
DB_PATH: Path = DATA_DIR / "haru_tdah.db"
ENV_PATH: Path = ROOT_DIR / ".env"

for _carpeta in (DATA_DIR, LOGS_DIR, CACHE_TTS_DIR, ASSETS_DIR, SPRITES_DIR, AUDIO_PRECARGADO_DIR):
    _carpeta.mkdir(parents=True, exist_ok=True)


def cargar_env_local(ruta_env: Path = ENV_PATH) -> Dict[str, str]:
    """Lector ligero de `.env` sin requerir librerías externas."""
    valores: Dict[str, str] = {}
    if not ruta_env.exists():
        return valores
    try:
        for linea in ruta_env.read_text(encoding="utf-8", errors="ignore").splitlines():
            limpia = linea.strip()
            if not limpia or limpia.startswith("#") or "=" not in limpia:
                continue
            clave, valor = limpia.split("=", 1)
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            valores[clave] = valor
            if clave and valor and clave not in os.environ:
                os.environ[clave] = valor
    except Exception:
        pass
    return valores


cargar_env_local()

# Voces Neuronales Edge-TTS (100% gratuitas, acento boliviano y latino tierno)
VOCES_DISPONIBLES: Dict[str, str] = {
    "Sofía (Bolivia - Tierna)": "es-BO-SofiaNeural",
    "Dalia (Infantil Cálida)": "es-MX-DaliaNeural",
    "Marcelo (Bolivia - Amigable)": "es-BO-MarceloNeural",
    "Salomé (Colombia - Alegre)": "es-CO-SalomeNeural",
}
VOZ_POR_DEFECTO = "es-BO-SofiaNeural"

# Modelo Gemini por defecto y URL REST
MODELO_GEMINI_DEFECTO = "gemini-flash-lite-latest"
OLLAMA_URL_BASE = "http://127.0.0.1:11434"

