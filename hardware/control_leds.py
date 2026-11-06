"""
Módulo de Control de Hardware Arduino UNO R3 para Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Maneja la comunicación serial con Arduino UNO R3 (Pines 2, 3 y 4) y provee
un modo de simulación automático 100% funcional en caso de que la computadora
de un compañero no tenga el circuito físico conectado.
"""

import threading
import time
import math
from typing import List, Optional, Callable

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class ControladorHardwareLEDs:
    def __init__(self, puerto_default: str = "COM15", baudrate: int = 9600,
                 callback_gui: Optional[Callable[[List[bool], str], None]] = None):
        self.puerto_default = puerto_default
        self.puerto_actual = None
        self.baudrate = baudrate
        self.conexion = None
        self.en_simulacion = True
        self.callback_gui = callback_gui
        self.estado_leds = [False, False, False]
        self._lock = threading.Lock()

        self.conectar()

    def listar_puertos_disponibles(self) -> List[str]:
        if not SERIAL_AVAILABLE:
            return []
        try:
            return [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            return []

    def _listar_puertos_usb_arduino(self) -> List[str]:
        """Filtra puertos USB/Arduino reales para no bloquear el arranque en COM1 de placa madre."""
        if not SERIAL_AVAILABLE:
            return []
        try:
            candidatos = []
            for p in serial.tools.list_ports.comports():
                desc = f"{p.description or ''} {p.manufacturer or ''} {p.hwid or ''}".lower()
                if any(k in desc for k in ("arduino", "ch340", "cp210", "ftdi", "usb")):
                    candidatos.append(p.device)
            return candidatos
        except Exception:
            return []

    def conectar(self, puerto_especifico: Optional[str] = None) -> bool:
        """Intenta conectar con la placa Arduino UNO. Si no está disponible, activa modo simulación."""
        if not SERIAL_AVAILABLE:
            print("[Hardware] pySerial no instalado. Activando MODO SIMULACIÓN visual de LEDs.")
            self.en_simulacion = True
            return False

        if self.conexion and self.conexion.is_open:
            try:
                self.conexion.close()
            except Exception:
                pass

        puertos_a_probar = []
        if puerto_especifico:
            puertos_a_probar.append(puerto_especifico)
        if self.puerto_default not in puertos_a_probar:
            puertos_a_probar.append(self.puerto_default)

        for p in self._listar_puertos_usb_arduino():
            if p not in puertos_a_probar:
                puertos_a_probar.append(p)

        for puerto in puertos_a_probar:
            try:
                self.conexion = serial.Serial(puerto, self.baudrate, timeout=1)
                time.sleep(1.2)
                self.en_simulacion = False
                self.puerto_actual = puerto
                print(f"[Hardware] ¡Conexión exitosa con Arduino UNO R3 en {puerto}!")
                return True
            except Exception:
                continue

        print("[Hardware] No se detectó placa Arduino física. Operando en MODO SIMULACIÓN.")
        self.en_simulacion = True
        self.puerto_actual = "Simulación Virtual"
        self.conexion = None
        return False

    def enviar_comando(self, comando: str):
        """Envía una trama de texto serial al Arduino y protege contra desconexiones."""
        with self._lock:
            if not self.en_simulacion and self.conexion and self.conexion.is_open:
                try:
                    mensaje = (comando.strip() + "\n").encode("utf-8")
                    self.conexion.write(mensaje)
                except Exception as e:
                    print(f"[Hardware] Desconexión serial detectada ({e}). Pasando a simulación.")
                    self.en_simulacion = True
                    self.puerto_actual = "Simulación Virtual"

    def actualizar_progreso(self, paso_actual: int, total_pasos: int = 3):
        """
        Mapea proporcionalmente el paso actual (de 1 a N) hacia los 3 LEDs físicos
        del circuito en protoboard (P1, P2, P3).
        """
        if paso_actual <= 0 or total_pasos <= 0:
            leds_encendidos = 0
        elif total_pasos <= 3:
            leds_encendidos = min(3, paso_actual)
        else:
            # Mapeo proporcional para tareas de 4 o más pasos
            proporcion = paso_actual / float(total_pasos)
            leds_encendidos = max(1, min(3, math.ceil(proporcion * 3)))

        self.estado_leds = [i < leds_encendidos for i in range(3)]

        if leds_encendidos <= 0:
            self.enviar_comando("OFF")
        elif leds_encendidos == 1:
            self.enviar_comando("P1")
        elif leds_encendidos == 2:
            self.enviar_comando("P2")
        else:
            self.enviar_comando("P3")

        self._notificar_gui("PROGRESO")

    def celebrar_victoria(self):
        """Envía comando de animación festiva (parpadeo de triunfo en los 3 LEDs)."""
        self.estado_leds = [True, True, True]
        self.enviar_comando("WIN")
        self._notificar_gui("WIN")

    def activar_pausa(self):
        """Envía comando de luz suave en LED central para pausa activa."""
        self.estado_leds = [False, True, False]
        self.enviar_comando("PAUSA")
        self._notificar_gui("PAUSA")

    def apagar_todo(self):
        """Apaga todos los LEDs."""
        self.estado_leds = [False, False, False]
        self.enviar_comando("OFF")
        self._notificar_gui("OFF")

    def _notificar_gui(self, evento: str):
        if self.callback_gui:
            try:
                self.callback_gui(list(self.estado_leds), evento)
            except Exception:
                pass

    def cerrar(self):
        self.apagar_todo()
        if self.conexion and self.conexion.is_open:
            try:
                self.conexion.close()
            except Exception:
                pass
