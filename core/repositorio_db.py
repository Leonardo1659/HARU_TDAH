"""
Repositorio de Base de Datos SQLite (Persistencia Local, Analítica y Seguridad)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Cumple con:
- Ley N.º 548 (Código Niña, Niño y Adolescente): Minimización de datos,
  sin almacenamiento de grabaciones de voz ni datos biométricos/personales,
  y sin almacenar llaves API en la base de datos.
- Ley N.º 070 y R.M. N.º 0069/2025: Seguimiento psicopedagógico de tareas,
  registro de frecuencia de descansos del estudiante y articulación con docentes.
- Seguridad: PIN docente protegido con PBKDF2-HMAC-SHA256 + sal aleatoria y
  bloqueo temporal persistente ante intentos fallidos.
"""

import csv
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.config import DB_PATH


def _quitar_tildes(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _sanitizar_celda_csv(valor: Any) -> Any:
    """Previene CSV Formula Injection (OWASP) en Excel/LibreOffice Calc y limpia saltos."""
    if isinstance(valor, (int, float)):
        return valor
    txt = re.sub(r"[\r\n]+", " ", str(valor or "")).strip()
    if txt and txt[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{txt}"
    return txt


def _formatear_duracion_humana(segundos: int) -> str:
    seg = max(0, int(segundos or 0))
    if seg < 60:
        return f"{seg}s"
    minutos, resto = divmod(seg, 60)
    if minutos < 60:
        return f"{minutos}m {resto:02d}s"
    horas, min_r = divmod(minutos, 60)
    return f"{horas}h {min_r:02d}m"


class RepositorioTDAH:
    SCHEMA_VERSION = "2"
    PBKDF2_ITERATIONS = 120_000
    MAX_INTENTOS_PIN = 3
    SEGUNDOS_BLOQUEO_PIN = 45
    RECOMPENSAS_SUGERIDAS = [
        ("🎨 5 min de dibujo o plastilina libre", 6, "Recompensa rápida alcanzable tras tu primera misión completada."),
        ("🎵 Escuchar mi canción favorita", 10, "Elegir una canción alegre en casa o en el aula."),
        ("🌟 Sticker o sello campeón en mi cuaderno", 15, "Reconocimiento por orden y atención paso a paso."),
        ("🎲 Elegir juego de mesa o recreo especial", 22, "Premio intermedio pactado con familia o docente."),
        ("🍿 Cuento, paseo o tarde especial en familia", 32, "Gran meta semanal por constancia y esfuerzo."),
    ]

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self.db_path = str(db_path)
        else:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(DB_PATH)

        self._inicializar_tablas()
        self._sembrar_datos_iniciales()
        self._migrar_seguridad_pin()

    @contextmanager
    def _conectar(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            conn.close()

    def _inicializar_tablas(self):
        with self._conectar() as conn:
            cursor = conn.cursor()
            # 1. Tabla de tareas secuenciales configurables por el docente/familia
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tareas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    categoria TEXT NOT NULL DEFAULT 'General',
                    pasos_json TEXT NOT NULL,
                    pistas_json TEXT NOT NULL,
                    es_predeterminada INTEGER NOT NULL DEFAULT 0,
                    fecha_creacion TEXT NOT NULL
                )
            """)

            # 2. Tabla de historial de sesiones (con métricas de descansos manuales e intervalo promedio)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sesiones_estudio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_hora TEXT NOT NULL,
                    nombre_tarea TEXT NOT NULL,
                    pasos_completados INTEGER NOT NULL,
                    total_pasos INTEGER NOT NULL,
                    segundos_concentracion INTEGER NOT NULL,
                    pausas_activas INTEGER NOT NULL,
                    pausas_manuales INTEGER NOT NULL DEFAULT 0,
                    intervalo_promedio_descanso_seg INTEGER NOT NULL DEFAULT 0,
                    pistas_usadas INTEGER NOT NULL,
                    estrellas_ganadas INTEGER NOT NULL,
                    estado_final TEXT NOT NULL
                )
            """)

            cursor.execute("PRAGMA table_info(sesiones_estudio)")
            columnas_actuales = [col["name"] for col in cursor.fetchall()]
            if "pausas_manuales" not in columnas_actuales:
                cursor.execute("ALTER TABLE sesiones_estudio ADD COLUMN pausas_manuales INTEGER NOT NULL DEFAULT 0")
            if "intervalo_promedio_descanso_seg" not in columnas_actuales:
                cursor.execute("ALTER TABLE sesiones_estudio ADD COLUMN intervalo_promedio_descanso_seg INTEGER NOT NULL DEFAULT 0")

            # 3. Bitácora detallada de descansos del estudiante
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bitacora_descansos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_hora TEXT NOT NULL,
                    nombre_tarea TEXT NOT NULL,
                    paso_actual INTEGER NOT NULL,
                    segundos_transcurridos INTEGER NOT NULL,
                    motivo TEXT NOT NULL DEFAULT 'Botón Descanso Alumno'
                )
            """)

            # 4. Perfil de gamificación, seguridad PIN (hash) y preferencias
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS perfil_progreso (
                    clave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                )
            """)

            # 5. Base de conocimiento educativo verificado para primaria
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conocimiento_escolar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    palabra_clave TEXT UNIQUE NOT NULL,
                    materia TEXT NOT NULL,
                    respuesta_amigable TEXT NOT NULL
                )
            """)

            # 6. Catálogo de premios reales pactados (Economía de Fichas TDAH)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recompensas_catalogo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT UNIQUE NOT NULL,
                    costo_estrellas INTEGER NOT NULL,
                    descripcion TEXT NOT NULL DEFAULT ''
                )
            """)

            # 7. Historial de canjes de estrellas por premios reales
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historial_canjes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_hora TEXT NOT NULL,
                    titulo_premio TEXT NOT NULL,
                    costo_estrellas INTEGER NOT NULL
                )
            """)
            conn.commit()

    TAREAS_BASE = [
        {
            "nombre": "Matemáticas - Sumas Divertidas",
            "categoria": "Matemáticas",
            "pasos": [
                "Saca tu cuaderno de matemáticas, tu lápiz y tu borrador sobre la mesa.",
                "Abre tu cuaderno en una hoja limpia y escribe la suma: 15 + 7.",
                "Suma primero las unidades (5 más 7) y luego la decena. ¡Presiona Paso Listo cuando termines!",
            ],
            "pistas": [
                "Busca en tu mochila únicamente el cuaderno de cuadros y un lápiz.",
                "Escribe el 15 arriba y el 7 justo debajo del 5 para alinear las unidades.",
                "Puedes contar desde 15 subiendo 7 deditos: 16, 17, 18, 19, 20, 21 y 22.",
            ],
        },
        {
            "nombre": "Lenguaje - Lectura de Cuento Corto",
            "categoria": "Lenguaje",
            "pasos": [
                "Abre tu libro de lectura en el cuento de hoy y pon tu dedo en el título.",
                "Lee en voz alta solo el primer párrafo despacito, respetando los puntos.",
                "Cuéntame o escribe en una oración corta quién es el personaje principal.",
                "Haz un pequeño dibujo de lo que más te gustó de la historia.",
            ],
            "pistas": [
                "Si no encuentras la página, mira el número en la esquina inferior del libro.",
                "Si una palabra es larga, divídela en palmadas sílaba por sílaba.",
                "Piensa: ¿De qué animalito o niño habla el primer párrafo?",
                "No tiene que ser perfecto, dibuja lo primero que imagines con tu color favorito.",
            ],
        },
        {
            "nombre": "Ciencias Naturales - El Ciclo del Agua",
            "categoria": "Ciencias",
            "pasos": [
                "Prepara tus colores azul, amarillo y verde junto a tu cuaderno.",
                "Dibuja un sol brillante arriba y un río o mar en la parte de abajo.",
                "Dibuja una nube blanca y flechitas que muestren cómo sube el vapor y cae la lluvia.",
            ],
            "pistas": [
                "Saca únicamente esos 3 colores de tu estuche para no distraerte.",
                "El sol calienta el agua del río; dibújalo en una esquina superior.",
                "Recuerda: el agua sube como vapor (evaporación), forma nubes y baja como lluvia.",
            ],
        },
        {
            "nombre": "Organización - Preparar mi Mochila",
            "categoria": "Hábitos y Orden",
            "pasos": [
                "Revisa tu horario de mañana y guarda los cuadernos que te tocan.",
                "Guarda tus lápices, colores, borrador y tajador dentro de tu estuche.",
                "Cierra tu mochila y déjala lista junto a la puerta para mañana.",
            ],
            "pistas": [
                "Mete primero los libros más grandes al fondo de la mochila.",
                "Revisa que no quede ningún lápiz suelto encima del escritorio.",
                "¡Ya casi terminas! Poner la mochila en su lugar te ahorrará tiempo mañana.",
            ],
        },
    ]

    def _sembrar_datos_iniciales(self):
        tareas_base = self.TAREAS_BASE

        conocimiento_base = [
            ("hola", "Saludo", "¡Hola amiguito! Soy Haru, tu compañero de estudio. ¡Qué alegría aprender contigo hoy!"),
            ("quien eres", "Identidad", "Soy Haru, un robotito educativo creado en la Universidad Salesiana de Bolivia para ayudarte a hacer tus tareas paso a paso."),
            ("quién eres", "Identidad", "Soy Haru, un robotito educativo creado en la Universidad Salesiana de Bolivia para ayudarte a hacer tus tareas paso a paso."),
            ("chiste", "Motivación", "¡Ahí va un chiste! ¿Qué le dice el número 1 al número 10? ¡Para ser como yo tienes que ser sincero! Jajaja."),
            ("sistema solar", "Ciencias", "El Sistema Solar tiene una estrella gigante llamada Sol y 8 planetas: Mercurio, Venus, Tierra, Marte, Júpiter, Saturno, Urano y Neptuno."),
            ("fotosintesis", "Ciencias", "La fotosíntesis es el súper poder de las plantas para fabricar su alimento usando luz del sol, agua y aire, ¡y nos regalan oxígeno!"),
            ("fotosíntesis", "Ciencias", "La fotosíntesis es el súper poder de las plantas para fabricar su alimento usando luz del sol, agua y aire, ¡y nos regalan oxígeno!"),
            ("ciclo del agua", "Ciencias", "El ciclo del agua tiene 3 pasos mágicos: el sol evapora el agua, en el cielo se condensa en nubes y luego cae como lluvia."),
            ("sustantivo", "Lenguaje", "Un sustantivo es la palabra que usamos para nombrar personas, animales, cosas o lugares, como perro, escuela, María o cuaderno."),
            ("verbo", "Lenguaje", "El verbo es la palabra que indica una acción o movimiento, por ejemplo: correr, saltar, estudiar, jugar o sonreír."),
            ("adjetivo", "Lenguaje", "El adjetivo nos dice cómo es algo o alguien, por ejemplo: grande, brillante, amable, rojo o divertido."),
            ("multiplicar", "Matemáticas", "Multiplicar es sumar el mismo número varias veces rápido. Por ejemplo, 3 por 4 es sumar 3 veces el 4: 4 + 4 + 4 = 12."),
            ("fraccion", "Matemáticas", "Una fracción es dividir algo entero en partes iguales, como cuando partes una pizza en 4 pedazos iguales y tomas 1 cuarto."),
            ("fracción", "Matemáticas", "Una fracción es dividir algo entero en partes iguales, como cuando partes una pizza en 4 pedazos iguales y tomas 1 cuarto."),
            ("dividir", "Matemáticas", "Dividir es repartir en partes iguales. Por ejemplo, si tienes 10 caramelos para 2 amigos, a cada uno le tocan 5."),
            ("bolivia", "Estudios Sociales", "Bolivia está en el corazón de Sudamérica, tiene 9 departamentos, su capital constitucional es Sucre y su sede de gobierno es La Paz."),
            ("cansado", "Apoyo Emocional", "¡Es normal sentirse cansado! Presiona el botón Respirar para inhalar como oliendo una flor y soplar como una velita."),
            ("dificil", "Apoyo Emocional", "¡No te preocupes! Cuando algo parece difícil, lo partimos en pedacitos pequeños. Hagamos solo este paso juntos."),
            ("difícil", "Apoyo Emocional", "¡No te preocupes! Cuando algo parece difícil, lo partimos en pedacitos pequeños. Hagamos solo este paso juntos."),
            ("como estas", "Conversación", "¡Estoy súper feliz y orgulloso de acompañarte hoy! ¿Y tú cómo te sientes después de avanzar en tus actividades?"),
            ("cómo estás", "Conversación", "¡Estoy súper feliz y orgulloso de acompañarte hoy! ¿Y tú cómo te sientes después de avanzar en tus actividades?"),
            ("que haces", "Conversación", "Aquí descansando tranquilo contigo en mi modo compañero. ¡Podemos charlar de tus tareas, curiosidades o contar una adivinanza!"),
            ("qué haces", "Conversación", "Aquí descansando tranquilo contigo en mi modo compañero. ¡Podemos charlar de tus tareas, curiosidades o contar una adivinanza!"),
            ("gracias", "Conversación", "¡De nada, campeón! Aprender contigo es mi parte favorita del día."),
            ("aburrido", "Conversación", "¡Podemos hacer algo divertido! Prueba el Reto de Colores con cámara, pídeme un chiste o pregúntame sobre dinosaurios o planetas."),
            ("feliz", "Apoyo Emocional", "¡Qué alegría escuchar eso! Cuando celebramos nuestros logros con calma, nuestro cerebro aprende cada día mejor."),
            ("adivinanza", "Motivación", "¡Adivina adivinador! Blanca por dentro, verde por fuera; si quieres que te lo diga, es-pera. ¡La pera!"),
            ("cuento", "Motivación", "Había una vez una pequeña estrellita andina que brillaba poquito, pero dando un pasito cada noche iluminó todo el cielo de Bolivia."),
            ("dinosaurio", "Ciencias", "Los dinosaurios vivieron hace millones de años; algunos como el Triceratops comían plantas y en Sucre, Bolivia, ¡hay miles de sus huellas en Cal Orck'o!"),
            ("dinosaurios", "Ciencias", "Los dinosaurios vivieron hace millones de años; algunos como el Triceratops comían plantas y en Sucre, Bolivia, ¡hay miles de sus huellas en Cal Orck'o!")
        ]

        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM tareas")
            if cursor.fetchone()["total"] == 0:
                ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for t in tareas_base:
                    cursor.execute("""
                        INSERT INTO tareas (nombre, categoria, pasos_json, pistas_json, es_predeterminada, fecha_creacion)
                        VALUES (?, ?, ?, ?, 1, ?)
                    """, (t["nombre"], t["categoria"], json.dumps(t["pasos"], ensure_ascii=False),
                          json.dumps(t["pistas"], ensure_ascii=False), ahora))

            preferencias_defecto = {
                "schema_version": self.SCHEMA_VERSION,
                "estrellas_totales": "5",
                "estrellas_gastadas": "0",
                "tareas_completadas": "0",
                "avatar_skin": "ROBOT_KAWAII",
                "tema_visual": "CALMA",
                "max_descansos_por_tarea": "2",
                "min_foco_pomodoro": "10",
                "min_pausa_pomodoro": "2",
                "modo_privado": "0",
                "voz_tts": "es-BO-SofiaNeural",
                "velocidad_tts": "+0%",
                "puerto_arduino": "COM15",
                "pin_intentos_fallidos": "0",
                "pin_bloqueado_hasta": "0",
                "pin_personalizado": "0",
            }
            for k, v in preferencias_defecto.items():
                cursor.execute("INSERT OR IGNORE INTO perfil_progreso (clave, valor) VALUES (?, ?)", (k, v))

            # Limpiar llave API si una versión previa la guardó en texto plano en SQLite
            cursor.execute("DELETE FROM perfil_progreso WHERE clave = 'gemini_api_key'")

            for clave, materia, resp in conocimiento_base:
                cursor.execute("""
                    INSERT OR IGNORE INTO conocimiento_escolar (palabra_clave, materia, respuesta_amigable)
                    VALUES (?, ?, ?)
                """, (clave, materia, resp))

            cursor.execute("SELECT COUNT(*) as total FROM recompensas_catalogo")
            if cursor.fetchone()["total"] == 0:
                for tit, costo, desc in self.RECOMPENSAS_SUGERIDAS:
                    cursor.execute("""
                        INSERT OR IGNORE INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                        VALUES (?, ?, ?)
                    """, (tit, costo, desc))
            else:
                # Asegurar que exista el premio inicial rápido (6 ⭐) alcanzable tras la 1.ª misión
                cursor.execute("SELECT COUNT(*) as c FROM recompensas_catalogo WHERE costo_estrellas <= 6")
                if cursor.fetchone()["c"] == 0:
                    tit0, costo0, desc0 = self.RECOMPENSAS_SUGERIDAS[0]
                    cursor.execute("""
                        INSERT OR IGNORE INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                        VALUES (?, ?, ?)
                    """, (tit0, costo0, desc0))

            conn.commit()

    # --- SEGURIDAD PIN CON PBKDF2-HMAC-SHA256 Y BLOQUEO PERSISTENTE ---
    def _calcular_hash_pin(self, pin: str, salt_hex: str) -> str:
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            pin.strip().encode("utf-8"),
            bytes.fromhex(salt_hex),
            self.PBKDF2_ITERATIONS,
        )
        return dk.hex()

    def _migrar_seguridad_pin(self):
        """Convierte cualquier PIN antiguo en texto plano a PBKDF2-HMAC-SHA256."""
        pin_hash = self.obtener_preferencia("pin_hash", "")
        pin_salt = self.obtener_preferencia("pin_salt", "")
        pin_plano = self.obtener_preferencia("pin_docente", "")

        if not pin_hash or not pin_salt:
            semilla_pin = pin_plano.strip() if pin_plano.strip() else "1234"
            nuevo_salt = secrets.token_hex(16)
            nuevo_hash = self._calcular_hash_pin(semilla_pin, nuevo_salt)
            self.guardar_preferencia("pin_salt", nuevo_salt)
            self.guardar_preferencia("pin_hash", nuevo_hash)
            if semilla_pin != "1234":
                self.guardar_preferencia("pin_personalizado", "1")

        if pin_plano:
            with self._conectar() as conn:
                conn.execute("DELETE FROM perfil_progreso WHERE clave = 'pin_docente'")
                conn.commit()

    def esta_pin_bloqueado(self) -> Tuple[bool, int]:
        """Retorna (bloqueado, segundos_restantes) persistente entre reinicios."""
        hasta_str = self.obtener_preferencia("pin_bloqueado_hasta", "0")
        try:
            hasta_ts = float(hasta_str)
        except ValueError:
            hasta_ts = 0.0
        ahora = time.time()
        if hasta_ts > ahora:
            return True, max(1, int(round(hasta_ts - ahora)))
        if hasta_ts > 0:
            self.guardar_preferencia("pin_bloqueado_hasta", "0")
            self.guardar_preferencia("pin_intentos_fallidos", "0")
        return False, 0

    def verificar_pin_docente(self, pin_ingresado: str) -> bool:
        """Verifica el PIN contra su hash PBKDF2 en tiempo constante."""
        bloqueado, _ = self.esta_pin_bloqueado()
        if bloqueado:
            return False
        pin_salt = self.obtener_preferencia("pin_salt", "")
        pin_hash = self.obtener_preferencia("pin_hash", "")
        if not pin_salt or not pin_hash:
            self._migrar_seguridad_pin()
            pin_salt = self.obtener_preferencia("pin_salt", "")
            pin_hash = self.obtener_preferencia("pin_hash", "")
        candidato = self._calcular_hash_pin(pin_ingresado, pin_salt)
        return hmac.compare_digest(candidato, pin_hash)

    def registrar_intento_pin(self, pin_ingresado: str) -> Tuple[bool, int, int]:
        """
        Valida un intento interactivo de PIN y persiste el bloqueo temporal.
        Retorna: (exito, intentos_restantes, segundos_bloqueo).
        """
        bloqueado, seg_restantes = self.esta_pin_bloqueado()
        if bloqueado:
            return False, 0, seg_restantes

        if self.verificar_pin_docente(pin_ingresado):
            self.guardar_preferencia("pin_intentos_fallidos", "0")
            self.guardar_preferencia("pin_bloqueado_hasta", "0")
            return True, self.MAX_INTENTOS_PIN, 0

        fallidos = int(self.obtener_preferencia("pin_intentos_fallidos", "0")) + 1
        if fallidos >= self.MAX_INTENTOS_PIN:
            hasta = time.time() + self.SEGUNDOS_BLOQUEO_PIN
            self.guardar_preferencia("pin_bloqueado_hasta", f"{hasta:.2f}")
            self.guardar_preferencia("pin_intentos_fallidos", str(fallidos))
            return False, 0, self.SEGUNDOS_BLOQUEO_PIN

        self.guardar_preferencia("pin_intentos_fallidos", str(fallidos))
        return False, self.MAX_INTENTOS_PIN - fallidos, 0

    def cambiar_pin_docente(self, nuevo_pin: str):
        limpio = nuevo_pin.strip()
        nuevo_salt = secrets.token_hex(16)
        nuevo_hash = self._calcular_hash_pin(limpio, nuevo_salt)
        self.guardar_preferencia("pin_salt", nuevo_salt)
        self.guardar_preferencia("pin_hash", nuevo_hash)
        self.guardar_preferencia("pin_personalizado", "1" if limpio != "1234" else "0")
        self.guardar_preferencia("pin_intentos_fallidos", "0")
        self.guardar_preferencia("pin_bloqueado_hasta", "0")

    # --- GESTIÓN DE TAREAS ---
    def listar_tareas(self) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tareas ORDER BY es_predeterminada DESC, id ASC")
            filas = cursor.fetchall()
            resultado = []
            for f in filas:
                resultado.append({
                    "id": f["id"],
                    "nombre": f["nombre"],
                    "categoria": f["categoria"],
                    "pasos": json.loads(f["pasos_json"]),
                    "pistas": json.loads(f["pistas_json"]),
                    "es_predeterminada": bool(f["es_predeterminada"])
                })
            return resultado

    def obtener_tarea(self, nombre: str) -> Optional[Dict]:
        for t in self.listar_tareas():
            if t["nombre"].lower() == nombre.lower():
                return t
        return None

    def guardar_tarea(self, nombre: str, pasos: List[str], pistas: Optional[List[str]] = None,
                      categoria: str = "Personalizada") -> bool:
        pasos_limpios = [p.strip() for p in pasos if p and p.strip()]
        if not pasos_limpios:
            return False
        if not pistas or len(pistas) < len(pasos_limpios):
            pistas_completas = [p.strip() for p in (pistas or [])]
            while len(pistas_completas) < len(pasos_limpios):
                idx = len(pistas_completas) + 1
                pistas_completas.append(f"Haz solo el paso {idx} con calma. Si tienes dudas, pregúntale a Haru IA.")
        else:
            pistas_completas = [
                p.strip() if p and p.strip() else f"Haz solo el paso {i + 1} con calma."
                for i, p in enumerate(pistas[:len(pasos_limpios)])
            ]

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tareas (nombre, categoria, pasos_json, pistas_json, es_predeterminada, fecha_creacion)
                VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT(nombre) DO UPDATE SET
                    categoria = excluded.categoria,
                    pasos_json = excluded.pasos_json,
                    pistas_json = excluded.pistas_json
            """, (nombre.strip(), categoria, json.dumps(pasos_limpios, ensure_ascii=False),
                  json.dumps(pistas_completas, ensure_ascii=False), ahora))
            conn.commit()
        return True

    def eliminar_tarea(self, nombre: str) -> bool:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM tareas")
            if cursor.fetchone()["total"] <= 1:
                # Resguardo de integridad: siempre mantener al menos 1 misión disponible para el niño
                return False
            cursor.execute("DELETE FROM tareas WHERE nombre = ?", (nombre,))
            eliminado = cursor.rowcount > 0
            conn.commit()
            return eliminado

    def restaurar_misiones_predeterminadas(self) -> None:
        """Restaura las 4 misiones base sin borrar las misiones personalizadas creadas por el docente."""
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            for t in self.TAREAS_BASE:
                cursor.execute("""
                    INSERT INTO tareas (nombre, categoria, pasos_json, pistas_json, es_predeterminada, fecha_creacion)
                    VALUES (?, ?, ?, ?, 1, ?)
                    ON CONFLICT(nombre) DO UPDATE SET
                        categoria = excluded.categoria,
                        pasos_json = excluded.pasos_json,
                        pistas_json = excluded.pistas_json,
                        es_predeterminada = 1
                """, (
                    t["nombre"],
                    t["categoria"],
                    json.dumps(t["pasos"], ensure_ascii=False),
                    json.dumps(t["pistas"], ensure_ascii=False),
                    ahora,
                ))
            conn.commit()

    def limpiar_historial_progreso(self, reiniciar_estrellas: bool = False) -> None:
        """Limpia sesiones, bitácora de descansos y canjes de prueba (conservando PIN y misiones)."""
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sesiones_estudio")
            cursor.execute("DELETE FROM bitacora_descansos")
            cursor.execute("DELETE FROM historial_canjes")
            conn.commit()
        self.guardar_preferencia("tareas_completadas", "0")
        if reiniciar_estrellas:
            self.guardar_preferencia("estrellas_totales", "5")
            self.guardar_preferencia("estrellas_gastadas", "0")
            self.guardar_preferencia("avatar_skin", "ROBOT_KAWAII")
        else:
            # Conservar estrellas ganadas y liberar saldo disponible si se borran canjes de prueba
            self.guardar_preferencia("estrellas_gastadas", "0")

    # --- REGISTRO DE SESIONES, DESCANSOS DEL ALUMNO Y GAMIFICACIÓN ---
    def registrar_evento_descanso(self, nombre_tarea: str, paso_actual: int,
                                  segundos_transcurridos: int, motivo: str = "Botón Descanso Alumno"):
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bitacora_descansos (fecha_hora, nombre_tarea, paso_actual, segundos_transcurridos, motivo)
                VALUES (?, ?, ?, ?, ?)
            """, (ahora, nombre_tarea, paso_actual, segundos_transcurridos, motivo))
            conn.commit()

    def obtener_bitacora_descansos(self, limite: int = 30) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bitacora_descansos ORDER BY id DESC LIMIT ?", (limite,))
            return [dict(row) for row in cursor.fetchall()]

    def registrar_sesion(self, nombre_tarea: str, pasos_completados: int, total_pasos: int,
                         segundos_concentracion: int, pausas_activas: int,
                         pistas_usadas: int, estrellas_ganadas: int,
                         estado_final: str = "COMPLETADA",
                         pausas_manuales: int = 0,
                         intervalo_promedio_descanso_seg: int = 0):
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sesiones_estudio (
                    fecha_hora, nombre_tarea, pasos_completados, total_pasos,
                    segundos_concentracion, pausas_activas, pausas_manuales,
                    intervalo_promedio_descanso_seg, pistas_usadas,
                    estrellas_ganadas, estado_final
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ahora, nombre_tarea, pasos_completados, total_pasos,
                  segundos_concentracion, pausas_activas, pausas_manuales,
                  intervalo_promedio_descanso_seg, pistas_usadas,
                  estrellas_ganadas, estado_final))
            conn.commit()

        if estado_final == "COMPLETADA":
            actual_tareas = int(self.obtener_preferencia("tareas_completadas", "0"))
            self.guardar_preferencia("tareas_completadas", str(actual_tareas + 1))

    def sumar_estrellas(self, cantidad: int) -> int:
        actual = int(self.obtener_preferencia("estrellas_totales", "0"))
        nuevo = max(0, actual + cantidad)
        self.guardar_preferencia("estrellas_totales", str(nuevo))
        return nuevo

    def obtener_estrellas(self) -> int:
        return int(self.obtener_preferencia("estrellas_totales", "5"))

    def obtener_estrellas_gastadas(self) -> int:
        try:
            return max(0, int(self.obtener_preferencia("estrellas_gastadas", "0")))
        except ValueError:
            return 0

    def obtener_estrellas_disponibles(self) -> int:
        """Fichas disponibles para canjear premios reales sin perder medallas/trajes históricos."""
        return max(0, self.obtener_estrellas() - self.obtener_estrellas_gastadas())

    # --- TIENDA Y CANJE DE PREMIOS PACTADOS (ECONOMÍA DE FICHAS TDAH) ---
    def listar_recompensas_catalogo(self) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recompensas_catalogo ORDER BY costo_estrellas ASC, id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def agregar_recompensa_catalogo(self, titulo: str, costo_estrellas: int,
                                    descripcion: str = "Premio pactado con familia/docente") -> bool:
        tit = re.sub(r"\s+", " ", (titulo or "")).strip()[:90]
        costo = max(1, min(999, int(costo_estrellas)))
        desc = re.sub(r"\s+", " ", (descripcion or "")).strip()[:140]
        if not tit:
            return False
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                VALUES (?, ?, ?)
                ON CONFLICT(titulo) DO UPDATE SET
                    costo_estrellas = excluded.costo_estrellas,
                    descripcion = excluded.descripcion
            """, (tit, costo, desc))
            conn.commit()
        return True

    def eliminar_recompensa_catalogo(self, recompensa_id: int) -> bool:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM recompensas_catalogo WHERE id = ?", (int(recompensa_id),))
            ok = cursor.rowcount > 0
            conn.commit()
            return ok

    def restaurar_recompensas_predeterminadas(self) -> None:
        """Restaura o inserta el catálogo psicopedagógico escalonado sugerido (6 a 32 ⭐)."""
        with self._conectar() as conn:
            cursor = conn.cursor()
            for tit, costo, desc in self.RECOMPENSAS_SUGERIDAS:
                cursor.execute("""
                    INSERT INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                    VALUES (?, ?, ?)
                    ON CONFLICT(titulo) DO UPDATE SET
                        costo_estrellas = excluded.costo_estrellas,
                        descripcion = excluded.descripcion
                """, (tit, costo, desc))
            conn.commit()

    def canjear_recompensa(self, recompensa_id: int) -> Tuple[bool, str, int]:
        """Canjea un premio real verificando saldo disponible de forma atómica."""
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recompensas_catalogo WHERE id = ?", (int(recompensa_id),))
            fila = cursor.fetchone()
            if not fila:
                return False, "El premio seleccionado ya no existe.", self.obtener_estrellas_disponibles()

            titulo = fila["titulo"]
            costo = int(fila["costo_estrellas"])

            cursor.execute("SELECT valor FROM perfil_progreso WHERE clave = 'estrellas_totales'")
            r_tot = cursor.fetchone()
            totales = int(r_tot["valor"]) if r_tot else 5

            cursor.execute("SELECT valor FROM perfil_progreso WHERE clave = 'estrellas_gastadas'")
            r_gas = cursor.fetchone()
            gastadas = int(r_gas["valor"]) if r_gas else 0

            disponibles = max(0, totales - gastadas)
            if disponibles < costo:
                faltan = costo - disponibles
                return (
                    False,
                    f"Te faltan {faltan} ⭐ disponibles para canjear «{titulo}».",
                    disponibles,
                )

            nuevas_gastadas = gastadas + costo
            nuevo_saldo = max(0, totales - nuevas_gastadas)
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO perfil_progreso (clave, valor) VALUES ('estrellas_gastadas', ?)
                ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """, (str(nuevas_gastadas),))
            cursor.execute("""
                INSERT INTO historial_canjes (fecha_hora, titulo_premio, costo_estrellas)
                VALUES (?, ?, ?)
            """, (ahora, titulo, costo))
            conn.commit()
            return True, f"¡Felicidades! Canjeaste «{titulo}» (-{costo} ⭐).", nuevo_saldo

    def obtener_historial_canjes(self, limite: int = 30) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM historial_canjes ORDER BY id DESC LIMIT ?", (limite,))
            return [dict(row) for row in cursor.fetchall()]

    def obtener_preferencia(self, clave: str, defecto: str = "") -> str:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM perfil_progreso WHERE clave = ?", (clave,))
            row = cursor.fetchone()
            return row["valor"] if row else defecto

    def guardar_preferencia(self, clave: str, valor: str):
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO perfil_progreso (clave, valor) VALUES (?, ?)
                ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """, (clave, str(valor)))
            conn.commit()

    def obtener_historial_sesiones(self, limite: int = 50) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sesiones_estudio ORDER BY id DESC LIMIT ?", (limite,))
            return [dict(row) for row in cursor.fetchall()]

    def obtener_estadisticas_resumen(self) -> Dict:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_sesiones,
                    COALESCE(SUM(pasos_completados), 0) as total_pasos_logrados,
                    COALESCE(SUM(segundos_concentracion), 0) as total_segundos_foco,
                    COALESCE(SUM(pausas_activas), 0) as total_pausas_pomodoro,
                    COALESCE(SUM(pausas_manuales), 0) as total_pausas_alumno,
                    COALESCE(AVG(CASE WHEN intervalo_promedio_descanso_seg > 0 THEN intervalo_promedio_descanso_seg ELSE NULL END), 0) as promedio_cada_cuanto_descansa_seg,
                    COALESCE(SUM(pistas_usadas), 0) as total_pistas
                FROM sesiones_estudio
            """)
            r = dict(cursor.fetchone())
            r["estrellas_totales"] = self.obtener_estrellas()
            r["estrellas_disponibles"] = self.obtener_estrellas_disponibles()
            r["estrellas_gastadas"] = self.obtener_estrellas_gastadas()
            r["tareas_completadas"] = int(self.obtener_preferencia("tareas_completadas", "0"))
            return r

    def buscar_conocimiento(self, consulta: str) -> Optional[str]:
        """
        Busca respuestas escolares locales usando límites de palabra exactos (`\\b`)
        para no interceptar por accidente saludos acompañados de preguntas reales
        (ej. «Hola Haru, ¿por qué brillan las estrellas?» debe pasar a la IA).
        """
        consulta_norm = _quitar_tildes((consulta or "").lower()).strip()
        if not consulta_norm:
            return None

        palabras_consulta = re.findall(r"[a-z0-9ñ]+", consulta_norm)
        tiene_interrogativo_complejo = any(
            p in palabras_consulta
            for p in ("como", "por", "porque", "cuando", "donde", "cual", "cuales", "cuanto", "cuantos", "explica", "diferencia", "ejemplo")
        )

        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT palabra_clave, materia, respuesta_amigable FROM conocimiento_escolar")
            filas = cursor.fetchall()

        # Ordenar claves más específicas primero ("ciclo del agua" antes que "agua"/"hola")
        filas_ordenadas = sorted(filas, key=lambda r: len(r["palabra_clave"]), reverse=True)
        for row in filas_ordenadas:
            clave_norm = _quitar_tildes(row["palabra_clave"].lower()).strip()
            if not clave_norm:
                continue
            patron = rf"\b{re.escape(clave_norm)}\b"
            if not re.search(patron, consulta_norm):
                continue

            # Si es solo un saludo ("hola"), responder rápido únicamente si no trae otra pregunta detrás
            if clave_norm == "hola" and (len(palabras_consulta) > 4 or "?" in consulta or tiene_interrogativo_complejo):
                continue

            # Si es concepto corto de 1 palabra pero la pregunta pide explicación compleja más larga, dejar que la IA contextualice si está activa
            if len(clave_norm.split()) == 1 and len(palabras_consulta) > 7 and tiene_interrogativo_complejo and row["materia"] not in ("Identidad", "Apoyo Emocional"):
                continue

            return row["respuesta_amigable"]
        return None

    def exportar_reporte_csv(self, ruta_destino: str) -> str:
        sesiones = self.obtener_historial_sesiones(limite=300)
        with open(ruta_destino, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "Fecha y Hora", "Tarea Escolar", "Pasos Logrados",
                "Total Pasos", "Tiempo Foco", "Tiempo Foco (seg)", "Pausas Pomodoro",
                "Descansos Pedidos por Alumno", "Cada Cuánto Pide Descanso (seg)",
                "Pistas Solicitadas", "Estrellas Ganadas", "Estado"
            ])
            for s in sesiones:
                seg_foco = int(s.get("segundos_concentracion", 0))
                writer.writerow([
                    int(s["id"]),
                    _sanitizar_celda_csv(s["fecha_hora"]),
                    _sanitizar_celda_csv(s["nombre_tarea"]),
                    int(s["pasos_completados"]),
                    int(s["total_pasos"]),
                    _formatear_duracion_humana(seg_foco),
                    seg_foco,
                    int(s["pausas_activas"]),
                    int(s.get("pausas_manuales", 0)),
                    int(s.get("intervalo_promedio_descanso_seg", 0)),
                    int(s["pistas_usadas"]),
                    int(s["estrellas_ganadas"]),
                    _sanitizar_celda_csv(s["estado_final"]),
                ])
        return ruta_destino

    def exportar_reporte_html(self, ruta_destino: str) -> str:
        resumen = self.obtener_estadisticas_resumen()
        sesiones = self.obtener_historial_sesiones(limite=120)
        descansos = self.obtener_bitacora_descansos(limite=50)
        canjes = self.obtener_historial_canjes(limite=40)

        esc = lambda v: html.escape(str(v if v is not None else ""), quote=True)

        filas_html = ""
        for s in sesiones:
            pausas_m = int(s.get("pausas_manuales", 0))
            interv = int(s.get("intervalo_promedio_descanso_seg", 0))
            cada_cuanto = f"Cada {_formatear_duracion_humana(interv)}" if pausas_m > 0 else "Sin pausas"
            estado_limpio = esc(s.get("estado_final", "COMPLETADA"))
            badge_cls = "ok" if estado_limpio == "COMPLETADA" else "parcial"
            filas_html += f"""
            <tr>
                <td>{esc(s['fecha_hora'])}</td>
                <td><b>{esc(s['nombre_tarea'])}</b></td>
                <td>{int(s['pasos_completados'])}/{int(s['total_pasos'])}</td>
                <td>{_formatear_duracion_humana(int(s['segundos_concentracion']))}</td>
                <td>{pausas_m} ({esc(cada_cuanto)})</td>
                <td>{int(s['pistas_usadas'])}</td>
                <td>⭐ +{int(s['estrellas_ganadas'])} <span class="badge {badge_cls}">{estado_limpio}</span></td>
            </tr>
            """

        filas_descansos = ""
        for d in descansos:
            filas_descansos += f"""
            <tr>
                <td>{esc(d['fecha_hora'])}</td>
                <td>{esc(d['nombre_tarea'])}</td>
                <td>Paso {int(d['paso_actual'])}</td>
                <td>A los {_formatear_duracion_humana(int(d['segundos_transcurridos']))}</td>
                <td>{esc(d['motivo'])}</td>
            </tr>
            """

        filas_canjes = ""
        for c in canjes:
            filas_canjes += f"""
            <tr>
                <td>{esc(c['fecha_hora'])}</td>
                <td><b>{esc(c['titulo_premio'])}</b></td>
                <td>-{int(c['costo_estrellas'])} ⭐</td>
            </tr>
            """

        foco_total_str = _formatear_duracion_humana(int(resumen["total_segundos_foco"]))
        prom_desc_str = _formatear_duracion_humana(int(resumen["promedio_cada_cuanto_descansa_seg"]))

        doc_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reporte Psicopedagógico Haru TDAH</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f0fdfa; color: #0f172a; margin: 0; padding: 24px; line-height: 1.45; }}
  .container {{ max-width: 1080px; margin: 0 auto; }}
  .header {{ background: linear-gradient(135deg, #2d7d7b, #0284c7); color: white; padding: 22px 26px; border-radius: 18px; margin-bottom: 20px; word-wrap: break-word; }}
  .header h2 {{ margin: 0 0 6px 0; font-size: 22px; }}
  .header p {{ margin: 0; font-size: 13px; opacity: 0.94; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 12px; margin-bottom: 22px; }}
  .kpi {{ background: white; padding: 14px 16px; border-radius: 14px; border: 2px solid #99f6e4; text-align: center; box-shadow: 0 3px 10px rgba(0,0,0,0.04); overflow-wrap: anywhere; }}
  .kpi h3 {{ font-size: 23px; margin: 0 0 4px 0; color: #0f766e; }}
  .kpi p {{ margin: 0; font-size: 12px; color: #475569; font-weight: 600; }}
  h3.sec {{ color: #0f766e; margin: 24px 0 10px 0; font-size: 17px; }}
  .table-wrap {{ width: 100%; overflow-x: auto; background: white; border-radius: 12px; box-shadow: 0 3px 10px rgba(0,0,0,0.04); margin-bottom: 18px; border: 1px solid #cbd5e1; }}
  table {{ width: 100%; table-layout: fixed; border-collapse: collapse; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: left; font-size: 13px; vertical-align: top; word-wrap: break-word; overflow-wrap: anywhere; }}
  th {{ background: #ccfbf1; color: #115e59; font-weight: 700; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 2px 7px; border-radius: 8px; font-size: 11px; font-weight: 700; margin-left: 4px; }}
  .badge.ok {{ background: #dcfce7; color: #166534; }}
  .badge.parcial {{ background: #fef3c7; color: #92400e; }}
  @media print {{
    body {{ background: white; padding: 0; }}
    .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .table-wrap {{ overflow-x: visible; box-shadow: none; }}
    tr {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h2>📊 Reporte de Seguimiento Psicopedagógico — Asistente Educativo Haru (TDAH)</h2>
    <p>Universidad Salesiana de Bolivia • Cumplimiento Ley N.º 548 (Datos Anónimos Locales) y R.M. N.º 0069/2025</p>
  </div>
  <div class="kpis">
    <div class="kpi"><h3>{int(resumen['tareas_completadas'])}</h3><p>Misiones Completadas</p></div>
    <div class="kpi"><h3>{int(resumen['total_pasos_logrados'])}</h3><p>Micro-Pasos Logrados</p></div>
    <div class="kpi"><h3>{esc(foco_total_str)}</h3><p>Tiempo Foco Efectivo</p></div>
    <div class="kpi"><h3>{int(resumen['total_pausas_alumno'])} ({esc(prom_desc_str)})</h3><p>Descansos Alumno / Ritmo</p></div>
    <div class="kpi"><h3>⭐ {int(resumen['estrellas_totales'])}</h3><p>Nivel Total ({int(resumen['estrellas_disponibles'])} disp.)</p></div>
  </div>

  <h3 class="sec">1. Historial de Sesiones Guiadas</h3>
  <div class="table-wrap">
    <table>
      <colgroup>
        <col style="width:16%"><col style="width:27%"><col style="width:9%"><col style="width:11%">
        <col style="width:16%"><col style="width:7%"><col style="width:14%">
      </colgroup>
      <thead>
        <tr>
          <th>Fecha y Hora</th><th>Misión Escolar</th><th>Pasos</th><th>Foco Efectivo</th>
          <th>Descansos Alumno</th><th>Pistas</th><th>Recompensa</th>
        </tr>
      </thead>
      <tbody>{filas_html or '<tr><td colspan="7">Sin sesiones registradas aún.</td></tr>'}</tbody>
    </table>
  </div>

  <h3 class="sec">2. Bitácora Detallada de Descansos del Estudiante</h3>
  <div class="table-wrap">
    <table>
      <colgroup>
        <col style="width:18%"><col style="width:30%"><col style="width:10%"><col style="width:14%"><col style="width:28%">
      </colgroup>
      <thead>
        <tr>
          <th>Fecha y Hora</th><th>Misión</th><th>Paso</th><th>Momento</th><th>Detalle</th>
        </tr>
      </thead>
      <tbody>{filas_descansos or '<tr><td colspan="5">El estudiante aún no solicitó descansos manuales.</td></tr>'}</tbody>
    </table>
  </div>

  <h3 class="sec">3. Premios Reales Canjeados (Economía de Fichas)</h3>
  <div class="table-wrap">
    <table>
      <colgroup>
        <col style="width:22%"><col style="width:60%"><col style="width:18%">
      </colgroup>
      <thead>
        <tr>
          <th>Fecha y Hora</th><th>Premio Pactado</th><th>Estrellas Usadas</th>
        </tr>
      </thead>
      <tbody>{filas_canjes or '<tr><td colspan="3">Aún no se canjearon premios del catálogo familiar/escolar.</td></tr>'}</tbody>
    </table>
  </div>
</div>
</body>
</html>"""
        with open(ruta_destino, mode="w", encoding="utf-8") as f:
            f.write(doc_html)
        return ruta_destino
