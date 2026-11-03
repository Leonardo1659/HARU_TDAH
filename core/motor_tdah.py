"""
Motor Pedagógico para Metodología TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Gestiona:
1. Descomposición de tareas escolares en micro-pasos secuenciales (Objetivo 1).
2. Orientación por voz y repetición amable con interrupción instantánea (Objetivo 2).
3. Seguimiento del avance, control de frecuencia de descansos del alumno,
   gamificación con estrellas y registro en SQLite (Objetivo 3).
4. Temporizador Micro-Pomodoro con Pausas Activas y acompañamiento adulto (Objetivo 4).
"""

import random
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from core.eventos import BusEventosUI


class MotorTDAH:
    ESTADO_IDLE = "IDLE"
    ESTADO_EN_PASO = "EN_PASO"
    ESTADO_PAUSA_ACTIVA = "PAUSA_ACTIVA"
    ESTADO_COMPLETADA = "COMPLETADA"

    FRASES_REFUERZO = [
        "¡Súper bien! ¡Ganaste una estrellita dorada, sigamos así!",
        "¡Genial! ¡Lo lograste, eres muy inteligente y valiente!",
        "¡Bravo! ¡Un paso menos para terminar tu misión de hoy!",
        "¡Qué gran concentración! ¡Estoy muy orgulloso de tu esfuerzo!",
        "¡Fantástico! ¡Vamos con toda la alegría al siguiente paso!",
    ]

    FRASES_ANIMAR_PAUSA = [
        "¡Tiempo de concentración cumplido! Descansa 3 minutos: levántate, estira los brazos o toma agüita.",
        "¡Hiciste un gran esfuerzo! Tu cerebro merece recargar energía en una pausa activa.",
        "¡Momento de recreo cortito! Sacude las manitos y respira profundo antes de seguir.",
    ]

    FRASES_RETOMAR_ESTUDIO = [
        "¡Terminó el descanso! Ya tenemos energía nueva para continuar con nuestro paso.",
        "¡Listos otra vez! Volvamos despacio y con alegría a donde nos quedamos.",
    ]

    HITOS_RECOMPENSA = [
        (5, "🌱 Medalla desbloqueada: Semilla Curiosa"),
        (8, "🐱 ¡Nuevo traje desbloqueado: Gatito Espacial!"),
        (12, "⚡ Medalla desbloqueada: Súper Enfoque"),
        (18, "🐻 ¡Nuevo traje desbloqueado: Osito Tutor!"),
        (25, "🚀 Medalla desbloqueada: Explorador Galáctico"),
        (32, "👑 ¡Nuevo traje desbloqueado: Súper Haru Dorado!"),
        (45, "🏆 Medalla desbloqueada: Campeón Dorado Haru"),
    ]

    def __init__(self, callback_voz: Optional[Callable[[str], None]] = None,
                 callback_ui: Optional[Callable[[Dict], None]] = None,
                 controlador_hardware=None,
                 repositorio_db=None,
                 motor_ia=None,
                 gestor_multimodal=None,
                 bus_eventos: Optional[BusEventosUI] = None):
        self.callback_voz = callback_voz
        self.callback_ui = callback_ui
        self.hardware = controlador_hardware
        self.db = repositorio_db
        self.ia = motor_ia
        self.multimodal = gestor_multimodal
        self.bus = bus_eventos

        self.estado = self.ESTADO_IDLE
        self.tarea_actual = "Matemáticas - Sumas Divertidas"
        self.pasos_actuales: List[str] = [
            "Saca tu cuaderno de matemáticas, tu lápiz y tu borrador sobre la mesa.",
            "Abre tu cuaderno en una hoja limpia y escribe la suma: 15 + 7.",
            "Suma primero las unidades (5 más 7) y luego la decena. ¡Presiona Paso Listo cuando termines!",
        ]
        self.pistas_actuales: List[str] = [
            "Busca en tu mochila únicamente el cuaderno de cuadros y un lápiz.",
            "Escribe el 15 arriba y el 7 justo debajo del 5 para alinear las unidades.",
            "Puedes contar desde 15 subiendo 7 deditos: 16, 17, 18, 19, 20, 21 y 22.",
        ]
        self.indice_paso = 0

        # Métricas de la sesión actual y control de descansos del alumno
        self.segundos_concentracion_sesion = 0
        self.pausas_activas_sesion = 0
        self.pausas_manuales_sesion = 0
        self.max_descansos_por_tarea = (
            int(self.db.obtener_preferencia("max_descansos_por_tarea", "2")) if self.db else 2
        )
        self.cooldown_descanso_seg = 10
        self.marcas_segundos_descanso: List[int] = []

        self.pistas_usadas_sesion = 0
        self.estrellas_sesion = 0
        self.estrellas_totales = self.db.obtener_estrellas() if self.db else 5
        self.pasos_premiados: set = set()
        self._sesion_guardada = False
        self.ultimo_mensaje_hablado = "¡Hola! Soy Haru, tu compañero de estudio. ¡Elige tu misión y empecemos!"

        # Parámetros del Temporizador Micro-Pomodoro TDAH (10m foco / 2m pausa por defecto, persistentes)
        self.modo_demo = False
        min_foco_cfg = int(self.db.obtener_preferencia("min_foco_pomodoro", "10")) if self.db else 10
        min_pausa_cfg = int(self.db.obtener_preferencia("min_pausa_pomodoro", "2")) if self.db else 2
        self.tiempo_foco = max(1, min_foco_cfg) * 60
        self.tiempo_pausa = max(1, min_pausa_cfg) * 60

        self.segundos_restantes = self.tiempo_foco
        self.temporizador_activo = False
        self.reloj_en_pausa_manual = False
        self._hilo_timer: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._ia_ocupada = False

    def set_modo_demo(self, activo: bool) -> None:
        self.modo_demo = activo
        if activo:
            self.tiempo_foco = 25
            self.tiempo_pausa = 10
        else:
            min_f = int(self.db.obtener_preferencia("min_foco_pomodoro", "10")) if self.db else 10
            min_p = int(self.db.obtener_preferencia("min_pausa_pomodoro", "2")) if self.db else 2
            self.tiempo_foco = max(1, min_f) * 60
            self.tiempo_pausa = max(1, min_p) * 60
        self.segundos_restantes = self.tiempo_foco
        self._notificar_ui()

    def configurar_tiempos_personalizados(self, min_foco: int, min_pausa: int,
                                          max_descansos: Optional[int] = None) -> None:
        self.modo_demo = False
        mf = max(1, min(60, int(min_foco)))
        mp = max(1, min(30, int(min_pausa)))
        self.tiempo_foco = mf * 60
        self.tiempo_pausa = mp * 60
        if self.db:
            self.db.guardar_preferencia("min_foco_pomodoro", str(mf))
            self.db.guardar_preferencia("min_pausa_pomodoro", str(mp))
        if max_descansos is not None:
            self.max_descansos_por_tarea = max(0, min(10, int(max_descansos)))
            if self.db:
                self.db.guardar_preferencia("max_descansos_por_tarea", str(self.max_descansos_por_tarea))
        self.segundos_restantes = self.tiempo_foco
        self._notificar_ui()

    def _otorgar_estrellas(self, cantidad: int) -> List[str]:
        """Suma estrellas y detecta automáticamente nuevos hitos (medallas o trajes)."""
        prev = self.estrellas_totales
        if self.db:
            self.estrellas_totales = self.db.sumar_estrellas(cantidad)
        else:
            self.estrellas_totales = max(0, prev + cantidad)

        nuevos_logros = [
            titulo for meta, titulo in self.HITOS_RECOMPENSA
            if prev < meta <= self.estrellas_totales
        ]
        if nuevos_logros and self.bus:
            for logro in nuevos_logros:
                self.bus.emitir("logro_desbloqueado", titulo=logro, estrellas=self.estrellas_totales)
        return nuevos_logros

    def guardar_sesion_parcial_si_aplica(self) -> None:
        """Persiste el esfuerzo real cuando se cambia de tarea o se cierra antes de terminar."""
        if (
            not self._sesion_guardada
            and self.db
            and self.estado in (self.ESTADO_EN_PASO, self.ESTADO_PAUSA_ACTIVA)
            and len(self.pasos_premiados) > 0
        ):
            self._sesion_guardada = True
            self.db.registrar_sesion(
                nombre_tarea=self.tarea_actual,
                pasos_completados=len(self.pasos_premiados),
                total_pasos=len(self.pasos_actuales),
                segundos_concentracion=self.segundos_concentracion_sesion,
                pausas_activas=self.pausas_activas_sesion,
                pistas_usadas=self.pistas_usadas_sesion,
                estrellas_ganadas=self.estrellas_sesion,
                estado_final="PARCIAL",
                pausas_manuales=self.pausas_manuales_sesion,
                intervalo_promedio_descanso_seg=self.calcular_intervalo_promedio_descanso(),
            )

    def cargar_tarea(self, nombre_tarea: str, pasos: List[str],
                     pistas: Optional[List[str]] = None) -> None:
        self.guardar_sesion_parcial_si_aplica()
        self.tarea_actual = nombre_tarea
        self.pasos_actuales = pasos if pasos else ["Realizar la actividad escolar indicada."]
        if pistas and len(pistas) >= len(self.pasos_actuales):
            self.pistas_actuales = pistas[:len(self.pasos_actuales)]
        else:
            self.pistas_actuales = []
            for i in range(len(self.pasos_actuales)):
                if pistas and i < len(pistas) and pistas[i]:
                    self.pistas_actuales.append(pistas[i])
                else:
                    self.pistas_actuales.append(f"Haz solo el paso {i + 1} con calma y sin prisa.")
        self.reiniciar()

    def iniciar_tarea(self) -> None:
        self.estado = self.ESTADO_EN_PASO
        self.indice_paso = 0
        self.segundos_restantes = self.tiempo_foco
        self.segundos_concentracion_sesion = 0
        self.pausas_activas_sesion = 0
        self.pausas_manuales_sesion = 0
        self.marcas_segundos_descanso = []
        self.pistas_usadas_sesion = 0
        self.estrellas_sesion = 0
        self.pasos_premiados = set()
        self._sesion_guardada = False
        self.reloj_en_pausa_manual = False
        if self.db:
            self.max_descansos_por_tarea = int(self.db.obtener_preferencia("max_descansos_por_tarea", "2"))
            self.estrellas_totales = self.db.obtener_estrellas()
        self.iniciar_temporizador()

        if self.hardware:
            self.hardware.actualizar_progreso(1, len(self.pasos_actuales))
        if self.bus:
            self.bus.emitir("avatar_reaccion", reaccion="SALUDANDO", duracion=2.0)

        mensaje = f"¡Vamos a comenzar con {self.tarea_actual}! Paso 1: {self.pasos_actuales[0]}"
        self._hablar(mensaje)
        self._notificar_ui()

    def reanudar_desde_pausa_activa(self) -> Tuple[bool, str]:
        """Permite al niño terminar su pausa activa antes de tiempo sin descontar descansos manuales."""
        if self.estado != self.ESTADO_PAUSA_ACTIVA:
            return False, ""
        self.estado = self.ESTADO_EN_PASO
        self.reloj_en_pausa_manual = False
        self.segundos_restantes = self.tiempo_foco
        if self.hardware:
            num = min(self.indice_paso + 1, max(1, len(self.pasos_actuales)))
            self.hardware.actualizar_progreso(num, len(self.pasos_actuales))
        paso_txt = (
            self.pasos_actuales[self.indice_paso]
            if self.indice_paso < len(self.pasos_actuales)
            else ""
        )
        msg = f"{random.choice(self.FRASES_RETOMAR_ESTUDIO)} Seguimos en el paso {self.indice_paso + 1}: {paso_txt}"
        self._hablar(msg)
        self._notificar_ui()
        return False, msg

    def avanzar_paso(self) -> None:
        if self.estado == self.ESTADO_IDLE:
            self.iniciar_tarea()
            return
        if self.estado == self.ESTADO_PAUSA_ACTIVA:
            self.reanudar_desde_pausa_activa()
            return
        if self.estado != self.ESTADO_EN_PASO:
            return

        self.reloj_en_pausa_manual = False
        gano_estrella_nueva = self.indice_paso not in self.pasos_premiados
        if gano_estrella_nueva:
            self.pasos_premiados.add(self.indice_paso)
            self.estrellas_sesion += 1
            self._otorgar_estrellas(1)
            if self.bus:
                self.bus.emitir("avatar_reaccion", reaccion="PASO_LOGRADO", duracion=2.5)

        self.indice_paso += 1

        if self.indice_paso >= len(self.pasos_actuales):
            self.completar_tarea()
            return

        if self.multimodal:
            self.multimodal.reproducir_sonido_paso()

        refuerzo = (
            random.choice(self.FRASES_REFUERZO)
            if gano_estrella_nueva
            else "¡Muy bien repasado!"
        )
        num_paso = self.indice_paso + 1
        siguiente = self.pasos_actuales[self.indice_paso]

        if self.hardware:
            self.hardware.actualizar_progreso(num_paso, len(self.pasos_actuales))

        mensaje = f"{refuerzo} Ahora vamos al paso {num_paso}: {siguiente}"
        self._hablar(mensaje)
        self._notificar_ui()

    def retroceder_paso(self) -> None:
        if self.estado == self.ESTADO_EN_PASO and self.indice_paso > 0:
            self.indice_paso -= 1
            num_paso = self.indice_paso + 1
            if self.hardware:
                self.hardware.actualizar_progreso(num_paso, len(self.pasos_actuales))
            self._hablar(f"Volvemos al paso {num_paso}: {self.pasos_actuales[self.indice_paso]}")
            self._notificar_ui()

    def repetir_paso(self) -> None:
        if self.estado == self.ESTADO_IDLE:
            self.iniciar_tarea()
            return
        if self.estado == self.ESTADO_COMPLETADA:
            msg = (
                f"¡Ya completaste {self.tarea_actual}! "
                "Puedes preguntarme cualquier duda, canjear tus premios o tocar Siguiente Misión."
            )
            self._hablar(msg)
            self._notificar_ui()
            return
        if self.estado == self.ESTADO_PAUSA_ACTIVA:
            msg = "Estamos en tu pausa activa saludable. Estira los brazos o toca Reanudar Estudio cuando estés listo."
            self._hablar(msg)
            self._notificar_ui()
            return
        if self.estado == self.ESTADO_EN_PASO and self.indice_paso < len(self.pasos_actuales):
            num_paso = self.indice_paso + 1
            instruccion = self.pasos_actuales[self.indice_paso]
            self._hablar(f"Con mucho gusto te repito el paso {num_paso}: {instruccion}")
            self._notificar_ui()

    def dar_pista(self) -> str:
        if self.estado == self.ESTADO_COMPLETADA:
            msg = "¡Ya completaste esta misión! Ahora podemos conversar de lo que quieras, canjear tus estrellas o pasar a la siguiente misión."
            self._hablar(msg)
            self._notificar_ui()
            return msg
        if self.estado != self.ESTADO_EN_PASO:
            msg = "Presiona ¡Empezar Misión! para avanzar paso a paso con mis pistas, o escríbeme cualquier pregunta."
            self._hablar(msg)
            self._notificar_ui()
            return msg

        self.pistas_usadas_sesion += 1
        paso_texto = self.pasos_actuales[self.indice_paso]
        num_paso = self.indice_paso + 1

        if self.pistas_usadas_sesion == 1 and self.indice_paso < len(self.pistas_actuales) and self.pistas_actuales[self.indice_paso]:
            pista = f"Pista de apoyo: {self.pistas_actuales[self.indice_paso]}"
        elif self.ia:
            pista = self.ia.generar_pista_contextual(self.tarea_actual, paso_texto, num_paso)
        else:
            pista = "Tómalo con calma. Haz una sola cosita a la vez y respira profundo."

        self._hablar(pista)
        self._notificar_ui()
        return pista

    def dar_pista_async(self) -> None:
        if self._ia_ocupada:
            return
        self._ia_ocupada = True
        if self.bus:
            self.bus.emitir("ia_pensando", mensaje="Preparando una pista mágica para ti...")

        def _worker():
            pista = "Tómalo con calma, hagamos un pasito a la vez."
            try:
                pista = self.dar_pista()
            finally:
                self._ia_ocupada = False
                if self.bus:
                    self.bus.emitir("ia_pista_lista", pista=pista)

        threading.Thread(target=_worker, daemon=True, name="HaruHintWorker").start()

    def consultar_ia(self, pregunta: str) -> str:
        en_paso_activo = self.estado == self.ESTADO_EN_PASO
        paso_txt = (
            self.pasos_actuales[self.indice_paso]
            if (en_paso_activo and self.indice_paso < len(self.pasos_actuales))
            else ""
        )
        if self.ia:
            respuesta = self.ia.responder_consulta_escolar(
                pregunta,
                self.tarea_actual,
                paso_txt,
                modo_charla_libre=not en_paso_activo,
            )
        else:
            respuesta = (
                f"¡Buena pregunta! Concentrémonos en nuestro paso actual: {paso_txt}"
                if paso_txt
                else "¡Qué lindo charlar contigo! Puedes preguntarme dudas de clase o elegir otra misión cuando gustes."
            )
        self._hablar(respuesta)
        self._notificar_ui()
        return respuesta

    def consultar_ia_async(self, pregunta: str) -> None:
        if self._ia_ocupada:
            return
        self._ia_ocupada = True
        if self.bus:
            self.bus.emitir("ia_pensando", mensaje="Haru está pensando tu respuesta...")

        def _worker():
            respuesta = "¡Aquí estoy contigo! Pregúntame de nuevo si necesitas ayuda."
            try:
                respuesta = self.consultar_ia(pregunta)
            finally:
                self._ia_ocupada = False
                if self.bus:
                    self.bus.emitir("ia_respuesta", respuesta=respuesta)

        threading.Thread(target=_worker, daemon=True, name="HaruAIWorker").start()

    def calcular_intervalo_promedio_descanso(self) -> int:
        if not self.marcas_segundos_descanso:
            return 0
        intervalos = []
        prev = 0
        for marca in self.marcas_segundos_descanso:
            intervalos.append(max(1, marca - prev))
            prev = marca
        return int(sum(intervalos) / len(intervalos))

    def solicitar_descanso_alumno(self) -> Tuple[bool, str]:
        if self.estado == self.ESTADO_PAUSA_ACTIVA:
            return self.reanudar_desde_pausa_activa()

        if self.estado == self.ESTADO_COMPLETADA:
            msg = "¡Ya terminaste tu misión! Ahora estás en tu tiempo libre de descanso con Haru."
            self._hablar(msg)
            self._notificar_ui()
            return False, msg

        if self.estado == self.ESTADO_IDLE:
            msg = "Primero toca ¡Empezar Misión!, y cuando necesites un respiro podrás usar tu botón de descanso."
            self._hablar(msg)
            self._notificar_ui()
            return False, msg

        if self.reloj_en_pausa_manual:
            self.reloj_en_pausa_manual = False
            msg = "¡Qué bien! Retomamos nuestro paso con energía renovada."
            self._hablar(msg)
            self._notificar_ui()
            return False, msg

        if self.pausas_manuales_sesion >= self.max_descansos_por_tarea:
            msg = (
                f"Ya usaste tus {self.max_descansos_por_tarea} descansos de esta misión. "
                f"¡Vamos, falta muy poquito para ganar tus estrellas!"
            )
            self._hablar(msg)
            self._notificar_ui()
            return False, msg

        if self.marcas_segundos_descanso:
            ultimo = self.marcas_segundos_descanso[-1]
            transcurrido_desde_ultimo = self.segundos_concentracion_sesion - ultimo
            if transcurrido_desde_ultimo < self.cooldown_descanso_seg:
                faltan = self.cooldown_descanso_seg - transcurrido_desde_ultimo
                msg = f"Acabas de descansar hace poquito. Avancemos {faltan} segundos más antes de otro descanso."
                self._hablar(msg)
                return False, msg

        self.reloj_en_pausa_manual = True
        self.pausas_manuales_sesion += 1
        segundo_actual = max(1, self.segundos_concentracion_sesion)
        self.marcas_segundos_descanso.append(segundo_actual)

        if self.db:
            self.db.registrar_evento_descanso(
                nombre_tarea=self.tarea_actual,
                paso_actual=self.indice_paso + 1,
                segundos_transcurridos=segundo_actual,
                motivo=f"Descanso #{self.pausas_manuales_sesion} solicitado por el alumno",
            )

        restantes = self.max_descansos_por_tarea - self.pausas_manuales_sesion
        msg = (
            f"Reloj en descanso corto. Respira profundo con Haru. "
            f"Te quedan {restantes} descansos disponibles en esta tarea."
        )
        self._hablar(msg)
        self._notificar_ui()
        return True, msg

    def alternar_pausa_reloj(self) -> bool:
        pausado, _ = self.solicitar_descanso_alumno()
        return pausado

    def completar_tarea(self) -> None:
        self.estado = self.ESTADO_COMPLETADA
        self.detener_temporizador()

        self.estrellas_sesion += 3
        self._otorgar_estrellas(3)
        intervalo_prom = self.calcular_intervalo_promedio_descanso()
        self._sesion_guardada = True

        if self.db:
            self.db.registrar_sesion(
                nombre_tarea=self.tarea_actual,
                pasos_completados=len(self.pasos_actuales),
                total_pasos=len(self.pasos_actuales),
                segundos_concentracion=self.segundos_concentracion_sesion,
                pausas_activas=self.pausas_activas_sesion,
                pistas_usadas=self.pistas_usadas_sesion,
                estrellas_ganadas=self.estrellas_sesion,
                estado_final="COMPLETADA",
                pausas_manuales=self.pausas_manuales_sesion,
                intervalo_promedio_descanso_seg=intervalo_prom,
            )

        if self.multimodal:
            self.multimodal.reproducir_sonido_victoria()

        if self.hardware:
            self.hardware.celebrar_victoria()

        if self.bus:
            # Festejo alegre de 5.5s tras el cual Haru baja a reposo tranquilo (Modo Compañero)
            self.bus.emitir("avatar_reaccion", reaccion="CELEBRANDO", duracion=5.5)

        mensaje = (
            f"¡FELICITACIONES CAMPEÓN! Completaste todos los pasos de {self.tarea_actual} "
            f"y ganaste {self.estrellas_sesion} estrellas hoy. "
            f"Ahora descanso tranquilo contigo: podemos charlar de lo que quieras o pasar a otra misión."
        )
        self._hablar(mensaje)
        self._notificar_ui()

    def iniciar_temporizador(self) -> None:
        if self._hilo_timer and self._hilo_timer.is_alive():
            self.temporizador_activo = False
            time.sleep(0.12)

        self.temporizador_activo = True
        self._hilo_timer = threading.Thread(target=self._bucle_timer, daemon=True, name="HaruPomodoroTimer")
        self._hilo_timer.start()

    def detener_temporizador(self) -> None:
        self.temporizador_activo = False

    def reiniciar(self) -> None:
        self.detener_temporizador()
        self.estado = self.ESTADO_IDLE
        self.indice_paso = 0
        self.segundos_restantes = self.tiempo_foco
        self.reloj_en_pausa_manual = False
        self.pausas_manuales_sesion = 0
        self.marcas_segundos_descanso = []
        self.pasos_premiados = set()
        self._sesion_guardada = False
        if self.db:
            self.estrellas_totales = self.db.obtener_estrellas()
        if self.hardware:
            self.hardware.apagar_todo()
        self._notificar_ui()

    def _bucle_timer(self) -> None:
        while self.temporizador_activo:
            time.sleep(1.0)
            if not self.temporizador_activo:
                break
            if self.reloj_en_pausa_manual:
                continue

            with self._lock:
                if self.segundos_restantes > 0:
                    self.segundos_restantes -= 1
                    if self.estado == self.ESTADO_EN_PASO:
                        self.segundos_concentracion_sesion += 1
                    self._notificar_ui()
                else:
                    if self.estado == self.ESTADO_EN_PASO:
                        self.estado = self.ESTADO_PAUSA_ACTIVA
                        self.pausas_activas_sesion += 1
                        self.segundos_restantes = self.tiempo_pausa
                        if self.multimodal:
                            self.multimodal.reproducir_sonido_pausa()
                        if self.hardware:
                            self.hardware.activar_pausa()
                        self._hablar(random.choice(self.FRASES_ANIMAR_PAUSA))
                    elif self.estado == self.ESTADO_PAUSA_ACTIVA:
                        self.estado = self.ESTADO_EN_PASO
                        self.segundos_restantes = self.tiempo_foco
                        if self.multimodal:
                            self.multimodal.reproducir_sonido_pausa()
                        if self.hardware:
                            num = self.indice_paso + 1
                            self.hardware.actualizar_progreso(num, len(self.pasos_actuales))
                        self._hablar(random.choice(self.FRASES_RETOMAR_ESTUDIO))
                    self._notificar_ui()

    def _hablar(self, texto: str) -> None:
        self.ultimo_mensaje_hablado = texto
        if self.callback_voz:
            try:
                self.callback_voz(texto)
            except Exception:
                pass

    def obtener_snapshot_ui(self) -> Dict:
        descansos_disp = max(0, self.max_descansos_por_tarea - self.pausas_manuales_sesion)
        return {
            "estado": self.estado,
            "tarea": self.tarea_actual,
            "paso_actual": self.indice_paso + 1 if self.estado != self.ESTADO_IDLE else 0,
            "total_pasos": len(self.pasos_actuales),
            "pasos_lista": list(self.pasos_actuales),
            "texto_paso": (
                self.pasos_actuales[self.indice_paso]
                if self.indice_paso < len(self.pasos_actuales)
                else "¡Misión escolar completada con éxito! 🏆"
            ),
            "pista_paso": (
                self.pistas_actuales[self.indice_paso]
                if self.indice_paso < len(self.pistas_actuales)
                else "¡Lo hiciste genial! Puedes elegir una nueva misión arriba."
            ),
            "segundos_restantes": self.segundos_restantes,
            "minutos": self.segundos_restantes // 60,
            "segundos": self.segundos_restantes % 60,
            "modo_demo": self.modo_demo,
            "reloj_pausado": self.reloj_en_pausa_manual,
            "pausas_manuales": self.pausas_manuales_sesion,
            "descansos_disponibles": descansos_disp,
            "max_descansos": self.max_descansos_por_tarea,
            "intervalo_promedio_descanso": self.calcular_intervalo_promedio_descanso(),
            "estrellas_totales": self.estrellas_totales,
            "estrellas_disponibles": self.db.obtener_estrellas_disponibles() if self.db else self.estrellas_totales,
            "estrellas_sesion": self.estrellas_sesion,
            "paso_ya_premiado": self.indice_paso in self.pasos_premiados,
            "ultimo_mensaje": self.ultimo_mensaje_hablado,
        }

    def _notificar_ui(self) -> None:
        datos = self.obtener_snapshot_ui()
        if self.bus:
            self.bus.emitir("motor_ui", snapshot=datos)
        if self.callback_ui:
            try:
                self.callback_ui(datos)
            except Exception:
                pass
