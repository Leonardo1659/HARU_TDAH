"""
Herramientas Multimodales y Sensoriales para el Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Proyecto Integrador

Integra:
- Efectos sonoros de refuerzo positivo inmediatos con `winsound` nativo de Windows
  (0 MB de dependencias extra, sin requerir `pygame`).
- Motor de detección de colores HSV en tiempo real con `OpenCV` + `NumPy` para el
  modal integrado de Cámara en CustomTkinter (`ui/reto_colores_modal.py`), detectando
  objetos de color Amarillo, Rojo, Azul y Verde con respaldo automático sin cámara.
"""

import threading
from typing import Callable, Optional, Tuple

try:
    import winsound
    WINSOUND_DISPONIBLE = True
except ImportError:
    WINSOUND_DISPONIBLE = False

try:
    import cv2
    import numpy as np
    OPENCV_DISPONIBLE = True
except ImportError:
    OPENCV_DISPONIBLE = False


def analizar_frame_colores(frame_bgr) -> Tuple[object, str]:
    """
    Procesa un fotograma BGR de OpenCV, dibuja contornos suaves alrededor de objetos
    escolares de color AMARILLO, ROJO, AZUL o VERDE y devuelve `(frame_rgb, color)`.
    """
    if not OPENCV_DISPONIBLE or frame_bgr is None:
        return frame_bgr, ""

    frame = cv2.flip(frame_bgr, 1)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    kernel = np.ones((5, 5), np.uint8)

    rangos = [
        ("AMARILLO", [((20, 115, 80), (36, 255, 255))], (0, 230, 255)),
        ("ROJO", [((0, 125, 75), (9, 255, 255)), ((168, 125, 75), (180, 255, 255))], (60, 60, 255)),
        ("AZUL", [((96, 115, 70), (132, 255, 255))], (255, 150, 30)),
        ("VERDE", [((40, 95, 65), (85, 255, 255))], (80, 220, 100)),
    ]

    mejor_color = ""
    mayor_area = 2400.0

    for nombre_color, sub_rangos, color_bgr in rangos:
        mascara = None
        for bajo, alto in sub_rangos:
            parcial = cv2.inRange(hsv, np.array(bajo, np.uint8), np.array(alto, np.uint8))
            mascara = parcial if mascara is None else cv2.add(mascara, parcial)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contornos:
            area = cv2.contourArea(c)
            if area > 2400:
                hull = cv2.convexHull(c)
                cv2.drawContours(frame, [hull], 0, color_bgr, 3, lineType=cv2.LINE_AA)
                if area > mayor_area:
                    mayor_area = area
                    mejor_color = nombre_color

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return frame_rgb, mejor_color


class GestorMultimodal:
    """Gestiona sonidos de dopamina y utilidades sensoriales de visión artificial."""

    def __init__(self):
        self.sonido_activo = True

    def reproducir_sonido_paso(self) -> None:
        if not self.sonido_activo or not WINSOUND_DISPONIBLE:
            return

        def _beep():
            try:
                winsound.Beep(523, 95)
                winsound.Beep(659, 110)
                winsound.Beep(784, 150)
            except Exception:
                pass

        threading.Thread(target=_beep, daemon=True).start()

    def reproducir_sonido_victoria(self) -> None:
        if not self.sonido_activo or not WINSOUND_DISPONIBLE:
            return

        def _fanfarria():
            try:
                for freq, dur in [(523, 100), (659, 100), (784, 100), (1046, 240), (784, 100), (1046, 320)]:
                    winsound.Beep(freq, dur)
            except Exception:
                pass

        threading.Thread(target=_fanfarria, daemon=True).start()

    def reproducir_sonido_pausa(self) -> None:
        if not self.sonido_activo or not WINSOUND_DISPONIBLE:
            return

        def _suave():
            try:
                winsound.Beep(440, 150)
                winsound.Beep(523, 190)
            except Exception:
                pass

        threading.Thread(target=_suave, daemon=True).start()

    def hay_camara_disponible(self) -> bool:
        if not OPENCV_DISPONIBLE:
            return False
        cap = cv2.VideoCapture(0, getattr(cv2, "CAP_DSHOW", 0))
        abierta = bool(cap and cap.isOpened())
        if cap:
            cap.release()
        return abierta

    def iniciar_reto_colores_camara(self, callback_resultado: Optional[Callable[[str], None]] = None) -> None:
        """Método de respaldo si se invoca sin modal gráfico."""
        if callback_resultado:
            callback_resultado(
                "¡Excelente atención visual! Ganaste +2 estrellas en el Reto Sensorial de Colores."
            )
