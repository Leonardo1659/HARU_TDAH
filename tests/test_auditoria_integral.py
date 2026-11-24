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
from core.semaforo_visual import ControladorHardwareLEDs, ControladorSemaforoVisual
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

            # Verificar escalado dinámico en pantalla completa (Haru crece más del doble en 1080p)
            alto_ventana, esc_ventana = escenario._calcular_escala_escenario(480, 310)
            alto_full, esc_full = escenario._calcular_escala_escenario(1200, 680)
            self.assertGreater(alto_full, alto_ventana + 150)
            self.assertGreater(esc_full, 1.8)
            img_full = _renderizar_haru_3d("ROBOT_KAWAII", "FELIZ", 0, "NEUTRO_A", 0, alto_px=alto_full)
            self.assertEqual(img_full.size[1], alto_full)
            self.assertGreater(img_full.size[0], 450)

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

    # =========================================================================
    # 7. OPCIÓN B (COMPROBACIÓN ACTIVA) E ÍCONOS VECTORIALES 100% OFFLINE
    # =========================================================================
    def test_11_comprobacion_activa_opcion_b_e_iconos_vectoriales_offline(self):
        from core.comprobacion_activa import generar_reto_paso, validar_respuesta_reto
        from ui.iconos import icono_ctk, icono_skin_ctk, svg_icono_html
        from ui.modales import ModalComprobacionPaso

        # 1) Reto matemático contextual (acepta dígitos, palabras en voz alta y total de misión)
        contexto_mate = [
            "Escribe la suma: 15 + 7.",
            "Suma primero las unidades (5 más 7) y escribe el resultado.",
        ]
        reto_mate = generar_reto_paso(contexto_mate[1], 2, "Misión de Matemáticas", contexto_mate)
        self.assertEqual(reto_mate["tipo"], "matematica")
        self.assertTrue(validar_respuesta_reto(reto_mate, "12")[0])
        self.assertTrue(validar_respuesta_reto(reto_mate, "me salió doce")[0])
        self.assertTrue(validar_respuesta_reto(reto_mate, "veintidós")[0])
        self.assertFalse(validar_respuesta_reto(reto_mate, "99")[0])
        self.assertFalse(validar_respuesta_reto(reto_mate, "todavía no")[0])

        # 2) Reto de colores, materiales escolares y lectura en voz alta
        reto_color = generar_reto_paso("Prepara tus colores azul, amarillo y verde.", 1)
        self.assertTrue(validar_respuesta_reto(reto_color, "azul")[0])
        self.assertFalse(validar_respuesta_reto(reto_color, "gris")[0])

        reto_mat = generar_reto_paso("Saca tu cuaderno y tu lápiz sobre la mesa.", 1)
        self.assertTrue(validar_respuesta_reto(reto_mat, "Mi cuaderno")[0])
        self.assertFalse(validar_respuesta_reto(reto_mat, "El control de la tele")[0])

        reto_lec = generar_reto_paso("Lee en voz alta el primer párrafo del cuento.", 2)
        self.assertTrue(validar_respuesta_reto(reto_lec, "el gatito valiente")[0])
        self.assertFalse(validar_respuesta_reto(reto_lec, "Me salté la lectura")[0])

        # 3) MotorTDAH bloquea avance sin verificar y recuerda pasos ya verificados
        self.motor.cargar_tarea("Misión Verificada", contexto_mate)
        self.motor.iniciar_tarea()
        self.assertTrue(self.motor.comprobacion_activa)
        self.assertTrue(self.motor.requiere_comprobacion_paso())

        # Desactivar y reactivar persiste en SQLite
        self.motor.set_comprobacion_activa(False)
        self.assertFalse(self.motor.requiere_comprobacion_paso())
        self.assertEqual(self.db.obtener_preferencia("comprobacion_activa"), "0")
        self.motor.set_comprobacion_activa(True)
        self.assertTrue(self.motor.requiere_comprobacion_paso())

        # Una vez superado el paso 0, si el niño retrocede no vuelve a pedir comprobación repetida
        self.motor.avanzar_paso()
        self.motor.retroceder_paso()
        self.assertFalse(self.motor.requiere_comprobacion_paso())

        # 4) ModalComprobacionPaso responde a voz y botones + íconos vectoriales offline y HTML limpio
        root = tk.Tk()
        root.withdraw()
        try:
            paso_confirmado = {"ok": False}
            reto_modal = self.motor.generar_reto_comprobacion_actual()
            modal = ModalComprobacionPaso(
                root,
                reto=reto_modal,
                numero_paso=1,
                tema=TEMAS["CALMA"],
                validador=self.motor.validar_comprobacion_actual,
                on_superado=lambda: paso_confirmado.__setitem__("ok", True),
            )
            modal.withdraw()
            # Respuesta incorrecta no cierra ni avanza
            modal.recibir_respuesta_voz("Todavía no lo copié")
            self.assertFalse(paso_confirmado["ok"])
            # Respuesta correcta por voz confirma
            modal.recibir_respuesta_voz("15 + 7")
            if modal.winfo_exists():
                modal._finalizar_exito()
            self.assertTrue(paso_confirmado["ok"])

            # Íconos vectoriales PIL y retratos 3D de skins cargan 100% offline
            for nombre_ico in ("chart", "clipboard", "mic", "shield", "star", "trophy", "check", "printer"):
                self.assertIsNotNone(icono_ctk(nombre_ico, "#246A73", 20))
            for sk in ("ROBOT_KAWAII", "GATITO_ESPACIAL", "OSITO_TUTOR", "SUPER_HARU_DORADO"):
                self.assertIsNotNone(icono_skin_ctk(sk, bloqueado=True, size=24))
        finally:
            root.destroy()

        # 5) Reporte HTML usa <svg> vectorial offline (incluyendo gráfico de barras + nodos) y cero emojis de WhatsApp
        ruta_html = os.path.join(self.temp_dir.name, "reporte_vectorial.html")
        self.db.exportar_reporte_html(ruta_html)
        html_txt = Path(ruta_html).read_text(encoding="utf-8")
        self.assertIn("<svg", html_txt)
        self.assertIn("<polyline", html_txt)
        self.assertGreaterEqual(html_txt.count("<svg"), 7)
        for emoji_informal in ("📊", "⭐", "🎯", "☕", "🎁", "✅", "⏱️"):
            self.assertNotIn(emoji_informal, html_txt)

    # =========================================================================
    # 8. 5 MÓDULOS CURRICULARES, AUTO-CLASIFICACIÓN, GUÍAS MIXTAS Y PENSUM
    # =========================================================================
    def test_12_modulos_autoclasificacion_documentos_mixtos_pensum_y_voz_docente(self):
        from core.archivos_estudio import cargar_archivo_estudio
        from core.comprobacion_activa import generar_reto_paso, validar_respuesta_reto
        from ui.modales import ModalAprobadorTareasDocumento

        # 1) Existen los 5 Módulos Curriculares oficiales y la misión de Inglés base
        tareas_ini = self.db.listar_tareas()
        self.assertGreaterEqual(len(tareas_ini), 5)
        ingles_tareas = self.db.listar_tareas_por_modulo("Inglés")
        self.assertGreaterEqual(len(ingles_tareas), 1)
        self.assertEqual(ingles_tareas[0]["nombre"], "Inglés - Jugando con Palabras")

        # 2) Comprobación activa bilingüe para pasos de Inglés (BLUE, CAT, One Two Three)
        pasos_ing = ingles_tareas[0]["pasos"]
        reto_blue = generar_reto_paso(pasos_ing[1], 2, "Inglés - Jugando con Palabras")
        self.assertEqual(reto_blue["tipo"], "ingles")
        self.assertTrue(validar_respuesta_reto(reto_blue, "BLUE")[0])
        self.assertTrue(validar_respuesta_reto(reto_blue, "azul")[0])

        reto_cat = generar_reto_paso(pasos_ing[2], 3, "Inglés - Jugando con Palabras")
        self.assertEqual(reto_cat["tipo"], "ingles")
        self.assertTrue(validar_respuesta_reto(reto_cat, "CAT")[0])

        reto_count = generar_reto_paso(pasos_ing[3], 4, "Inglés - Jugando con Palabras")
        self.assertEqual(reto_count["tipo"], "ingles")
        self.assertTrue(validar_respuesta_reto(reto_count, "One, Two, Three")[0])

        # 3) Auto-clasificación inteligente de módulo por texto/voz/archivo
        self.assertEqual(self.ia.detectar_modulo_automatico("Sumas y restas llevando 24 + 18"), "Matemáticas")
        self.assertEqual(self.ia.detectar_modulo_automatico("Colors in English: BLUE, RED and CAT"), "Inglés")
        self.assertEqual(self.ia.detectar_modulo_automatico("El ciclo del agua y las plantas"), "Ciencias")
        self.assertEqual(self.ia.detectar_modulo_automatico("Lectura de cuento: verbos y sustantivos"), "Lenguaje")
        self.assertEqual(self.ia.detectar_modulo_automatico("Ordenar mi mochila y mi estuche"), "Hábitos y Orden")

        # 4) Ingesta de documento escolar MIXTO (Matemáticas + Inglés en un mismo archivo)
        ruta_guia = os.path.join(self.temp_dir.name, "guia_escolar_mixta.md")
        contenido_mixto = (
            "# Tema 1: Sumas y Restas de Dos Cifras\n"
            "Resuelve en tu cuaderno de matemáticas las operaciones 18 + 14 y 35 - 12 alineando decenas y unidades.\n\n"
            "# Tema 2: English Vocabulary Colors and Animals\n"
            "Practice in English the colors BLUE, RED, GREEN and animals CAT and DOG repeating aloud.\n"
        )
        Path(ruta_guia).write_text(contenido_mixto, encoding="utf-8")

        doc = cargar_archivo_estudio(ruta_guia)
        self.assertTrue(doc.exito)
        propuestas = self.ia.extraer_tareas_de_documento(doc)
        self.assertGreaterEqual(len(propuestas), 2)
        categorias_detectadas = {p["categoria"] for p in propuestas}
        self.assertIn("Matemáticas", categorias_detectadas)
        self.assertIn("Inglés", categorias_detectadas)

        # 5) Panel Docente procesa archivo, guarda Pensum, aprueba en lote y filtra por módulo
        root = tk.Tk()
        root.withdraw()
        try:
            panel = PanelDocente(
                root,
                motor_tdah=self.motor,
                repositorio_db=self.db,
                motor_ia=self.ia,
                controlador_hardware=self.hw,
                tema=TEMAS["CALMA"],
            )
            panel.withdraw()
            self.assertTrue(hasattr(panel, "btn_dictar_ia"))
            self.assertTrue(hasattr(panel, "btn_subir_archivo"))

            lote = panel.procesar_archivo_pensum(ruta_guia, abrir_modal=False)
            self.assertGreaterEqual(len(lote), 2)
            self.assertIsNotNone(self.db.obtener_pensum_modulo("Matemáticas"))
            self.assertIsNotNone(self.db.obtener_pensum_modulo("Inglés"))

            # Probar aprobación en lote ("Subir Todas de Golpe") desde ModalAprobadorTareasDocumento
            importadas = {"n": 0}
            modal_doc = ModalAprobadorTareasDocumento(
                panel,
                nombre_archivo=doc.nombre_archivo,
                tareas_propuestas=lote,
                tema=TEMAS["CALMA"],
                on_aprobar_lote=lambda lista: importadas.__setitem__(
                    "n", self.db.guardar_lote_tareas(lista)
                ),
            )
            modal_doc.withdraw()
            modal_doc._confirmar_importacion(forzar_todas=True)
            self.assertGreaterEqual(importadas["n"], 2)

            # Verificar que cada tarea fue a su módulo correspondiente sin mezclarse
            tareas_mate = self.db.listar_tareas_por_modulo("Matemáticas")
            tareas_ing = self.db.listar_tareas_por_modulo("Inglés")
            self.assertGreaterEqual(len(tareas_mate), 2)
            self.assertGreaterEqual(len(tareas_ing), 2)

            # Progreso por módulo se actualiza al completar una misión
            self.motor.cargar_tarea(ingles_tareas[0]["nombre"], ingles_tareas[0]["pasos"], ingles_tareas[0]["pistas"])
            self.motor.iniciar_tarea()
            self.motor.completar_tarea()
            prog = self.db.obtener_progreso_modulos()
            self.assertGreaterEqual(prog["Inglés"][0], 1)

            # Nudge de retención de atención emite evento no punitivo
            self.bus.extraer_pendientes()
            msg_nudge = self.motor.disparar_nudge_retencion()
            self.assertIn("paso", msg_nudge.lower())
            evs = self.bus.extraer_pendientes()
            self.assertTrue(any(e.tipo == "nudge_atencion" for e in evs))

            # Verificar normalización relacional 3FN, FKs reales y bitácora de auditoría
            with self.db._conectar() as conn:
                cur = conn.cursor()
                for tabla_fk in (
                    "tareas",
                    "pasos_tarea",
                    "sesiones_estudio",
                    "bitacora_descansos",
                    "historial_canjes",
                    "pensum_modulos",
                    "conocimiento_escolar",
                ):
                    cur.execute(f"PRAGMA foreign_key_list({tabla_fk})")
                    self.assertGreaterEqual(len(cur.fetchall()), 1, f"Falta FK en {tabla_fk}")
                cur.execute("SELECT COUNT(*) AS c FROM pasos_tarea")
                self.assertGreaterEqual(cur.fetchone()["c"], 15)
            eventos_aud = self.db.obtener_auditoria_eventos(limite=20)
            self.assertGreaterEqual(len(eventos_aud), 2)

            panel.cerrar_panel()
        finally:
            root.destroy()

    def test_13_razonamiento_guardian_documentos_y_comprobacion_progresiva(self):
        from core.comprobacion_activa import generar_reto_paso, validar_respuesta_reto

        self.ia._ollama_check_ts = 9e12
        self.ia._ollama_modelo_cache = None

        # 1) Filtro Guardián Infantil bloquea temas no aptos o videojuegos comerciales
        r_juego = self.ia.responder_consulta_escolar("¿Cómo mejorar en freefire y dar headshot?", "Matemáticas", "")
        self.assertEqual(self.ia.ultima_fuente, "Filtro Guardián Infantil")
        self.assertIn("estudio", r_juego.lower())

        r_romance = self.ia.responder_consulta_escolar("¿Cómo puedo tener novia en el colegio?", "Lenguaje", "")
        self.assertEqual(self.ia.ultima_fuente, "Filtro Guardián Infantil")
        self.assertIn("primaria", r_romance.lower())

        # 2) Consultas cotidianas útiles (hora actual y técnicas de estudio)
        r_hora = self.ia.responder_consulta_escolar("Haru, ¿qué hora es?")
        self.assertRegex(r_hora, r"\d{2}:\d{2}")

        r_estudio = self.ia.responder_consulta_escolar("¿Cómo puedo mejorar en mis estudios y concentrarme?")
        self.assertIn("10 minutos", r_estudio.lower())

        # 3) Resolución real de ejercicio específico dentro de archivo del alumno
        guia_alumno = (
            "Práctica de Matemáticas\n"
            "Ejercicio 1: Calcula 14 + 5 en tu cuaderno.\n"
            "Ejercicio 2: Resuelve 24 + 18 alineando unidades y decenas.\n"
        )
        r_doc = self.ia.responder_sobre_documento(
            guia_alumno,
            pregunta="ayúdame con el ejercicio 2",
            nombre_doc="practica.txt",
        )
        self.assertIn("42", r_doc)
        self.assertIn("24 + 18", r_doc)

        # 4) Descomposición concreta de tareas sin relleno genérico
        pasos_frac, _pistas_frac = self.ia.descomponer_tarea_ia("Fracciones homogéneas")
        self.assertEqual(len(pasos_frac), 4)
        self.assertFalse(any("primera parte" in p.lower() for p in pasos_frac))

        # 5) Comprobación activa sin botones triviales y con rechazo de confirmaciones vacías
        reto_custom = generar_reto_paso("Dibuja un esquema sobre la fotosíntesis en tu cuaderno.", 3, "Ciencias", ["Saca tu cuaderno", "Lee sobre las plantas"], total_pasos=3)
        self.assertFalse(any("completé el paso" in op.lower() for op in reto_custom["opciones"]))
        for intento_vacio in ("completé el ejercicio", "sí", "listo", "hola", "asdfg", "ya terminé todo el paso"):
            ok_v, _msg_v = validar_respuesta_reto(reto_custom, intento_vacio)
            self.assertFalse(ok_v, f"Debió rechazar '{intento_vacio}'")

        # En Paso 3 tras copiar 15 + 7, exige cálculo total del cuaderno (22)
        reto_paso3 = generar_reto_paso(
            "Suma primero las unidades y luego la decena en tu cuaderno.",
            3,
            "Matemáticas - Sumas Divertidas",
            ["Saca tu cuaderno.", "Escribe la suma: 15 + 7."],
            total_pasos=3,
        )
        self.assertEqual(reto_paso3["respuesta_principal"], "22")
        self.assertTrue(validar_respuesta_reto(reto_paso3, "22")[0])
        self.assertFalse(validar_respuesta_reto(reto_paso3, "completé el ejercicio")[0])

        # 6) Lip-Sync: si TTS empieza mientras el avatar estaba en PENSANDO, prevalece el movimiento labial
        root = tk.Tk()
        root.withdraw()
        try:
            escenario = EscenarioCentralHaru(root, tema=TEMAS["CALMA"])
            escenario.actualizar_estado("PENSANDO")
            escenario.actualizar_habla(True, boca=2)
            accion_h, _oj, boca_h, *_ = escenario.resolver_pose_actual()
            self.assertEqual(accion_h, "HABLANDO")
            self.assertEqual(boca_h, 2)
            escenario.detener_animacion()
        finally:
            root.destroy()

    # =========================================================================
    # 9. R1: SEMÁFORO VISUAL NATIVO, PERFIL PEDAGÓGICO E INACTIVIDAD CONFIGURABLE
    # =========================================================================
    def test_14_r1_semaforo_visual_perfil_pedagogico_e_inactividad_panel_docente(self):
        import contextlib
        import io
        from hardware.control_leds import ControladorHardwareLEDs as LegacyHardwareLEDs

        # 1) Reubicación a core/semaforo_visual.py, alias legado y ausencia de carpeta hardware/
        self.assertIs(ControladorHardwareLEDs, ControladorSemaforoVisual)
        self.assertIs(LegacyHardwareLEDs, ControladorSemaforoVisual)
        raiz_repo = Path(__file__).resolve().parent.parent
        self.assertFalse(
            (raiz_repo / "hardware").exists(),
            "El directorio legado 'hardware/' no debe existir en el repositorio.",
        )

        # 2) Cero salida de consola '[Hardware] No se detectó placa Arduino'
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            sem = ControladorSemaforoVisual()
            self.assertTrue(sem.en_simulacion)
            self.assertEqual(sem.puerto_actual, "Guía Visual")
            self.assertEqual(sem.listar_puertos_disponibles(), [])
            sem.actualizar_progreso(1, 3)
            self.assertEqual(sem.estado_leds, [True, False, False])
            sem.actualizar_progreso(2, 3)
            self.assertEqual(sem.estado_leds, [True, True, False])
            sem.celebrar_victoria()
            self.assertEqual(sem.estado_leds, [True, True, True])
            sem.apagar_todo()
            self.assertEqual(sem.estado_leds, [False, False, False])
        self.assertNotIn("No se detectó placa Arduino", buf_out.getvalue() + buf_err.getvalue())

        # 3) Panel Docente Pestaña 4 ("4. Seguridad y Perfil"), Perfil Pedagógico y Aviso de Inactividad
        root = tk.Tk()
        root.withdraw()
        try:
            panel = PanelDocente(
                root,
                motor_tdah=self.motor,
                repositorio_db=self.db,
                motor_ia=self.ia,
                controlador_hardware=self.hw,
                tema=TEMAS["CALMA"],
            )
            panel.withdraw()

            # Verificar pestaña 4 renombrada y sin combo_com de Arduino
            self.assertEqual(panel._botones_nav["seguridad"].cget("text").strip(), "4. Seguridad y Perfil")
            panel.mostrar_seccion("seguridad")
            root.update_idletasks()
            self.assertFalse(hasattr(panel, "combo_com"))
            self.assertTrue(hasattr(panel, "ent_nombre_estudiante"))
            self.assertTrue(hasattr(panel, "combo_grado_primaria"))
            self.assertTrue(hasattr(panel, "btn_guardar_perfil_estudiante"))

            # Guardar Perfil Pedagógico del Estudiante
            panel.ent_nombre_estudiante.delete(0, "end")
            panel.ent_nombre_estudiante.insert(0, "Mateo")
            panel.combo_grado_primaria.set("2.° de Primaria")
            panel._guardar_perfil_estudiante()

            self.assertEqual(self.db.obtener_preferencia("nombre_estudiante"), "Mateo")
            self.assertEqual(self.db.obtener_preferencia("grado_primaria"), "2.° de Primaria")
            self.assertEqual(self.ia.nombre_estudiante, "Mateo")
            self.assertEqual(self.ia.grado_primaria, "2.° de Primaria")

            # Botones de prueba en vivo del Semáforo Visual (Inicio, Avance, Meta, Apagar)
            self.assertEqual(set(panel.botones_semaforo_visual.keys()), {"Inicio", "Avance", "Meta", "Apagar"})
            panel.botones_semaforo_visual["Inicio"].invoke()
            self.assertEqual(self.hw.estado_leds, [True, False, False])
            panel.botones_semaforo_visual["Avance"].invoke()
            self.assertEqual(self.hw.estado_leds, [True, True, False])
            panel.botones_semaforo_visual["Meta"].invoke()
            self.assertEqual(self.hw.estado_leds, [True, True, True])
            panel.botones_semaforo_visual["Apagar"].invoke()
            self.assertEqual(self.hw.estado_leds, [False, False, False])

            # Pestaña 3 ("voz_ia"): Aviso Inactividad (min) configurable y persistente
            panel.mostrar_seccion("voz_ia")
            root.update_idletasks()
            self.assertTrue(hasattr(panel, "ent_inactividad"))
            panel.ent_foco.delete(0, "end")
            panel.ent_foco.insert(0, "12")
            panel.ent_pausa.delete(0, "end")
            panel.ent_pausa.insert(0, "3")
            panel.ent_max_desc.delete(0, "end")
            panel.ent_max_desc.insert(0, "4")
            panel.ent_inactividad.delete(0, "end")
            panel.ent_inactividad.insert(0, "5")
            panel._aplicar_tiempos()

            self.assertEqual(self.motor.tiempo_foco, 12 * 60)
            self.assertEqual(self.motor.tiempo_pausa, 3 * 60)
            self.assertEqual(self.motor.max_descansos_por_tarea, 4)
            self.assertEqual(self.motor.umbral_inactividad_seg, 5 * 60)
            self.assertEqual(self.db.obtener_preferencia("min_inactividad_nudge"), "5")

            # Preset Pomodoro también restaura aviso de inactividad (por defecto 3 min)
            panel._cargar_preset_pomodoro(10, 2, 2, "Equilibrado")
            self.assertEqual(self.motor.umbral_inactividad_seg, 3 * 60)
            self.assertEqual(self.db.obtener_preferencia("min_inactividad_nudge"), "3")

            panel.cerrar_panel()
        finally:
            root.destroy()

    # =========================================================================
    # 10. R2: CALCULADORA ARITMÉTICA SEGURA AST (PALABRAS, PROBLEMAS Y GUARDAS)
    # =========================================================================
    def test_15_r2_calculadora_ast_palabras_decimales_problemas_verbales_y_guardas(self):
        # 1) Números en palabras hasta 999,999 (centenas y miles)
        self.assertIn("120", resolver_pregunta_matematica("¿Cuánto es cien más veinte?") or "")
        self.assertIn("325", resolver_pregunta_matematica("¿Cuánto es ciento veinte más doscientos cinco?") or "")
        self.assertIn("1500", resolver_pregunta_matematica("¿Cuánto es mil más quinientos?") or "")
        self.assertIn("2500", resolver_pregunta_matematica("¿Cuánto es dos mil más quinientos?") or "")
        self.assertIn("100000", resolver_pregunta_matematica("¿Cuánto es cincuenta mil por dos?") or "")

        # 2) Decimales con coma/punto, negativos, potencias, porcentajes y operadores prefijo anidados
        self.assertIn("6", resolver_pregunta_matematica("¿Cuánto es 3,5 más 2,5?") or "")
        self.assertIn("-2", resolver_pregunta_matematica("Calcula -5 + 3") or "")
        self.assertIn("25", resolver_pregunta_matematica("¿Cuánto es 5 al cuadrado?") or "")
        self.assertIn("8", resolver_pregunta_matematica("¿Cuánto es 2 al cubo?") or "")
        self.assertIn("81", resolver_pregunta_matematica("¿Cuánto es 3 elevado a 4?") or "")
        self.assertIn("30", resolver_pregunta_matematica("¿Cuánto es el 20% de 150?") or "")
        self.assertIn("40", resolver_pregunta_matematica("¿Cuánto es 50 por ciento de 80?") or "")
        self.assertIn("0.5", resolver_pregunta_matematica("Calcula 20% + 30%") or "")
        self.assertIn("2", resolver_pregunta_matematica("¿Cuánto es la mitad de la mitad de 8?") or "")
        self.assertIn("14", resolver_pregunta_matematica("¿Cuánto es el doble de (3 + 4)?") or "")
        self.assertIn("300", resolver_pregunta_matematica("¿Cuánto es el triple de 10 al cuadrado?") or "")
        self.assertIn("14", resolver_pregunta_matematica("Calcula 2(3 + 4)") or "")
        self.assertIn("25", resolver_pregunta_matematica("Calcula (2 + 3)(4 + 1)") or "")

        # 3) Problemas verbales de primaria (suma, resta, multiplicación, reparto)
        self.assertIn("17", resolver_pregunta_matematica("Tenía 12 manzanas y me regalaron 5, ¿cuántas tengo en total?") or "")
        self.assertIn("14", resolver_pregunta_matematica("Tenía 20 caramelos y regalé 6, ¿cuántos quedan?") or "")
        self.assertIn("24", resolver_pregunta_matematica("Compré 4 cajas con 6 colores cada caja, ¿cuántos hay?") or "")
        self.assertIn("4", resolver_pregunta_matematica("Repartí 24 galletas entre 6 amigos en partes iguales") or "")

        # 4) Guardas contra falsos positivos (conceptuales, narrativos, fechas, ecuaciones, variables)
        for no_calculo in (
            "¿Qué es una fracción como 1/2?",
            "¿Por qué 2 + 2 es 4?",
            "¿Cuál es la diferencia entre 1/2 y 1/4?",
            "¿Cuántos cuartos hay en 1/2?",
            "Dibuja 1/2 de un círculo en tu hoja",
            "Necesito 3/4 de taza de harina para la receta",
            "Tengo un 15% de descuento en la tienda",
            "El 12-10-2026 estudiamos la gestión 2024-2025",
            "Lee las páginas 10-15 del libro",
            "¿Es verdad que 2 + 2 = 4?",
            "1 + 2 = 3",
            "Resuelve 1 + 2 + x",
            "Calcula sin(3 + 4)",
        ):
            self.assertIsNone(
                resolver_pregunta_matematica(no_calculo),
                f"No debió interceptarse como cálculo directo: {no_calculo}",
            )

        # 5) Mensajes pedagógicos amigables ante división por cero, fuera de rango y dominio no real
        r_cero = resolver_pregunta_matematica("¿Cuánto es 15 dividido entre 0?") or ""
        self.assertIn("dividir entre cero", r_cero.lower())

        r_rango = resolver_pregunta_matematica("¿Cuánto es 10 elevado a 12?") or ""
        self.assertIn("rango seguro de primaria", r_rango.lower())

        r_complejo = resolver_pregunta_matematica("Calcula (-4) ** 0.5") or ""
        self.assertIn("números reales", r_complejo.lower())

    # =========================================================================
    # 11. R3: MOTOR IA (PERFIL, MULTI-TURNO, EMPATÍA, ORTOGRAFÍA, GUARDIÁN, DOCS)
    # =========================================================================
    def test_16_r3_motor_ia_perfil_memoria_multiturno_empatia_ortografia_guardian_y_documentos(self):
        self.ia._ollama_check_ts = 9e12
        self.ia._ollama_modelo_cache = None

        # 1) Adaptación al Perfil Pedagógico (nombre_estudiante, grado_primaria)
        self.ia.actualizar_perfil_estudiante("Lucía", "1.° de Primaria")
        perfil = self.ia.recargar_perfil_estudiante()
        self.assertEqual(perfil["nombre_estudiante"], "Lucía")
        self.assertEqual(perfil["grado_primaria"], "1.° de Primaria")
        self.assertEqual(perfil["nombre"], "Lucía")
        self.assertEqual(perfil["grado"], "1.° de Primaria")

        sys_prompt_1 = self.ia._construir_system_prompt()
        self.assertIn("Lucía", sys_prompt_1)
        self.assertIn("1.° de Primaria", sys_prompt_1)
        self.assertIn("6 a 7 años", sys_prompt_1)

        r_saludo = self.ia.responder_consulta_escolar("¡Hola!")
        self.assertIn("Lucía", r_saludo)
        r_ciencias_1 = self.ia.responder_consulta_escolar("fotosíntesis")
        self.assertIn("Lucía", r_ciencias_1)
        self.assertIn("1.° de Primaria", r_ciencias_1)

        self.ia.actualizar_perfil_estudiante("Mateo", "6.° de Primaria")
        sys_prompt_6 = self.ia._construir_system_prompt()
        self.assertIn("Mateo", sys_prompt_6)
        self.assertIn("6.° de Primaria", sys_prompt_6)
        self.assertIn("10 a 11 años", sys_prompt_6)
        r_ciencias_6 = self.ia.responder_consulta_escolar("fotosíntesis")
        self.assertIn("6.° de Primaria", r_ciencias_6)

        # Limpiar perfil para las siguientes pruebas
        self.ia.actualizar_perfil_estudiante("", "")

        # 2) Memoria conversacional multi-turno (_historial_chat, seguimiento matemático y reformulación)
        self.ia._historial_chat.clear()
        self.ia._ultimo_resultado_num = None

        r_m1 = self.ia.responder_consulta_escolar("¿Cuánto es 10 + 5?")
        self.assertIn("15", r_m1)
        self.assertEqual(self.ia._historial_chat[-1][2], 15)

        r_m2 = self.ia.responder_consulta_escolar("¿y si le sumo 2?")
        self.assertIn("17", r_m2)
        self.assertEqual(self.ia._historial_chat[-1][2], 17)

        r_m3 = self.ia.responder_consulta_escolar("¿y más 5?")
        self.assertIn("22", r_m3)
        self.assertEqual(self.ia._historial_chat[-1][2], 22)

        r_m4 = self.ia.responder_consulta_escolar("¿y la mitad?")
        self.assertIn("11", r_m4)
        self.assertEqual(self.ia._historial_chat[-1][2], 11)

        r_reform = self.ia.responder_consulta_escolar("no entendí, explícame otra vez")
        self.assertEqual(self.ia.ultima_fuente, "Andamiaje Multi-Turno Haru")
        self.assertIn("11", r_reform)

        # 3) Detección prioritaria de negaciones y empatía emocional (sin exigir 'como' o 'consejo')
        for frase_emocional in (
            "no estoy feliz",
            "me fue mal",
            "estoy triste",
            "soy tonto",
            "no me sale",
            "estoy frustrado",
            "no puedo",
        ):
            resp_emo = self.ia.responder_consulta_escolar(frase_emocional)
            self.assertEqual(
                self.ia.ultima_fuente,
                "Apoyo Emocional Haru",
                f"Falló detección emocional prioritaria para: {frase_emocional}",
            )
            self.assertNotIn("celebramos nuestros logros", resp_emo.lower())

        # En SQLite, 'no estoy feliz' jamás debe devolver la respuesta positiva de 'feliz'
        resp_db_no_feliz = self.db.buscar_conocimiento("no estoy feliz") or ""
        self.assertIn("no sentirse feliz", resp_db_no_feliz.lower())
        self.assertIsNone(self.db.buscar_conocimiento("no quiero un chiste"))

        # 4) Ortografía y jerga infantil (_normalizar_ortografia_infantil)
        norm_fn = self.ia._normalizar_ortografia_infantil
        self.assertEqual(norm_fn("q ora es"), "que hora es")
        self.assertEqual(norm_fn("ola"), "hola")
        self.assertEqual(norm_fn("berbo"), "verbo")
        self.assertEqual(norm_fn("fotosintecis"), "fotosintesis")
        self.assertEqual(norm_fn("fracion"), "fraccion")
        self.assertEqual(norm_fn("xfa"), "por favor")
        self.assertEqual(norm_fn("xq"), "porque")

        self.assertRegex(self.ia.responder_consulta_escolar("q ora es xfa"), r"\d{2}:\d{2}")
        self.assertIn("acción", self.ia.responder_consulta_escolar("berbo").lower())

        # 5) Filtro Guardián contextual (permite consultas académicas, protege en bullying y bloquea evasiones)
        for consulta_academica_legitima in (
            "reproducción sexual y asexual de las plantas",
            "cuento del beso a la rana",
            "ligar sílabas",
            "pelearon por la independencia",
            "efectos del alcohol en el cuerpo humano",
            "cómo evitar distraerme con TikTok o Roblox mientras estudio",
        ):
            resp_leg = self.ia.responder_consulta_escolar(consulta_academica_legitima)
            self.assertNotEqual(
                self.ia.ultima_fuente,
                "Filtro Guardián Infantil",
                f"No debió bloquear consulta legítima: {consulta_academica_legitima}",
            )
            self.assertTrue(len(resp_leg) > 20)

        for reporte_bullying in (
            "me quieren golpear en el recreo",
            "me pegan en el colegio",
            "me hacen bullying",
        ):
            resp_prot = self.ia.responder_consulta_escolar(reporte_bullying)
            self.assertEqual(self.ia.ultima_fuente, "Protocolo de Protección Infantil")
            self.assertTrue(
                any(w in resp_prot.lower() for w in ("profesor", "familia", "adulto", "mamá", "papá")),
                f"Falta orientación protectora en: {resp_prot}",
            )

        for evasion_inapropiada in ("fr33 fir3", "n o v i a", "f r e e f i r e"):
            _ = self.ia.responder_consulta_escolar(evasion_inapropiada)
            self.assertEqual(
                self.ia.ultima_fuente,
                "Filtro Guardián Infantil",
                f"Debió bloquear evasión: {evasion_inapropiada}",
            )

        # 6) Preservar operadores matemáticos en _limpiar_respuesta_ia
        limpio_op = _limpiar_respuesta_ia("### Multiplica **3 * 4** = 12 en `tu cuaderno`")
        self.assertNotIn("**", limpio_op)
        self.assertNotIn("###", limpio_op)
        self.assertNotIn("`", limpio_op)
        self.assertIn("3 * 4", limpio_op)

        # 7) Lectura exacta de documentos, precedencia, auto-clasificación y pistas graduadas
        doc_ejercicios = (
            "Guía de Práctica — Fecha: 12-10-2026 (Gestión 2024-2025)\n"
            "Problema 1: Calcula 3,5 + 2,5 en tu cuaderno.\n"
            "Problema 2: Resuelve la operación combinada 2 + 3 * 4 = 14.\n"
            "Problema 3: Calcula 50 - 18 paso a paso.\n"
        )
        bloque_1 = self.ia._extraer_bloque_ejercicio_documento(doc_ejercicios, "ayúdame con el problema 1")
        self.assertIn("3,5 + 2,5", bloque_1)
        self.assertNotIn("Problema 2", bloque_1)

        bloque_ult = self.ia._extraer_bloque_ejercicio_documento(doc_ejercicios, "explícame el último")
        self.assertIn("50 - 18", bloque_ult)
        self.assertNotIn("Problema 1", bloque_ult)

        ops_doc = self.ia._analizar_operaciones_en_texto(doc_ejercicios)
        valores_ops = [val for _etq, val, _exp in ops_doc]
        self.assertIn(6, valores_ops)
        self.assertIn(14, valores_ops)
        self.assertIn(32, valores_ops)
        # Las fechas 12-10-2026 y 2024-2025 NO deben evaluarse como restas (-2024 ni -1)
        self.assertNotIn(-2024, valores_ops)
        self.assertNotIn(-1, valores_ops)

        self.assertNotEqual(self.ia.detectar_modulo_automatico("La red trófica y alimentaria de los seres vivos"), "Inglés")
        self.assertEqual(self.ia.detectar_modulo_automatico("Perimetro de un triangulo y un rectangulo"), "Matemáticas")
        self.assertEqual(self.ia.detectar_modulo_automatico("Historia de la independencia de Bolivia"), "Ciencias")

        pasos_tablas, _ = self.ia.descomponer_tarea_ia("Tablas del 7 y 8")
        self.assertTrue(any("7 × 8" in p for p in pasos_tablas))
        self.assertTrue(any("56" in p for p in pasos_tablas))

        p1 = self.ia.generar_pista_contextual("Matemáticas", "Suma 15 + 7 en tu cuaderno", 1)
        p2 = self.ia.generar_pista_contextual("Matemáticas", "Suma 15 + 7 en tu cuaderno", 1)
        p3 = self.ia.generar_pista_contextual("Matemáticas", "Suma 15 + 7 en tu cuaderno", 1)
        self.assertEqual(len({p1, p2, p3}), 3, "Las pistas sucesivas para el mismo paso deben ser graduadas y distintas.")

    # =========================================================================
    # 12. R4: COMPROBACIÓN ACTIVA (DECIMALES, PALABRAS, INGLÉS Y DIAGNÓSTICO)
    # =========================================================================
    def test_17_r4_comprobacion_activa_operadores_equivalencias_negaciones_ingles_y_diagnostico_progresivo(self):
        from core.comprobacion_activa import generar_reto_paso, validar_respuesta_reto

        # 1) Operadores × y ÷, decimales (. y ,), 4+ cifras, multi-término, palabras hasta 1000+, equivalencias y negativos
        reto_mul = generar_reto_paso("Resuelve la multiplicación 8 × 4 en tu cuaderno.", 2)
        self.assertEqual(reto_mul["respuesta_principal"], "32")
        self.assertTrue(validar_respuesta_reto(reto_mul, "32")[0])
        self.assertTrue(validar_respuesta_reto(reto_mul, "treinta y dos")[0])

        reto_div = generar_reto_paso("Calcula la división 20 ÷ 4.", 2)
        self.assertEqual(reto_div["respuesta_principal"], "5")
        self.assertTrue(validar_respuesta_reto(reto_div, "cinco")[0])

        reto_dec = generar_reto_paso("Calcula 0,25 + 0,25 en tu cuaderno.", 2)
        self.assertEqual(reto_dec["respuesta_principal"], "0.5")
        for eq in ("0.5", "0,5", "1/2", "50%", "un medio"):
            self.assertTrue(validar_respuesta_reto(reto_dec, eq)[0], f"Debió aceptar equivalencia '{eq}'")

        reto_miles = generar_reto_paso("Suma 1000 + 200 en tu cuaderno.", 2)
        self.assertEqual(reto_miles["respuesta_principal"], "1200")
        self.assertTrue(validar_respuesta_reto(reto_miles, "mil doscientos")[0])
        self.assertTrue(validar_respuesta_reto(reto_miles, "1200")[0])

        reto_multi = generar_reto_paso("Resuelve 15 + 7 - 2 = 20 en tu hoja.", 2)
        self.assertEqual(reto_multi["respuesta_principal"], "20")
        self.assertTrue(validar_respuesta_reto(reto_multi, "veinte")[0])

        reto_neg = generar_reto_paso("Calcula 3 - 8 en la recta numérica.", 2)
        self.assertEqual(reto_neg["respuesta_principal"], "-5")
        self.assertEqual(len(set(reto_neg["opciones"])), 3)
        self.assertTrue(validar_respuesta_reto(reto_neg, "-5")[0])
        self.assertTrue(validar_respuesta_reto(reto_neg, "menos cinco")[0])

        reto_cero = generar_reto_paso("Calcula 5 - 5 en tu cuaderno.", 2)
        self.assertEqual(reto_cero["respuesta_principal"], "0")
        self.assertEqual(len(set(reto_cero["opciones"])), 3)

        # 2) Robustez ante división por cero y entradas None / int
        reto_div0 = generar_reto_paso("Intenta calcular 10 ÷ 0.", 2)
        self.assertIsInstance(reto_div0, dict)
        self.assertEqual(len(reto_div0["opciones"]), 3)
        self.assertIsInstance(generar_reto_paso(None, None, None), dict)
        self.assertIsInstance(generar_reto_paso(12345, "invalido"), dict)
        self.assertFalse(validar_respuesta_reto(reto_mul, None)[0])
        self.assertTrue(validar_respuesta_reto(reto_mul, 32)[0])
        self.assertFalse(validar_respuesta_reto(None, "32")[0])

        # 3) Validación numérica exacta (rechaza texto parcial sin el resultado o expresión sin calcular)
        self.assertFalse(validar_respuesta_reto(reto_mul, "suma unidades")[0])
        self.assertFalse(validar_respuesta_reto(reto_mul, "8 × 4")[0])
        self.assertFalse(validar_respuesta_reto(reto_mul, "99")[0])

        # 4) Rechazo de negaciones y frases ajenas en cualquier tipo de reto (incluido lectura)
        reto_lec = generar_reto_paso("Lee en voz alta el cuento del bosque.", 2)
        for respuesta_invalida in (
            "no saqué mi cuaderno",
            "no leí el cuento",
            "no entiendo",
            "no sé cómo hacerlo",
            "no lo hice",
            "todavía no",
            "fui al baño",
            "tengo hambre",
        ):
            self.assertFalse(
                validar_respuesta_reto(reto_lec, respuesta_invalida)[0],
                f"Debió rechazar negación/frase ajena: '{respuesta_invalida}'",
            )

        # 5) Límites de palabra \b ('accion' vs 'fracción'), vocabulario de inglés ampliado y diagnóstico progresivo
        reto_accion = generar_reto_paso("Identifica la acción principal en tu oración.", 2, "Lenguaje")
        self.assertNotIn("fracción", reto_accion["pregunta"].lower())
        self.assertIn("verbo", reto_accion["pregunta"].lower())

        reto_dog = generar_reto_paso("Aprende cómo se dice perro en inglés: DOG.", 2, "Inglés")
        self.assertEqual(reto_dog["tipo"], "ingles")
        self.assertEqual(reto_dog["respuesta_principal"], "DOG")
        self.assertTrue(validar_respuesta_reto(reto_dog, "DOG")[0])
        self.assertFalse(validar_respuesta_reto(reto_dog, "perro")[0])

        reto_apple = generar_reto_paso("Dibuja una manzana y escribe APPLE en inglés.", 2, "Inglés")
        self.assertEqual(reto_apple["tipo"], "ingles")
        self.assertTrue(validar_respuesta_reto(reto_apple, "apple")[0])

        # Retroalimentación diagnóstica progresiva (intentos 1, 2, 3+ automáticos y reinicio al acertar)
        reto_prog = generar_reto_paso("Calcula 14 + 6 en tu cuaderno.", 2)
        ok1, msg1 = validar_respuesta_reto(reto_prog, "11")
        ok2, msg2 = validar_respuesta_reto(reto_prog, "12")
        ok3, msg3 = validar_respuesta_reto(reto_prog, "13")
        self.assertFalse(ok1)
        self.assertFalse(ok2)
        self.assertFalse(ok3)
        self.assertIn("intento 2", msg2.lower())
        self.assertIn("intento 3", msg3.lower())
        self.assertIn("20", msg3)
        self.assertEqual(len({msg1, msg2, msg3}), 3)

        # Al responder correctamente se reinicia el contador de intentos fallidos
        self.assertTrue(validar_respuesta_reto(reto_prog, "20")[0])
        self.assertEqual(reto_prog.get("_intentos_fallidos"), 0)

    # =========================================================================
    # 13. PANEL DOCENTE: ESTADO LED DE OLLAMA Y BARRA DE CARGA EN DOCUMENTOS
    # =========================================================================
    def test_18_panel_docente_ollama_led_y_barra_carga_documento(self):
        import io as _io
        import json as _json
        import tempfile
        import time as _time
        import urllib.request
        from unittest.mock import patch

        from core.archivos_estudio import cargar_archivo_estudio
        from ui.panel_docente import PanelDocente
        from ui.theme import TEMAS

        class _FakeResp:
            def __init__(self, payload: bytes):
                self._buf = _io.BytesIO(payload)

            def read(self) -> bytes:
                return self._buf.read()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        # 1) MotorIAHaru.obtener_info_ollama conectado y preferencia de modelo local
        payload_ok = _json.dumps(
            {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:1b"}]}
        ).encode("utf-8")
        with patch.object(urllib.request, "urlopen", return_value=_FakeResp(payload_ok)):
            info_ok = self.ia.obtener_info_ollama(forzar=True)
        self.assertTrue(info_ok["conectado"])
        self.assertEqual(info_ok["modelo_activo"], "qwen2.5:3b")
        self.assertEqual(info_ok["modelos_disponibles"], ["qwen2.5:3b", "llama3.2:1b"])

        self.ia.configurar_modelo_ollama("llama3.2:1b")
        self.assertEqual(self.db.obtener_preferencia("modelo_ollama"), "llama3.2:1b")
        with patch.object(urllib.request, "urlopen", return_value=_FakeResp(payload_ok)):
            info_pref = self.ia.obtener_info_ollama(forzar=True)
        self.assertEqual(info_pref["modelo_activo"], "llama3.2:1b")

        # 2) Documento de prueba y verificación de callback on_progreso monótono
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_doc = os.path.join(tmpdir, "guia_progreso_prueba.txt")
            contenido_doc = (
                "# Tema 1: Sumas Rápidas\n"
                "Resuelve en tu cuaderno 12 + 8 y 25 + 15 paso a paso.\n\n"
                "# Tema 2: English Vocabulary\n"
                "Practice the words RED, BLUE, CAT and DOG in English aloud.\n"
            )
            Path(ruta_doc).write_text(contenido_doc, encoding="utf-8")
            doc = cargar_archivo_estudio(ruta_doc)
            self.assertTrue(doc.exito)

            eventos_prog = []
            propuestas = self.ia.extraer_tareas_de_documento(
                doc,
                on_progreso=lambda frac, msg: eventos_prog.append((frac, msg)),
            )
            self.assertGreaterEqual(len(propuestas), 2)
            self.assertGreaterEqual(len(eventos_prog), 3)
            valores_p = [f for f, _m in eventos_prog]
            self.assertTrue(all(0.0 < v <= 1.0 for v in valores_p))
            self.assertEqual(valores_p, sorted(valores_p))

            # 3) PanelDocente UI: LED verde/rojo Ollama en _vista_voz_ia y barra de carga async en _vista_misiones
            self.ia._ollama_check_ts = 9e12  # evitar sondeo real no mockeado al abrir UI
            root = tk.Tk()
            root.withdraw()
            try:
                panel = PanelDocente(
                    root,
                    motor_tdah=self.motor,
                    repositorio_db=self.db,
                    motor_ia=self.ia,
                    controlador_hardware=self.hw,
                    tema=TEMAS["CALMA"],
                )
                panel.withdraw()

                # Sección Misiones: widgets de barra de progreso presentes y procesamiento async
                self.assertTrue(hasattr(panel, "panel_progreso_doc"))
                self.assertTrue(hasattr(panel, "barra_progreso_doc"))
                self.assertTrue(hasattr(panel, "lbl_progreso_doc"))

                resultado_async = {"listo": False, "tareas": None}
                max_progreso_visto = {"val": 0.0}

                def _al_terminar(tareas):
                    resultado_async["tareas"] = tareas
                    resultado_async["listo"] = True

                panel.procesar_archivo_pensum_async(
                    ruta_doc,
                    abrir_modal=False,
                    on_completado=_al_terminar,
                )
                t0 = _time.time()
                while not resultado_async["listo"] and (_time.time() - t0) < 10.0:
                    root.update()
                    try:
                        max_progreso_visto["val"] = max(
                            max_progreso_visto["val"], float(panel.barra_progreso_doc.get())
                        )
                    except Exception:
                        pass
                    _time.sleep(0.02)

                self.assertTrue(resultado_async["listo"], "El procesamiento asíncrono de documento debe completar sin bloquear.")
                self.assertGreaterEqual(len(resultado_async["tareas"] or []), 2)
                self.assertGreaterEqual(max_progreso_visto["val"], 0.99)
                self.assertEqual(panel.btn_subir_archivo.cget("state"), "normal")

                # Sección Voz e IA: tarjeta Ollama con LED verde/rojo y modelo conectado
                self.ia._ollama_check_ts = 9e12
                self.ia._ollama_modelo_cache = "llama3.2:1b"
                self.ia._ollama_modelos_disponibles = ["qwen2.5:3b", "llama3.2:1b"]
                panel.mostrar_seccion("voz_ia")
                root.update_idletasks()
                for attr in ("led_ollama", "lbl_ollama_estado", "lbl_ollama_modelo", "combo_modelo_ollama", "btn_refrescar_ollama"):
                    self.assertTrue(hasattr(panel, attr), f"Falta el widget '{attr}' en PanelDocente.")

                self.assertEqual(panel.led_ollama.cget("fg_color"), "#22c55e")
                self.assertIn("Conectado", panel.lbl_ollama_estado.cget("text"))
                self.assertIn("llama3.2:1b", panel.lbl_ollama_modelo.cget("text"))

                # Selector de modelo cambia preferencia y actualiza etiqueta
                panel._seleccionar_modelo_ollama("qwen2.5:3b")
                self.assertEqual(self.db.obtener_preferencia("modelo_ollama"), "qwen2.5:3b")
                self.assertIn("qwen2.5:3b", panel.lbl_ollama_modelo.cget("text"))

                # Cambiar a estado desconectado y verificar LED rojo
                with patch.object(urllib.request, "urlopen", side_effect=OSError("sin conexion")):
                    info_off = self.ia.obtener_info_ollama(forzar=True)
                self.assertFalse(info_off["conectado"])
                panel._aplicar_estado_ollama_ui(info_off)
                self.assertEqual(panel.led_ollama.cget("fg_color"), "#ef4444")
                self.assertIn("Desconectado", panel.lbl_ollama_estado.cget("text"))
            finally:
                try:
                    panel.cerrar_panel()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass

    # =========================================================================
    # 14. DOCUMENTOS DEL ALUMNO: 30 EJERCICIOS, MEMORIA MULTI-TURNO Y PRECISIÓN
    # =========================================================================
    def test_19_documento_alumno_30_ejercicios_memoria_navegacion_y_precision(self):
        import tempfile
        from unittest.mock import patch

        from core.archivos_estudio import _leer_pdf_fallback_nativo, cargar_archivo_estudio

        self.ia._ollama_check_ts = 9e12
        self.ia._ollama_modelo_cache = None

        # 1) PDF mínimo con texto puro numérico sin letras para probar fallback nativo y pypdf
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_pdf = os.path.join(tmpdir, "mate_pura.pdf")
            stream_pdf = b"BT\n/F1 12 Tf\n72 720 Td\n(1. 15 + 7 =) Tj\n0 -20 Td\n(2. 24 / 6 =) Tj\nET\n"
            pdf_bytes = (
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
                b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
                b"4 0 obj<</Length " + str(len(stream_pdf)).encode("ascii") + b">>stream\n"
                + stream_pdf
                + b"endstream\nendobj\n"
                b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
                b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000054 00000 n \n0000000105 00000 n \n0000000222 00000 n \n0000000355 00000 n \n"
                b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n425\n%%EOF\n"
            )
            Path(ruta_pdf).write_bytes(pdf_bytes)

            txt_fallback = _leer_pdf_fallback_nativo(Path(ruta_pdf))
            self.assertIn("1. 15 + 7 =", txt_fallback)
            self.assertIn("2. 24 / 6 =", txt_fallback)

            doc_pdf = cargar_archivo_estudio(ruta_pdf)
            self.assertTrue(doc_pdf.exito)
            self.assertIn("15 + 7", doc_pdf.texto_completo)
            self.assertIn("24 / 6", doc_pdf.texto_completo)

        # 2) Documento completo con 30 ejercicios y formatos numéricos exigentes
        lineas_guia = [
            "Guía Práctica de Matemática — Fecha: 12-10-2026",
            "1. 15 + 7 =",
            "2) 3,5 + 2,5 =",
            "3.- -5 + 8 =",
            "4- 20 ÷ 4 =",
            "5. 2 + 3 * 4 =",
            "6. Ana tiene 24 caramelos y los reparte entre 6 amigos, ¿cuántos le tocan?",
            "7. ¿Cuánto es el 15% de 80?",
        ]
        for i in range(8, 30):
            lineas_guia.append(f"{i}. Calcula {i} + 10 =")
        lineas_guia.append("30. Calcula 9 × 8")
        texto_30 = "\n".join(lineas_guia)

        enc, ejs = self.ia._parsear_ejercicios_documento(texto_30)
        self.assertIn("Guía Práctica", enc)
        self.assertEqual(len(ejs), 30, f"Debió detectar exactamente 30 ejercicios, halló {len(ejs)}")

        # 3) Verificar limpieza de prefijos y cálculos exactos (sin falsos negativos como 13 o -1)
        ops_3 = self.ia._analizar_operaciones_en_texto("3.- -5 + 8 =")
        self.assertTrue(ops_3)
        self.assertEqual(ops_3[0][1], 3)

        ops_4 = self.ia._analizar_operaciones_en_texto("4- 20 ÷ 4 =")
        self.assertTrue(ops_4)
        self.assertEqual(ops_4[0][1], 5)

        ops_5 = self.ia._analizar_operaciones_en_texto("5. 2 + 3 * 4 =")
        self.assertTrue(ops_5)
        self.assertEqual(ops_5[0][1], 14)

        ops_6 = self.ia._analizar_operaciones_en_texto(
            "6. Ana tiene 24 caramelos y los reparte entre 6 amigos, ¿cuántos le tocan?"
        )
        self.assertTrue(ops_6)
        self.assertEqual(ops_6[0][1], 4)

        ops_7 = self.ia._analizar_operaciones_en_texto("7. ¿Cuánto es el 15% de 80?")
        self.assertTrue(ops_7)
        self.assertEqual(ops_7[0][1], 12)

        # 4) Conversación multi-turno continua SIN volver a adjuntar el documento
        with patch.object(self.ia, "_llamar_gemini", return_value=None):
            r_ini = self.ia.responder_sobre_documento(texto_30, pregunta="", nombre_doc="guia_30.pdf")
            self.assertIn("30 ejercicios", r_ini)
            self.assertIn("22", r_ini)

            info_act = self.motor.obtener_info_documento_activo()
            self.assertIsNotNone(info_act)
            self.assertEqual(info_act["total_ejercicios"], 30)
            self.assertEqual(info_act["ejercicio_actual"], 1)

            # Preguntar por "los otros ejercicios" NO debe irse a reposo de misión
            r_otros = self.ia.responder_consulta_escolar(
                "¿me puedes explicar los otros ejercicios?",
                modo_charla_libre=True,
            )
            self.assertNotIn("Toca Empezar Misión", r_otros)
            self.assertIn("6", r_otros)
            self.assertIn("3", r_otros)
            self.assertIn("5", r_otros)
            self.assertEqual(self.ia.obtener_documento_activo()["ejercicio_actual"], 4)

            # "siguiente" avanza al 5 (2 + 3 * 4 = 14)
            r_sig = self.ia.responder_consulta_escolar("siguiente", modo_charla_libre=True)
            self.assertIn("5/30", r_sig)
            self.assertIn("14", r_sig)

            # Salto directo al 30
            r_30 = self.ia.responder_consulta_escolar("ejercicio 30", modo_charla_libre=True)
            self.assertIn("30/30", r_30)
            self.assertIn("72", r_30)

            # Rango "del 10 al 12"
            r_rango = self.ia.responder_consulta_escolar("del 10 al 12", modo_charla_libre=True)
            self.assertIn("20", r_rango)
            self.assertIn("21", r_rango)
            self.assertIn("22", r_rango)
            self.assertEqual(self.ia.obtener_documento_activo()["ejercicio_actual"], 12)

            # Cantidad total
            r_cnt = self.ia.responder_consulta_escolar("cuántos ejercicios hay en el archivo")
            self.assertIn("30 ejercicios", r_cnt)

            # Pregunta externa ("qué hora es") NO cierra ni borra el documento activo
            r_hora = self.ia.responder_consulta_escolar("qué hora es")
            self.assertIn(":", r_hora)
            self.assertIsNotNone(self.ia.obtener_documento_activo())

            # Tras preguntar la hora, "siguiente" retoma el ejercicio 13 (13 + 10 = 23)
            r_13 = self.ia.responder_consulta_escolar("siguiente")
            self.assertIn("13/30", r_13)
            self.assertIn("23", r_13)

            # Cerrar archivo limpia el estado activo
            r_cerrar = self.ia.responder_consulta_escolar("cerrar archivo")
            self.assertIsNone(self.ia.obtener_documento_activo())
            self.assertIn("Cerré", r_cerrar)

        # 5) Barrera anti-alucinación: si un LLM devuelve un resultado falso (99), AST lo rechaza y corrige a 22
        with patch.object(self.ia, "_llamar_gemini", return_value="El resultado de 15 + 7 es 99."):
            r_guard = self.ia.responder_sobre_documento(texto_30, pregunta="ejercicio 1", nombre_doc="guia_30.pdf")
        self.assertIn("22", r_guard)
        self.assertNotIn("99", r_guard)

    # =========================================================================
    # 15. ECONOMÍA EN DOCUMENTOS: 1 ESTRELLA CADA 3 EJERCICIOS ÚNICOS
    # =========================================================================
    def test_20_cobro_una_estrella_cada_tres_ejercicios_documento(self):
        import time as _time
        from unittest.mock import patch

        self.ia._ollama_check_ts = 9e12
        self.ia._ollama_modelo_cache = None
        self.ia.cerrar_documento_activo()

        # Ajustar saldo disponible inicial exactamente a 2 estrellas
        saldo_act = self.db.obtener_estrellas_disponibles()
        if saldo_act > 2:
            ok_aj, saldo_act = self.db.consumir_estrellas_ayuda(saldo_act - 2, "Ajuste test pack 3")
            self.assertTrue(ok_aj)
        elif saldo_act < 2:
            self.db.sumar_estrellas(2 - saldo_act)
        self.assertEqual(self.db.obtener_estrellas_disponibles(), 2)

        lineas = [f"{i}. Calcula {i * 10} + 1 =" for i in range(1, 10)]
        texto_9 = "\n".join(lineas)

        with patch.object(self.ia, "_llamar_gemini", return_value=None):
            # Ejercicio 1 -> cobra 1 estrella y desbloquea cupo de 3 ejercicios (quedan 2 libres)
            r1 = self.ia.responder_sobre_documento(
                texto_9, pregunta="", nombre_doc="pack3.txt", cobrar_estrellas=True
            )
            self.assertIn("11", r1)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)
            self.assertEqual(self.ia.ultimo_cobro_documento["estrellas"], 1)
            info1 = self.ia.obtener_documento_activo()
            self.assertEqual(info1["ejercicios_explicados"], 1)
            self.assertEqual(info1["ejercicios_desbloqueados"], 3)
            self.assertEqual(info1["ejercicios_restantes_pack"], 2)

            # Ejercicio 2 y 3 -> gratis dentro del primer pack
            r2 = self.ia.responder_consulta_escolar("siguiente")
            self.assertIn("21", r2)
            self.assertIsNone(self.ia.ultimo_cobro_documento)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)

            r3 = self.ia.responder_consulta_escolar("siguiente")
            self.assertIn("31", r3)
            self.assertIsNone(self.ia.ultimo_cobro_documento)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)

            # Repetir ejercicio 3 ("no entendí") y resumen ("cuántos ejercicios") -> 0 estrellas
            _ = self.ia.responder_consulta_escolar("no entendí")
            _ = self.ia.responder_consulta_escolar("cuántos ejercicios hay")
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)

            # Ejercicio 4 -> cobra la 2da estrella y desbloquea cupos hasta 6
            r4 = self.ia.responder_consulta_escolar("siguiente")
            self.assertIn("41", r4)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 0)
            self.assertEqual(self.ia.ultimo_cobro_documento["estrellas"], 1)
            self.assertEqual(self.ia.obtener_documento_activo()["ejercicios_desbloqueados"], 6)

            # "los otros ejercicios" pide 5, 6 y 7 pero solo quedan 2 cupos libres (5 y 6) y 0 estrellas:
            # debe explicar 5 y 6 SIN revelar la respuesta del 7 (71), y avisar que necesita 1 estrella
            r_56 = self.ia.responder_consulta_escolar("los otros ejercicios")
            self.assertIn("51", r_56)
            self.assertIn("61", r_56)
            self.assertNotIn("71", r_56)
            self.assertIn("estrella", r_56.lower())
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 0)
            self.assertEqual(self.ia.obtener_documento_activo()["ejercicio_actual"], 6)

            # Intentar avanzar al 7 sin estrellas ni cupos -> bloqueo amable sin explicar el 7
            r_bloq = self.ia.responder_consulta_escolar("siguiente")
            self.assertNotIn("71", r_bloq)
            self.assertIn("3 ejercicios", r_bloq.lower())

            # Tras ganar 1 estrella nueva, "siguiente" desbloquea el 3er pack y explica el ejercicio 7
            self.db.sumar_estrellas(1)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)
            r7 = self.ia.responder_consulta_escolar("siguiente")
            self.assertIn("71", r7)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 0)
            self.assertEqual(self.ia.obtener_documento_activo()["ejercicios_desbloqueados"], 9)

            # Verificar coordinación completa MotorTDAH.consultar_documento_async + consultar_ia (cero doble cobro)
            self.ia.cerrar_documento_activo()
            self.db.sumar_estrellas(2)
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 2)
            self.bus.extraer_pendientes()

            self.motor.consultar_documento_async(
                texto_9, "pack_motor.txt", pregunta="", consumir_estrella=True
            )
            t0 = _time.time()
            while self.motor._ia_ocupada and (_time.time() - t0) < 5.0:
                _time.sleep(0.02)

            self.assertEqual(
                self.db.obtener_estrellas_disponibles(),
                1,
                "consultar_documento_async debe cobrar exactamente 1 estrella (sin doble cobro).",
            )
            evs = self.bus.extraer_pendientes()
            resps_ui = [e.datos.get("respuesta", "") for e in evs if e.tipo == "ia_respuesta"]
            self.assertTrue(any("Pack 3 ejercicios" in r for r in resps_ui))

            # Pasos 2 y 3 gratuitos por consultar_ia, paso 4 cobra la 2da estrella
            self.motor.consultar_ia("siguiente")
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)
            self.motor.consultar_ia("siguiente")
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 1)
            self.motor.consultar_ia("siguiente")
            self.assertEqual(self.db.obtener_estrellas_disponibles(), 0)

    def test_21_zona_juegos_tictactoe_y_memorama(self):
        """Verifica ModalMenuJuegos, Tres en Raya (anti-farming y dificultades) y Memorama."""
        import customtkinter as ctk
        from ui.app import VentanaPrincipalHaru
        from ui.juegos_modal import ModalMenuJuegos, VentanaMemorama, VentanaTicTacToe
        from ui.theme import obtener_tema

        self.assertTrue(hasattr(VentanaPrincipalHaru, "_abrir_zona_juegos"))
        raiz_repo = Path(__file__).resolve().parent.parent
        app_src = (raiz_repo / "ui" / "app.py").read_text(encoding="utf-8")
        self.assertIn("btn_juegos", app_src)

        tema = obtener_tema("CALMA")
        root = ctk.CTk()
        root.withdraw()
        try:
            menu = ModalMenuJuegos(root, tema=tema, funcion_hablar=lambda _t: None)
            self.assertTrue(menu.winfo_exists())
            menu.destroy()

            # 1) Tres en Raya: victoria + anti-farming en deshacer + dificultades + pista
            victorias_ttt = []
            ttt = VentanaTicTacToe(
                root,
                tema=tema,
                funcion_hablar=lambda _t: None,
                on_victoria=lambda: victorias_ttt.append(1),
            )
            ttt.tablero = ["X", "X", "X", "O", "O", "", "", "", ""]
            ttt.historial = [[0, 3], [1, 4], [2, None]]
            self.assertTrue(ttt._verificar_estado("X"))
            self.assertFalse(ttt.juego_activo)
            self.assertEqual(len(victorias_ttt), 1)

            # Deshacer tras finalizar ronda debe estar bloqueado (anti-farming)
            ttt._deshacer_jugada()
            self.assertFalse(ttt.juego_activo)
            self.assertEqual(len(victorias_ttt), 1)

            for dif in ("Fácil", "Normal", "Desafío"):
                ttt._cambiar_dificultad(dif)
                self.assertEqual(ttt.dificultad, dif)
                self.assertTrue(ttt.juego_activo)
            ttt._usar_pista()
            ttt._cerrar_ventana()

            # 2) Memorama: niveles 6/8 pares, espiar 2s, victoria y cierre seguro
            victorias_mem = []
            mem = VentanaMemorama(
                root,
                tema=tema,
                funcion_hablar=lambda _t: None,
                on_victoria=lambda: victorias_mem.append(1),
            )
            self.assertEqual(len(mem.cartas), 12)
            mem._cambiar_dificultad("Normal")
            self.assertEqual(len(mem.cartas), 16)
            mem.update_idletasks()
            self.assertEqual(mem.resizable(), (True, True))
            self.assertGreaterEqual(mem.btn_espiar.winfo_reqheight(), 36)
            self.assertLessEqual(mem.winfo_reqheight(), mem.winfo_height())
            mem._espiar_tablero()
            self.assertEqual(mem.espias_disponibles, 0)
            mem.bloqueado = False

            # Emparejar todas las cartas del tablero Normal
            indices_por_icono = {}
            for idx, (icono, _color) in enumerate(mem.cartas):
                indices_por_icono.setdefault(icono, []).append(idx)
            for _icono, (i1, i2) in indices_por_icono.items():
                mem.seleccionadas = [i1, i2]
                mem._evaluar_pareja()

            self.assertEqual(len(victorias_mem), 1)
            mem._cerrar_ventana()

            # 3) Panel Docente: pills compactas y botón Subir Archivo sin desbordamiento
            panel = PanelDocente(
                root,
                motor_tdah=self.motor,
                repositorio_db=self.db,
                motor_ia=self.ia,
                controlador_hardware=self.hw,
                tema=tema,
            )
            panel.update()
            self.assertLess(panel._botones_modulo["Todos"].cget("width"), 140)
            ancho_total_pills = sum(btn.cget("width") + 4 for btn in panel._botones_modulo.values())
            self.assertLess(ancho_total_pills, 650)
            self.assertGreaterEqual(panel.btn_subir_archivo.winfo_reqwidth(), 150)
            self.assertGreaterEqual(panel.winfo_width(), 1240)
            self.assertLessEqual(panel.winfo_reqwidth(), panel.winfo_width())
            panel.cerrar_panel()
        finally:
            try:
                root.update_idletasks()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

