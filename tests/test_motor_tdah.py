"""
Suite Completa de Pruebas Unitarias e Integración — Asistente Virtual TDAH "Haru"
Universidad Salesiana de Bolivia - Fase 3 (Estudio y Verificación)

Verifica:
1. Motor Pedagógico TDAH (progresión secuencial, retroceso, pistas, gamificación).
2. Control de Descansos del Alumno (límite por misión, cooldown, bitácora e intervalo promedio).
3. Seguridad PIN Docente (hash PBKDF2-HMAC-SHA256, migración de texto plano y bloqueo persistente).
4. Calculadora Aritmética Segura `ast` (lenguaje natural infantil + bloqueo de inyecciones/exponentes).
5. Motor de IA en Capas y Modo Privado (respeto estricto a Ley N.º 548 bloqueando llamadas cloud).
6. Motor de Voz y Karaoke (limpieza de emojis, caché determinista y estimación de marcas por palabra).
7. Bus de Eventos Multihilo (`BusEventosUI`), Exportación CSV/HTML y Empaquetador `.zip` sin `.env`.
"""

import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.eventos import BusEventosUI
from core.ia.calculadora_ast import evaluar_ast_seguro, resolver_pregunta_matematica
from core.ia_asistente import MotorIAHaru
from core.motor_tdah import MotorTDAH
from core.repositorio_db import RepositorioTDAH
from core.voz.tts import MotorVozHaru, estimar_marcas_proporcionales, limpiar_texto_para_voz
from hardware.control_leds import ControladorHardwareLEDs
from tools.empaquetar_zip import crear_paquete_zip


