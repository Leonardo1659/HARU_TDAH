"""
Suite de Auditoría Integral (Seguridad, Economía de Recompensas, Lip-Sync Fonético,
Movimientos Situacionales del Avatar, Anti-Desbordamiento y Precisión de IA)
Proyecto Haru — Universidad Salesiana de Bolivia
"""

import csv
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk

from core.eventos import BusEventosUI
from core.ia.calculadora_ast import evaluar_ast_seguro, resolver_pregunta_matematica
from core.ia.motor_ia import MotorIAHaru, _limpiar_respuesta_ia
from core.motor_tdah import MotorTDAH
from core.repositorio_db import RepositorioTDAH
from core.voz.tts import calcular_visema_fonetico
from hardware.control_leds import ControladorHardwareLEDs
from ui.avatar_sprite import REQUISITOS_SKIN, EscenarioCentralHaru, _renderizar_haru_3d
from ui.karaoke import SubtitulosKaraoke
from ui.modales import ModalAlbumPremios
from ui.panel_docente import PanelDocente
from ui.theme import TEMAS


class TestAuditoriaIntegralHaru(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "auditoria_haru.db")
        self.db = RepositorioTDAH(db_path=self.db_path)
        self.ia = MotorIAHaru(repositorio_db=self.db)
        self.ia.set_modo_privado(True)
        self.hw = ControladorHardwareLEDs(puerto_default="COM_INEXISTENTE")
        self.bus = BusEventosUI()
        self.motor = MotorTDAH(
            callback_voz=lambda _t: None,
            callback_ui=lambda _d: None,
            controlador_hardware=self.hw,
            repositorio_db=self.db,
            motor_ia=self.ia,
            bus_eventos=self.bus,
        )

    def tearDown(self):
        self.motor.detener_temporizador()
        self.hw.cerrar()
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. SISTEMA DE RECOMPENSAS COMPLETO Y ANTI-FARMING
    # =========================================================================
    def test_1_anti_farming_hitos_skins_y_economia_de_fichas(self):
        self.motor.cargar_tarea("Misión Fracciones", ["Paso A", "Paso B", "Paso C"])
        estrellas_ini = self.db.obtener_estrellas()  # 5 iniciales
        self.assertEqual(estrellas_ini, 5)

        self.motor.iniciar_tarea()
        # Paso 0 -> 1 otorga +1 estrella (total = 6)
        self.motor.avanzar_paso()
        self.assertEqual(self.db.obtener_estrellas(), 6)

        # Intentar hacer farming retrocediendo y avanzando varias veces sobre el mismo paso
        for _ in range(4):
            self.motor.retroceder_paso()
            self.motor.avanzar_paso()
        self.assertEqual(
            self.db.obtener_estrellas(),
            6,
            "Retroceder y volver a avanzar el mismo paso NO debe regalar estrellas infinitas.",
        )

        # Completar pasos restantes: Paso 1->2 (+1=7), Paso 2->Fin (+1 + 3 bono = 11)
        self.motor.avanzar_paso()
        self.assertEqual(self.db.obtener_estrellas(), 7)
        self.motor.avanzar_paso()
        self.assertEqual(self.db.obtener_estrellas(), 11)
        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_COMPLETADA)

        # Al cruzar 8 estrellas debe haberse emitido evento logro_desbloqueado (Gatito Espacial)
        eventos = self.bus.extraer_pendientes()
        logros = [ev.datos for ev in eventos if ev.tipo == "logro_desbloqueado"]
        self.assertTrue(
            any(l.get("estrellas") == 8 or l.get("meta") == 8 for l in logros),
            f"Cruzar 8 estrellas debe disparar logro_desbloqueado; recibidos={logros}",
        )

        # Verificar las 4 skins progresivas y sus umbrales (0, 8, 18, 32)
        umbrales = {k: v[0] for k, v in REQUISITOS_SKIN.items()}
        self.assertEqual(
            umbrales,
            {
                "ROBOT_KAWAII": 0,
                "GATITO_ESPACIAL": 8,
                "OSITO_TUTOR": 18,
                "SUPER_HARU_DORADO": 32,
            },
        )

        # Economía de fichas: catálogo escalonado desde 6 ⭐ (alcanzable en la 1.ª misión) hasta 32 ⭐
        catalogo = self.db.listar_recompensas_catalogo()
        self.assertGreaterEqual(len(catalogo), 5)
        self.assertEqual(catalogo[0]["costo_estrellas"], 6)
        premio_10 = next(r for r in catalogo if r["costo_estrellas"] == 10)

        ok, msg, disp = self.db.canjear_recompensa(premio_10["id"])
        self.assertTrue(ok, msg)
        self.assertEqual(disp, 1)  # 11 - 10 = 1 disponible
        self.assertEqual(self.db.obtener_estrellas(), 11)  # XP total intacto para no perder skins

        # Intentar volver a canjear sin saldo suficiente (1 < 6)
        ok2, _msg2, disp2 = self.db.canjear_recompensa(catalogo[0]["id"])
        self.assertFalse(ok2)
        self.assertEqual(disp2, 1)

        canjes = self.db.obtener_historial_canjes()
        self.assertEqual(len(canjes), 1)
        self.assertEqual(canjes[0]["costo_estrellas"], 10)

    def test_2_guardado_sesion_parcial_al_cerrar(self):
        self.motor.cargar_tarea("Tarea Larga", ["P1", "P2", "P3", "P4"])
        self.motor.iniciar_tarea()
        self.motor.segundos_concentracion_sesion = 42
        self.motor.avanzar_paso()
        self.motor.guardar_sesion_parcial_si_aplica()

        sesiones = self.db.obtener_historial_sesiones()
        self.assertEqual(len(sesiones), 1)
        self.assertEqual(sesiones[0]["estado_final"], "PARCIAL")
        self.assertEqual(sesiones[0]["segundos_concentracion"], 42)
        self.assertEqual(sesiones[0]["pasos_completados"], 1)

    # =========================================================================
    # 2. LIP-SYNC FONÉTICO Y 10 MOVIMIENTOS SITUACIONALES DEL AVATAR
    # =========================================================================
    def test_3_visemas_foneticos_y_cierre_en_pausas(self):
        # Simula marcas reales estilo edge-tts con pausa de exclamación de 780 ms en medio
        marcas = [
            {"word": "casa", "offset_ms": 100, "duration_ms": 320},   # vocal dominante 'a' -> visema 1
            {"word": "lobo", "offset_ms": 1200, "duration_ms": 300},  # vocal dominante 'o' -> visema 2
            {"word": "sí", "offset_ms": 1600, "duration_ms": 220},    # vocal 'i' -> visema 3
        ]

        # Antes de empezar a hablar -> boca cerrada (0)
        self.assertEqual(calcular_visema_fonetico(marcas, 0, 20), 0)
        # Pronunciando "casa" -> boca abierta A/E (1)
        self.assertEqual(calcular_visema_fonetico(marcas, 0, 170), 1)
        # En medio del silencio de 780ms entre "casa" (termina 420ms) y "lobo" (inicia 1200ms) -> boca cerrada (0)
        self.assertEqual(calcular_visema_fonetico(marcas, 0, 750), 0)
        # Pronunciando "lobo" -> boca redondeada O/U (2)
        self.assertEqual(calcular_visema_fonetico(marcas, 1, 1260), 2)
        # Pronunciando "sí" -> sonrisa consonántica/I (3)
        self.assertEqual(calcular_visema_fonetico(marcas, 2, 1650), 3)
        # Al terminar toda la frase -> boca cerrada (0)
        self.assertEqual(calcular_visema_fonetico(marcas, 2, 2100), 0)

    def test_4_diez_estados_avatar_cuatro_skins_y_karaoke_matematico(self):
        root = tk.Tk()
        root.withdraw()
        try:
            tema = TEMAS["CALMA"]
            escenario = EscenarioCentralHaru(root, tema=tema)

            # 1) IDLE: boca cerrada en sonrisa tierna (0), NO abierta con lengua
            escenario.actualizar_estado("IDLE")
            escenario.actualizar_habla(False)
            accion, _ojos, boca, brazos, _inc, _dy = escenario.resolver_pose_actual()
            self.assertEqual(accion, "IDLE")
            self.assertEqual(boca, 0)
            self.assertIn(brazos, ("NEUTRO_A", "NEUTRO_B"))

            # Verificar píxel a píxel que boca=0 (reposo) difiere de boca=1 (abierta con lengua coral)
            img_cerrada = _renderizar_haru_3d("ROBOT_KAWAII", "ABIERTO", 0, "NEUTRO_A", 0)
            img_abierta = _renderizar_haru_3d("ROBOT_KAWAII", "ABIERTO", 1, "NEUTRO_A", 0)
            self.assertNotEqual(img_cerrada.tobytes(), img_abierta.tobytes())

            # 2) ESCUCHANDO: mano al oído y boca cerrada atenta (0)
            escenario.actualizar_estado("ESCUCHANDO")
            escenario.actualizar_nivel_mic(0.75)
            _acc, _ojos, boca_esc, brazos_esc, _inc, _dy = escenario.resolver_pose_actual()
            self.assertEqual(boca_esc, 0)
            self.assertEqual(brazos_esc, "ESCUCHANDO_OIDO")

            # 3) PENSANDO: mano al mentón y gesto pensativo (5)
            escenario.actualizar_estado("PENSANDO")
            _acc, _ojos, boca_pen, brazos_pen, _inc, _dy = escenario.resolver_pose_actual()
            self.assertEqual(boca_pen, 5)
            self.assertEqual(brazos_pen, "PENSANDO_MENTON")

            # 4) PASO_LOGRADO: salto + brazos en victoria + sonrisa amplia (4)
            escenario.disparar_reaccion("PASO_LOGRADO", 2.0)
            _acc, _ojos, boca_paso, brazos_paso, _inc, _dy = escenario.resolver_pose_actual()
            self.assertEqual(boca_paso, 4)
            self.assertIn(brazos_paso, ("VICTORIA_A", "VICTORIA_B"))
            escenario._reaccion_restante = 0.0

            # 5) CELEBRANDO mientras habla: mantiene baile de victoria Y mueve la boca según el visema fonético
            escenario.actualizar_estado("CELEBRANDO")
            escenario.actualizar_habla(True, boca=2)
            _acc, _ojos, boca_cel, brazos_cel, _inc, _dy = escenario.resolver_pose_actual()
            self.assertEqual(boca_cel, 2)
            self.assertIn(brazos_cel, ("VICTORIA_A", "VICTORIA_B"))

            # 6) Probar renderizado completo de las 4 skins y los 10 estados sin errores gráficos
            for skin in ("ROBOT_KAWAII", "GATITO_ESPACIAL", "OSITO_TUTOR", "SUPER_HARU_DORADO"):
                escenario.cambiar_skin(skin)
                escenario._reaccion_restante = 0.0
                for estado in (
                    "IDLE", "SALUDANDO", "HABLANDO", "ESCUCHANDO", "PENSANDO",
                    "PASO_LOGRADO", "CELEBRANDO", "RESPIRANDO", "PAUSA", "COSQUILLAS",
                ):
                    escenario._respiracion_restante = 0.0
                    escenario.actualizar_estado(estado)
                    escenario._redibujar()

            escenario.mostrar_banner_logro("👑 ¡Súper Haru Dorado!")
            escenario._redibujar()

            # 7) Karaoke sin desfase ante signos matemáticos
            karaoke = SubtitulosKaraoke(root, tema=tema)
            karaoke.preparar_texto("Suma: 15 + 7 = 22 amigos")
            # Tokens pronunciables indexados por regex: ['suma', '15', '7', '22', 'amigos']
            karaoke.resaltar_palabra(0, "Suma")
            self.assertEqual(karaoke._cursor_busqueda, 0)
            karaoke.resaltar_palabra(1, "15")
            self.assertEqual(karaoke._cursor_busqueda, 1)
            karaoke.resaltar_palabra(2, "7")
            self.assertEqual(karaoke._cursor_busqueda, 2)
            karaoke.resaltar_palabra(3, "22")
            self.assertEqual(karaoke._cursor_busqueda, 3)

            escenario.detener_animacion()
        finally:
            root.destroy()

    # =========================================================================
    # 3. SEGURIDAD RIGUROSA (XSS, CSV INJECTION, AST DOS, .ENV INJECTION, PIN)
    # =========================================================================
    def test_5_seguridad_xss_html_y_csv_formula_injection(self):
        payload_xss = "<script>alert('hack')</script><img src=x onerror=alert(1)>"
        payload_csv = "=CMD|'/C calc'!A0\r\n+HYPERLINK(\"http://evil\")"

        self.db.registrar_sesion(payload_xss, 2, 3, 125, 1, 0, 2, estado_final="PARCIAL")
        self.db.registrar_sesion(payload_csv, 3, 3, 240, 0, 1, 6, estado_final="COMPLETADA")
        self.db.registrar_evento_descanso(payload_csv, 2, 95, motivo=payload_xss)
        self.db.agregar_recompensa_catalogo(payload_xss, 2, payload_csv)
        premio_xss = next(r for r in self.db.listar_recompensas_catalogo() if r["costo_estrellas"] == 2)
        self.db.canjear_recompensa(premio_xss["id"])

        ruta_html = os.path.join(self.temp_dir.name, "informe_seguro.html")
        ruta_csv = os.path.join(self.temp_dir.name, "informe_seguro.csv")
        self.db.exportar_reporte_html(ruta_html)
        self.db.exportar_reporte_csv(ruta_csv)

        contenido_html = Path(ruta_html).read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", contenido_html)
        self.assertNotIn("<img src=x", contenido_html)
        self.assertIn("&lt;script&gt;", contenido_html)
        self.assertIn("table-layout: fixed", contenido_html)
        self.assertIn("overflow-wrap: anywhere", contenido_html)

        with open(ruta_csv, "r", encoding="utf-8-sig", newline="") as f:
            filas = list(csv.reader(f))
        self.assertGreaterEqual(len(filas[0]), 9)
        num_cols = len(filas[0])
        for fila in filas[1:]:
            self.assertEqual(len(fila), num_cols, "Ninguna fila CSV debe romperse por saltos de línea inyectados.")
            celda_mision = fila[1]
            self.assertFalse(
                celda_mision.startswith(("=", "+", "-", "@")),
                f"Celda peligrosa sin neutralizar en CSV: {celda_mision}",
            )

    def test_6_seguridad_ast_dos_potencias_anidadas_y_env_injection(self):
        t0 = time.perf_counter()
        for expr_peligrosa in (
            "((9**8)**8)**8",
            "100000 ** 4",
            "2 ** (3 ** 4)",
            "().__class__.__mro__",
            "__import__('os').listdir('.')",
            "1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+(1+1)))))))))))))))))",
        ):
            with self.assertRaises(ValueError, msg=f"Debió bloquearse: {expr_peligrosa}"):
                evaluar_ast_seguro(expr_peligrosa)
        transcurrido = time.perf_counter() - t0
        self.assertLess(transcurrido, 0.08, "El bloqueo anti-DoS del AST debe ser instantáneo (<80ms).")

        # Verificar sanitización de salto de línea al guardar API Key en un .env temporal aislado
        env_temporal = Path(self.temp_dir.name) / ".env_test"
        env_temporal.write_text("HARU_MODO_PRIVADO=0\n", encoding="utf-8")
        env_previa = os.environ.get("GEMINI_API_KEY", "")
        try:
            with patch("core.ia.motor_ia.ENV_PATH", env_temporal):
                self.ia.configurar_api_key("AQ.ClaveValida123\r\nVARIABLE_INTRUSA=1\n\"comillas\"")
            lineas_env = env_temporal.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lineas_env), 2)
            self.assertFalse(any(l.startswith("VARIABLE_INTRUSA") for l in lineas_env))
            self.assertTrue(any(l.startswith("GEMINI_API_KEY=AQ.ClaveValida123") for l in lineas_env))
        finally:
            if env_previa:
                os.environ["GEMINI_API_KEY"] = env_previa

    # =========================================================================
    # 4. PRECISIÓN DE ENRUTAMIENTO DE IA Y LIMPIEZA DE RESPUESTAS
    # =========================================================================
    def test_7_enrutamiento_ia_sin_falsos_positivos_y_limpieza_markdown(self):
        # Antes "Hola" dentro de una pregunta real secuestraba la consulta e impedía llamar a Gemini
        res_saludo_puro = self.db.buscar_conocimiento("¡Hola Haru!")
        self.assertIsNotNone(res_saludo_puro)

        res_pregunta_con_hola = self.db.buscar_conocimiento("Hola Haru, ¿por qué brillan las estrellas en la noche?")
        self.assertIsNone(
            res_pregunta_con_hola,
            "Una pregunta académica que empieza con 'Hola' NO debe ser interceptada por el saludo fijo.",
        )

        # Pregunta histórica/científica con números o palabra 'por' NO debe disparar la calculadora
        self.assertIsNone(resolver_pregunta_matematica("¿Por qué en 2024 hubo 3 eclipses?"))
        self.assertIsNone(resolver_pregunta_matematica("Explicación paso por paso de los animales"))
        # Operaciones reales sí deben resolverse con precisión
        self.assertIn("56", resolver_pregunta_matematica("¿Cuánto es 7 x 8?") or "")
        self.assertIn("25", resolver_pregunta_matematica("100 dividido entre 4") or "")

        # Limpieza de Markdown para niños y TTS
        texto_sucio = "### ¡Claro!\nLos **planetas** giran alrededor del *Sol* usando `gravedad`."
        limpio = _limpiar_respuesta_ia(texto_sucio)
        self.assertNotIn("**", limpio)
        self.assertNotIn("###", limpio)
        self.assertNotIn("`", limpio)
        self.assertIn("planetas giran alrededor del Sol", limpio)

    # =========================================================================
    # 5. PRUEBA DE ESTRÉS DE INTERFAZ Y ANTI-DESBORDAMIENTO
    # =========================================================================
    def test_8_estres_panel_docente_y_modal_premios_sin_desbordes(self):
        titulo_extremo = "Misión Súper Extensa de Ciencias Naturales sobre Ecosistemas Andinos de Bolivia " * 3
        self.db.guardar_tarea(titulo_extremo[:100], ["Paso largo " * 15], ["Pista larga " * 15])
        for i in range(10):
            self.db.registrar_sesion(f"{i}_{titulo_extremo[:90]}", 3, 4, 95 + i * 35, 1, 0, 5, pausas_manuales=1)
        self.db.sumar_estrellas(15)

        root = ctk.CTk()
        root.withdraw()
        try:
            tema = TEMAS["CALMA"]
            panel = PanelDocente(
                root,
                motor_tdah=self.motor,
                repositorio_db=self.db,
                motor_ia=self.ia,
                controlador_hardware=self.hw,
                motor_voz=None,
                tema=tema,
            )
            panel.withdraw()
            for nombre_tema in ("CALMA", "DIA", "NOCHE"):
                panel.aplicar_tema(TEMAS[nombre_tema]) if hasattr(panel, "aplicar_tema") else None
            for seccion in ("misiones", "progreso", "voz_ia", "seguridad"):
                panel.mostrar_seccion(seccion)
                root.update_idletasks()

            modal = ModalAlbumPremios(
                root,
                estrellas=self.db.obtener_estrellas(),
                tareas_logradas=3,
                tema=tema,
                repositorio_db=self.db,
            )
            modal.withdraw()
            modal._mostrar_tab("logros")
            root.update_idletasks()
            modal._mostrar_tab("tienda")
            root.update_idletasks()

            modal.destroy()
            panel.destroy()
        finally:
            root.destroy()

    # =========================================================================
    # 6. POST-MISIÓN: FESTEJO BREVE -> REPOSO CONVERSACIONAL + POMODORO PERSISTENTE
    # =========================================================================
    def test_9_post_mision_reposo_charla_libre_y_pomodoro_persistente(self):
        # 1) Pomodoro 10m foco / 2m pausa por defecto y persistencia en SQLite
        self.assertEqual(self.motor.tiempo_foco, 10 * 60)
        self.assertEqual(self.motor.tiempo_pausa, 2 * 60)
        self.motor.configurar_tiempos_personalizados(8, 2, 3)
        motor_reabierto = MotorTDAH(repositorio_db=self.db, motor_ia=self.ia)
        self.assertEqual(motor_reabierto.tiempo_foco, 8 * 60)
        self.assertEqual(motor_reabierto.tiempo_pausa, 2 * 60)
        self.assertEqual(motor_reabierto.max_descansos_por_tarea, 3)

        # 2) Al completar la lección, Haru NO queda colgado saltando para siempre:
        #    celebra temporalmente y luego queda en IDLE sereno con el cofre abierto y listo para escuchar/pensar.
        self.motor.cargar_tarea("Misión Corta", ["Único paso"])
        self.motor.iniciar_tarea()
        self.motor.avanzar_paso()
        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_COMPLETADA)

        root = tk.Tk()
        root.withdraw()
        try:
            escenario = EscenarioCentralHaru(root, tema=TEMAS["CALMA"])
            escenario.actualizar_progreso_camino(1, 1, completada=True)
            escenario.disparar_reaccion("CELEBRANDO", 5.5)
            acc_festejo, *_ = escenario.resolver_pose_actual()
            self.assertEqual(acc_festejo, "CELEBRANDO")

            # Simular fin de los 5.5s de festejo -> baja a IDLE sereno con sonrisa cerrada (boca=0)
            escenario._reaccion_restante = 0.0
            escenario.actualizar_habla(False, boca=0)
            escenario.actualizar_estado("IDLE")
            acc_reposo, _ojos, boca_reposo, _brazos, _inc, _dy = escenario.resolver_pose_actual()
            self.assertEqual(acc_reposo, "IDLE")
            self.assertEqual(boca_reposo, 0)
            self.assertTrue(escenario.mision_completada)

            # Si el niño le habla tras terminar, Haru escucha y piensa sin ser bloqueado por mision_completada
            escenario.actualizar_estado("ESCUCHANDO")
            self.assertEqual(escenario.resolver_pose_actual()[0], "ESCUCHANDO")
            escenario.actualizar_estado("PENSANDO")
            self.assertEqual(escenario.resolver_pose_actual()[0], "PENSANDO")
            escenario.detener_animacion()
        finally:
            root.destroy()

        # 3) Conversación libre post-misión (cotidiana + curiosidades + respaldo sin forzar el paso viejo)
        self.ia._ollama_check_ts = 9e12
        self.ia._ollama_modelo_cache = None
        r_cotidiana = self.motor.consultar_ia("¿Cómo estás hoy Haru?")
        self.assertIn("orgulloso", r_cotidiana.lower())
        r_dino = self.motor.consultar_ia("Cuéntame algo de los dinosaurios")
        self.assertIn("sucre", r_dino.lower())
        r_abierta = self.motor.consultar_ia("Hoy jugué fútbol en el recreo con mis amigos")
        self.assertNotIn("hagamos primero este pasito", r_abierta.lower())

    # =========================================================================
    # 7. AUDITORÍA EXHAUSTIVA DE INTERACCIÓN FRONTEND NIÑO + PANEL DOCENTE/FAMILIA
    # =========================================================================
    def test_10_auditoria_exhaustiva_frontend_y_panel_docente(self):
        from core.voz.stt import EscuchaVozHaru
        from core.voz.tts import MotorVozHaru

        # 1) Bug corregido: Reanudar desde PAUSA_ACTIVA NO debe descontar descansos manuales del alumno
        self.motor.cargar_tarea("Misión Pausa", ["Paso A", "Paso B"])
        self.motor.iniciar_tarea()
        self.motor.estado = MotorTDAH.ESTADO_PAUSA_ACTIVA
        self.motor.segundos_restantes = 45
        descansos_antes = self.motor.pausas_manuales_sesion

        pausado, msg_reanuda = self.motor.solicitar_descanso_alumno()
        self.assertFalse(pausado)
        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_EN_PASO)
        self.assertEqual(self.motor.pausas_manuales_sesion, descansos_antes)
        self.assertEqual(self.motor.segundos_restantes, self.motor.tiempo_foco)
        self.assertIn("paso 1", msg_reanuda.lower())

        # Y tampoco debe descontar descansos si ya terminó la misión (ESTADO_COMPLETADA)
        self.motor.avanzar_paso()
        self.motor.avanzar_paso()
        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_COMPLETADA)
        pausado_comp, _ = self.motor.solicitar_descanso_alumno()
        self.assertFalse(pausado_comp)
        self.assertEqual(self.motor.pausas_manuales_sesion, 0)

        # 2) Protección de catálogo: nunca permite quedarse con 0 misiones + restaurar base funciona
        tareas_ini = self.db.listar_tareas()
        self.assertGreaterEqual(len(tareas_ini), 4)
        for t in tareas_ini[:-1]:
            self.assertTrue(self.db.eliminar_tarea(t["nombre"]))
        ultima = self.db.listar_tareas()[0]
        self.assertFalse(self.db.eliminar_tarea(ultima["nombre"]))
        self.assertEqual(len(self.db.listar_tareas()), 1)

        self.db.restaurar_misiones_predeterminadas()
        self.assertGreaterEqual(len(self.db.listar_tareas()), 4)

        # 3) Limpieza de historial de prueba conserva PIN y misiones pero limpia sesiones/canjes
        self.db.cambiar_pin_docente("9876")
        self.db.limpiar_historial_progreso(reiniciar_estrellas=True)
        self.assertEqual(len(self.db.obtener_historial_sesiones()), 0)
        self.assertEqual(self.db.obtener_estrellas(), 5)
        self.assertTrue(self.db.registrar_intento_pin("9876")[0])
        self.assertGreaterEqual(len(self.db.listar_tareas()), 4)

        # 4) Modo Privado Estricto (Ley N.º 548) sincroniza IA + Voz (TTS) + Micrófono (STT) sin enviar audio a red
        voz = MotorVozHaru(bus_eventos=self.bus, silenciado=True)
        stt = EscuchaVozHaru(bus_eventos=self.bus)
        try:
            root = tk.Tk()
            root.withdraw()
            panel = PanelDocente(
                root,
                motor_tdah=self.motor,
                repositorio_db=self.db,
                motor_ia=self.ia,
                controlador_hardware=self.hw,
                motor_voz=voz,
                motor_stt=stt,
                tema=TEMAS["CALMA"],
            )
            panel.withdraw()
            panel.mostrar_seccion("voz_ia")
            panel.sw_privado.select()
            panel._alternar_modo_privado()

            self.assertTrue(self.ia.modo_privado)
            self.assertTrue(voz.forzar_offline)
            self.assertTrue(stt.forzar_modo_privado)

            # En Modo Privado, STT emite fallback local inmediato sin tocar micrófono/nube
            self.bus.extraer_pendientes()
            stt._capturar_y_transcribir()
            eventos = self.bus.extraer_pendientes()
            self.assertTrue(any(e.tipo == "stt_fallback_texto" and "Ley N.º 548" in e.datos.get("motivo", "") for e in eventos))

            panel.cerrar_panel()
            root.destroy()
        finally:
            voz.cerrar()


if __name__ == "__main__":
    unittest.main()
