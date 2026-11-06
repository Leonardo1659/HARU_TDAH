"""
Pre-generador de Frases Neuronales Fijas (`es-BO-SofiaNeural`) para Uso 100% Offline
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Sintetiza y guarda en `assets/voz_precargada/` las ~22 frases esenciales de Haru
junto con sus tiempos exactos `WordBoundary` para que viajen dentro del `.zip`
(ocupan < 450 KB en total) y suenen con calidad neuronal incluso sin internet.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import AUDIO_PRECARGADO_DIR, VOZ_POR_DEFECTO
from core.motor_tdah import MotorTDAH
from core.voz.tts import MotorVozHaru, limpiar_texto_para_voz


FRASES_ESENCIALES = [
    "¡Hola amiguito! Soy Haru, tu compañero de estudio. ¡Toca Empezar Misión cuando estés listo!",
    "¡Jajaja, eso me dio cosquillas! ¡Vamos súper bien con nuestra misión!",
    "Vamos a respirar juntos. Inhala profundo por la nariz como oliendo una flor... y ahora sopla despacito como apagando una velita. ¡Qué tranquilidad!",
    "¡Hora del reto de colores! Muéstrame un objeto amarillo, rojo, azul o verde.",
    "¡Traje de Robotito Celeste activado!",
    "¡Miau! ¡Traje de Gatito Espacial listo!",
    "¡Qué tierno! ¡Traje de Osito Tutor activado!",
    "¡Qué bien! Retomamos nuestro paso con energía renovada.",
    "¡Vamos a comenzar con Matemáticas - Sumas Divertidas! Paso 1: Saca tu cuaderno de matemáticas, tu lápiz y tu borrador sobre la mesa.",
    "Pista de apoyo: Busca en tu mochila únicamente el cuaderno de cuadros y un lápiz.",
    "Pista de apoyo: Escribe el 15 arriba y el 7 justo debajo del 5 para alinear las unidades.",
    "Pista de apoyo: Puedes contar desde 15 subiendo 7 deditos: 16, 17, 18, 19, 20, 21 y 22.",
    "¡Hola! Así suena mi voz neuronal lista para acompañar tus tareas.",
    *MotorTDAH.FRASES_REFUERZO,
    *MotorTDAH.FRASES_ANIMAR_PAUSA,
    *MotorTDAH.FRASES_RETOMAR_ESTUDIO,
]


def main() -> int:
    voz = MotorVozHaru(voz=VOZ_POR_DEFECTO, velocidad="+0%", silenciado=True)
    ok_count = 0
    try:
        for i, frase in enumerate(FRASES_ESENCIALES, start=1):
            limpia = limpiar_texto_para_voz(frase)
            res = voz.obtener_o_sintetizar_mp3(limpia, directorio_destino=AUDIO_PRECARGADO_DIR)
            if res:
                mp3_path, marcas = res
                print(f"[{i:02d}/{len(FRASES_ESENCIALES)}] OK -> {mp3_path.name} ({len(marcas)} palabras)")
                ok_count += 1
            else:
                print(f"[{i:02d}/{len(FRASES_ESENCIALES)}] OMITIDO (sin red) -> {limpia[:48]}...")
    finally:
        voz.cerrar()

    total_kb = sum(p.stat().st_size for p in AUDIO_PRECARGADO_DIR.glob("*")) / 1024.0
    print(f"\nResumen: {ok_count}/{len(FRASES_ESENCIALES)} frases listas en assets/voz_precargada/ ({total_kb:.1f} KB).")
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

