"""
Repositorio Relacional Normalizado (3FN) en SQLite con Integridad Referencial y Auditoría
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Arquitectura Relacional Normalizada (1FN / 2FN / 3FN con `PRAGMA foreign_keys = ON`):
- `modulos`: Catálogo maestro de los 5 Módulos Curriculares oficiales.
- `tareas`: Misiones escolares vinculadas a `modulos(id)` mediante `modulo_id` (FK).
- `pasos_tarea`: Micro-pasos y pistas atómicas normalizadas (1FN) vinculadas a `tareas(id)` con `ON DELETE CASCADE`.
- `pensum_modulos`: Guías/pensum curriculares vinculados a `modulos(id)` mediante `modulo_id` (FK).
- `sesiones_estudio`: Historial de sesiones vinculado a `tareas(id)` y `modulos(id)` (`ON DELETE SET NULL` para preservar trazabilidad histórica).
- `bitacora_descansos`: Registro de descansos vinculado a `tareas(id)` y `modulos(id)` (`ON DELETE SET NULL`).
- `recompensas_catalogo`: Catálogo de premios reales pactados.
- `historial_canjes`: Canjes vinculados a `recompensas_catalogo(id)` mediante `recompensa_id` (`ON DELETE SET NULL`).
- `conocimiento_escolar`: Respuestas curriculares vinculadas a `modulos(id)` mediante `modulo_id` (FK).
- `auditoria_eventos`: Bitácora relacional de eventos críticos de seguridad, pedagogía y configuración.
- `perfil_progreso`: Estado de perfil local y hash criptográfico PBKDF2-HMAC-SHA256 del PIN docente.
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
    SCHEMA_VERSION = "3"
    PBKDF2_ITERATIONS = 120_000
    MAX_INTENTOS_PIN = 3
    SEGUNDOS_BLOQUEO_PIN = 45
    MODULOS_CURRICULARES = (
        "Matemáticas",
        "Lenguaje",
        "Ciencias",
        "Inglés",
        "Hábitos y Orden",
    )
    DESCRIPCIONES_MODULOS = {
        "Matemáticas": "Razonamiento lógico, cálculo aritmético y resolución guiada de problemas.",
        "Lenguaje": "Comprensión lectora, expresión oral/escrita y vocabulario estructurado.",
        "Ciencias": "Exploración de la naturaleza, el cuerpo humano y el entorno boliviano.",
        "Inglés": "Vocabulario bilingüe interactivo por asociación auditiva y visual.",
        "Hábitos y Orden": "Funciones ejecutivas, organización de útiles y rutinas de autonomía.",
    }
    RECOMPENSAS_SUGERIDAS = [
        ("5 min de dibujo o plastilina libre", 6, "Recompensa rápida alcanzable tras tu primera misión completada."),
        ("Escuchar mi canción favorita", 10, "Elegir una canción alegre en casa o en el aula."),
        ("Sello o insignia campeón en mi cuaderno", 15, "Reconocimiento por orden y atención paso a paso."),
        ("Elegir juego de mesa o recreo especial", 22, "Premio intermedio pactado con familia o docente."),
        ("Cuento, paseo o tarde especial en familia", 32, "Gran meta semanal por constancia y esfuerzo."),
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
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    def _obtener_o_crear_modulo_id(self, cursor: sqlite3.Cursor, categoria: str) -> int:
        mod_norm = self.normalizar_modulo(categoria)
        cursor.execute("SELECT id FROM modulos WHERE nombre = ?", (mod_norm,))
        fila = cursor.fetchone()
        if fila:
            return int(fila["id"])
        orden = (
            self.MODULOS_CURRICULARES.index(mod_norm) + 1
            if mod_norm in self.MODULOS_CURRICULARES
            else 99
        )
        desc = self.DESCRIPCIONES_MODULOS.get(mod_norm, "Módulo curricular escolar.")
        cursor.execute(
            "INSERT INTO modulos (nombre, descripcion, orden) VALUES (?, ?, ?)",
            (mod_norm, desc, orden),
        )
        return int(cursor.lastrowid)

    def _sincronizar_pasos_normalizados(
        self, cursor: sqlite3.Cursor, tarea_id: int, pasos: List[str], pistas: List[str]
    ) -> None:
        """Sincroniza la tabla relacional 1FN `pasos_tarea` para la tarea indicada."""
        cursor.execute("DELETE FROM pasos_tarea WHERE tarea_id = ?", (int(tarea_id),))
        for idx, texto_paso in enumerate(pasos, start=1):
            pista = (
                pistas[idx - 1]
                if idx - 1 < len(pistas) and pistas[idx - 1]
                else f"Haz solo el paso {idx} con calma."
            )
            cursor.execute(
                """
                INSERT INTO pasos_tarea (tarea_id, numero_paso, instruccion, pista_apoyo)
                VALUES (?, ?, ?, ?)
                """,
                (int(tarea_id), idx, str(texto_paso).strip(), str(pista).strip()),
            )

    def _inicializar_tablas(self):
        with self._conectar() as conn:
            cursor = conn.cursor()

            # 1. Tabla Maestra de Módulos Curriculares (Entidad Fuerte)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS modulos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    descripcion TEXT NOT NULL DEFAULT '',
                    orden INTEGER NOT NULL DEFAULT 1
                )
            """)
            for idx, mod_nom in enumerate(self.MODULOS_CURRICULARES, start=1):
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO modulos (nombre, descripcion, orden)
                    VALUES (?, ?, ?)
                    """,
                    (mod_nom, self.DESCRIPCIONES_MODULOS.get(mod_nom, ""), idx),
                )

            # 2. Tabla de Tareas Escolares (con FK a modulos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tareas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE RESTRICT,
                    nombre TEXT UNIQUE NOT NULL,
                    categoria TEXT NOT NULL DEFAULT 'Matemáticas',
                    pasos_json TEXT NOT NULL DEFAULT '[]',
                    pistas_json TEXT NOT NULL DEFAULT '[]',
                    es_predeterminada INTEGER NOT NULL DEFAULT 0,
                    fecha_creacion TEXT NOT NULL
                )
            """)

            # 3. Tabla Normalizada 1FN/3FN de Micro-Pasos y Pistas por Tarea (con FK a tareas)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pasos_tarea (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER NOT NULL REFERENCES tareas(id) ON UPDATE CASCADE ON DELETE CASCADE,
                    numero_paso INTEGER NOT NULL,
                    instruccion TEXT NOT NULL,
                    pista_apoyo TEXT NOT NULL,
                    UNIQUE(tarea_id, numero_paso)
                )
            """)

            # 4. Tabla de Historial de Sesiones Guiadas (con FKs a tareas y modulos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sesiones_estudio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER REFERENCES tareas(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE SET NULL,
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

            # 5. Bitácora Detallada de Descansos del Estudiante (con FKs a tareas y modulos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bitacora_descansos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarea_id INTEGER REFERENCES tareas(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    fecha_hora TEXT NOT NULL,
                    nombre_tarea TEXT NOT NULL,
                    paso_actual INTEGER NOT NULL,
                    segundos_transcurridos INTEGER NOT NULL,
                    motivo TEXT NOT NULL DEFAULT 'Botón Descanso Alumno'
                )
            """)

            # 6. Perfil de Gamificación, Seguridad PIN (PBKDF2) y Preferencias
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS perfil_progreso (
                    clave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                )
            """)

            # 7. Base de Conocimiento Educativo Verificado (con FK a modulos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conocimiento_escolar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    palabra_clave TEXT UNIQUE NOT NULL,
                    materia TEXT NOT NULL,
                    respuesta_amigable TEXT NOT NULL
                )
            """)

            # 8. Catálogo de Premios Reales Pactados (Economía de Fichas TDAH)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recompensas_catalogo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titulo TEXT UNIQUE NOT NULL,
                    costo_estrellas INTEGER NOT NULL,
                    descripcion TEXT NOT NULL DEFAULT ''
                )
            """)

            # 9. Historial de Canjes de Puntos por Premios (con FK a recompensas_catalogo)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historial_canjes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recompensa_id INTEGER REFERENCES recompensas_catalogo(id) ON UPDATE CASCADE ON DELETE SET NULL,
                    fecha_hora TEXT NOT NULL,
                    titulo_premio TEXT NOT NULL,
                    costo_estrellas INTEGER NOT NULL
                )
            """)

            # 10. Pensum / Guías Escolares por Módulo (con FK a modulos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pensum_modulos (
                    categoria TEXT PRIMARY KEY,
                    modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE CASCADE,
                    nombre_archivo TEXT NOT NULL,
                    contenido_resumen TEXT NOT NULL,
                    fecha_actualizacion TEXT NOT NULL
                )
            """)

            # 11. Bitácora Relacional de Auditoría y Seguridad del Sistema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auditoria_eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha_hora TEXT NOT NULL,
                    tipo_evento TEXT NOT NULL,
                    entidad TEXT NOT NULL DEFAULT 'SISTEMA',
                    referencia_id INTEGER,
                    detalle TEXT NOT NULL
                )
            """)

            self._migrar_esquema_relacional_3fn(cursor)
            conn.commit()

    def _migrar_esquema_relacional_3fn(self, cursor: sqlite3.Cursor) -> None:
        """
        Actualiza de forma transparente bases de datos previas agregando las llaves
        foráneas (`modulo_id`, `tarea_id`, `recompensa_id`) y poblando `pasos_tarea`.
        """
        def _cols(tabla: str) -> List[str]:
            cursor.execute(f"PRAGMA table_info({tabla})")
            return [r["name"] for r in cursor.fetchall()]

        cols_tareas = _cols("tareas")
        if "modulo_id" not in cols_tareas:
            cursor.execute(
                "ALTER TABLE tareas ADD COLUMN modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE RESTRICT"
            )

        cols_sesiones = _cols("sesiones_estudio")
        if "pausas_manuales" not in cols_sesiones:
            cursor.execute("ALTER TABLE sesiones_estudio ADD COLUMN pausas_manuales INTEGER NOT NULL DEFAULT 0")
        if "intervalo_promedio_descanso_seg" not in cols_sesiones:
            cursor.execute("ALTER TABLE sesiones_estudio ADD COLUMN intervalo_promedio_descanso_seg INTEGER NOT NULL DEFAULT 0")
        if "tarea_id" not in cols_sesiones:
            cursor.execute(
                "ALTER TABLE sesiones_estudio ADD COLUMN tarea_id INTEGER REFERENCES tareas(id) ON UPDATE CASCADE ON DELETE SET NULL"
            )
        if "modulo_id" not in cols_sesiones:
            cursor.execute(
                "ALTER TABLE sesiones_estudio ADD COLUMN modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE SET NULL"
            )

        cols_descansos = _cols("bitacora_descansos")
        if "tarea_id" not in cols_descansos:
            cursor.execute(
                "ALTER TABLE bitacora_descansos ADD COLUMN tarea_id INTEGER REFERENCES tareas(id) ON UPDATE CASCADE ON DELETE SET NULL"
            )
        if "modulo_id" not in cols_descansos:
            cursor.execute(
                "ALTER TABLE bitacora_descansos ADD COLUMN modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE SET NULL"
            )

        cols_canjes = _cols("historial_canjes")
        if "recompensa_id" not in cols_canjes:
            cursor.execute(
                "ALTER TABLE historial_canjes ADD COLUMN recompensa_id INTEGER REFERENCES recompensas_catalogo(id) ON UPDATE CASCADE ON DELETE SET NULL"
            )

        cols_conoc = _cols("conocimiento_escolar")
        if "modulo_id" not in cols_conoc:
            cursor.execute(
                "ALTER TABLE conocimiento_escolar ADD COLUMN modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE SET NULL"
            )

        cols_pensum = _cols("pensum_modulos")
        if "modulo_id" not in cols_pensum:
            cursor.execute(
                "ALTER TABLE pensum_modulos ADD COLUMN modulo_id INTEGER REFERENCES modulos(id) ON UPDATE CASCADE ON DELETE CASCADE"
            )

        # Poblar modulo_id y pasos_tarea para tareas existentes
        cursor.execute("SELECT id, categoria, pasos_json, pistas_json, modulo_id FROM tareas")
        for t in cursor.fetchall():
            mod_id = self._obtener_o_crear_modulo_id(cursor, t["categoria"])
            if t["modulo_id"] != mod_id:
                cursor.execute(
                    "UPDATE tareas SET modulo_id = ?, categoria = ? WHERE id = ?",
                    (mod_id, self.normalizar_modulo(t["categoria"]), t["id"]),
                )
            cursor.execute("SELECT COUNT(*) as c FROM pasos_tarea WHERE tarea_id = ?", (t["id"],))
            if cursor.fetchone()["c"] == 0:
                try:
                    pasos = json.loads(t["pasos_json"] or "[]")
                    pistas = json.loads(t["pistas_json"] or "[]")
                    if pasos:
                        self._sincronizar_pasos_normalizados(cursor, int(t["id"]), pasos, pistas)
                except Exception:
                    pass

        # Enlazar registros históricos existentes con sus FKs correspondientes
        cursor.execute("""
            UPDATE sesiones_estudio
            SET tarea_id = (SELECT id FROM tareas WHERE LOWER(tareas.nombre) = LOWER(sesiones_estudio.nombre_tarea)),
                modulo_id = (SELECT modulo_id FROM tareas WHERE LOWER(tareas.nombre) = LOWER(sesiones_estudio.nombre_tarea))
            WHERE tarea_id IS NULL
        """)
        cursor.execute("""
            UPDATE bitacora_descansos
            SET tarea_id = (SELECT id FROM tareas WHERE LOWER(tareas.nombre) = LOWER(bitacora_descansos.nombre_tarea)),
                modulo_id = (SELECT modulo_id FROM tareas WHERE LOWER(tareas.nombre) = LOWER(bitacora_descansos.nombre_tarea))
            WHERE tarea_id IS NULL
        """)
        cursor.execute("""
            UPDATE historial_canjes
            SET recompensa_id = (SELECT id FROM recompensas_catalogo WHERE LOWER(recompensas_catalogo.titulo) = LOWER(historial_canjes.titulo_premio))
            WHERE recompensa_id IS NULL
        """)
        cursor.execute("SELECT categoria FROM pensum_modulos WHERE modulo_id IS NULL")
        for row_p in cursor.fetchall():
            mid = self._obtener_o_crear_modulo_id(cursor, row_p["categoria"])
            cursor.execute("UPDATE pensum_modulos SET modulo_id = ? WHERE categoria = ?", (mid, row_p["categoria"]))

    def registrar_evento_auditoria(
        self,
        tipo_evento: str,
        entidad: str,
        detalle: str,
        referencia_id: Optional[int] = None,
    ) -> None:
        """Registra un evento trazable en la tabla relacional `auditoria_eventos`."""
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._conectar() as conn:
                conn.execute(
                    """
                    INSERT INTO auditoria_eventos (fecha_hora, tipo_evento, entidad, referencia_id, detalle)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        ahora,
                        (tipo_evento or "EVENTO").strip()[:50],
                        (entidad or "SISTEMA").strip()[:50],
                        int(referencia_id) if referencia_id is not None else None,
                        (detalle or "").strip()[:300],
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def obtener_auditoria_eventos(self, limite: int = 50) -> List[Dict]:
        """Devuelve los eventos recientes de auditoría del sistema."""
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM auditoria_eventos ORDER BY id DESC LIMIT ?",
                (max(1, int(limite)),),
            )
            return [dict(r) for r in cursor.fetchall()]

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
        {
            "nombre": "Inglés - Jugando con Palabras",
            "categoria": "Inglés",
            "pasos": [
                "¡Hello! Vamos a aprender inglés. Primero, saca tu cuaderno y ponte cómodo en tu silla para empezar.",
                "Busca algo de color azul cerca de ti y tócalo. Azul en inglés se dice BLUE. ¡Repite conmigo: BLUE!",
                "Ahora, haz el sonido de un gatito. ¡Miau! Gato en inglés se dice CAT. ¡Dilo muy fuerte: CAT!",
                "¡You are a champion! Para terminar, da tres aplausos mientras cuentas: One, Two, Three! ¡Y guarda tu cuaderno!",
            ],
            "pistas": [
                "Solo necesitas tu cuaderno de inglés y estar bien sentado.",
                "Puede ser un lápiz, un juguete o tu ropa que sea de color blue (azul).",
                "Imagina que eres un gatito (cat) y haz su sonido.",
                "One es uno, Two es dos, Three es tres. ¡Aplaude en cada número y luego guarda tus cosas!",
            ],
        },
    ]

    def _insertar_tarea_base_con_pasos(self, cursor: sqlite3.Cursor, t: Dict, ahora: str) -> None:
        mod_norm = self.normalizar_modulo(t["categoria"])
        mod_id = self._obtener_o_crear_modulo_id(cursor, mod_norm)
        cursor.execute(
            """
            INSERT OR IGNORE INTO tareas (modulo_id, nombre, categoria, pasos_json, pistas_json, es_predeterminada, fecha_creacion)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                mod_id,
                t["nombre"],
                mod_norm,
                json.dumps(t["pasos"], ensure_ascii=False),
                json.dumps(t["pistas"], ensure_ascii=False),
                ahora,
            ),
        )
        cursor.execute("SELECT id FROM tareas WHERE nombre = ?", (t["nombre"],))
        row_t = cursor.fetchone()
        if row_t:
            cursor.execute("SELECT COUNT(*) as c FROM pasos_tarea WHERE tarea_id = ?", (row_t["id"],))
            if cursor.fetchone()["c"] == 0:
                self._sincronizar_pasos_normalizados(cursor, int(row_t["id"]), t["pasos"], t["pistas"])

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
            ("bolivia", "Ciencias", "Bolivia está en el corazón de Sudamérica, tiene 9 departamentos, su capital constitucional es Sucre y su sede de gobierno es La Paz."),
            ("cansado", "Hábitos y Orden", "¡Es normal sentirse cansado! Presiona el botón Respirar para inhalar como oliendo una flor y soplar como una velita."),
            ("dificil", "Hábitos y Orden", "¡No te preocupes! Cuando algo parece difícil, lo partimos en pedacitos pequeños. Hagamos solo este paso juntos."),
            ("difícil", "Hábitos y Orden", "¡No te preocupes! Cuando algo parece difícil, lo partimos en pedacitos pequeños. Hagamos solo este paso juntos."),
            ("como estas", "Conversación", "¡Estoy súper feliz y orgulloso de acompañarte hoy! ¿Y tú cómo te sientes después de avanzar en tus actividades?"),
            ("cómo estás", "Conversación", "¡Estoy súper feliz y orgulloso de acompañarte hoy! ¿Y tú cómo te sientes después de avanzar en tus actividades?"),
            ("que haces", "Conversación", "Aquí descansando tranquilo contigo en mi modo compañero. ¡Podemos charlar de tus tareas, curiosidades o contar una adivinanza!"),
            ("qué haces", "Conversación", "Aquí descansando tranquilo contigo en mi modo compañero. ¡Podemos charlar de tus tareas, curiosidades o contar una adivinanza!"),
            ("gracias", "Conversación", "¡De nada, campeón! Aprender contigo es mi parte favorita del día."),
            ("aburrido", "Conversación", "¡Podemos hacer algo divertido! Prueba el Reto de Colores con cámara, pídeme un chiste o pregúntame sobre dinosaurios o planetas."),
            ("feliz", "Hábitos y Orden", "¡Qué alegría escuchar eso! Cuando celebramos nuestros logros con calma, nuestro cerebro aprende cada día mejor."),
            ("adivinanza", "Lenguaje", "¡Adivina adivinador! Blanca por dentro, verde por fuera; si quieres que te lo diga, es-pera. ¡La pera!"),
            ("cuento", "Lenguaje", "Había una vez una pequeña estrellita andina que brillaba poquito, pero dando un pasito cada noche iluminó todo el cielo de Bolivia."),
            ("dinosaurio", "Ciencias", "Los dinosaurios vivieron hace millones de años; algunos como el Triceratops comían plantas y en Sucre, Bolivia, ¡hay miles de sus huellas en Cal Orck'o!"),
            ("dinosaurios", "Ciencias", "Los dinosaurios vivieron hace millones de años; algunos como el Triceratops comían plantas y en Sucre, Bolivia, ¡hay miles de sus huellas en Cal Orck'o!"),
            ("ingles", "Inglés", "¡En inglés podemos jugar con colores y animales! Por ejemplo: azul es BLUE, rojo es RED, gato es CAT, perro es DOG y contamos One, Two, Three."),
            ("inglés", "Inglés", "¡En inglés podemos jugar con colores y animales! Por ejemplo: azul es BLUE, rojo es RED, gato es CAT, perro es DOG y contamos One, Two, Three."),
            ("colores en ingles", "Inglés", "Los colores básicos en inglés son: Azul = BLUE, Rojo = RED, Amarillo = YELLOW, Verde = GREEN. ¡Repítelos conmigo!"),
            ("numeros en ingles", "Inglés", "Del 1 al 5 en inglés se cuenta así: One (1), Two (2), Three (3), Four (4), Five (5). ¡You are a champion!"),
        ]

        with self._conectar() as conn:
            cursor = conn.cursor()
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("SELECT COUNT(*) as total FROM tareas")
            if cursor.fetchone()["total"] == 0:
                for t in tareas_base:
                    self._insertar_tarea_base_con_pasos(cursor, t, ahora)
            else:
                for t in tareas_base:
                    if t["categoria"] == "Inglés":
                        self._insertar_tarea_base_con_pasos(cursor, t, ahora)

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
                "comprobacion_activa": "1",
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
            cursor.execute(
                "UPDATE perfil_progreso SET valor = ? WHERE clave = 'schema_version'",
                (self.SCHEMA_VERSION,),
            )

            cursor.execute("DELETE FROM perfil_progreso WHERE clave = 'gemini_api_key'")

            for clave, materia, resp in conocimiento_base:
                mod_id = (
                    self._obtener_o_crear_modulo_id(cursor, materia)
                    if materia in self.MODULOS_CURRICULARES
                    else None
                )
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO conocimiento_escolar (modulo_id, palabra_clave, materia, respuesta_amigable)
                    VALUES (?, ?, ?, ?)
                    """,
                    (mod_id, clave, materia, resp),
                )

            reemplazos_legado = [
                ("🎨 5 min de dibujo o plastilina libre", "5 min de dibujo o plastilina libre"),
                ("🎵 Escuchar mi canción favorita", "Escuchar mi canción favorita"),
                ("🌟 Sticker o sello campeón en mi cuaderno", "Sello o insignia campeón en mi cuaderno"),
                ("🎲 Elegir juego de mesa o recreo especial", "Elegir juego de mesa o recreo especial"),
                ("🍿 Cuento, paseo o tarde especial en familia", "Cuento, paseo o tarde especial en familia"),
            ]
            for ant, nvo in reemplazos_legado:
                cursor.execute("UPDATE OR IGNORE recompensas_catalogo SET titulo = ? WHERE titulo = ?", (nvo, ant))
                cursor.execute("DELETE FROM recompensas_catalogo WHERE titulo = ?", (ant,))

            cursor.execute("SELECT COUNT(*) as total FROM recompensas_catalogo")
            if cursor.fetchone()["total"] == 0:
                for tit, costo, desc in self.RECOMPENSAS_SUGERIDAS:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                        VALUES (?, ?, ?)
                        """,
                        (tit, costo, desc),
                    )
            else:
                cursor.execute("SELECT COUNT(*) as c FROM recompensas_catalogo WHERE costo_estrellas <= 6")
                if cursor.fetchone()["c"] == 0:
                    tit0, costo0, desc0 = self.RECOMPENSAS_SUGERIDAS[0]
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                        VALUES (?, ?, ?)
                        """,
                        (tit0, costo0, desc0),
                    )

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
            self.registrar_evento_auditoria("PIN_EXITOSO", "SEGURIDAD", "Acceso docente autorizado")
            return True, self.MAX_INTENTOS_PIN, 0

        fallidos = int(self.obtener_preferencia("pin_intentos_fallidos", "0")) + 1
        if fallidos >= self.MAX_INTENTOS_PIN:
            hasta = time.time() + self.SEGUNDOS_BLOQUEO_PIN
            self.guardar_preferencia("pin_bloqueado_hasta", f"{hasta:.2f}")
            self.guardar_preferencia("pin_intentos_fallidos", str(fallidos))
            self.registrar_evento_auditoria(
                "PIN_BLOQUEADO",
                "SEGURIDAD",
                f"Bloqueo temporal por {self.SEGUNDOS_BLOQUEO_PIN}s tras {fallidos} intentos fallidos",
            )
            return False, 0, self.SEGUNDOS_BLOQUEO_PIN

        self.guardar_preferencia("pin_intentos_fallidos", str(fallidos))
        self.registrar_evento_auditoria(
            "PIN_FALLIDO",
            "SEGURIDAD",
            f"Intento fallido #{fallidos} de ingreso al Panel Docente",
        )
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
        self.registrar_evento_auditoria("PIN_CAMBIADO", "SEGURIDAD", "Actualización de PIN docente con PBKDF2-HMAC-SHA256")

    # --- GESTIÓN DE MÓDULOS CURRICULARES, TAREAS Y PENSUM ---
    def normalizar_modulo(self, categoria: str) -> str:
        """Unifica nombres de categorías hacia los 5 Módulos Curriculares oficiales."""
        cat = _quitar_tildes((categoria or "").strip().lower())
        if any(k in cat for k in ("ingl", "english")):
            return "Inglés"
        if any(k in cat for k in ("matem", "aritmet", "calcul")):
            return "Matemáticas"
        if any(k in cat for k in ("lengu", "lectur", "comunic")):
            return "Lenguaje"
        if any(k in cat for k in ("cienc", "natural", "social", "biolog")):
            return "Ciencias"
        if any(k in cat for k in ("habit", "orden", "organiz", "rutin")):
            return "Hábitos y Orden"
        for mod in self.MODULOS_CURRICULARES:
            if _quitar_tildes(mod.lower()) == cat:
                return mod
        return (categoria or "Matemáticas").strip() or "Matemáticas"

    def listar_tareas(self) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.id, t.modulo_id, t.nombre, t.categoria, t.pasos_json, t.pistas_json,
                       t.es_predeterminada, m.nombre AS nombre_modulo
                FROM tareas t
                LEFT JOIN modulos m ON t.modulo_id = m.id
                ORDER BY t.es_predeterminada DESC, t.id ASC
            """)
            filas = cursor.fetchall()
            resultado = []
            for f in filas:
                tid = int(f["id"])
                cursor.execute(
                    "SELECT instruccion, pista_apoyo FROM pasos_tarea WHERE tarea_id = ? ORDER BY numero_paso ASC",
                    (tid,),
                )
                filas_pasos = cursor.fetchall()
                if filas_pasos:
                    pasos = [r["instruccion"] for r in filas_pasos]
                    pistas = [r["pista_apoyo"] for r in filas_pasos]
                else:
                    pasos = json.loads(f["pasos_json"] or "[]")
                    pistas = json.loads(f["pistas_json"] or "[]")
                cat_efectiva = f["nombre_modulo"] or f["categoria"]
                resultado.append({
                    "id": tid,
                    "modulo_id": f["modulo_id"],
                    "nombre": f["nombre"],
                    "categoria": self.normalizar_modulo(cat_efectiva),
                    "pasos": pasos,
                    "pistas": pistas,
                    "es_predeterminada": bool(f["es_predeterminada"]),
                })
            return resultado

    def listar_tareas_por_modulo(self, categoria: str) -> List[Dict]:
        """Filtra las misiones pertenecientes a un Módulo Curricular específico."""
        todas = self.listar_tareas()
        if not categoria or categoria.strip().lower() in ("todos", "todas", ""):
            return todas
        mod_norm = self.normalizar_modulo(categoria)
        return [t for t in todas if self.normalizar_modulo(t.get("categoria", "")) == mod_norm]

    def obtener_progreso_modulos(self) -> Dict[str, Tuple[int, int]]:
        """
        Retorna `{modulo: (misiones_completadas, total_misiones)}` usando tanto la llave
        foránea `tarea_id` como el nombre para mantener trazabilidad incluso si se renombra.
        """
        tareas = self.listar_tareas()
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT tarea_id, LOWER(nombre_tarea) AS nt FROM sesiones_estudio WHERE estado_final = 'COMPLETADA'"
            )
            filas_comp = cursor.fetchall()
            ids_completados = {int(r["tarea_id"]) for r in filas_comp if r["tarea_id"] is not None}
            nombres_completados = {r["nt"] for r in filas_comp if r["nt"]}

        progreso: Dict[str, Tuple[int, int]] = {}
        for mod in self.MODULOS_CURRICULARES:
            tareas_mod = [t for t in tareas if self.normalizar_modulo(t.get("categoria", "")) == mod]
            total = len(tareas_mod)
            hechas = sum(
                1
                for t in tareas_mod
                if int(t["id"]) in ids_completados or t["nombre"].lower() in nombres_completados
            )
            progreso[mod] = (hechas, total)
        return progreso

    def guardar_pensum_modulo(self, categoria: str, nombre_archivo: str, texto: str) -> None:
        """Guarda el resumen del pensum o guía escolar de un módulo enlazado a `modulos(id)`."""
        mod = self.normalizar_modulo(categoria)
        resumen = re.sub(r"\s+", " ", (texto or "")).strip()[:2400]
        if not resumen:
            return
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        arch_limpio = (nombre_archivo or "Guia_Escolar").strip()[:120]
        with self._conectar() as conn:
            cursor = conn.cursor()
            mod_id = self._obtener_o_crear_modulo_id(cursor, mod)
            cursor.execute(
                """
                INSERT INTO pensum_modulos (categoria, modulo_id, nombre_archivo, contenido_resumen, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(categoria) DO UPDATE SET
                    modulo_id = excluded.modulo_id,
                    nombre_archivo = excluded.nombre_archivo,
                    contenido_resumen = excluded.contenido_resumen,
                    fecha_actualizacion = excluded.fecha_actualizacion
                """,
                (mod, mod_id, arch_limpio, resumen, ahora),
            )
            conn.commit()
        self.registrar_evento_auditoria(
            "PENSUM_CARGADO",
            "MODULOS",
            f"Pensum actualizado para {mod} ({arch_limpio})",
            referencia_id=mod_id,
        )

    def obtener_pensum_modulo(self, categoria: str) -> Optional[Dict[str, str]]:
        """Recupera el pensum/contexto escolar guardado para el módulo indicado."""
        mod = self.normalizar_modulo(categoria)
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.categoria, p.modulo_id, p.nombre_archivo, p.contenido_resumen, p.fecha_actualizacion
                FROM pensum_modulos p
                LEFT JOIN modulos m ON p.modulo_id = m.id
                WHERE p.categoria = ? OR m.nombre = ?
                """,
                (mod, mod),
            )
            fila = cursor.fetchone()
            return dict(fila) if fila else None

    def guardar_lote_tareas(
        self, lista_tareas: List[Dict], categoria_defecto: str = "Matemáticas"
    ) -> int:
        guardadas = 0
        for item in lista_tareas or []:
            nombre = str(item.get("nombre", "")).strip()
            pasos = item.get("pasos") or []
            pistas = item.get("pistas") or []
            cat = self.normalizar_modulo(str(item.get("categoria") or categoria_defecto))
            if nombre and pasos and self.guardar_tarea(nombre, pasos, pistas, categoria=cat):
                guardadas += 1
        return guardadas

    def obtener_tarea(self, nombre: str) -> Optional[Dict]:
        for t in self.listar_tareas():
            if t["nombre"].lower() == nombre.lower():
                return t
        return None

    def guardar_tarea(
        self,
        nombre: str,
        pasos: List[str],
        pistas: Optional[List[str]] = None,
        categoria: str = "Personalizada",
    ) -> bool:
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

        mod_norm = self.normalizar_modulo(categoria)
        nombre_limpio = nombre.strip()
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            mod_id = self._obtener_o_crear_modulo_id(cursor, mod_norm)
            cursor.execute(
                """
                INSERT INTO tareas (modulo_id, nombre, categoria, pasos_json, pistas_json, es_predeterminada, fecha_creacion)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(nombre) DO UPDATE SET
                    modulo_id = excluded.modulo_id,
                    categoria = excluded.categoria,
                    pasos_json = excluded.pasos_json,
                    pistas_json = excluded.pistas_json
                """,
                (
                    mod_id,
                    nombre_limpio,
                    mod_norm,
                    json.dumps(pasos_limpios, ensure_ascii=False),
                    json.dumps(pistas_completas, ensure_ascii=False),
                    ahora,
                ),
            )
            cursor.execute("SELECT id FROM tareas WHERE nombre = ?", (nombre_limpio,))
            tarea_id = int(cursor.fetchone()["id"])
            self._sincronizar_pasos_normalizados(cursor, tarea_id, pasos_limpios, pistas_completas)
            conn.commit()
        self.registrar_evento_auditoria(
            "TAREA_GUARDADA",
            "TAREAS",
            f"Misión '{nombre_limpio}' ({mod_norm}) guardada con {len(pasos_limpios)} pasos",
            referencia_id=tarea_id,
        )
        return True

    def eliminar_tarea(self, nombre: str) -> bool:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM tareas")
            if cursor.fetchone()["total"] <= 1:
                return False
            cursor.execute("SELECT id FROM tareas WHERE nombre = ?", (nombre,))
            row = cursor.fetchone()
            tid = int(row["id"]) if row else None
            cursor.execute("DELETE FROM tareas WHERE nombre = ?", (nombre,))
            eliminado = cursor.rowcount > 0
            conn.commit()
        if eliminado:
            self.registrar_evento_auditoria("TAREA_ELIMINADA", "TAREAS", f"Misión '{nombre}' eliminada", referencia_id=tid)
        return eliminado

    def restaurar_misiones_predeterminadas(self) -> None:
        """Restaura las 5 misiones base junto con sus pasos normalizados."""
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            for t in self.TAREAS_BASE:
                mod_norm = self.normalizar_modulo(t["categoria"])
                mod_id = self._obtener_o_crear_modulo_id(cursor, mod_norm)
                cursor.execute(
                    """
                    INSERT INTO tareas (modulo_id, nombre, categoria, pasos_json, pistas_json, es_predeterminada, fecha_creacion)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(nombre) DO UPDATE SET
                        modulo_id = excluded.modulo_id,
                        categoria = excluded.categoria,
                        pasos_json = excluded.pasos_json,
                        pistas_json = excluded.pistas_json,
                        es_predeterminada = 1
                    """,
                    (
                        mod_id,
                        t["nombre"],
                        mod_norm,
                        json.dumps(t["pasos"], ensure_ascii=False),
                        json.dumps(t["pistas"], ensure_ascii=False),
                        ahora,
                    ),
                )
                cursor.execute("SELECT id FROM tareas WHERE nombre = ?", (t["nombre"],))
                tid = int(cursor.fetchone()["id"])
                self._sincronizar_pasos_normalizados(cursor, tid, t["pasos"], t["pistas"])
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
            self.guardar_preferencia("estrellas_gastadas", "0")
        self.registrar_evento_auditoria(
            "HISTORIAL_LIMPIADO",
            "SESIONES",
            f"Limpieza de historial (reiniciar_estrellas={reiniciar_estrellas})",
        )

    # --- REGISTRO DE SESIONES, DESCANSOS DEL ALUMNO Y GAMIFICACIÓN ---
    def _resolver_fk_tarea_y_modulo(
        self, cursor: sqlite3.Cursor, nombre_tarea: str
    ) -> Tuple[Optional[int], Optional[int]]:
        cursor.execute(
            "SELECT id, modulo_id FROM tareas WHERE LOWER(nombre) = LOWER(?)",
            ((nombre_tarea or "").strip(),),
        )
        fila = cursor.fetchone()
        if fila:
            return int(fila["id"]), (int(fila["modulo_id"]) if fila["modulo_id"] is not None else None)
        return None, None

    def registrar_evento_descanso(
        self,
        nombre_tarea: str,
        paso_actual: int,
        segundos_transcurridos: int,
        motivo: str = "Botón Descanso Alumno",
    ):
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            tarea_id, modulo_id = self._resolver_fk_tarea_y_modulo(cursor, nombre_tarea)
            cursor.execute(
                """
                INSERT INTO bitacora_descansos (tarea_id, modulo_id, fecha_hora, nombre_tarea, paso_actual, segundos_transcurridos, motivo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tarea_id, modulo_id, ahora, nombre_tarea, paso_actual, segundos_transcurridos, motivo),
            )
            conn.commit()

    def obtener_bitacora_descansos(self, limite: int = 30) -> List[Dict]:
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bitacora_descansos ORDER BY id DESC LIMIT ?", (limite,))
            return [dict(row) for row in cursor.fetchall()]

    def registrar_sesion(
        self,
        nombre_tarea: str,
        pasos_completados: int,
        total_pasos: int,
        segundos_concentracion: int,
        pausas_activas: int,
        pistas_usadas: int,
        estrellas_ganadas: int,
        estado_final: str = "COMPLETADA",
        pausas_manuales: int = 0,
        intervalo_promedio_descanso_seg: int = 0,
    ):
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            cursor = conn.cursor()
            tarea_id, modulo_id = self._resolver_fk_tarea_y_modulo(cursor, nombre_tarea)
            cursor.execute(
                """
                INSERT INTO sesiones_estudio (
                    tarea_id, modulo_id, fecha_hora, nombre_tarea, pasos_completados, total_pasos,
                    segundos_concentracion, pausas_activas, pausas_manuales,
                    intervalo_promedio_descanso_seg, pistas_usadas,
                    estrellas_ganadas, estado_final
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tarea_id,
                    modulo_id,
                    ahora,
                    nombre_tarea,
                    pasos_completados,
                    total_pasos,
                    segundos_concentracion,
                    pausas_activas,
                    pausas_manuales,
                    intervalo_promedio_descanso_seg,
                    pistas_usadas,
                    estrellas_ganadas,
                    estado_final,
                ),
            )
            sesion_id = int(cursor.lastrowid)
            conn.commit()

        if estado_final == "COMPLETADA":
            actual_tareas = int(self.obtener_preferencia("tareas_completadas", "0"))
            self.guardar_preferencia("tareas_completadas", str(actual_tareas + 1))

        self.registrar_evento_auditoria(
            "SESION_REGISTRADA",
            "SESIONES",
            f"Sesión {estado_final}: '{nombre_tarea}' ({pasos_completados}/{total_pasos} pasos, +{estrellas_ganadas} pts)",
            referencia_id=sesion_id,
        )

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

    def agregar_recompensa_catalogo(
        self,
        titulo: str,
        costo_estrellas: int,
        descripcion: str = "Premio pactado con familia/docente",
    ) -> bool:
        tit = re.sub(r"\s+", " ", (titulo or "")).strip()[:90]
        costo = max(1, min(999, int(costo_estrellas)))
        desc = re.sub(r"\s+", " ", (descripcion or "")).strip()[:140]
        if not tit:
            return False
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                VALUES (?, ?, ?)
                ON CONFLICT(titulo) DO UPDATE SET
                    costo_estrellas = excluded.costo_estrellas,
                    descripcion = excluded.descripcion
                """,
                (tit, costo, desc),
            )
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
        """Restaura o inserta el catálogo psicopedagógico escalonado sugerido (6 a 32 puntos)."""
        titulos_legado = (
            "🎨 5 min de dibujo o plastilina libre",
            "🎵 Escuchar mi canción favorita",
            "🌟 Sticker o sello campeón en mi cuaderno",
            "🎲 Elegir juego de mesa o recreo especial",
            "🍿 Cuento, paseo o tarde especial en familia",
        )
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.executemany("DELETE FROM recompensas_catalogo WHERE titulo = ?", [(t,) for t in titulos_legado])
            for tit, costo, desc in self.RECOMPENSAS_SUGERIDAS:
                cursor.execute(
                    """
                    INSERT INTO recompensas_catalogo (titulo, costo_estrellas, descripcion)
                    VALUES (?, ?, ?)
                    ON CONFLICT(titulo) DO UPDATE SET
                        costo_estrellas = excluded.costo_estrellas,
                        descripcion = excluded.descripcion
                    """,
                    (tit, costo, desc),
                )
            conn.commit()

    def canjear_recompensa(self, recompensa_id: int) -> Tuple[bool, str, int]:
        """Canjea un premio real verificando saldo disponible de forma atómica."""
        with self._conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recompensas_catalogo WHERE id = ?", (int(recompensa_id),))
            fila = cursor.fetchone()
            if not fila:
                return False, "El premio seleccionado ya no existe.", self.obtener_estrellas_disponibles()

            rid = int(fila["id"])
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
                    f"Te faltan {faltan} puntos disponibles para canjear «{titulo}».",
                    disponibles,
                )

            nuevas_gastadas = gastadas + costo
            nuevo_saldo = max(0, totales - nuevas_gastadas)
            ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                """
                INSERT INTO perfil_progreso (clave, valor) VALUES ('estrellas_gastadas', ?)
                ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
                """,
                (str(nuevas_gastadas),),
            )
            cursor.execute(
                """
                INSERT INTO historial_canjes (recompensa_id, fecha_hora, titulo_premio, costo_estrellas)
                VALUES (?, ?, ?, ?)
                """,
                (rid, ahora, titulo, costo),
            )
            conn.commit()

        self.registrar_evento_auditoria(
            "PREMIO_CANJEADO",
            "RECOMPENSAS",
            f"Canje de '{titulo}' por {costo} puntos (saldo restante: {nuevo_saldo})",
            referencia_id=rid,
        )
        return True, f"¡Felicidades! Canjeaste «{titulo}» (-{costo} puntos).", nuevo_saldo

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
            cursor.execute(
                """
                INSERT INTO perfil_progreso (clave, valor) VALUES (?, ?)
                ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
                """,
                (clave, str(valor)),
            )
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
        para no interceptar por accidente saludos acompañados de preguntas reales.
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

        filas_ordenadas = sorted(filas, key=lambda r: len(r["palabra_clave"]), reverse=True)
        for row in filas_ordenadas:
            clave_norm = _quitar_tildes(row["palabra_clave"].lower()).strip()
            if not clave_norm:
                continue
            patron = rf"\b{re.escape(clave_norm)}\b"
            if not re.search(patron, consulta_norm):
                continue

            if clave_norm == "hola" and (len(palabras_consulta) > 4 or "?" in consulta or tiene_interrogativo_complejo):
                continue

            if len(clave_norm.split()) == 1 and len(palabras_consulta) > 7 and tiene_interrogativo_complejo and row["materia"] not in ("Identidad", "Apoyo Emocional", "Hábitos y Orden"):
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
        from ui.iconos import svg_icono_html

        resumen = self.obtener_estadisticas_resumen()
        sesiones = self.obtener_historial_sesiones(limite=120)
        descansos = self.obtener_bitacora_descansos(limite=50)
        canjes = self.obtener_historial_canjes(limite=40)

        esc = lambda v: html.escape(str(v if v is not None else ""), quote=True)
        svg_star_sm = svg_icono_html("star", 15, "#d97706")
        svg_header = svg_icono_html("chart_trend", 28, "#ffffff")
        svg_kpi_mision = svg_icono_html("check_circle", 20, "#0f766e")
        svg_kpi_pasos = svg_icono_html("steps", 20, "#0f766e")
        svg_kpi_foco = svg_icono_html("clock", 20, "#0f766e")
        svg_kpi_pausa = svg_icono_html("coffee", 20, "#0f766e")
        svg_kpi_nivel = svg_icono_html("star", 20, "#d97706")

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
                <td>{svg_star_sm} +{int(s['estrellas_ganadas'])} <span class="badge {badge_cls}">{estado_limpio}</span></td>
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
                <td>-{int(c['costo_estrellas'])} {svg_star_sm}</td>
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
  .header {{ background: linear-gradient(135deg, #1f5c5a, #0369a1); color: white; padding: 22px 26px; border-radius: 18px; margin-bottom: 20px; word-wrap: break-word; }}
  .header h2 {{ margin: 0 0 6px 0; font-size: 22px; display: flex; align-items: center; gap: 10px; }}
  .header p {{ margin: 0; font-size: 13px; opacity: 0.94; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 12px; margin-bottom: 22px; }}
  .kpi {{ background: white; padding: 14px 16px; border-radius: 14px; border: 2px solid #99f6e4; text-align: center; box-shadow: 0 3px 10px rgba(0,0,0,0.04); overflow-wrap: anywhere; }}
  .kpi .ico {{ margin-bottom: 4px; display: flex; justify-content: center; }}
  .kpi h3 {{ font-size: 23px; margin: 0 0 4px 0; color: #0f766e; }}
  .kpi p {{ margin: 0; font-size: 12px; color: #475569; font-weight: 600; }}
  h3.sec {{ color: #0f766e; margin: 24px 0 10px 0; font-size: 17px; display: flex; align-items: center; gap: 8px; }}
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
    <h2>{svg_header} <span>Reporte de Seguimiento Psicopedagógico — Asistente Educativo Haru (TDAH)</span></h2>
    <p>Universidad Salesiana de Bolivia • Cumplimiento Ley N.º 548 (Datos Anónimos Locales) y R.M. N.º 0069/2025</p>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="ico">{svg_kpi_mision}</div><h3>{int(resumen['tareas_completadas'])}</h3><p>Misiones Completadas</p></div>
    <div class="kpi"><div class="ico">{svg_kpi_pasos}</div><h3>{int(resumen['total_pasos_logrados'])}</h3><p>Micro-Pasos Logrados</p></div>
    <div class="kpi"><div class="ico">{svg_kpi_foco}</div><h3>{esc(foco_total_str)}</h3><p>Tiempo Foco Efectivo</p></div>
    <div class="kpi"><div class="ico">{svg_kpi_pausa}</div><h3>{int(resumen['total_pausas_alumno'])} ({esc(prom_desc_str)})</h3><p>Descansos Alumno / Ritmo</p></div>
    <div class="kpi"><div class="ico">{svg_kpi_nivel}</div><h3>{int(resumen['estrellas_totales'])}</h3><p>Nivel Total ({int(resumen['estrellas_disponibles'])} disp.)</p></div>
  </div>

  <h3 class="sec">{svg_icono_html("steps", 19, "#0f766e")} 1. Historial de Sesiones Guiadas</h3>
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

  <h3 class="sec">{svg_icono_html("coffee", 19, "#0f766e")} 2. Bitácora Detallada de Descansos del Estudiante</h3>
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

  <h3 class="sec">{svg_icono_html("gift", 19, "#0f766e")} 3. Premios Reales Canjeados (Economía de Fichas)</h3>
  <div class="table-wrap">
    <table>
      <colgroup>
        <col style="width:22%"><col style="width:60%"><col style="width:18%">
      </colgroup>
      <thead>
        <tr>
          <th>Fecha y Hora</th><th>Premio Pactado</th><th>Puntos Usados</th>
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
