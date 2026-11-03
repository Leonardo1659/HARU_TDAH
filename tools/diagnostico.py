"""
Herramienta de Diagnóstico Integral del Sistema — Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Comprueba en segundos el estado real de cada módulo:
- Python y librerías visuales (`customtkinter`, `pillow`, `opencv-python`)
- Voz Neuronal (`edge-tts` + frases precargadas + respaldo Windows SAPI5)
- Micrófono sin compiladores (`sounddevice` + `SpeechRecognition`)
- IA en Capas (`ast` seguro, SQLite, Ollama local y llamada real a Gemini API)
- Base de Datos SQLite WAL + Seguridad PIN PBKDF2
- Hardware Serial Arduino UNO R3 (`pyserial`)
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Configurar consola en UTF-8 para Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def imprimir_estado(nombre: str, ok: bool, detalle: str) -> None:
    icono = "[OK]" if ok else "[AVISO]"
    print(f"  {icono:<8} {nombre:<30} -> {detalle}")


def ejecutar_diagnostico(rapido: bool = False) -> int:
    print("=" * 74)
    print("  DIAGNÓSTICO INTEGRAL — ASISTENTE EDUCATIVO HARU (TDAH)")
    print(f"  Python detectado: {sys.version.split()[0]} ({sys.executable})")
    print("=" * 74)

    # 1. Dependencias gráficas y visión
    for mod_name, label in [
        ("customtkinter", "Interfaz CustomTkinter"),
        ("PIL", "Motor Gráfico Pillow 3D"),
        ("edge_tts", "Voz Neuronal Edge-TTS"),
        ("sounddevice", "Audio Micrófono SoundDevice"),
        ("speech_recognition", "Transcripción SpeechRec"),
        ("serial", "Comunicación Arduino PySerial"),
        ("cv2", "Visión Cámara OpenCV"),
    ]:
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", "instalado")
            imprimir_estado(label, True, f"Versión {ver}")
        except ImportError as e:
            imprimir_estado(label, False, f"No instalado ({e})")

    # 2. Base de datos, WAL y PBKDF2
    from core.config import AUDIO_PRECARGADO_DIR
    from core.ia import MotorIAHaru, evaluar_ast_seguro
    from core.repositorio_db import RepositorioTDAH
    from core.voz.stt import EscuchaVozHaru
    from hardware.control_leds import ControladorHardwareLEDs

    db = RepositorioTDAH()
    pin_hasheado = bool(db.obtener_preferencia("pin_hash", "")) and not bool(db.obtener_preferencia("pin_docente", ""))
    imprimir_estado("SQLite WAL + PIN PBKDF2", pin_hasheado, f"{len(db.listar_tareas())} misiones cargadas, PIN cifrado")

    res_ast = evaluar_ast_seguro("(15 + 7) * 2")
    imprimir_estado("Calculadora Segura AST", res_ast == 44, f"(15 + 7) * 2 = {res_ast} (sin eval ni SymPy)")

    # 3. Audios neuronales precargados offline
    precargados = list(AUDIO_PRECARGADO_DIR.glob("*.mp3"))
    kb_voz = sum(p.stat().st_size for p in precargados) / 1024.0
    imprimir_estado("Frases Neuronales Offline", len(precargados) > 0, f"{len(precargados)} audios MP3 ({kb_voz:.1f} KB)")

    # 4. Periféricos locales (Micrófono y Arduino)
    stt = EscuchaVozHaru()
    hay_mic = stt.hay_microfono_disponible()
    imprimir_estado("Micrófono Físico", hay_mic, "Detectado y listo" if hay_mic else "No detectado (usará cuadro de texto)")

    hw = ControladorHardwareLEDs()
    puertos = hw.listar_puertos_disponibles()
    imprimir_estado(
        "Placa Arduino UNO R3",
        not hw.en_simulacion,
        f"Conectada en {hw.puerto_actual}" if not hw.en_simulacion else f"Modo Simulación (Puertos COM: {puertos or 'ninguno'})",
    )
    hw.cerrar()

    if rapido:
        print("=" * 74)
        return 0

    # 5. Verificación en vivo de Ollama y Gemini API
    ia = MotorIAHaru(repositorio_db=db)
    mod_ollama = ia.detectar_ollama_local(forzar=True)
    imprimir_estado("IA Local Ollama (11434)", bool(mod_ollama), f"Modelo activo: {mod_ollama}" if mod_ollama else "No activo (opcional)")

    ok_gem, msg_gem = ia.probar_conexion_cloud()
    imprimir_estado("IA Cloud Google Gemini", ok_gem, msg_gem)

    print("=" * 74)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnóstico integral de Haru TDAH")
    parser.add_argument("--rapido", action="store_true", help="Omitir pruebas de red en vivo")
    args = parser.parse_args()
    raise SystemExit(ejecutar_diagnostico(rapido=args.rapido))