class TestHaruProyectoIntegrador(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_test_path = os.path.join(self.temp_dir.name, "test_haru.db")
        self.db = RepositorioTDAH(db_path=self.db_test_path)
        self.ia = MotorIAHaru(repositorio_db=self.db)
        self.ia.set_modo_privado(True)  # Evitar llamadas de red durante pruebas unitarias
        self.hardware = ControladorHardwareLEDs(puerto_default="COM_INEXISTENTE")
        self.bus = BusEventosUI()

        self.mensajes_voz = []
        self.notificaciones_ui = []

        self.motor = MotorTDAH(
            callback_voz=lambda t: self.mensajes_voz.append(t),
            callback_ui=lambda d: self.notificaciones_ui.append(d),
            controlador_hardware=self.hardware,
            repositorio_db=self.db,
            motor_ia=self.ia,
            bus_eventos=self.bus,
        )
        self.motor.cargar_tarea("Prueba Unitaria", ["Paso 1", "Paso 2", "Paso 3"])

    def tearDown(self):
        self.motor.detener_temporizador()
        self.hardware.cerrar()
        self.temp_dir.cleanup()

    def test_1_inicializacion_e_inicio_secuencial(self):
        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_IDLE)
        self.motor.iniciar_tarea()
        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_EN_PASO)
        self.assertEqual(self.motor.indice_paso, 0)
        self.assertIn("Paso 1", self.mensajes_voz[-1])

        eventos = self.bus.extraer_pendientes()
        self.assertTrue(any(ev.tipo == "motor_ui" for ev in eventos))

    def test_2_progresion_pasos_gamificacion_y_registro_db(self):
        estrellas_iniciales = self.db.obtener_estrellas()
        self.motor.iniciar_tarea()

        self.motor.avanzar_paso()
        self.assertEqual(self.motor.indice_paso, 1)
        self.assertEqual(self.db.obtener_estrellas(), estrellas_iniciales + 1)

        self.motor.retroceder_paso()
        self.assertEqual(self.motor.indice_paso, 0)
        self.motor.avanzar_paso()
        self.motor.avanzar_paso()
        self.motor.avanzar_paso()

        self.assertEqual(self.motor.estado, MotorTDAH.ESTADO_COMPLETADA)
        self.assertFalse(self.motor.temporizador_activo)
        self.assertGreaterEqual(self.db.obtener_estrellas(), estrellas_iniciales + 6)

        historial = self.db.obtener_historial_sesiones()
        self.assertEqual(len(historial), 1)
        self.assertEqual(historial[0]["nombre_tarea"], "Prueba Unitaria")

    def test_3_control_descansos_alumno_y_bitacora(self):
        self.motor.iniciar_tarea()
        self.motor.max_descansos_por_tarea = 2
        self.motor.cooldown_descanso_seg = 5

        self.motor.segundos_concentracion_sesion = 20
        pausado, _ = self.motor.solicitar_descanso_alumno()
        self.assertTrue(pausado)
        self.assertEqual(self.motor.pausas_manuales_sesion, 1)

        # Reanudar
        pausado, _ = self.motor.solicitar_descanso_alumno()
        self.assertFalse(pausado)

        # Segundo descanso a los 50s -> intervalos [20, 30] -> promedio 25s
        self.motor.segundos_concentracion_sesion = 50
        pausado, _ = self.motor.solicitar_descanso_alumno()
        self.assertTrue(pausado)
        self.assertEqual(self.motor.calcular_intervalo_promedio_descanso(), 25)

        # Tercer descanso bloqueado por límite
        self.motor.solicitar_descanso_alumno()
        self.motor.segundos_concentracion_sesion = 90
        pausado, msg = self.motor.solicitar_descanso_alumno()
        self.assertFalse(pausado)
        self.assertIn("Ya usaste tus 2 descansos", msg)
        self.assertEqual(len(self.db.obtener_bitacora_descansos()), 2)

    def test_4_seguridad_pin_pbkdf2_migracion_y_bloqueo_persistente(self):
        # El PIN jamás debe quedar en texto plano
        self.assertEqual(self.db.obtener_preferencia("pin_docente", ""), "")
        self.assertNotEqual(self.db.obtener_preferencia("pin_hash", ""), "1234")
        self.assertTrue(self.db.verificar_pin_docente("1234"))
        self.assertFalse(self.db.verificar_pin_docente("9999"))

        # Cambio de PIN
        self.db.cambiar_pin_docente("4321")
        self.assertTrue(self.db.verificar_pin_docente("4321"))
        self.assertEqual(self.db.obtener_preferencia("pin_personalizado", "0"), "1")

        # 3 intentos fallidos activan bloqueo persistente incluso al reabrir la BD
        self.assertFalse(self.db.registrar_intento_pin("0000")[0])
        self.assertFalse(self.db.registrar_intento_pin("1111")[0])
        exito, restantes, seg_bloq = self.db.registrar_intento_pin("2222")
        self.assertFalse(exito)
        self.assertEqual(restantes, 0)
        self.assertGreater(seg_bloq, 0)

        db_reabierta = RepositorioTDAH(db_path=self.db_test_path)
        bloqueado, seg = db_reabierta.esta_pin_bloqueado()
        self.assertTrue(bloqueado)
        self.assertGreater(seg, 0)
        self.assertFalse(db_reabierta.verificar_pin_docente("4321"))

        # Verificar migración automática desde una BD antigua con pin_docente en texto plano
        ruta_legacy = os.path.join(self.temp_dir.name, "legacy.db")
        conn = sqlite3.connect(ruta_legacy)
        conn.execute("CREATE TABLE perfil_progreso (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
        conn.execute("INSERT INTO perfil_progreso VALUES ('pin_docente', '7788')")
        conn.commit()
        conn.close()

        db_migrada = RepositorioTDAH(db_path=ruta_legacy)
        self.assertEqual(db_migrada.obtener_preferencia("pin_docente", ""), "")
        self.assertTrue(db_migrada.verificar_pin_docente("7788"))

    def test_5_calculadora_ast_segura_y_bloqueo_inyeccion(self):
        self.assertEqual(evaluar_ast_seguro("15 + 7"), 22)
        self.assertEqual(evaluar_ast_seguro("(12 + 8) / 4"), 5.0)
        self.assertIn("22", resolver_pregunta_matematica("¿Cuánto es 15 más 7?") or "")
        self.assertIn("12", resolver_pregunta_matematica("la mitad de 24") or "")
        self.assertIn("32", resolver_pregunta_matematica("cuánto es 8 por 4") or "")

        # Bloquear ejecución arbitraria y exponentes gigantes (DoS)
        with self.assertRaises(ValueError):
            evaluar_ast_seguro("__import__('os').system('echo hack')")
        with self.assertRaises(ValueError):
            evaluar_ast_seguro("9 ** 999999")

    def test_6_modo_privado_ley548_y_descomposicion_ia(self):
        self.ia.api_key = "AQ.ClaveFicticiaDePrueba"
        self.ia.set_modo_privado(True)
        with patch("urllib.request.urlopen", side_effect=AssertionError("No debe salir a internet en Modo Privado")):
            # En modo privado puede consultar 127.0.0.1 Ollama, forzamos caché sin Ollama para verificar cero nube
            self.ia._ollama_check_ts = 9e12
            self.ia._ollama_modelo_cache = None
            resp = self.ia.responder_consulta_escolar("¿Cómo hago un resumen?", "Lenguaje", "Lee el cuento")
            self.assertIn("Lenguaje", resp)
            pasos, pistas = self.ia.descomponer_tarea_ia("Multiplicaciones de Primaria")
            self.assertGreaterEqual(len(pasos), 3)
            self.assertEqual(len(pasos), len(pistas))

    def test_7_voz_limpieza_emojis_y_marcas_karaoke(self):
        limpio = limpiar_texto_para_voz("¡Paso 1 listo! ⭐🎉 Saca tu cuaderno 📓")
        self.assertNotIn("⭐", limpio)
        self.assertNotIn("📓", limpio)
        self.assertIn("Paso 1 listo", limpio)

        marcas = estimar_marcas_proporcionales(limpio)
        self.assertEqual(len(marcas), len(limpio.split()))
        self.assertGreater(marcas[-1]["offset_ms"], marcas[0]["offset_ms"])

        k1 = MotorVozHaru.clave_cache("Hola Haru", "es-BO-SofiaNeural", "+0%")
        k2 = MotorVozHaru.clave_cache("Hola Haru", "es-BO-SofiaNeural", "+0%")
        self.assertEqual(k1, k2)

    def test_8_exportacion_reportes_y_zip_limpio_sin_secretos(self):
        self.db.registrar_sesion("Matemáticas", 3, 3, 180, 1, 0, 6, pausas_manuales=2, intervalo_promedio_descanso_seg=45)
        csv_path = os.path.join(self.temp_dir.name, "reporte.csv")
        html_path = os.path.join(self.temp_dir.name, "reporte.html")
        self.db.exportar_reporte_csv(csv_path)
        self.db.exportar_reporte_html(html_path)
        self.assertTrue(os.path.exists(csv_path))
        self.assertTrue(os.path.exists(html_path))

        zip_destino = Path(self.temp_dir.name) / "prueba_compartir.zip"
        crear_paquete_zip(zip_destino)
        self.assertTrue(zip_destino.exists())
        with zipfile.ZipFile(zip_destino, "r") as zf:
            nombres = zf.namelist()
            self.assertFalse(any(n.endswith("/.env") or n == ".env" for n in nombres))
            self.assertFalse(any(n.endswith(".db") for n in nombres))
            self.assertTrue(any(n.endswith(".env.example") for n in nombres))
            self.assertTrue(any(n.endswith("haru.pyw") for n in nombres))


if __name__ == "__main__":
    unittest.main()
