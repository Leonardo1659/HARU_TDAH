"""
Motor de Inteligencia Artificial en Capas para el Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Cadena de resolución inteligente, ligera y gratuita (0 MB de SDKs pesados):
1. Capa Exacta Local: Calculadora aritmética segura (`ast`) + Conocimiento SQLite.
2. Capa IA Local (Opcional): Ollama en `127.0.0.1:11434` (100% offline y privado).
3. Capa IA Cloud (Gratuita): Google Gemini Flash vía REST estándar (`urllib.request`),
   desactivada automáticamente si el docente activa el "Modo Privado (Solo Local)"
   en cumplimiento estricto de la Ley N.º 548.
4. Capa Pedagógica Empática: Andamiaje contextual paso a paso sin conexión.
"""

from datetime import datetime
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple, Union

from core.archivos_estudio import DocumentoEstudio
from core.config import ENV_PATH, MODELO_GEMINI_DEFECTO, OLLAMA_URL_BASE, cargar_env_local
from core.ia.calculadora_ast import evaluar_ast_seguro, resolver_pregunta_matematica

SYSTEM_INSTRUCTION_HARU = (
    "Eres Haru, un tierno, cálido, inteligente y paciente compañero virtual educativo para niños de "
    "primaria (6 a 11 años) con TDAH en Bolivia. "
    "ÁMBITO PERMITIDO: tareas escolares, estudio paso a paso, técnicas para concentrarse y recordar, "
    "la hora/organización diaria, hábitos saludables y curiosidades educativas seguras para niños. "
    "RESTRICCIONES ESTRICTAS: si te preguntan sobre novios/novias, romance, sexualidad, videojuegos comerciales "
    "(Free Fire, Fortnite, Roblox, etc.), violencia, armas, drogas, apuestas o cómo hacer trampa, "
    "declina con amabilidad en una oración y redirige al estudio. "
    "Responde en 2 a 4 oraciones claras, sin usar asteriscos ni Markdown, guiando paso a paso con ejemplos reales."
)


class _PerfilEstudianteDict(dict):
    """Diccionario de perfil con alias compatibles (`nombre`/`nombre_estudiante`, `grado`/`grado_primaria`)."""

    def __getitem__(self, key: str):
        if key == "nombre" and "nombre" not in self:
            return super().__getitem__("nombre_estudiante")
        if key == "grado" and "grado" not in self:
            return super().__getitem__("grado_primaria")
        return super().__getitem__(key)

    def get(self, key: str, default=None):
        if key == "nombre" and "nombre" not in self:
            return super().get("nombre_estudiante", default)
        if key == "grado" and "grado" not in self:
            return super().get("grado_primaria", default)
        return super().get(key, default)


def _normalizar_ia(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (texto or "").lower())
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip()


_REEMPLAZOS_ORTOGRAFIA_INFANTIL: Tuple[Tuple[re.Pattern, str], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), rep)
    for pat, rep in (
        (r"\bx\s*fa(?:vor)?\b", "por favor"),
        (r"\bporfa(?:vor)?\b", "por favor"),
        (r"\bplis\b", "por favor"),
        (r"\b(?:xq|xk|pq|x\s+q|x\s+que)\b", "porque"),
        (r"\b(?:q|k|ke|qe)\b", "que"),
        (r"\bora\b", "hora"),
        (r"\bola+\b", "hola"),
        (r"\bholi+s?\b", "hola"),
        (r"\bberb(o|os)\b", r"verb\1"),
        (r"\bfoto[sc]int[eé][sc]is\b", "fotosintesis"),
        (r"\bfraci[oó]n\b", "fraccion"),
        (r"\bfraciones\b", "fracciones"),
        (r"\bsustantib(o|os)\b", r"sustantiv\1"),
        (r"\badjetib(o|os)\b", r"adjetiv\1"),
        (r"\b[sc]ilab(a|as)\b", r"silab\1"),
        (r"\bsilav(a|as)\b", r"silab\1"),
        (r"\bmultiplicasi[oó]n\b", "multiplicacion"),
        (r"\bdi[bv]i[sc]i[oó]n\b", "division"),
        (r"\bejer[sc]i[sc]i(o|os)\b", r"ejercici\1"),
        (r"\b[sc]ien[sc]ias\b", "ciencias"),
        (r"\blenguage\b", "lenguaje"),
        (r"\bbolibia\b", "bolivia"),
        (r"\bvolivia\b", "bolivia"),
        (r"\bdino[sz]auri(o|os)\b", r"dinosauri\1"),
        (r"\be[bv]aporasi[oó]n\b", "evaporacion"),
        (r"\bebaporaci[oó]n\b", "evaporacion"),
        (r"\bcondensasi[oó]n\b", "condensacion"),
        (r"\bpre[sc]ipitasi[oó]n\b", "precipitacion"),
        (r"\badi[bv]inan[sz]a\b", "adivinanza"),
        (r"\btmb\b", "tambien"),
        (r"\bbn\b", "bien"),
        (r"\bdnd\b", "donde"),
        (r"\bcdo\b", "cuando"),
    )
)


def _normalizar_ortografia_infantil(texto: str) -> str:
    """
    Normaliza abreviaturas de chat y errores ortográficos frecuentes en niños de primaria
    (ej. 'q ora es' -> 'que hora es', 'ola' -> 'hola', 'berbo' -> 'verbo',
    'fotosintecis' -> 'fotosintesis', 'fracion' -> 'fraccion', 'xfa' -> 'por favor', 'xq' -> 'porque').
    """
    if not isinstance(texto, str) or not texto.strip():
        return ""
    limpio = re.sub(r"\s+", " ", texto).strip()
    for patron, reemplazo in _REEMPLAZOS_ORTOGRAFIA_INFANTIL:
        limpio = patron.sub(reemplazo, limpio)
    return re.sub(r"\s+", " ", limpio).strip()


def _limpiar_respuesta_ia(texto: str, max_chars: int = 340) -> str:
    """
    Elimina marcas Markdown (`**`, `#`, backticks) preservando operadores matemáticos (`*` entre números)
    y evita desbordes en tarjetas UI.
    """
    if not texto:
        return ""
    # Conservar el contenido interno si viene en bloques de código Markdown
    limpio = re.sub(r"```(?:[a-zA-Z0-9_+-]+\n)?([\s\S]*?)```", r" \1 ", texto)
    # Eliminar negritas/subrayados dobles primero (**texto**, __texto__)
    limpio = re.sub(r"\*\*+", "", limpio)
    limpio = re.sub(r"__+", "", limpio)
    # Proteger el operador matemático '*' cuando aparece entre dígitos o paréntesis
    limpio = re.sub(r"(?<=[\d\)])\s*\*\s*(?=[\d\(])", " \x00MUL\x00 ", limpio)
    # Eliminar marcas Markdown restantes (` * _ #)
    limpio = re.sub(r"[`*_#]+", "", limpio)
    limpio = limpio.replace("\x00MUL\x00", "*")
    limpio = re.sub(r"\s+", " ", limpio).strip()
    if len(limpio) > max_chars:
        recorte = limpio[:max_chars]
        ultimo_punto = max(recorte.rfind(". "), recorte.rfind("! "), recorte.rfind("? "))
        if ultimo_punto > 120:
            limpio = recorte[: ultimo_punto + 1].strip()
        else:
            limpio = recorte.rsplit(" ", 1)[0].strip() + "…"
    return limpio


def _actualizar_clave_en_env(clave: str, valor: str) -> None:
    """Actualiza o inserta una variable en `.env` sanitizando saltos/comillas contra inyección."""
    clave_segura = re.sub(r"[^A-Za-z0-9_]", "", clave or "").strip()
    valor_seguro = re.sub(r"[\r\n\"'`]", "", valor or "").strip()[:260]
    if not clave_segura:
        return

    lineas_nuevas: List[str] = []
    encontrada = False
    if ENV_PATH.exists():
        for linea in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            limpia = linea.strip()
            if limpia and not limpia.startswith("#") and "=" in limpia:
                k, _ = limpia.split("=", 1)
                if k.strip() == clave_segura:
                    lineas_nuevas.append(f"{clave_segura}={valor_seguro}")
                    encontrada = True
                    continue
            lineas_nuevas.append(linea)
    if not encontrada:
        if not lineas_nuevas:
            lineas_nuevas.append("# Configuración local de llaves API (excluida del .zip compartido)")
        lineas_nuevas.append(f"{clave_segura}={valor_seguro}")
    ENV_PATH.write_text("\n".join(lineas_nuevas) + "\n", encoding="utf-8")


def _normalizar_grado_primaria(grado: str) -> str:
    """Normaliza la etiqueta del grado de primaria ('1.° de Primaria' a '6.° de Primaria' o '')."""
    raw = re.sub(r"\s+", " ", (grado or "")).strip()[:40]
    if not raw:
        return ""
    low = _normalizar_ia(raw)
    mapa_num = {
        "primero": 1, "primer": 1, "1": 1,
        "segundo": 2, "2": 2,
        "tercero": 3, "tercer": 3, "3": 3,
        "cuarto": 4, "4": 4,
        "quinto": 5, "5": 5,
        "sexto": 6, "6": 6,
    }
    m = re.search(r"\b([1-6])\b", low)
    if m:
        return f"{int(m.group(1))}.° de Primaria"
    for pal, n in mapa_num.items():
        if re.search(rf"\b{pal}\b", low):
            return f"{n}.° de Primaria"
    return raw


class MotorIAHaru:
    MODELOS_CANDIDATOS = [
        MODELO_GEMINI_DEFECTO,
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]
    GRADOS_PRIMARIA = (
        "1.° de Primaria",
        "2.° de Primaria",
        "3.° de Primaria",
        "4.° de Primaria",
        "5.° de Primaria",
        "6.° de Primaria",
    )
    EJERCICIOS_POR_ESTRELLA = 3

    _normalizar_ortografia_infantil = staticmethod(_normalizar_ortografia_infantil)

    def __init__(self, repositorio_db=None):
        self.db = repositorio_db
        cargar_env_local()
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._modelo_gemini_activo: Optional[str] = None
        self._ollama_modelo_cache: Optional[str] = None
        self._ollama_modelos_disponibles: List[str] = []
        self._ollama_check_ts: float = 0.0
        self.ultima_fuente: str = "Local"
        self.ultimo_error_cloud: str = ""

        # Perfil pedagógico del estudiante (nombre y grado de primaria)
        self.nombre_estudiante: str = ""
        self.grado_primaria: str = ""
        self.recargar_perfil_estudiante()

        # Memoria conversacional multi-turno: [(pregunta, respuesta, ultimo_resultado_num), ...]
        self._historial_chat: List[Tuple[str, str, Optional[Union[int, float]]]] = []
        self._ultimo_resultado_num: Optional[Union[int, float]] = None

        # Seguimiento de intentos de pistas graduadas por paso
        self._conteo_pistas_paso: Dict[Tuple[str, int, str], int] = {}

        # Documento activo en sesión del estudiante (para navegar varios ejercicios sin olvidarlo)
        self._documento_activo: Optional[Dict[str, object]] = None
        self._ultimo_turno_fue_documento: bool = False
        self.ultimo_cobro_documento: Optional[Dict[str, int]] = None

    # =========================================================================
    # PERFIL PEDAGÓGICO DEL ESTUDIANTE (NOMBRE Y GRADO DE PRIMARIA)
    # =========================================================================
    def recargar_perfil_estudiante(self) -> Dict[str, str]:
        """Lee `nombre_estudiante` y `grado_primaria` desde SQLite y actualiza el estado del motor."""
        if self.db and hasattr(self.db, "obtener_preferencia"):
            nom_db = self.db.obtener_preferencia("nombre_estudiante", "") or ""
            grado_db = self.db.obtener_preferencia("grado_primaria", "") or ""
            self.nombre_estudiante = re.sub(r"\s+", " ", str(nom_db)).strip()[:45]
            self.grado_primaria = _normalizar_grado_primaria(str(grado_db))
        return _PerfilEstudianteDict(
            nombre_estudiante=self.nombre_estudiante,
            grado_primaria=self.grado_primaria,
        )

    def actualizar_perfil_estudiante(self, nombre: str = "", grado: str = "") -> None:
        """Actualiza en memoria y persiste en SQLite el perfil pedagógico del estudiante."""
        nom_limpio = re.sub(r"[\r\n\t]+", " ", str(nombre or "")).strip()
        nom_limpio = re.sub(r"\s+", " ", nom_limpio)[:45]
        grado_limpio = _normalizar_grado_primaria(str(grado or ""))

        self.nombre_estudiante = nom_limpio
        self.grado_primaria = grado_limpio
        if self.db and hasattr(self.db, "guardar_preferencia"):
            try:
                self.db.guardar_preferencia("nombre_estudiante", self.nombre_estudiante)
                self.db.guardar_preferencia("grado_primaria", self.grado_primaria)
            except Exception:
                pass

    def _sincronizar_perfil_ligero(self) -> Tuple[str, str]:
        """Retorna `(nombre, grado)` sincronizando con SQLite si se actualizó por fuera."""
        if self.db and hasattr(self.db, "obtener_preferencia"):
            try:
                nom_db = re.sub(r"\s+", " ", (self.db.obtener_preferencia("nombre_estudiante", "") or "")).strip()[:45]
                grado_db = _normalizar_grado_primaria(self.db.obtener_preferencia("grado_primaria", "") or "")
                if nom_db and not self.nombre_estudiante:
                    self.nombre_estudiante = nom_db
                if grado_db and not self.grado_primaria:
                    self.grado_primaria = grado_db
            except Exception:
                pass
        return self.nombre_estudiante, self.grado_primaria

    def _numero_grado_primaria(self) -> int:
        """Extrae el nivel numérico de primaria (1..6, por defecto 3)."""
        _, grado = self._sincronizar_perfil_ligero()
        m = re.search(r"([1-6])", grado or "")
        return int(m.group(1)) if m else 3

    def _construir_system_prompt(self, base_prompt: str = SYSTEM_INSTRUCTION_HARU) -> str:
        """Incorpora el nombre del estudiante y la adaptación al grado escolar en el System Prompt."""
        nombre, grado = self._sincronizar_perfil_ligero()
        grado_efectivo = grado or "3.° de Primaria"
        num_grado = self._numero_grado_primaria()
        if num_grado <= 2:
            guia_vocab = (
                "Usa vocabulario muy sencillo y tierno para niños de 6 a 7 años (1.° y 2.° de Primaria), "
                "con frases cortitas y ejemplos concretos de conteo con deditos, frutas o juguetes."
            )
        elif num_grado <= 4:
            guia_vocab = (
                "Usa vocabulario claro e intermedio para niños de 8 a 9 años (3.° y 4.° de Primaria), "
                "explicando paso a paso con ejemplos escolares cotidianos."
            )
        else:
            guia_vocab = (
                "Usa vocabulario de primaria superior para niños de 10 a 11 años (5.° y 6.° de Primaria), "
                "incluyendo conceptos completos, razonamiento lógico y verificación de resultados."
            )
        perfil_txt = f"PERFIL DEL ESTUDIANTE: Grado escolar: {grado_efectivo}. "
        if nombre:
            perfil_txt += f"Nombre del estudiante: {nombre} (dirígete a {nombre} por su nombre con cariño). "
        perfil_txt += guia_vocab
        return f"{base_prompt} {perfil_txt}".strip()

    def _personalizar_respuesta_local(
        self,
        respuesta: str,
        adaptar_grado: bool = False,
    ) -> str:
        """Personaliza respuestas locales con el nombre del estudiante y adapta la complejidad al grado."""
        if not respuesta:
            return respuesta
        nombre, grado = self._sincronizar_perfil_ligero()
        texto = respuesta.strip()

        if adaptar_grado and grado:
            num_g = self._numero_grado_primaria()
            if num_g <= 2 and grado.lower() not in texto.lower():
                texto = (
                    f"{texto} Para {grado}, imagínalo pasito a pasito usando tus deditos o dibujitos sencillos."
                )
            elif num_g >= 5 and grado.lower() not in texto.lower():
                texto = (
                    f"{texto} En {grado}, anota un ejemplo completo en tu cuaderno y comprueba tu razonamiento."
                )

        if nombre and nombre.lower() not in texto.lower():
            # Reemplazar vocativos genéricos si existen
            if re.search(r"\bamiguit[oa]\b", texto, flags=re.IGNORECASE):
                texto = re.sub(r"\bamiguit[oa]\b", nombre, texto, count=1, flags=re.IGNORECASE)
            elif texto.startswith("¡Hola!"):
                texto = texto.replace("¡Hola!", f"¡Hola, {nombre}!", 1)
            elif texto.startswith("¡") and "!" in texto[:42]:
                idx_adm = texto.find("!")
                texto = f"{texto[:idx_adm]}, {nombre}{texto[idx_adm:]}"
            else:
                texto = f"{nombre}, {texto[0].lower() + texto[1:] if len(texto) > 1 and texto[1].islower() else texto}"
        return texto

    @property
    def modo_privado(self) -> bool:
        if not self.db:
            return False
        return self.db.obtener_preferencia("modo_privado", "0") == "1"

    def set_modo_privado(self, activo: bool) -> None:
        if self.db:
            self.db.guardar_preferencia("modo_privado", "1" if activo else "0")

    def configurar_api_key(self, nueva_key: str) -> None:
        """Actualiza la API Key en memoria y en `.env` sanitizada (nunca en SQLite)."""
        limpia = re.sub(r"[\r\n\"'`\s]", "", nueva_key or "")[:260]
        self.api_key = limpia
        os.environ["GEMINI_API_KEY"] = self.api_key
        self._modelo_gemini_activo = None
        try:
            _actualizar_clave_en_env("GEMINI_API_KEY", self.api_key)
        except Exception:
            pass

    def detectar_ollama_local(self, forzar: bool = False) -> Optional[str]:
        """Detecta en <0.6s si Ollama está corriendo localmente y elige un modelo ligero."""
        ahora = time.time()
        if not forzar and (ahora - self._ollama_check_ts) < 30.0:
            return self._ollama_modelo_cache

        self._ollama_check_ts = ahora
        try:
            req = urllib.request.Request(f"{OLLAMA_URL_BASE}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=0.6) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
                modelos = [m.get("name", "") for m in datos.get("models", []) if m.get("name")]
                self._ollama_modelos_disponibles = list(modelos)
                if modelos:
                    modelo_preferido = ""
                    if self.db and hasattr(self.db, "obtener_preferencia"):
                        try:
                            modelo_preferido = (self.db.obtener_preferencia("modelo_ollama", "") or "").strip()
                        except Exception:
                            modelo_preferido = ""
                    if modelo_preferido and modelo_preferido in modelos:
                        self._ollama_modelo_cache = modelo_preferido
                        return modelo_preferido
                    for pref in ("qwen", "gemma", "llama3.2", "phi", "mistral"):
                        for m in modelos:
                            if pref in m.lower():
                                self._ollama_modelo_cache = m
                                return m
                    self._ollama_modelo_cache = modelos[0]
                    return modelos[0]
        except Exception:
            pass

        self._ollama_modelos_disponibles = []
        self._ollama_modelo_cache = None
        return None

    def obtener_info_ollama(self, forzar: bool = False) -> Dict[str, object]:
        """Retorna el estado de conexión local de Ollama y la lista de modelos disponibles."""
        modelo = self.detectar_ollama_local(forzar=forzar)
        modelos = list(self._ollama_modelos_disponibles)
        if modelo and modelo not in modelos:
            modelos.insert(0, modelo)
        return {
            "conectado": bool(modelo),
            "modelo_activo": modelo or "",
            "modelos_disponibles": modelos,
            "url": OLLAMA_URL_BASE,
        }

    def configurar_modelo_ollama(self, modelo: str) -> None:
        """Guarda el modelo local de Ollama preferido y lo activa si está disponible."""
        modelo_limpio = (modelo or "").strip()
        if self.db and hasattr(self.db, "guardar_preferencia"):
            try:
                self.db.guardar_preferencia("modelo_ollama", modelo_limpio)
            except Exception:
                pass
        if modelo_limpio and (
            modelo_limpio in self._ollama_modelos_disponibles or bool(self._ollama_modelo_cache)
        ):
            self._ollama_modelo_cache = modelo_limpio

    def obtener_estado_ia(self) -> str:
        modelo_ollama = self.detectar_ollama_local()
        if self.modo_privado:
            if modelo_ollama:
                return f"Modo Privado Activo: Ollama Local ({modelo_ollama}) + Motor Exacto"
            return "Modo Privado Activo: 100% Local (Matemática AST + Base Escolar)"
        partes = []
        if self.api_key:
            mod = self._modelo_gemini_activo or MODELO_GEMINI_DEFECTO
            partes.append(f"Gemini Cloud ({mod})")
        if modelo_ollama:
            partes.append(f"Ollama ({modelo_ollama})")
        partes.append("Motor Pedagógico Local")
        return " + ".join(partes)

    # =========================================================================
    # MEMORIA CONVERSACIONAL MULTI-TURNO (`_historial_chat`)
    # =========================================================================
    def _obtener_ultimo_resultado_num(self) -> Optional[Union[int, float]]:
        for _preg, _resp, num in reversed(self._historial_chat):
            if num is not None:
                return num
        return self._ultimo_resultado_num

    @staticmethod
    def _extraer_resultado_numerico(pregunta: str, respuesta: str) -> Optional[Union[int, float]]:
        """Extrae el resultado numérico principal cuando una respuesta resuelve un cálculo."""
        if not respuesta:
            return None
        patrones = (
            r"da como resultado\s+(-?\d+(?:\.\d+)?)",
            r"el resultado es\s+(-?\d+(?:\.\d+)?)",
            r":\s*¡da\s+(-?\d+(?:\.\d+)?)!",
            r"¡que nos da\s+(-?\d+(?:\.\d+)?)!",
            r"obtienes\s+(-?\d+(?:\.\d+)?)",
            r"le toca\s+(-?\d+(?:\.\d+)?)",
            r"queda\s+(-?\d+(?:\.\d+)?)",
            r"¡Anota el\s+(-?\d+(?:\.\d+)?)\s+en tu cuaderno",
        )
        for pat in patrones:
            m = re.search(pat, respuesta, flags=re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    return int(val) if val.is_integer() else round(val, 4)
                except ValueError:
                    continue
        return None

    def _registrar_turno_chat(
        self,
        pregunta: str,
        respuesta: str,
        resultado_num: Optional[Union[int, float]] = None,
        es_documento: bool = False,
    ) -> str:
        self._ultimo_turno_fue_documento = bool(es_documento)
        if resultado_num is None:
            resultado_num = self._extraer_resultado_numerico(pregunta, respuesta)
        if resultado_num is not None:
            self._ultimo_resultado_num = resultado_num
        efectivo_num = resultado_num if resultado_num is not None else self._ultimo_resultado_num
        self._historial_chat.append((pregunta, respuesta, efectivo_num))
        if len(self._historial_chat) > 10:
            self._historial_chat = self._historial_chat[-10:]
        return respuesta

    def _formatear_historial_para_prompt(self, max_turnos: int = 3) -> str:
        if not self._historial_chat:
            return ""
        recientes = self._historial_chat[-max_turnos:]
        lineas = []
        for p_ant, r_ant, n_ant in recientes:
            extra_n = f" [último resultado numérico={n_ant}]" if n_ant is not None else ""
            lineas.append(f"Estudiante: '{p_ant[:100]}' -> Haru: '{r_ant[:140]}'{extra_n}")
        return "Historial reciente de conversación: " + " | ".join(lineas) + ". "

    def _resolver_seguimiento_matematico(
        self, pregunta: str
    ) -> Optional[Tuple[str, Union[int, float]]]:
        """
        Resuelve preguntas matemáticas de seguimiento que continúan el cálculo anterior
        (ej. '¿y si le sumo 2?', '¿y más 5?', '¿y la mitad?', '¿y el doble?', '¿y por 3?').
        """
        prev_num = self._obtener_ultimo_resultado_num()
        if prev_num is None:
            return None

        q_ort = _normalizar_ortografia_infantil(pregunta)
        q_norm = _normalizar_ia(q_ort)
        q_clean = re.sub(r"[¿?¡!]", " ", q_norm).strip()
        if not q_clean:
            return None

        prev_str = str(int(prev_num)) if float(prev_num).is_integer() else str(prev_num)

        # 1) Seguimiento unario sobre el resultado previo: "¿y la mitad?", "¿y el doble?", "¿y el triple?"
        m_unario = re.match(
            r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:cual\s+es\s+|sacamos\s+|calcula\s+|dime\s+)?"
            r"(?:la\s+|el\s+|su\s+)?(mitad|doble|triple)(?:\s+de\s+(?:eso|ese\s+numero|el\s+resultado))?\s*$",
            q_clean,
        )
        if m_unario:
            tipo_u = m_unario.group(1)
            resp_u = resolver_pregunta_matematica(f"la {tipo_u} de {prev_str}" if tipo_u == "mitad" else f"el {tipo_u} de {prev_str}")
            if resp_u:
                nuevo_num = self._extraer_resultado_numerico(pregunta, resp_u)
                if nuevo_num is not None:
                    return resp_u, nuevo_num

        # 2) Seguimiento con verbo aritmético explícito ("¿y si le sumo 2?", "¿y si le resto 4?", "¿y si lo multiplico por 3?", "¿y si lo divido entre 2?")
        patrones_followup = (
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:a\s+eso\s+|al\s+resultado\s+)?"
                r"(?:le\s+|lo\s+)?(?:sumo|sumamos|sumas|sumale|agrega|agrego|agregamos|anado|anadimos)\s+(.+)$",
                "más",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:a\s+eso\s+|al\s+resultado\s+)?"
                r"(?:le\s+|lo\s+)?(?:resto|restamos|restas|restale|quito|quitamos|quitas|quitale)\s+(.+)$",
                "menos",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:a\s+eso\s+|al\s+resultado\s+)?"
                r"(?:lo\s+|le\s+)?(?:multiplico|multiplicamos|multiplicas|multiplicale|multiplicado)\s+(?:por\s+)?(.+)$",
                "por",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:a\s+eso\s+|al\s+resultado\s+)?"
                r"(?:lo\s+|le\s+)?(?:divido|dividimos|divides|divide|dividelo|dividido|reparto|repartimos)\s+(?:entre\s+|por\s+|en\s+)?(.+)$",
                "entre",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:es\s+)?(?:mas|\+)\s+(.+)$",
                "más",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:es\s+)?(?:menos|\-)\s+(.+)$",
                "menos",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:por|veces|\*|×|x)\s+(.+)$",
                "por",
            ),
            (
                r"^(?:y\s+)?(?:si\s+)?(?:ahora\s+)?(?:entre|dividido\s+entre|\/|÷)\s+(.+)$",
                "entre",
            ),
        )
        for pat, op_palabra in patrones_followup:
            m_f = re.match(pat, q_clean)
            if m_f:
                resto = m_f.group(1).strip()
                consulta_sintetica = f"cuánto es {prev_str} {op_palabra} {resto}"
                resp_f = resolver_pregunta_matematica(consulta_sintetica)
                if resp_f:
                    nuevo_num = self._extraer_resultado_numerico(consulta_sintetica, resp_f)
                    if nuevo_num is not None:
                        return resp_f, nuevo_num

        return None

    def _resolver_reformulacion_previa(self, pregunta: str) -> Optional[str]:
        """
        Si el estudiante dice 'no entendí' o 'explícame otra vez' y existe un turno previo,
        reformula la explicación anterior con palabras más sencillas y un ejemplo concreto.
        """
        if not self._historial_chat:
            return None

        q_ort = _normalizar_ortografia_infantil(pregunta)
        q_norm = _normalizar_ia(q_ort)
        es_pedido_reformular = bool(
            re.search(
                r"\b(?:no\s+(?:lo\s+)?entendi|no\s+entiendo(?:\s+bien|\s+eso|\s+nada|\s+esto)?|"
                r"explicame\s+(?:otra\s+vez|de\s+nuevo|mas\s+facil|mejor)|"
                r"explica\s+(?:otra\s+vez|de\s+nuevo)|"
                r"repiteme(?:lo)?|otra\s+vez\s+por\s+favor|mas\s+facil|con\s+otras\s+palabras|"
                r"dame\s+(?:un|otro)\s+ejemplo|no\s+me\s+quedo\s+claro)\b",
                q_norm,
            )
        )
        if not es_pedido_reformular:
            return None

        # Verificar que no esté preguntando por un tema académico completamente nuevo en la misma frase
        palabras_tema_nuevo = re.findall(r"[a-zñ]+", q_norm)
        ignorar = {
            "no", "lo", "entendi", "entiendo", "bien", "eso", "esto", "nada", "haru", "hola",
            "por", "favor", "explicame", "explica", "otra", "vez", "de", "nuevo", "mas",
            "facil", "mejor", "repiteme", "repitemelo", "con", "otras", "palabras", "dame",
            "un", "otro", "ejemplo", "me", "quedo", "claro", "puedes", "ayudame", "a", "entender",
        }
        extras = [w for w in palabras_tema_nuevo if len(w) > 3 and w not in ignorar]
        if extras:
            return None

        prev_preg, prev_resp, prev_num = self._historial_chat[-1]
        self.ultima_fuente = "Andamiaje Multi-Turno Haru"
        if prev_num is not None:
            num_bonito = str(int(prev_num)) if float(prev_num).is_integer() else str(prev_num)
            return (
                f"¡Te lo explico más fácil con un ejemplo concreto! En nuestra cuenta anterior de «{prev_preg[:60]}», "
                f"imagina que cuentas manzanas o lápices uno por uno sobre tu mesa hasta llegar a {num_bonito}. "
                f"En palabras sencillas: {prev_resp}"
            )
        return (
            f"¡No te preocupes, te lo explico con palabras más sencillas! Sobre «{prev_preg[:60]}»: "
            f"{prev_resp} Por ejemplo, imagínalo con algo que ves todos los días en casa o en tu escuela para recordarlo súper fácil."
        )

    # =========================================================================
    # PROVEEDORES DE IA (OLLAMA LOCAL Y GEMINI REST)
    # =========================================================================
    def _llamar_ollama(self, prompt: str, system_prompt: str = SYSTEM_INSTRUCTION_HARU) -> Optional[str]:
        modelo = self.detectar_ollama_local()
        if not modelo:
            return None
        sys_efectivo = self._construir_system_prompt(system_prompt)
        hist_txt = self._formatear_historial_para_prompt()
        prompt_efectivo = f"{hist_txt}{prompt}" if (hist_txt and hist_txt not in prompt) else prompt
        try:
            payload = {
                "model": modelo,
                "system": sys_efectivo,
                "prompt": prompt_efectivo,
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 140},
            }
            req = urllib.request.Request(
                f"{OLLAMA_URL_BASE}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                texto = (body.get("response") or "").strip()
                if texto:
                    self.ultima_fuente = f"Ollama ({modelo})"
                    return texto
        except Exception:
            self._ollama_modelo_cache = None
        return None

    def _descubrir_modelo_gemini(self) -> List[str]:
        """Construye la lista ordenada de modelos Flash disponibles para esta API Key."""
        if self._modelo_gemini_activo:
            return [self._modelo_gemini_activo]

        candidatos = list(self.MODELOS_CANDIDATOS)
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(self.api_key)}"
            req = urllib.request.Request(url, headers={"x-goog-api-key": self.api_key}, method="GET")
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                datos = json.loads(resp.read().decode("utf-8"))
                disponibles = []
                for m in datos.get("models", []):
                    nombre = m.get("name", "").replace("models/", "")
                    metodos = m.get("supportedGenerationMethods", [])
                    if "generateContent" in metodos and "flash" in nombre.lower() and "tts" not in nombre.lower() and "image" not in nombre.lower():
                        disponibles.append(nombre)
                for d in disponibles:
                    if d not in candidatos:
                        candidatos.append(d)
        except Exception:
            pass
        return candidatos

    def _llamar_gemini(self, prompt: str, system_prompt: str = SYSTEM_INSTRUCTION_HARU) -> Optional[str]:
        """
        Invoca Google Gemini vía HTTPS REST estándar (`urllib.request`) sin SDKs pesados.
        Respeta estrictamente el Modo Privado (Ley N.º 548) y soporta automáticamente:
        - Claves `AQ....` (Vertex AI Studio Express Mode -> `aiplatform.googleapis.com`)
        - Claves `AIza...` (Google AI Studio -> `generativelanguage.googleapis.com`)
        """
        if not self.api_key or self.modo_privado:
            return None

        sys_efectivo = self._construir_system_prompt(system_prompt)
        hist_txt = self._formatear_historial_para_prompt()
        prompt_efectivo = f"{hist_txt}{prompt}" if (hist_txt and hist_txt not in prompt) else prompt

        contents_list = []
        for p_ant, r_ant, _n_ant in self._historial_chat[-3:]:
            contents_list.append({"role": "user", "parts": [{"text": p_ant}]})
            contents_list.append({"role": "model", "parts": [{"text": r_ant}]})
        contents_list.append({"role": "user", "parts": [{"text": prompt_efectivo}]})

        payload_contenido = {
            "systemInstruction": {"parts": [{"text": sys_efectivo}]},
            "contents": contents_list,
            "generationConfig": {"temperature": 0.45, "maxOutputTokens": 600},
        }

        es_clave_aq = self.api_key.startswith("AQ.")
        bases_orden = (
            ["vertex_express", "ai_studio"] if es_clave_aq else ["ai_studio", "vertex_express"]
        )

        # 1. Intentar API Interactions v1beta con store=False cuando sea clave AI Studio
        if not es_clave_aq:
            modelo_inicial = self._modelo_gemini_activo or MODELO_GEMINI_DEFECTO
            try:
                url_inter = "https://generativelanguage.googleapis.com/v1beta/interactions"
                payload_inter = {
                    "model": f"models/{modelo_inicial}",
                    "system_instruction": sys_efectivo,
                    "input": prompt_efectivo,
                    "store": False,
                }
                req_inter = urllib.request.Request(
                    url_inter,
                    data=json.dumps(payload_inter).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self.api_key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req_inter, timeout=5.0) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    for step in body.get("steps", []):
                        if step.get("type") == "model_output":
                            partes = [
                                c.get("text", "")
                                for c in step.get("content", [])
                                if c.get("type") == "text"
                            ]
                            texto = " ".join(partes).strip()
                            if texto:
                                self._modelo_gemini_activo = modelo_inicial
                                self.ultima_fuente = f"Gemini ({modelo_inicial})"
                                return texto
            except Exception:
                pass

        # 2. Probar modelos candidatos en el endpoint correspondiente (Vertex Express / AI Studio)
        modelos_probar = [self._modelo_gemini_activo] if self._modelo_gemini_activo else self._descubrir_modelo_gemini()
        for tipo_base in bases_orden:
            for modelo in modelos_probar:
                if not modelo:
                    continue
                try:
                    if tipo_base == "vertex_express":
                        url = (
                            f"https://aiplatform.googleapis.com/v1/publishers/google/models/"
                            f"{urllib.parse.quote(modelo)}:generateContent?key={urllib.parse.quote(self.api_key)}"
                        )
                        headers = {"Content-Type": "application/json"}
                    else:
                        url = (
                            f"https://generativelanguage.googleapis.com/v1beta/models/"
                            f"{urllib.parse.quote(modelo)}:generateContent"
                        )
                        headers = {
                            "Content-Type": "application/json",
                            "x-goog-api-key": self.api_key,
                        }

                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload_contenido).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=6.5) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        for cand in body.get("candidates", []):
                            partes = cand.get("content", {}).get("parts", [])
                            texto = " ".join(p.get("text", "") for p in partes if p.get("text")).strip()
                            if texto:
                                self._modelo_gemini_activo = modelo
                                self.ultima_fuente = f"Gemini ({modelo})"
                                return texto
                except urllib.error.HTTPError as e:
                    try:
                        err_txt = e.read().decode("utf-8", errors="ignore")
                        err_json = json.loads(err_txt)
                        detalle_http = err_json.get("error", {}).get("message", err_txt[:160])
                    except Exception:
                        detalle_http = str(e)
                    self.ultimo_error_cloud = f"HTTP {e.code} ({tipo_base}/{modelo}): {detalle_http}"
                    if e.code in (401, 403):
                        break
                    continue
                except Exception as e:
                    self.ultimo_error_cloud = f"Red ({tipo_base}): {e}"
                    break

        return None

    def probar_conexion_cloud(self) -> Tuple[bool, str]:
        """Prueba en vivo la API Key actual para el panel docente y `tools/diagnostico.py`."""
        if not self.api_key:
            return False, "GEMINI_API_KEY está vacía en .env (usando motor local)."
        if self.modo_privado:
            return False, "Modo Privado activo: las llamadas a la nube están deshabilitadas por elección docente."

        self.ultimo_error_cloud = ""
        respuesta = self._llamar_gemini("Di únicamente: ¡Hola, conexión lista con Haru!")
        if respuesta:
            return True, f"Conectado correctamente a {self.ultima_fuente}: «{respuesta}»"
        extra = f" Detalle: {self.ultimo_error_cloud}" if self.ultimo_error_cloud else ""
        return False, f"No fue posible conectar con Gemini API.{extra}"

    # =========================================================================
    # 0. CLASIFICADOR AUTOMÁTICO DE MÓDULO CURRICULAR (TEXTO, VOZ O ARCHIVO)
    # =========================================================================
    def detectar_modulo_automatico(self, texto: str, modulo_preferido: str = "") -> str:
        """
        Detecta automáticamente a cuál de los 5 Módulos Curriculares pertenece una
        instrucción escrita, dictada por micrófono o extraída de un archivo escolar:
        ('Matemáticas', 'Lenguaje', 'Ciencias', 'Inglés', 'Hábitos y Orden').
        """
        txt_ort = _normalizar_ortografia_infantil(texto or "")
        txt_low = txt_ort.lower()
        txt_norm = _normalizar_ia(txt_ort)
        limpio = re.sub(r"[^a-z0-9+\-×*/\s]", " ", txt_norm)
        tokens = set(limpio.split())

        puntajes: Dict[str, int] = {
            "Inglés": 0,
            "Matemáticas": 0,
            "Lenguaje": 0,
            "Ciencias": 0,
            "Hábitos y Orden": 0,
        }

        # Palabras e indicadores de Inglés (sin 'red' ni 'ten' aislados para evitar falsos positivos en español)
        kw_ingles_fuerte = {
            "ingles", "english", "hello", "goodbye", "vocabulary",
            "colors", "animals", "numbers", "blue", "yellow", "green",
            "orange", "purple", "pink", "white", "black", "cat", "dog", "bird",
            "rabbit", "lion", "monkey", "elephant", "one", "two", "three", "four",
            "five", "six", "seven", "eight", "nine", "mother", "father", "sister",
            "brother", "family", "apple", "banana", "school", "teacher", "student",
            "book", "pencil", "good", "morning", "afternoon", "night", "champion",
            "words", "translate", "pronounce",
        }
        tiene_indicador_ingles = False
        for w in kw_ingles_fuerte:
            if w in tokens:
                tiene_indicador_ingles = True
                puntajes["Inglés"] += 3 if w in ("ingles", "english", "vocabulary", "translate") else 2
        if any(
            fr in txt_norm
            for fr in ("en ingles", "in english", "how do you say", "repeat after me", "vocabulario en ingles")
        ):
            tiene_indicador_ingles = True
            puntajes["Inglés"] += 5
        # 'red' y 'ten' solo suman a Inglés si ya existe contexto bilingüe/inglés
        if tiene_indicador_ingles and ("red" in tokens or "ten" in tokens):
            puntajes["Inglés"] += 2

        # Palabras e indicadores de Matemáticas (normalizadas sin tilde para aceptar con y sin acento)
        kw_mate = {
            "matematica", "matematicas", "suma", "sumas", "sumar", "resta", "restas",
            "restar", "multiplica", "multiplicacion", "multiplicar", "multiplicaciones",
            "tabla", "tablas", "divide", "division", "dividir", "divisiones",
            "fraccion", "fracciones", "numerador", "denominador", "numero", "numeros",
            "calculo", "calcular", "calcula", "decena", "decenas", "unidad", "unidades",
            "centena", "centenas", "geometria", "triangulo", "triangulos", "cuadrado",
            "cuadrados", "rectangulo", "rectangulos", "circulo", "circulos", "perimetro",
            "area", "angulo", "angulos", "poligono", "operacion", "operaciones",
            "aritmetica", "porcentaje", "potencia", "mitad", "doble", "triple",
        }
        for w in kw_mate:
            if w in tokens:
                puntajes["Matemáticas"] += 2
        if re.search(r"\b\d+(?:[.,]\d+)?\s*[+\-×x*/÷]\s*\d+(?:[.,]\d+)?\b", txt_low):
            puntajes["Matemáticas"] += 4

        # Palabras e indicadores de Lenguaje
        kw_lenguaje = {
            "lenguaje", "lectura", "leer", "cuento", "cuentos", "fabula", "fabulas",
            "poema", "poesia", "oracion", "oraciones", "parrafo", "parrafos",
            "verbo", "verbos", "sustantivo", "sustantivos", "adjetivo", "adjetivos",
            "silaba", "silabas", "ortografia", "redaccion", "abecedario", "sinonimo",
            "sinonimos", "antonimo", "antonimos", "personaje", "narracion", "sujeto",
            "predicado", "tilde", "acento", "vocabulario", "resumen", "comunicacion",
        }
        for w in kw_lenguaje:
            if w in tokens:
                puntajes["Lenguaje"] += 2

        # Palabras e indicadores de Ciencias (Naturales + Sociales / Historia / Bolivia)
        kw_ciencias = {
            "ciencias", "ciencia", "naturales", "sociales", "planta", "plantas",
            "fotosintesis", "agua", "evaporacion", "condensacion", "precipitacion",
            "nube", "lluvia", "planeta", "planetas", "solar", "tierra", "ecosistema",
            "naturaleza", "cuerpo", "humano", "experimento", "dinosaurio", "dinosaurios",
            "celula", "celulas", "energia", "vertebrados", "invertebrados", "reciclaje",
            "reproduccion", "asexual", "semilla", "semillas", "organo", "organos",
            "salud", "historia", "geografia", "bolivia", "independencia", "libertad",
            "batalla", "heroes", "proceres", "sucre", "bolivar", "murillo", "avaroa",
            "departamento", "departamentos", "potosi", "oruro", "cochabamba", "tarija",
            "beni", "pando", "simbolos", "patrios", "bandera", "escudo", "himno",
            "mapa", "continente", "cultura", "tiwanaku", "incas", "andina", "red",
            "trofica", "alimentaria",
        }
        for w in kw_ciencias:
            if w in tokens:
                puntajes["Ciencias"] += 2 if w != "red" else 1
        if any(
            fr in txt_norm
            for fr in (
                "ciclo del agua", "sistema solar", "seres vivos", "cuerpo humano",
                "ciencias sociales", "historia de bolivia", "simbolos patrios",
                "reproduccion sexual", "reproduccion asexual", "red trofica", "red alimentaria",
            )
        ):
            puntajes["Ciencias"] += 4

        # Palabras e indicadores de Hábitos y Orden
        kw_habitos = {
            "habito", "habitos", "orden", "organizacion", "mochila", "estuche",
            "cartuchera", "horario", "rutina", "escritorio", "limpieza", "puntualidad",
            "responsabilidad", "alistar", "guardar", "ordenar", "concentracion",
            "concentrarme", "distraerme", "distraccion",
        }
        for w in kw_habitos:
            if w in tokens:
                puntajes["Hábitos y Orden"] += 2

        mejor_modulo, mejor_puntaje = max(puntajes.items(), key=lambda kv: kv[1])
        if mejor_puntaje > 0:
            return mejor_modulo

        if modulo_preferido:
            if self.db and hasattr(self.db, "normalizar_modulo"):
                return self.db.normalizar_modulo(modulo_preferido)
            return modulo_preferido
        return "Matemáticas"

    def _obtener_contexto_pensum(self, tarea_o_texto: str) -> str:
        """Recupera el resumen de pensum cargado por el docente para el módulo actual."""
        if not self.db or not hasattr(self.db, "obtener_pensum_modulo"):
            return ""
        modulo = self.detectar_modulo_automatico(tarea_o_texto)
        info = self.db.obtener_pensum_modulo(modulo)
        if not info or not info.get("contenido_resumen"):
            return ""
        return (
            f"Contexto del pensum escolar del módulo {modulo} ({info.get('nombre_archivo', 'Guía')}): "
            f"'{info['contenido_resumen'][:420]}'. "
        )

    # =========================================================================
    # 1. TUTOR ACADÉMICO GUIADO EN CAPAS + GUARDRAILS CONTEXTUALES + DOCUMENTOS
    # =========================================================================
    @staticmethod
    def _normalizar_anti_evasion(texto_norm: str) -> str:
        """
        Detecta evasiones con letras separadas por espacios/puntos/guiones ('n o v i a', 'f r e e f i r e')
        y sustituciones leetspeak ('fr33 fir3', 'n0v1a', 'r0bl0x').
        """
        # 1. Unir secuencias de 3 o más caracteres individuales separados por espacios/puntos/guiones
        def _unir_letras(m: re.Match) -> str:
            return re.sub(r"[\s.\-_]+", "", m.group(0))

        compacto = re.sub(
            r"\b[a-z0-9ñ](?:[\s.\-_]+[a-z0-9ñ]){2,}\b",
            _unir_letras,
            texto_norm,
        )
        # 2. Traducir dígitos/símbolos leetspeak cuando están mezclados con letras
        tabla_leet = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

        def _desleet_token(m: re.Match) -> str:
            tok = m.group(0)
            if any(c.isalpha() for c in tok) and any(c in "013457@$" for c in tok):
                return tok.translate(tabla_leet)
            return tok

        return re.sub(r"[a-z0-9ñ@$]+", _desleet_token, compacto)

    def _verificar_restriccion_tematica(self, texto: str) -> Optional[str]:
        """
        Filtro Guardián Infantil Contextual:
        1) Detecta situaciones de bullying o agresión hacia el niño y brinda orientación protectora inmediata.
        2) Permite consultas académicas legítimas (biología de las plantas, historia de la independencia,
           salud/prevención en ciencias, lectura de cuentos, sílabas y técnicas para evitar distracciones).
        3) Bloquea temas inapropiados incluso con leetspeak o letras espaciadas.
        """
        norm = _normalizar_ia(texto)
        if not norm:
            return None

        norm_evasion = self._normalizar_anti_evasion(norm)

        # 1. PRIORIDAD DE PROTECCIÓN INFANTIL: Bullying o agresión sufrida por el estudiante
        es_reporte_agresion_o_bullying = bool(
            re.search(
                r"\b(?:bullying|acoso\s+escolar|ciberbullying|cyberbullying|matonaje)\b"
                r"|\bme\s+(?:quieren|van\s+a|estan|esta|intentan)?\s*"
                r"(?:golpear|pegar|lastimar|amenazar|empujar|acosar|insultar|molestar|hacer\s+dano|hacer\s+bullying)\b"
                r"|\bme\s+(?:pegan|pegaron|golpean|golpearon|amenazan|amenazaron|empujan|empujaron|molestan|insultan|acosan|hacen\s+burla)\b"
                r"|\b(?:un(?:os)?\s+(?:ninos?|companeros?|chicos?)|en\s+el\s+recreo)\s+.*?\bme\s+(?:pegan|golpean|molestan|quieren\s+pegar|quieren\s+golpear)\b",
                norm_evasion,
            )
        )
        if es_reporte_agresion_o_bullying:
            self.ultima_fuente = "Protocolo de Protección Infantil"
            return self._personalizar_respuesta_local(
                "Lo que me cuentas es muy importante y tú mereces estar seguro y protegido; no estás solo. "
                "Por favor, habla ahora mismo con tu profesor, profesora, mamá, papá o un adulto de confianza de tu familia "
                "para que te cuiden y ayuden de inmediato."
            )

        # 2. EXCEPCIONES CONTEXTUALES ACADÉMICAS Y DE HÁBITOS DE ESTUDIO
        es_biologia_reproduccion = bool(
            re.search(
                r"\b(?:reproduccion|asexual|planta|plantas|flor|flores|semilla|semillas|polen|polinizacion|"
                r"celula|celulas|seres\s+vivos|biologia|ciencias\s+naturales|especies|esporas|bulbos|tuberculos)\b",
                norm_evasion,
            )
        )
        es_lenguaje_o_cuento = bool(
            re.search(
                r"\b(?:cuento|fabula|historia|rana|sapo|princesa|poema|oracion|oraciones|palabra|palabras|"
                r"silaba|silabas|letra|letras|vocal|vocales|consonante|lectura|leer|verbo|sustantivo|adjetivo|"
                r"sinonimo|antonimo|diccionario)\b",
                norm_evasion,
            )
        )
        es_historia_independencia = bool(
            re.search(
                r"\b(?:independencia|historia|libertad|batalla|heroes|proceres|bolivia|america|sucre|bolivar|"
                r"murillo|avaroa|juana\s+azurduy|tupac\s+katari|pacifico|chaco|revolucion|colonia|republica|"
                r"patria|indigenas|siglo)\b",
                norm_evasion,
            )
        )
        es_salud_prevencion_ciencias = bool(
            re.search(
                r"\b(?:efectos?|consecuencias?|dano|danos|perjudica\w*|salud|cuerpo\s+humano|organos?|cerebro|"
                r"higado|pulmones|corazon|sistema\s+nervioso|prevencion|enfermedad\w*|cuidar\s+(?:el|mi)\s+cuerpo|"
                r"por\s+que\s+hace\s+(?:mal|dano)|alcohol\s+en\s+gel|alcohol\s+medicinal|desinfectar)\b",
                norm_evasion,
            )
        )
        es_evitar_distraccion_estudio = bool(
            re.search(
                r"\b(?:evitar\s+distra\w*|no\s+distra\w*|dejar\s+de\s+distra\w*|distraerme|distraccion\w*|"
                r"concentr\w*|enfocar\w*|mientras\s+estudio|al\s+estudiar|para\s+estudiar|hacer\s+mi\s+tarea|"
                r"controlar\s+el\s+tiempo|dejar\s+el\s+celular|apagar)\b",
                norm_evasion,
            )
        )

        # 3. VERIFICACIÓN DE ROMANCE / CONTENIDO ADULTO (respetando biología y lenguaje/cuentos)
        tiene_romance_duro = bool(
            re.search(
                r"\b(novia|novio|enamorar(?:me|se)?|enamorad[oa]|conquistar|"
                r"cita\s+romantica|tener\s+pareja|desnud\w*|porno\w*|erotic\w*|"
                r"contenido\s+para\s+adultos|paginas?\s+para\s+adultos)\b",
                norm_evasion,
            )
        )
        tiene_sexual_no_academico = bool(
            re.search(r"\b(sexo|sexual\w*)\b", norm_evasion) and not es_biologia_reproduccion
        )
        tiene_beso_o_ligar_no_academico = bool(
            re.search(r"\b(besar|beso|ligar)\b", norm_evasion) and not es_lenguaje_o_cuento
        )
        if tiene_romance_duro or tiene_sexual_no_academico or tiene_beso_o_ligar_no_academico:
            self.ultima_fuente = "Filtro Guardián Infantil"
            return (
                "Soy Haru, tu compañero educativo para primaria, así que no converso sobre novios, romance ni temas de adultos. "
                "Si quieres ayuda con tus tareas, cómo concentrarte o dudas de clase, ¡aquí estoy para ti!"
            )

        # 4. VERIFICACIÓN DE VIDEOJUEGOS COMERCIALES / REDES / APUESTAS (respetando consultas de concentración)
        tiene_trucos_o_apuestas = bool(
            re.search(r"\b(headshot|diamantes\s+gratis|apuestas?|casino|hackear|cheats?)\b", norm_evasion)
        )
        tiene_juego_o_red = bool(
            re.search(
                r"\b(free\s*fire|freefire|fortnite|warzone|valorant|call\s+of\s+duty|gta|roblox|"
                r"brawl\s+stars|clash\s+royale|pubg|minecraft\s+pvp|tiktok)\b",
                norm_evasion,
            )
        )
        if tiene_trucos_o_apuestas or (tiene_juego_o_red and not es_evitar_distraccion_estudio):
            self.ultima_fuente = "Filtro Guardián Infantil"
            return (
                "Estoy aquí para ayudarte en tus materias de primaria y hábitos de estudio, no doy trucos ni consejos de videojuegos o redes. "
                "¡Avancemos tus pasitos de tarea primero para que luego disfrutes tu tiempo libre tranquilo!"
            )

        # 5. VERIFICACIÓN DE VIOLENCIA / SUSTANCIAS / TRAMPAS (respetando historia y ciencias de la salud)
        tiene_trampa_o_arma_dura = bool(
            re.search(
                r"\b(matar|pistola|cuchillo|cerveza|vape\w*|hacer\s+trampa|copiar\s+en\s+el\s+examen|pasame\s+las\s+respuestas)\b",
                norm_evasion,
            )
        )
        tiene_pelea_no_historica = bool(
            re.search(r"\b(pelear(?:me|se|on)?|golpear|arma|armas)\b", norm_evasion)
            and not es_historia_independencia
        )
        tiene_sustancia_no_academica = bool(
            re.search(r"\b(droga\w*|alcohol|cigarrillo)\b", norm_evasion)
            and not es_salud_prevencion_ciencias
        )
        if tiene_trampa_o_arma_dura or tiene_pelea_no_historica or tiene_sustancia_no_academica:
            self.ultima_fuente = "Filtro Guardián Infantil"
            return (
                "Como tu tutor escolar cuido tu seguridad y aprendizaje honesto, por eso no ayudo con violencia, armas, sustancias ni trampas. "
                "Cuéntame qué ejercicio o materia quieres aprender y lo resolvemos paso a paso."
            )
        return None

    def _detectar_contencion_emocional(self, texto: str) -> Optional[str]:
        """
        Detecta prioritariamente estados emocionales y negaciones ('no estoy feliz', 'me fue mal',
        'estoy triste', 'soy tonto', 'no me sale', 'estoy frustrado', 'no puedo') ANTES de buscar
        palabras clave genéricas y sin exigir palabras como 'como' o 'consejo'.
        """
        norm = _normalizar_ia(_normalizar_ortografia_infantil(texto))
        if not norm:
            return None

        # 1. Negación de ánimo positivo ("no estoy feliz", "no me siento bien", "no estoy contento")
        if re.search(
            r"\b(?:no|nunca|tampoco|nada)\s+(?:(?:me\s+siento|estoy|soy|anda|ando|estaba|fui|me\s+fue)\s+){0,2}"
            r"(?:nada\s+|muy\s+|tan\s+)?(?:feliz|felices|content[oa]s?|alegre|alegres|bien|animad[oa]s?|genial|excelente)\b",
            norm,
        ):
            self.ultima_fuente = "Apoyo Emocional Haru"
            resp = (
                "Está bien no sentirse feliz ahora mismo. Respira despacito conmigo y, si quieres, "
                "dividimos tu tarea en un pasito muy pequeño o tomamos un breve respiro."
            )
            return self._personalizar_respuesta_local(resp)

        # 2. Mal resultado / frustración por desempeño ("me fue mal", "me salió mal", "saqué mala nota")
        if re.search(
            r"\b(?:me\s+fue\s+(?:muy\s+|re\s+|super\s+|tan\s+)?mal|me\s+salio\s+mal|saque\s+mala\s+nota|reprobe)\b",
            norm,
        ):
            self.ultima_fuente = "Apoyo Emocional Haru"
            resp = (
                "Un mal momento no borra todo lo que eres capaz de lograr. Respiremos con calma "
                "y revisemos juntos qué parte podemos mejorar poco a poco."
            )
            return self._personalizar_respuesta_local(resp)

        # 3. Tristeza o desánimo ("estoy triste", "me siento triste", "quiero llorar")
        if re.search(
            r"(?<!\bno\s)(?<!\bnunca\s)(?<!\btampoco\s)\b(?:estoy|me\s+siento|anda|ando|estaba)\s+"
            r"(?:muy\s+|re\s+|algo\s+|un\s+poco\s+|tan\s+)?(?:triste|tristes|mal|fatal|horrible|desanimad[oa]s?|abrumad[oa]s?)\b"
            r"|\bquiero\s+llorar\b",
            norm,
        ):
            self.ultima_fuente = "Apoyo Emocional Haru"
            resp = (
                "Siento mucho que te sientas triste hoy. Estoy aquí para acompañarte con calma; "
                "podemos respirar juntos o avanzar solo un pasito muy suave."
            )
            return self._personalizar_respuesta_local(resp)

        # 4. Autodescalificación ("soy tonto", "soy bruto", "soy torpe", "no sirvo")
        if re.search(
            r"(?<!\bno\s)(?<!\bnunca\s)\b(?:soy|me\s+siento)\s+(?:un\s+|una\s+|muy\s+|re\s+)?(?:tont[oa]|brut[oa]|burr[oa]|torpe|incapaz|inutil)\b"
            r"|\bno\s+sirvo\s+para\s+esto\b",
            norm,
        ):
            self.ultima_fuente = "Apoyo Emocional Haru"
            resp = (
                "No eres tonto para nada; eres muy valioso y tu mente solo necesita un poco más de tiempo "
                "y calma para aprenderlo. Vamos paso a paso, yo te acompaño."
            )
            return self._personalizar_respuesta_local(resp)

        # 5. Frustración, enojo o nervios ("estoy frustrado", "estoy nervioso", "me rindo")
        if re.search(
            r"(?<!\bno\s)(?<!\bnunca\s)(?<!\btampoco\s)\b(?:estoy|me\s+siento|anda|ando|estaba)\s+"
            r"(?:muy\s+|re\s+|algo\s+|un\s+poco\s+|tan\s+)?(?:frustrad[oa]s?|enojad[oa]s?|molest[oa]s?|angustiad[oa]s?|ansios[oa]s?|nervios[oa]s?|estresad[oa]s?)\b"
            r"|\b(?:me\s+rindo|ya\s+no\s+quiero\s+intentar|odio\s+estudiar)\b",
            norm,
        ):
            self.ultima_fuente = "Apoyo Emocional Haru"
            resp = (
                "Es normal sentir frustración cuando algo cuesta trabajo. Hagamos una pausa corta, "
                "inhala profundo tres veces en el botón Respirar y luego probamos juntos paso a paso."
            )
            return self._personalizar_respuesta_local(resp)

        # 6. Bloqueo ante la tarea ("no me sale", "no puedo")
        m_bloq = re.search(r"\b(no\s+me\s+salen?|no\s+puedo(?:\s+mas|\s+hacerlo|\s+con\s+esto)?)\b", norm)
        if m_bloq:
            frase = m_bloq.group(1)
            self.ultima_fuente = "Apoyo Emocional Haru"
            if frase.startswith("no me sale"):
                resp = (
                    "Cuando algo no sale al primer intento, significa que estás practicando. "
                    "Tomemos aire despacito y partamos este ejercicio en un paso pequeñito."
                )
            else:
                resp = (
                    "A veces todo junto parece muy grande, pero sí puedes avanzar poco a poco. "
                    "Hagamos solo un pedacito pequeño juntos y sin apuro."
                )
            return self._personalizar_respuesta_local(resp)

        return None

    def _responder_temas_curriculares_locales(self, pregunta: str) -> Optional[str]:
        """
        Provee respuestas educativas verificadas 100% offline para consultas académicas
        curriculares frecuentes (biología de plantas, historia de la independencia,
        salud del cuerpo humano, sílabas, cuentos).
        """
        norm = _normalizar_ia(_normalizar_ortografia_infantil(pregunta))
        if not norm:
            return None

        if "reproduccion" in norm and ("planta" in norm or "sexual" in norm or "asexual" in norm):
            self.ultima_fuente = "Conocimiento Curricular Haru"
            return self._personalizar_respuesta_local(
                "En Ciencias Naturales, las plantas tienen dos formas de reproducción: la reproducción sexual usa "
                "las flores, el polen y las semillas para crear una nueva planta, mientras que la reproducción asexual "
                "nace de una parte de la misma planta, como un tallo, bulbo o tubérculo como la papa.",
                adaptar_grado=True,
            )

        if "independencia" in norm or ("pelearon" in norm and "historia" in norm):
            self.ultima_fuente = "Conocimiento Curricular Haru"
            return self._personalizar_respuesta_local(
                "En la historia de la independencia, valientes patriotas y heroínas como Juana Azurduy, Pedro Domingo Murillo, "
                "Simón Bolívar y Antonio José de Sucre lucharon por la libertad para fundar una nación libre en 1825.",
                adaptar_grado=True,
            )

        if "alcohol" in norm and any(w in norm for w in ("efecto", "cuerpo", "salud", "dano", "cerebro", "higado")):
            self.ultima_fuente = "Conocimiento Curricular Haru"
            return self._personalizar_respuesta_local(
                "En Ciencias de la Salud aprendemos que el alcohol daña el cerebro, el hígado y el sistema nervioso, "
                "disminuyendo los reflejos y la memoria. Por eso los niños y las personas cuidan su cuerpo tomando agua "
                "y alimentos saludables.",
                adaptar_grado=True,
            )

        if "ligar" in norm and "silaba" in norm:
            self.ultima_fuente = "Conocimiento Curricular Haru"
            return self._personalizar_respuesta_local(
                "Ligar o unir sílabas consiste en juntar consonantes y vocales paso a paso con palmadas "
                "(por ejemplo: ma + pa = mapa, me + sa = mesa) para leer y formar palabras completas.",
                adaptar_grado=True,
            )

        if ("beso" in norm and "rana" in norm) or ("princesa" in norm and "sapo" in norm):
            self.ultima_fuente = "Conocimiento Curricular Haru"
            return self._personalizar_respuesta_local(
                "El cuento clásico del príncipe rana nos enseña el valor de cumplir las promesas y tratar con amabilidad "
                "a los demás. Al leerlo, identifica el inicio, el nudo y el desenlace de la historia.",
                adaptar_grado=True,
            )

        return None

    def _responder_vida_cotidiana_y_estudio(self, pregunta: str) -> Optional[str]:
        """Responde dudas cotidianas útiles (hora, fecha, hábitos de estudio, concentración)."""
        norm = _normalizar_ia(_normalizar_ortografia_infantil(pregunta))
        if not norm:
            return None

        if re.search(r"\b(que\s+hora\s+(es|son)|dime\s+la\s+hora|hora\s+actual|sabes\s+la\s+hora|tienes\s+la\s+hora)\b", norm):
            ahora = datetime.now()
            periodo = "de la mañana" if ahora.hour < 12 else ("de la tarde" if ahora.hour < 19 else "de la noche")
            self.ultima_fuente = "Reloj y Guía Diaria Haru"
            return self._personalizar_respuesta_local(
                f"Son las {ahora.strftime('%H:%M')} {periodo}. ¡Buen momento para hacer un pasito con calma o tomar un descanso breve!"
            )

        if re.search(r"\b(que\s+dia\s+es\s+(hoy|ahora)|cual\s+es\s+la\s+fecha|fecha\s+de\s+hoy|en\s+que\s+fecha\s+estamos)\b", norm):
            ahora = datetime.now()
            dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
            meses = (
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
            )
            self.ultima_fuente = "Reloj y Guía Diaria Haru"
            return self._personalizar_respuesta_local(
                f"Hoy es {dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]} de {ahora.year}. ¡Organicemos tus tareas del día paso a paso!"
            )

        pide_consejo = any(
            w in norm
            for w in ("como", "mejorar", "consejo", "tips", "ayuda", "puedo", "organizar", "sacar", "evitar", "dejar")
        )
        if re.search(r"\b(mejorar\s+(?:en\s+)?(?:mis|los)\s+estudios|estudiar\s+mejor|rendir\s+mejor|sacar\s+buenas\s+notas|mejorar\s+(?:mis\s+)?calificaciones|habitos\s+de\s+estudio|como\s+estudio)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return self._personalizar_respuesta_local(
                "Para mejorar en tus estudios: 1) despeja tu mesa dejando solo un cuaderno, "
                "2) divide cada tarea en bloques cortos de 10 minutos con 2 minutos de descanso, "
                "y 3) al terminar, explícate en voz alta con tus propias palabras lo que aprendiste."
            )

        if (pide_consejo or "distra" in norm) and re.search(
            r"\b(concentr\w*|no\s+distra\w*|evitar\s+distra\w*|distraerme|distraccion\w*|atencion|enfocar\w*|foco|organizar\s+(?:mis\s+)?tareas)\b",
            norm,
        ):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return self._personalizar_respuesta_local(
                "Para concentrarte mejor y evitar distracciones con pantallas o juegos: deja el celular o juguetes en otra habitación, "
                "usa el reloj de Haru por 10 minutos y enfócate únicamente en el paso actual antes de tu descanso."
            )

        if pide_consejo and re.search(r"\b(examen\w*|evaluacion\w*|memori\w*|no\s+olvid\w*|acordarme)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return self._personalizar_respuesta_local(
                "Para recordar mejor para un examen: lee cada idea en voz alta, dibuja o escribe un ejemplo propio en tu cuaderno "
                "y descansa bien la noche anterior para que tu cerebro ordene lo aprendido."
            )

        if re.search(r"\b(nervios\w*|frustrad\w*|enojad\w*|triste|no\s+me\s+sale|estres\w*)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return self._personalizar_respuesta_local(
                "Cuando te sientas frustrado o nervioso es normal: toca el botón Respirar para tomar 3 respiraciones suaves, "
                "toma un poquito de agua y luego resolvamos juntos solo el primer pedacito del ejercicio."
            )

        return None

    @staticmethod
    def _formatear_num_doc(val: float) -> str:
        num = int(round(val)) if abs(val - round(val)) < 1e-9 else round(float(val), 4)
        if isinstance(num, int):
            return str(num)
        return f"{num:.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def _explicar_operacion_primaria(a: float, op: str, b: float, res: float) -> str:
        a_s = MotorIAHaru._formatear_num_doc(a)
        b_s = MotorIAHaru._formatear_num_doc(b)
        r_s = MotorIAHaru._formatear_num_doc(res)
        if op == "+":
            if a >= 10 and b >= 10 and a == int(a) and b == int(b):
                u_sum = (int(a) % 10) + (int(b) % 10)
                return f"Para sumar {a_s} + {b_s}, alinea unidades ({int(a)%10}+{int(b)%10}={u_sum}) y luego las decenas: da {r_s}."
            return f"Para sumar {a_s} + {b_s}, parte desde {a_s} y agrega {b_s}: el resultado es {r_s}."
        if op == "-":
            if a >= 10 and b >= 10 and a == int(a) and b == int(b):
                return f"Para restar {a_s} - {b_s}, resta primero las unidades y luego las decenas en columna: queda {r_s}."
            return f"Para restar {a_s} - {b_s}, quita {b_s} a {a_s}: el resultado es {r_s}."
        if op == "*":
            return f"Para multiplicar {a_s} × {b_s}, suma {a_s} veces el número {b_s}: obtienes {r_s}."
        if op == "/":
            return f"Para dividir {a_s} ÷ {b_s}, reparte {a_s} en {b_s} grupos iguales: a cada grupo le toca {r_s}."
        return f"La operación {a_s} {op} {b_s} da como resultado {r_s}."

    @staticmethod
    def _limpiar_prefijo_ejercicio(texto: str) -> str:
        """Elimina numeración de lista (`1.`, `2)`, `3.-`, `4-`, `Ejercicio 5:`) para que no contamine cálculos."""
        lineas_limpias: List[str] = []
        patron_pref = re.compile(
            r"^\s*(?:"
            r"(?:#+\s*)?(?:ejercicio|problema|actividad|pregunta|punto|tema|inciso|tarea|reto)\s*\d{1,3}\s*(?:[:.\-–)]+\s*|\s+)"
            r"|\(\s*\d{1,3}\s*\)\s*[:.\-–)]*\s*"
            r"|\d{1,3}\s*[).]\s*[-–]?\s*"
            r"|\d{1,3}\s*[-–]\s+(?=\S)"
            r"|[a-zA-Z]\s*\)\s+"
            r")",
            re.IGNORECASE,
        )
        for ln in (texto or "").splitlines():
            limpia = patron_pref.sub("", ln).strip()
            if limpia:
                lineas_limpias.append(limpia)
        return "\n".join(lineas_limpias)

    def _analizar_operaciones_en_texto(self, texto: str) -> List[Tuple[str, Union[int, float], str]]:
        """
        Detecta y evalúa de forma segura (`ast`) operaciones aritméticas en guías o ejercicios:
        - Limpia prefijos numéricos (`1.`, `2)`, `3.-`, `4-`) para que nunca se mezclen con operaciones.
        - Soporta comas decimales (`3,5 + 2,5`), negativos iniciales (`-5 + 8`), potencias (`^`),
          porcentajes (`15% de 80`), expresiones compuestas (`2 + 3 * 4`) y problemas verbales simples.
        - Ignora fechas (`12-10-2026`, `12/10/2026`) y rangos de años (`2024-2025`).
        """
        if not texto or not texto.strip():
            return []

        sin_pref = self._limpiar_prefijo_ejercicio(texto) or texto
        limpio = sin_pref
        # 1. Ignorar fechas completas (DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY) y rangos de años (2024-2025)
        limpio = re.sub(r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b", " ", limpio)
        limpio = re.sub(r"\b(?:1[5-9]\d{2}|20\d{2})\s*[-–]\s*(?:1[5-9]\d{2}|20\d{2})\b", " ", limpio)
        limpio = re.sub(r"\b[a-zA-ZñÑáéíóúü_]+(?:-[a-zA-ZñÑáéíóúü_\d]+)+\b", " ", limpio)
        # Si hay "= <resultado>" escrito en la guía (ej. "2 + 3 * 4 = 14"), separar el lado izquierdo
        limpio = re.sub(r"=\s*-?\d+(?:[.,]\d+)?", " ", limpio)

        # 2. Normalizar comas decimales entre dígitos, porcentajes y símbolos de operadores
        limpio = re.sub(r"(\d),(\d)", r"\1.\2", limpio)
        limpio = re.sub(
            r"(\d+(?:\.\d+)?)\s*%\s*de\s*(\d+(?:\.\d+)?)",
            r"((\1 / 100) * \2)",
            limpio,
            flags=re.IGNORECASE,
        )
        limpio = limpio.replace("×", "*").replace("÷", "/").replace("\u2212", "-").replace("^", "**")
        limpio = re.sub(r"(?<=[\d\)])\s*[xX]\s*(?=[\d\(])", " * ", limpio)

        resultados: List[Tuple[str, Union[int, float], str]] = []
        vistos = set()

        # 3. Capturar expresiones completas (simples, con signo unario inicial o compuestas con precedencia)
        patron_expr = re.compile(
            r"(?:(?<![\w\d\)])-(?=\s*\(|\d))?"
            r"(?:\(\s*)*-?\d+(?:\.\d+)?(?:\s*\))*"
            r"(?:\s*(?:\*\*|[+\-*/])\s*(?:\(\s*)*-?\d+(?:\.\d+)?(?:\s*\))*)+"
        )
        for m in patron_expr.finditer(limpio):
            expr_raw = re.sub(r"\s+", " ", m.group(0)).strip()
            if not expr_raw or expr_raw in vistos:
                continue
            try:
                val = evaluar_ast_seguro(expr_raw)
            except Exception:
                continue
            vistos.add(expr_raw)
            val_num: Union[int, float] = (
                int(round(val)) if abs(val - round(val)) < 1e-9 else round(float(val), 4)
            )
            r_s = self._formatear_num_doc(float(val_num))

            m_bin = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)", expr_raw)
            if m_bin:
                a_str, op, b_str = m_bin.group(1), m_bin.group(2), m_bin.group(3)
                explicacion = self._explicar_operacion_primaria(float(a_str), op, float(b_str), float(val))
                op_vis = {"*": "×", "/": "÷"}.get(op, op)
                etq = f"{a_str} {op_vis} {b_str}"
            else:
                etq = expr_raw.replace("*", "×").replace("/", "÷")
                explicacion = (
                    f"Para resolver {etq}, aplica el orden de operaciones "
                    f"(paréntesis, multiplicaciones/divisiones y luego sumas/restas): el resultado es {r_s}."
                )
            resultados.append((etq, val_num, explicacion))

        # 4. Si no hubo expresión simbólica, verificar problemas verbales / palabras numéricas / mitad / doble / porcentaje
        if not resultados:
            for linea in sin_pref.splitlines():
                ln_limpia = re.sub(r"=\s*$", "", linea).strip()
                if len(ln_limpia) < 5:
                    continue
                resp_ast = resolver_pregunta_matematica(ln_limpia)
                if resp_ast:
                    num_ast = self._extraer_resultado_numerico(ln_limpia, resp_ast)
                    if num_ast is not None:
                        resultados.append((ln_limpia[:52], num_ast, resp_ast))
        return resultados

    def obtener_documento_activo(self) -> Optional[Dict[str, object]]:
        """Retorna resumen del documento actualmente abierto con el estudiante, o `None`."""
        doc = self._documento_activo
        if not doc:
            return None
        ejercicios = doc.get("ejercicios") or []
        total = len(ejercicios)
        idx = int(doc.get("indice_actual") or 0)
        explicados = len(doc.get("ejercicios_explicados") or ())
        desbloqueados = int(doc.get("ejercicios_desbloqueados") or 0)
        return {
            "nombre": str(doc.get("nombre") or "archivo"),
            "total_ejercicios": total,
            "ejercicio_actual": min(total, idx + 1) if total else 0,
            "modulo": str(doc.get("modulo") or "Matemáticas"),
            "ejercicios_explicados": explicados,
            "ejercicios_desbloqueados": desbloqueados,
            "ejercicios_restantes_pack": max(0, desbloqueados - explicados),
        }

    def cerrar_documento_activo(self) -> None:
        """Cierra el documento en sesión para volver al flujo libre de misiones."""
        self._documento_activo = None
        self._ultimo_turno_fue_documento = False

    def _parsear_ejercicios_documento(self, documento_texto: str) -> Tuple[str, List[Dict[str, object]]]:
        """
        Descompone cualquier guía o archivo en `(encabezado_doc, lista_de_ejercicios)`
        soportando del 1 al 999, encabezados (`Ejercicio 1:`, `Problema 2`, `4.-`),
        incisos (`a)`, `b)`) y columnas inline separadas por varios espacios o `|`.
        """
        raw = (documento_texto or "").replace("\r\n", "\n")
        lineas_raw: List[str] = []
        for ln in raw.splitlines():
            ln_s = ln.strip()
            if not ln_s:
                continue
            # Separar columnas inline tipo "1) 5+3=   2) 8+4=" o "1. 5+3 | 2. 8+4"
            ln_div = re.sub(
                r"(?:[ \t]{2,}|\s*\|\s*)(?=(?:\(\d{1,3}\)|\d{1,3}\s*[).]|(?:Ejercicio|Problema|Actividad|Pregunta|Punto|Inciso|Reto)\s+\d{1,3}\b))",
                "\n",
                ln_s,
                flags=re.IGNORECASE,
            )
            for sub in ln_div.splitlines():
                sub_s = sub.strip()
                if sub_s:
                    lineas_raw.append(sub_s)

        if not lineas_raw:
            return "", []

        patron_encabezado = re.compile(
            r"^\s*(?:"
            r"(?:#+\s*)?(?:ejercicio|problema|actividad|pregunta|punto|tema|inciso|tarea|reto)\s*(\d{1,3})\b"
            r"|#+\s*.*?\b(?:ejercicio|problema|actividad|pregunta|punto|tema)\s*(\d{1,3})\b"
            r"|\(\s*(\d{1,3})\s*\)(?=\s*\S)"
            r"|(\d{1,3})\s*(?:[).]|-\s+(?=\S)|\.-\s*)(?=\s*\S)"
            r")",
            re.IGNORECASE,
        )

        items: List[Dict[str, object]] = []
        encabezado_lineas: List[str] = []
        actual: Optional[Dict[str, object]] = None

        for ln in lineas_raw:
            m = patron_encabezado.match(ln)
            if m:
                num_str = next((g for g in m.groups() if g is not None), None)
                num_val = int(num_str) if num_str is not None else (len(items) + 1)
                if actual is not None:
                    actual["texto"] = "\n".join(actual["lineas"])[:1400]
                    items.append(actual)
                actual = {
                    "numero": num_val,
                    "etiqueta": f"Ejercicio {num_val}",
                    "lineas": [ln],
                }
            elif actual is not None:
                # Cortar en notas finales explícitas para no contaminar el último ejercicio
                if ln.startswith("[Documento truncado"):
                    continue
                if len(actual["lineas"]) < 8:
                    actual["lineas"].append(ln)
            else:
                encabezado_lineas.append(ln)

        if actual is not None:
            actual["texto"] = "\n".join(actual["lineas"])[:1400]
            items.append(actual)

        # Si no hubo numeración explícita, intentar letras a), b), c) o párrafos sustanciales
        if not items:
            patron_letra = re.compile(r"^\s*([a-zA-Z])\s*\)\s+\S")
            encabezado_lineas = []
            for ln in lineas_raw:
                if patron_letra.match(ln):
                    if actual is not None:
                        actual["texto"] = "\n".join(actual["lineas"])[:1400]
                        items.append(actual)
                    idx_n = len(items) + 1
                    actual = {"numero": idx_n, "etiqueta": f"Ejercicio {idx_n}", "lineas": [ln]}
                elif actual is not None:
                    if len(actual["lineas"]) < 8:
                        actual["lineas"].append(ln)
                else:
                    encabezado_lineas.append(ln)
            if actual is not None:
                actual["texto"] = "\n".join(actual["lineas"])[:1400]
                items.append(actual)

        if not items:
            ejercicios_crudos = [
                ln for ln in lineas_raw
                if len(ln) >= 6
                and not ln.startswith("[Documento truncado")
                and not ln.lower().startswith(("nombre:", "curso:", "fecha:", "guía", "guia", "práctica", "practica"))
            ]
            if not ejercicios_crudos:
                ejercicios_crudos = [ln for ln in lineas_raw if not ln.startswith("[Documento truncado")]
            for i, ln in enumerate(ejercicios_crudos, start=1):
                items.append({"numero": i, "etiqueta": f"Ejercicio {i}", "texto": ln[:1400]})
            encabezado_lineas = [
                ln for ln in lineas_raw
                if ln.lower().startswith(("nombre:", "curso:", "fecha:", "guía", "guia", "práctica", "practica"))
            ]

        for it in items:
            it.pop("lineas", None)

        encabezado_txt = " | ".join(encabezado_lineas)[:320]
        return encabezado_txt, items

    def _extraer_bloque_ejercicio_documento(self, documento_texto: str, pregunta: str) -> str:
        """
        Localiza el ejercicio o sección exacta del documento que el niño preguntó,
        deteniendo la captura al encontrar el siguiente encabezado (`Problema 2`, `Ejercicio 2`, etc.)
        y soportando referencias como `'el último'` / `'ultimo'`.
        """
        lineas = [ln.strip() for ln in (documento_texto or "").splitlines() if ln.strip()]
        if not lineas:
            return ""
        q_norm = _normalizar_ia(_normalizar_ortografia_infantil(pregunta))
        if not q_norm:
            return "\n".join(lineas[:8])[:1400]

        _enc, ejercicios = self._parsear_ejercicios_documento(documento_texto)

        # Soporte para "el último" / "ultimo" / "última" / "final"
        if re.search(r"\b(?:ultim[oa]s?|final)\b", q_norm) and ejercicios:
            return str(ejercicios[-1]["texto"])

        # Soporte para rango "del N al M"
        m_rango = re.search(r"\bdel\s+(\d{1,3})\s+al\s+(\d{1,3})\b", q_norm)
        if m_rango and ejercicios:
            n_ini, n_fin = int(m_rango.group(1)), int(m_rango.group(2))
            if n_ini > n_fin:
                n_ini, n_fin = n_fin, n_ini
            sel = [str(e["texto"]) for e in ejercicios if n_ini <= int(e["numero"]) <= n_fin][:3]
            if sel:
                return "\n".join(sel)[:1400]

        ordinales = {
            "primero": 1, "primer": 1, "uno": 1, "primera": 1,
            "segundo": 2, "dos": 2, "segunda": 2,
            "tercero": 3, "tercer": 3, "tres": 3, "tercera": 3,
            "cuarto": 4, "cuatro": 4, "cuarta": 4,
            "quinto": 5, "cinco": 5, "quinta": 5,
            "sexto": 6, "seis": 6, "sexta": 6,
            "septimo": 7, "siete": 7, "septima": 7,
            "octavo": 8, "ocho": 8, "octava": 8,
            "noveno": 9, "nueve": 9, "novena": 9,
            "decimo": 10, "diez": 10, "decima": 10,
        }
        num_pedida: Optional[int] = None
        m_num = re.search(
            r"\b(?:ejercicio|problema|punto|actividad|pregunta|tema|inciso|el|la|numero|n)?\s*(\d{1,3})\b",
            q_norm,
        )
        if m_num:
            num_pedida = int(m_num.group(1))
        else:
            for pal, n_ord in ordinales.items():
                if re.search(rf"\b{pal}\b", q_norm):
                    num_pedida = n_ord
                    break

        if num_pedida is not None and ejercicios:
            for e in ejercicios:
                if int(e["numero"]) == num_pedida:
                    return str(e["texto"])
            if 1 <= num_pedida <= len(ejercicios):
                return str(ejercicios[num_pedida - 1]["texto"])

        stopwords = {
            "ayuda", "ayudame", "explica", "explicame", "resolver", "resuelve",
            "como", "hago", "este", "esta", "archivo", "tarea", "ejercicio",
            "problema", "hola", "haru", "por", "favor",
        }
        kws = [w for w in re.findall(r"[a-z0-9ñ]+", q_norm) if len(w) >= 3 and w not in stopwords]
        if kws and ejercicios:
            mejor_ej = None
            mejor_score = 0
            for e in ejercicios:
                e_norm = _normalizar_ia(str(e["texto"]))
                score = sum(1 for kw in kws if kw in e_norm)
                if score > mejor_score:
                    mejor_score = score
                    mejor_ej = str(e["texto"])
            if mejor_score > 0 and mejor_ej:
                return mejor_ej[:1400]

        return "\n".join(lineas[:8])[:1400]

    def _es_seguimiento_documento(self, pregunta_limpia: str) -> bool:
        """Determina si una pregunta del estudiante continúa sobre el documento abierto."""
        doc = self._documento_activo
        if not doc:
            return False
        q_norm = _normalizar_ia(pregunta_limpia)
        if not q_norm:
            return False

        # No interceptar consultas explícitamente externas al documento
        if re.search(r"\b(que\s+hora\s+es|la\s+hora|que\s+dia\s+es|que\s+fecha)\b", q_norm):
            return False
        if self._detectar_contencion_emocional(pregunta_limpia):
            return False
        # Si escribe una operación aritmética nueva explícita (e.g. "cuanto es 50 + 50") sin mencionar archivo/ejercicio
        if (
            not re.search(r"\b(ejercicio|problema|punto|archivo|documento|guia|hoja|pdf|del\s+\d+\s+al\s+\d+)\b", q_norm)
            and re.search(r"\d\s*[+\-*/×÷^]\s*\d", q_norm)
        ):
            return False

        if re.search(
            r"\b(siguiente|el\s+que\s+sigue|siguientes|otro\s+ejercicio|otros\s+ejercicios|los\s+otros|"
            r"las\s+otras|otro\b|otros\b|los\s+demas|las\s+demas|mas\s+ejercicios|continua|continuemos|"
            r"sigue\s+con|anterior|atras|ultimo|ultima|todos\s+los\s+ejercicios|"
            r"cuantos\s+ejercicios|cuantas\s+preguntas|que\s+ejercicios|del\s+\d{1,3}\s+al\s+\d{1,3}|"
            r"archivo|documento|guia|hoja|pdf)\b",
            q_norm,
        ):
            return True

        if re.search(
            r"\b(?:ejercicio|problema|actividad|pregunta|punto|inciso|el|la|numero)\s*\d{1,3}\b",
            q_norm,
        ):
            return True

        # Número suelto dentro del rango del documento (ej. "15", "el 15")
        m_solo = re.fullmatch(r"(?:el\s+|la\s+|numero\s+)?(\d{1,3})", q_norm)
        if m_solo:
            total = len(doc.get("ejercicios") or [])
            if 1 <= int(m_solo.group(1)) <= max(1, total):
                return True

        if self._ultimo_turno_fue_documento and re.search(
            r"\b(no\s+entendi|no\s+comprendi|explicame|otra\s+vez|mas\s+facil|repiteme|repite|no\s+entiendo)\b",
            q_norm,
        ):
            return True

        return False

    def responder_consulta_escolar(
        self,
        pregunta: str,
        tarea_actual: str = "",
        paso_actual: str = "",
        modo_charla_libre: bool = False,
    ) -> str:
        pregunta_raw = re.sub(r"\s+", " ", (pregunta or "")).strip()[:360]
        if not pregunta_raw:
            self.ultima_fuente = "Local"
            return self._personalizar_respuesta_local(
                "¡Hola! Escribe o dime tu duda y la resolvemos juntos con calma."
            )

        # Normalizar ortografía infantil para comprensión robusta
        pregunta_limpia = _normalizar_ortografia_infantil(pregunta_raw)

        # 0. Filtro Guardián Infantil Contextual (bullying, excepciones académicas y anti-evasión)
        bloqueo = self._verificar_restriccion_tematica(pregunta_raw)
        if bloqueo:
            return bloqueo

        # 0B. Continuación o cierre sobre documento escolar activo en sesión
        if self._documento_activo is not None:
            q_doc_norm = _normalizar_ia(pregunta_limpia)
            if re.search(
                r"\b(?:cerrar|quitar|terminar|termine|salir\s+del?|dejar)\s+(?:el\s+)?(?:archivo|documento|guia|pdf)\b",
                q_doc_norm,
            ):
                nom_c = str(self._documento_activo.get("nombre") or "tu archivo")
                self.cerrar_documento_activo()
                self.ultima_fuente = "Tutor Local de Documentos"
                return self._registrar_turno_chat(
                    pregunta_raw,
                    self._personalizar_respuesta_local(
                        f"¡Listo! Cerré «{nom_c}» y volvemos a nuestras misiones. Puedes adjuntar otro archivo cuando quieras."
                    ),
                )
            if self._es_seguimiento_documento(pregunta_limpia):
                doc_act = self._documento_activo
                return self.responder_sobre_documento(
                    str(doc_act.get("texto") or ""),
                    pregunta=pregunta_raw,
                    nombre_doc=str(doc_act.get("nombre") or "tu archivo"),
                )

        # 1. Seguimiento conversacional multi-turno: "¿no entendí?" / "¿explícame otra vez?"
        resp_reformulacion = self._resolver_reformulacion_previa(pregunta_limpia)
        if resp_reformulacion:
            resp_pers = self._personalizar_respuesta_local(resp_reformulacion, adaptar_grado=True)
            return self._registrar_turno_chat(pregunta_raw, resp_pers)

        # 2. Seguimiento matemático multi-turno sobre `ultimo_resultado_num` ("¿y si le sumo 2?", "¿y la mitad?")
        seg_mate = self._resolver_seguimiento_matematico(pregunta_limpia)
        if seg_mate is not None:
            resp_seg, nuevo_num = seg_mate
            self.ultima_fuente = "Calculadora Segura AST"
            resp_pers = self._personalizar_respuesta_local(resp_seg)
            return self._registrar_turno_chat(pregunta_raw, resp_pers, resultado_num=nuevo_num)

        # 3. Prioridad de Empatía y Contención Emocional (antes de coincidencias genéricas)
        resp_emocional = self._detectar_contencion_emocional(pregunta_limpia)
        if resp_emocional:
            return self._registrar_turno_chat(pregunta_raw, resp_emocional)

        # 4. Capa 1A: Calculadora aritmética segura (AST)
        respuesta_mate = resolver_pregunta_matematica(pregunta_limpia)
        if not respuesta_mate and pregunta_limpia != pregunta_raw:
            respuesta_mate = resolver_pregunta_matematica(pregunta_raw)
        if respuesta_mate:
            self.ultima_fuente = "Calculadora Segura AST"
            num_calc = self._extraer_resultado_numerico(pregunta_limpia, respuesta_mate)
            resp_pers = self._personalizar_respuesta_local(respuesta_mate)
            return self._registrar_turno_chat(pregunta_raw, resp_pers, resultado_num=num_calc)

        # 5. Capa 1B: Respuestas curriculares específicas (biología plantas, independencia, salud, sílabas)
        resp_curricular = self._responder_temas_curriculares_locales(pregunta_limpia)
        if resp_curricular:
            return self._registrar_turno_chat(pregunta_raw, resp_curricular)

        # 6. Capa 1C: Hora, fecha, técnicas de estudio y guía cotidiana segura
        resp_cotidiana = self._responder_vida_cotidiana_y_estudio(pregunta_limpia)
        if resp_cotidiana:
            return self._registrar_turno_chat(pregunta_raw, resp_cotidiana)

        # 7. Capa 1D: Base de conocimiento escolar y conversacional SQLite
        if self.db:
            resp_local = self.db.buscar_conocimiento(pregunta_limpia)
            if not resp_local and pregunta_limpia != pregunta_raw:
                resp_local = self.db.buscar_conocimiento(pregunta_raw)
            if resp_local:
                self.ultima_fuente = "Conocimiento Escolar SQLite"
                es_academica = not any(
                    sal in _normalizar_ia(pregunta_limpia)
                    for sal in ("hola", "como estas", "que haces", "gracias", "chiste")
                )
                resp_pers = self._personalizar_respuesta_local(resp_local, adaptar_grado=es_academica)
                return self._registrar_turno_chat(pregunta_raw, resp_pers)

        # 8. Preparar prompt contextual con perfil del estudiante e historial multi-turno
        contexto_pensum = self._obtener_contexto_pensum(f"{tarea_actual} {pregunta_limpia}")
        nombre_est, grado_est = self._sincronizar_perfil_ligero()
        perfil_inline = (
            f"Estudiante: {nombre_est or 'Alumno'} ({grado_est or '3.° de Primaria'}). "
            if (nombre_est or grado_est)
            else ""
        )
        if modo_charla_libre or not paso_actual:
            contexto = (
                f"El niño de primaria ya está en modo descanso/charla libre tras terminar '{tarea_actual[:80]}'. "
                "Puede preguntarte sobre tareas escolares, organización del estudio, curiosidades o temas cotidianos sanos. "
            )
        else:
            contexto = (
                f"Tarea actual: '{tarea_actual[:90]}'. Paso actual: '{paso_actual[:140]}'. "
                if tarea_actual
                else ""
            )
        prompt = (
            f"{perfil_inline}{contexto_pensum}{contexto}Mensaje del niño de primaria: '{pregunta_limpia}'. "
            f"Responde como Haru en español claro adaptado a {grado_est or 'primaria'}, "
            f"en 2 o 3 oraciones breves, prácticas y sin Markdown."
        )

        # Capa 2: Ollama local (si está activo en la PC)
        resp_ollama = self._llamar_ollama(prompt)
        if resp_ollama:
            limpia_o = self._personalizar_respuesta_local(_limpiar_respuesta_ia(resp_ollama))
            return self._registrar_turno_chat(pregunta_raw, limpia_o)

        # Capa 3: Gemini Cloud REST (si hay clave y no está en Modo Privado)
        resp_gemini = self._llamar_gemini(prompt)
        if resp_gemini:
            limpia_g = self._personalizar_respuesta_local(_limpiar_respuesta_ia(resp_gemini))
            return self._registrar_turno_chat(pregunta_raw, limpia_g)

        # Capa 4: Respaldo pedagógico o conversacional empático local
        self.ultima_fuente = "Andamiaje Local"
        if modo_charla_libre or not paso_actual:
            resp_fb = self._personalizar_respuesta_local(
                "¡Qué interesante lo que me cuentas! Podemos charlar sobre tus metas de estudio, "
                "preguntarme la hora, resolver cuentas o elegir una nueva misión cuando gustes.",
                adaptar_grado=True,
            )
            return self._registrar_turno_chat(pregunta_raw, resp_fb)

        resp_fb = self._personalizar_respuesta_local(
            f"¡Buena pregunta! Para avanzar en «{(tarea_actual or 'tu misión')[:60]}», "
            f"hagamos primero este pasito: {(paso_actual or 'leer con calma el ejercicio')[:120]}. "
            f"Si quieres que resuelva una cuenta o lea un archivo de ejercicios, dímelo con gusto.",
            adaptar_grado=True,
        )
        return self._registrar_turno_chat(pregunta_raw, resp_fb)

    # =========================================================================
    # 2. GENERADOR DE PISTAS CONTEXTUALES GRADUADAS (ANDAMIAJE TDAH)
    # =========================================================================
    def generar_pista_contextual(
        self,
        nombre_tarea: str,
        texto_paso: str,
        num_paso: int,
        intento: Optional[int] = None,
    ) -> str:
        """
        Genera pistas graduadas y distintas cuando el estudiante pide ayuda repetidas veces
        en el mismo paso (Intento 1: orientación de inicio; Intento 2: procedimiento intermedio;
        Intento 3+: ejemplo concreto casi resuelto).
        """
        clave_paso = (_normalizar_ia(nombre_tarea or ""), int(num_paso or 1), _normalizar_ia(texto_paso or ""))
        if intento is None:
            nivel = self._conteo_pistas_paso.get(clave_paso, 0) + 1
        else:
            nivel = max(1, int(intento))
        self._conteo_pistas_paso[clave_paso] = nivel

        etiqueta_nivel = {
            1: "primera pista suave de orientación inicial",
            2: "segunda pista intermedia explicando el procedimiento paso a paso",
        }.get(nivel, "tercera pista detallada con un ejemplo concreto casi resuelto")

        prompt = (
            f"El niño de primaria con TDAH está en el Paso {num_paso} de '{(nombre_tarea or '')[:80]}': "
            f"'{(texto_paso or '')[:150]}'. Dale una {etiqueta_nivel} (intento #{nivel}), "
            f"práctica y tierna de máximo 22 palabras, sin asteriscos."
        )
        pista_ollama = self._llamar_ollama(prompt)
        if pista_ollama:
            return self._personalizar_respuesta_local(_limpiar_respuesta_ia(pista_ollama, max_chars=200))

        pista_gemini = self._llamar_gemini(prompt)
        if pista_gemini:
            return self._personalizar_respuesta_local(_limpiar_respuesta_ia(pista_gemini, max_chars=200))

        self.ultima_fuente = "Andamiaje Local"
        paso_low = (texto_paso or "").lower()
        ops = self._analizar_operaciones_en_texto(f"{texto_paso} {nombre_tarea}")

        if any(w in paso_low for w in ["saca", "prepara", "mochila", "cuaderno", "lápiz", "lapiz", "mesa"]):
            opciones = (
                "Pista 1 (Inicio): Pon en tu mesa solo el cuaderno y el lápiz que pide este paso, guardando lo demás.",
                "Pista 2 (Proceso): Abre el cuaderno en una página limpia y ten tu borrador justo al lado derecho.",
                "Pista 3 (Ejemplo): Deja únicamente tu cuaderno abierto al centro de la mesa y respira profundo para empezar.",
            )
            return self._personalizar_respuesta_local(opciones[min(nivel - 1, len(opciones) - 1)])

        if any(w in paso_low for w in ["lee", "lectura", "párrafo", "parrafo", "cuento", "libro"]):
            opciones = (
                "Pista 1 (Inicio): Sigue cada renglón con tu dedito o una regla para mantener el foco en la lectura.",
                "Pista 2 (Proceso): Lee en voz alta hasta el primer punto y separa en palmadas las palabras largas.",
                "Pista 3 (Ejemplo): Pregúntate de quién habla la primera oración (por ejemplo, el personaje principal) y subráyalo.",
            )
            return self._personalizar_respuesta_local(opciones[min(nivel - 1, len(opciones) - 1)])

        if ops or any(w in paso_low for w in ["suma", "resta", "multiplica", "divide", "ejercicio", "número", "numero", "calcula"]):
            if ops:
                etq, res_val, exp_op = ops[0]
                opciones = (
                    f"Pista 1 (Inicio): Copia con calma la operación {etq} alineando cada cifra en su columna.",
                    f"Pista 2 (Proceso): {exp_op.split(':')[0]}. ¡Avanza una columna a la vez!",
                    f"Pista 3 (Ejemplo guiado): {exp_op} ¡Verifica que en tu cuaderno te quede {res_val}!",
                )
            else:
                opciones = (
                    "Pista 1 (Inicio): Resuelve una sola columna a la vez empezando por las unidades de la derecha.",
                    "Pista 2 (Proceso): Anota arribita lo que llevas o prestas y usa tus dedos o rayitas para contar seguro.",
                    "Pista 3 (Ejemplo): Escribe la cuenta en la barra de Haru IA para comprobar paso a paso tu resultado.",
                )
            return self._personalizar_respuesta_local(opciones[min(nivel - 1, len(opciones) - 1)])

        if any(w in paso_low for w in ["escribe", "oración", "oracion", "copia", "anota", "redacta"]):
            opciones = (
                "Pista 1 (Inicio): Di primero tu idea corta en voz alta antes de escribirla en el cuaderno.",
                "Pista 2 (Proceso): Empieza con letra mayúscula, escribe palabra por palabra y pon punto final.",
                "Pista 3 (Ejemplo): Usa una oración sencilla como «El niño aprende con alegría» y léela en voz alta.",
            )
            return self._personalizar_respuesta_local(opciones[min(nivel - 1, len(opciones) - 1)])

        if any(w in paso_low for w in ["dibuja", "pinta", "color", "colorea"]):
            opciones = (
                "Pista 1 (Inicio): ¡No tiene que ser perfecto! Saca solo 3 colores y empieza por la figura central.",
                "Pista 2 (Proceso): Haz primero el contorno grande con lápiz y luego rellena suave con tu color favorito.",
                "Pista 3 (Ejemplo): Agrega una palabra o flecha corta junto a tu dibujo para recordar qué representa.",
            )
            return self._personalizar_respuesta_local(opciones[min(nivel - 1, len(opciones) - 1)])

        opciones_gen = (
            f"Pista 1 (Paso {num_paso}): Haz solo la primera acción pequeña que dice la tarjeta y avanza sin prisa.",
            f"Pista 2 (Paso {num_paso}): Divide este paso en dos partecitas: primero léelo en voz alta y luego hazlo en tu cuaderno.",
            f"Pista 3 (Paso {num_paso}): ¡Ya casi lo tienes! Completa este último detalle del paso {num_paso} y presiona ¡Paso Listo!",
        )
        return self._personalizar_respuesta_local(opciones_gen[min(nivel - 1, len(opciones_gen) - 1)])

    # =========================================================================
    # 3. DESCOMPONEDOR AUTOMÁTICO DE TAREAS Y EXTRACTOR MULTIMODAL DE DOCUMENTOS
    # =========================================================================
    def _descomponer_local_concreto(self, tema: str, modulo: str) -> Tuple[List[str], List[str]]:
        """Genera 4 micro-pasos verificables con ejercicios/datos reales adaptados al título/prompt."""
        ops = self._analizar_operaciones_en_texto(tema)
        t_norm = _normalizar_ia(_normalizar_ortografia_infantil(tema))
        nums_tema = [int(n) for n in re.findall(r"\b(\d{1,3})\b", tema) if int(n) > 0]

        if ops and (modulo == "Matemáticas" or len(ops) >= 1):
            etq1, _res1, exp1 = ops[0]
            if len(ops) >= 2:
                etq2, _res2, exp2 = ops[1]
                pasos = [
                    f"Prepara tu cuaderno de cuadros y copia claramente la primera operación: {etq1}.",
                    f"Resuelve paso a paso {etq1} alineando unidades y decenas en tu cuaderno.",
                    f"Ahora copia y resuelve la segunda operación: {etq2}.",
                    f"Revisa ambas respuestas ({etq1} y {etq2}) en voz alta antes de cerrar tu cuaderno.",
                ]
                pistas = [
                    f"Deja buen espacio debajo de {etq1} para anotar lo que llevas o prestas.",
                    exp1,
                    exp2,
                    "Vuelve a comprobar unidades y decenas para confirmar tus dos resultados.",
                ]
            else:
                pasos = [
                    f"Abre tu cuaderno de matemáticas y escribe la operación {etq1}.",
                    f"Identifica qué operación pide ({etq1}) y resuelve primero las unidades.",
                    f"Completa el cálculo final de {etq1} y escribe la respuesta con lápiz rojo o subrayada.",
                    f"Crea un segundo ejemplo parecido a {etq1} y compruébalo con Haru.",
                ]
                pistas = [
                    "Alinea cada número en su columna correcta.",
                    exp1,
                    "Si terminas este paso, Haru te preguntará cuánto te salió.",
                    "Puedes escribir otro ejercicio parecido en tu cuaderno para practicar.",
                ]
            return pasos, pistas

        if modulo == "Inglés":
            vocab_conocido = (
                "BLUE", "RED", "GREEN", "YELLOW", "ORANGE", "PURPLE", "PINK", "WHITE", "BLACK",
                "CAT", "DOG", "BIRD", "LION", "RABBIT", "MONKEY", "ELEPHANT",
                "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN",
                "MOTHER", "FATHER", "SISTER", "BROTHER", "FAMILY",
                "APPLE", "BANANA", "BOOK", "PENCIL", "SCHOOL", "TEACHER", "STUDENT",
                "HELLO", "GOODBYE", "MORNING", "NIGHT",
            )
            m_pal = re.findall(r"\b(" + "|".join(vocab_conocido) + r")\b", tema.upper())
            if not m_pal:
                # Extraer palabras específicas según el subtema mencionado en el título
                if "animal" in t_norm:
                    m_pal = ["CAT", "DOG", "RABBIT"]
                elif "famil" in t_norm:
                    m_pal = ["MOTHER", "FATHER", "SISTER"]
                elif "numer" in t_norm or "number" in t_norm or "count" in t_norm:
                    m_pal = ["ONE", "TWO", "THREE"]
                elif "util" in t_norm or "school" in t_norm or "escuela" in t_norm:
                    m_pal = ["BOOK", "PENCIL", "TEACHER"]
                else:
                    m_pal = ["BLUE", "CAT", "ONE, TWO, THREE"]

            pal1 = m_pal[0]
            pal2 = m_pal[1] if len(m_pal) > 1 else ("DOG" if pal1 == "CAT" else "CAT")
            pal3 = m_pal[2] if len(m_pal) > 2 else "ONE, TWO, THREE"
            pasos = [
                f"¡Hello! Saca tu cuaderno de inglés y escribe el título «{tema[:42]}».",
                f"Dibuja un ejemplo de {pal1}, escribe {pal1} con letra grande y pronúncialo 3 veces en voz alta.",
                f"Ahora escribe y pronuncia la palabra {pal2} haciendo un pequeño dibujo al lado.",
                f"¡You are a champion! Repasa en voz alta {pal1}, {pal2} y {pal3} antes de guardar tus útiles.",
            ]
            pistas = [
                "Ten en tu mesa solo tu cuaderno de inglés y colores.",
                f"Repite despacio en voz alta: {pal1}.",
                f"Asocia el dibujo con su palabra en inglés ({pal2}) para recordarlo fácil.",
                f"Practica una vez más la pronunciación de {pal1} y {pal2}.",
            ]
            return pasos, pistas

        if modulo == "Matemáticas":
            if "fraccion" in t_norm:
                fracs = re.findall(r"\b(\d+\s*/\s*\d+)\b", tema)
                f1 = fracs[0].replace(" ", "") if fracs else "1/2"
                f2 = fracs[1].replace(" ", "") if len(fracs) > 1 else "1/4"
                ej1 = f"{f1} (la mitad de un círculo)" if f1 == "1/2" else f"la fracción {f1}"
                ej2 = f"{f2} (un cuarto pintado)" if f2 == "1/4" else f"la fracción {f2}"
                pasos = [
                    f"Prepara tu cuaderno y regla para practicar «{tema[:42]}».",
                    f"Dibuja una figura dividida en partes iguales y pinta {ej1}.",
                    f"Dibuja un segundo esquema en tu cuaderno y representa {ej2}.",
                    "Escribe debajo de cada dibujo qué número es el numerador (arriba) y el denominador (abajo).",
                ]
                pistas = [
                    "Usa monedas o regla si te ayuda a dibujar figuras ordenadas.",
                    f"{f1} indica cuántas partes tomamos del total dividido.",
                    f"Representa {f2} pintando con tu color favorito las partes indicadas.",
                    "Recuerda: el denominador abajo dice en cuántas partes se divide el entero.",
                ]
            elif "multiplica" in t_norm or "tabla" in t_norm:
                if len(nums_tema) >= 2:
                    n1, n2 = nums_tema[0], nums_tema[1]
                    op1_str = f"{n1} × {n2}"
                    res1_val = n1 * n2
                    op2_str = f"{n2} × 5" if n2 != 5 else f"{n1} × 4"
                    res2_val = (n2 * 5) if n2 != 5 else (n1 * 4)
                elif len(nums_tema) == 1:
                    n1 = nums_tema[0]
                    n2 = 4 if n1 != 4 else 3
                    op1_str = f"{n1} × {n2}"
                    res1_val = n1 * n2
                    op2_str = f"{n1} × 6"
                    res2_val = n1 * 6
                else:
                    n1, n2 = 3, 4
                    op1_str = "3 × 4"
                    res1_val = 12
                    op2_str = "6 × 5"
                    res2_val = 30
                pasos = [
                    f"Prepara tu cuaderno y escribe estas dos multiplicaciones: {op1_str} y {op2_str}.",
                    f"Resuelve {op1_str} sumando {n1} grupos de {n2} y anota el resultado ({res1_val}).",
                    f"Resuelve {op2_str} paso a paso en tu cuaderno y anota el resultado ({res2_val}).",
                    f"Comprueba tus resultados de {op1_str} y {op2_str} en voz alta con Haru.",
                ]
                pistas = [
                    "Deja dos cuadritos de espacio entre cada ejercicio.",
                    f"Para {op1_str}, contar {n1} veces {n2} nos da {res1_val}.",
                    f"Para {op2_str}, revisa tu tabla y confirma que da {res2_val}.",
                    f"Revisa que tus resultados de {op1_str} y {op2_str} estén claros.",
                ]
            elif "divi" in t_norm:
                if len(nums_tema) >= 2 and nums_tema[1] != 0:
                    d1, d2 = nums_tema[0], nums_tema[1]
                    if d1 < d2:
                        d1 = d1 * d2
                elif len(nums_tema) == 1 and nums_tema[0] > 0:
                    d2 = nums_tema[0]
                    d1 = d2 * 4
                else:
                    d1, d2 = 12, 3
                pasos = [
                    f"Prepara tu cuaderno y escribe las divisiones {d1} ÷ {d2} y 20 ÷ 4.",
                    f"Resuelve {d1} ÷ {d2} imaginando que repartes {d1} elementos entre {d2} grupos iguales.",
                    "Resuelve 20 ÷ 4 repartiendo 20 lápices en 4 grupos iguales.",
                    "Comprueba tus respuestas multiplicando cada resultado por el divisor.",
                ]
                pistas = [
                    f"Dibuja {d2} círculos en borrador si quieres repartir los {d1} elementos.",
                    "Cuenta cuántos quedaron dentro de cada grupo.",
                    "Pregunta: ¿qué número por 4 nos da 20?",
                    "Si 4 × 5 = 20, entonces 20 ÷ 4 = 5.",
                ]
            elif "triangulo" in t_norm or "rectangulo" in t_norm or "cuadrado" in t_norm or "geometria" in t_norm:
                figura = "triángulo" if "triangulo" in t_norm else ("rectángulo" if "rectangulo" in t_norm else "cuadrado")
                lados = 3 if figura == "triángulo" else 4
                pasos = [
                    f"Prepara tu cuaderno de matemáticas, lápiz y regla para trazar un {figura}.",
                    f"Dibuja con tu regla los {lados} lados del {figura} y señala sus vértices con color.",
                    f"Mide cada lado de tu {figura} en centímetros y anota las medidas junto a cada línea.",
                    f"Suma las medidas de los {lados} lados para calcular el perímetro total del {figura}.",
                ]
                pistas = [
                    "Apoya firme la regla sobre el papel antes de trazar cada línea.",
                    f"Un {figura} tiene {lados} lados y {lados} esquinas llamadas vértices.",
                    "Empieza a medir desde el número 0 de tu regla.",
                    "El perímetro es la suma de todos los lados de la figura.",
                ]
            elif "resta" in t_norm:
                r1 = f"{nums_tema[0]} - {nums_tema[1]}" if len(nums_tema) >= 2 else "28 - 13"
                pasos = [
                    f"Abre tu cuaderno en hoja limpia y escribe las restas {r1} y 45 - 19.",
                    f"Calcula primero {r1} restando unidades y luego decenas en orden.",
                    "Ahora calcula 45 - 19 prestando 1 decena al 5 para restar 15 - 9.",
                    "Revisa ambas restas sumando el resultado con el número que quitaste.",
                ]
                pistas = [
                    "Alinea siempre las unidades a la derecha y decenas a la izquierda.",
                    f"Resuelve {r1} empezando por la columna de la derecha.",
                    "Al pedir prestado a la decena, el 4 queda en 3 y el 5 sube a 15.",
                    "Comprobar con una suma asegura que no hubo descuidos.",
                ]
            else:
                s1 = f"{nums_tema[0]} + {nums_tema[1]}" if len(nums_tema) >= 2 else "16 + 8"
                pasos = [
                    f"Abre tu cuaderno de matemáticas y escribe dos sumas de práctica para «{tema[:38]}»: {s1} y 24 + 15.",
                    f"Resuelve {s1} sumando primero la columna de las unidades y llevando a la decena si pasa de 9.",
                    "Resuelve 24 + 15 alineando las columnas de unidades (4 + 5) y decenas (2 + 1).",
                    f"Verifica con calma el resultado de {s1} y 24 + 15 antes de guardar tu lápiz.",
                ]
                pistas = [
                    "Mantén sobre la mesa solo cuaderno, lápiz y borrador.",
                    f"Suma las unidades de {s1} con calma.",
                    "4 + 5 = 9 y 20 + 10 = 30.",
                    "Lee tus dos resultados finales en voz alta.",
                ]
            return pasos, pistas

        if modulo == "Lenguaje":
            if "verbo" in t_norm:
                pasos = [
                    "Abre tu cuaderno de lenguaje y escribe el título «Los Verbos (Acciones)».",
                    "Subraya o copia 3 palabras que indiquen acción: correr, leer y dibujar.",
                    "Escribe 2 oraciones cortas usando esos verbos (ej. «El niño lee un cuento»).",
                    "Lee tus oraciones en voz alta señalando con tu dedo el verbo de cada una.",
                ]
                pistas = [
                    "Recuerda: el verbo siempre responde a «¿qué hace?».",
                    "Piensa en cosas que haces todos los días en la escuela o en casa.",
                    "Empieza cada oración con mayúscula y termina con punto.",
                    "Pregúntate qué palabra muestra movimiento o acción.",
                ]
            elif "sustantivo" in t_norm:
                pasos = [
                    "Prepara tu cuaderno de lenguaje para practicar «Sustantivos».",
                    "Escribe 2 sustantivos comunes de objetos a tu vista (ej. cuaderno, mesa).",
                    "Escribe 2 sustantivos propios con mayúscula inicial (ej. Bolivia, Haru).",
                    "Arma una oración que junte un sustantivo propio y uno común.",
                ]
                pistas = [
                    "Los sustantivos nombran personas, animales, cosas o lugares.",
                    "Mira a tu alrededor y nombra objetos escolares.",
                    "Los nombres propios siempre empiezan con letra mayúscula.",
                    "Ejemplo guía: «María guarda su cuaderno azul».",
                ]
            else:
                pasos = [
                    f"Prepara tu lectura sobre «{tema[:44]}» y apoya tu dedo bajo el título.",
                    "Lee en voz alta el primer párrafo despacio haciendo pausa en cada punto.",
                    "Subraya quién es el personaje principal y escribe 3 palabras clave del texto.",
                    "Redacta una oración propia contando lo que ocurrió al final del fragmento.",
                ]
                pistas = [
                    "Una regla bajo el renglón te ayuda a no perder la línea.",
                    "Si hay una palabra difícil, divídela por sílabas con palmadas.",
                    "Pregúntate: ¿de quién habla el texto y qué hace?",
                    "Di primero tu oración en voz alta antes de escribirla.",
                ]
            return pasos, pistas

        if modulo == "Ciencias":
            if "agua" in t_norm:
                pasos = [
                    "Prepara tu cuaderno y tus colores azul, amarillo y celeste para «El Ciclo del Agua».",
                    "Dibuja el sol arriba calentando un río abajo y escribe la palabra EVAPORACIÓN.",
                    "Dibuja una nube arriba con flechas que suben y escribe la palabra CONDENSACIÓN.",
                    "Dibuja gotas cayendo desde la nube hacia el río y escribe PRECIPITACIÓN.",
                ]
                pistas = [
                    "El sol calienta el agua y la convierte en vapor invisible.",
                    "Evaporación es cuando el agua sube como vapor.",
                    "Condensación es cuando ese vapor forma las nubes en el cielo.",
                    "Precipitación es cuando vuelve a caer como lluvia.",
                ]
            elif "solar" in t_norm or "planeta" in t_norm:
                pasos = [
                    "Abre tu cuaderno de ciencias y dibuja al centro un Sol grande y brillante.",
                    "Dibuja las órbitas y los 4 primeros planetas: Mercurio, Venus, Tierra y Marte.",
                    "Agrega los 4 planetas gigantes más lejanos: Júpiter, Saturno, Urano y Neptuno.",
                    "Señala la Tierra con un círculo verde y escribe 1 dato de por qué permite la vida.",
                ]
                pistas = [
                    "Usa color amarillo o naranja para el Sol.",
                    "Recuerda: somos el tercer planeta desde el Sol.",
                    "Saturno se reconoce muy fácil por sus anillos.",
                    "La Tierra tiene agua líquida y oxígeno para vivir.",
                ]
            elif "fotosint" in t_norm or "planta" in t_norm:
                pasos = [
                    "Dibuja en tu cuaderno una plantita con raíces, tallo, hojas verdes y flor.",
                    "Agrega flechas mostrando los 3 ingredientes que toma: luz del sol, agua y aire.",
                    "Escribe la palabra FOTOSÍNTESIS junto a las hojas verdes.",
                    "Anota abajo por qué las plantas nos ayudan a vivir (producen oxígeno).",
                ]
                pistas = [
                    "Empieza dibujando la tierra y las raíces por abajo.",
                    "Las raíces toman agua y las hojas captan la luz solar.",
                    "Las hojas usan el color verde (clorofila) para fabricar alimento.",
                    "Al respirar aire limpio agradecemos el oxígeno de las plantas.",
                ]
            elif any(w in t_norm for w in ("historia", "independencia", "bolivia", "sociales", "departamento", "simbolos")):
                pasos = [
                    f"Abre tu cuaderno de Ciencias Sociales y escribe el título «{tema[:44]}».",
                    "Anota 2 datos principales o personajes históricos clave del tema.",
                    "Dibuja un mapa sencillo o símbolo representativo en el centro de tu hoja.",
                    "Escribe en 1 oración por qué este hecho o lugar es importante para Bolivia.",
                ]
                pistas = [
                    "Usa colores claros para resaltar el título en tu cuaderno.",
                    "Identifica qué ocurrió, dónde pasó y quiénes participaron.",
                    "Un esquema visual ayuda a recordar fechas y lugares sin esfuerzo.",
                    "Lee tu oración final en voz alta para repasar lo aprendido.",
                ]
            else:
                pasos = [
                    f"Saca tu cuaderno de ciencias y escribe el título «{tema[:44]}».",
                    "Anota con tus palabras qué fenómeno o ser vivo estudia este tema.",
                    "Dibuja un esquema central con 3 partes señaladas usando flechas de colores.",
                    "Escribe una conclusión de 1 oración sobre cómo cuidarlo en la vida diaria.",
                ]
                pistas = [
                    "Prepara solo 3 lápices de color para no distraerte.",
                    "Piensa: ¿qué cambia, qué necesita o cómo funciona?",
                    "Coloca etiquetas cortas y claras en cada flecha.",
                    "Relacionarlo con tu entorno ayuda a recordarlo mejor.",
                ]
            return pasos, pistas

        # Hábitos y Orden
        pasos = [
            f"Despeja tu espacio de estudio y reúne únicamente lo necesario para «{tema[:40]}».",
            "Separa los materiales por orden de uso (primero cuaderno/agenda, luego estuche).",
            "Ejecuta la primera acción práctica de organización y guarda cada útil usado en su sitio.",
            "Revisa tu escritorio o mochila lista y marca qué horario respetarás mañana.",
        ]
        pistas = [
            "Si ves juguetes o pantallas cerca, guárdalos fuera de la mesa.",
            "Un lugar fijo para cada lápiz y cuaderno evita buscar cosas tarde.",
            "Haz una sola tarea de orden a la vez con música tranquila o calma.",
            "¡Un espacio ordenado le da paz a tu mente para aprender!",
        ]
        return pasos, pistas

    def descomponer_tarea_ia(
        self, tema_tarea: str, modulo_forzado: Optional[str] = None
    ) -> Tuple[List[str], List[str]]:
        tema = re.sub(r"\s+", " ", (tema_tarea or "")).strip()[:280] or "Actividad Escolar"
        modulo = (
            self.db.normalizar_modulo(modulo_forzado)
            if (modulo_forzado and self.db and hasattr(self.db, "normalizar_modulo"))
            else (modulo_forzado or self.detectar_modulo_automatico(tema))
        )
        contexto_pensum = self._obtener_contexto_pensum(f"{modulo} {tema}")
        _, grado_est = self._sincronizar_perfil_ligero()
        grado_txt = grado_est or "3.° de Primaria"
        instruccion_idioma = (
            "Como es del módulo de Inglés para niños hispanohablantes de primaria, redacta las instrucciones "
            "en español cálido e incluye las palabras clave en inglés en MAYÚSCULAS (ej. BLUE, CAT, One, Two, Three). "
            if modulo == "Inglés"
            else ""
        )
        prompt = (
            f"{contexto_pensum}Como especialista en psicopedagogía TDAH para niños de {grado_txt} en el módulo '{modulo}', "
            f"divide la tarea '{tema}' en exactamente 4 micro-pasos secuenciales CONCRETOS y verificables y 4 pistas breves. "
            f"REGLA DE CALIDAD: NO escribas pasos vacíos o genéricos como 'haz la primera parte' o 'completa la segunda parte'. "
            f"Incluye ejercicios, operaciones, palabras clave o acciones exactas en el cuaderno extraídas del tema. "
            f"{instruccion_idioma}"
            f"Responde ÚNICAMENTE con un objeto JSON válido con las claves 'pasos' (4 strings) y 'pistas' (4 strings)."
        )

        for proveedor in (self._llamar_ollama, self._llamar_gemini):
            respuesta = proveedor(prompt)
            if respuesta:
                try:
                    inicio = respuesta.find("{")
                    fin = respuesta.rfind("}")
                    if inicio != -1 and fin != -1:
                        datos = json.loads(respuesta[inicio:fin + 1])
                        pasos = [_limpiar_respuesta_ia(str(x), max_chars=210) for x in datos.get("pasos", []) if str(x).strip()]
                        pistas = [_limpiar_respuesta_ia(str(x), max_chars=210) for x in datos.get("pistas", []) if str(x).strip()]
                        if len(pasos) >= 2:
                            while len(pistas) < len(pasos):
                                pistas.append("Avanza con calma un pedacito a la vez.")
                            return pasos[:6], pistas[:len(pasos[:6])]
                except Exception:
                    pass

        self.ultima_fuente = "Plantilla Psicopedagógica Local"
        return self._descomponer_local_concreto(tema, modulo)

    @staticmethod
    def _respuesta_llm_concuerda_con_calculos(
        respuesta_llm: str, valores_esperados: List[Union[int, float]]
    ) -> bool:
        """Verifica que la respuesta generada por IA externa contenga todos los resultados AST exactos."""
        if not valores_esperados:
            return True
        if not respuesta_llm or not respuesta_llm.strip():
            return False
        nums_txt = re.findall(r"-?\d+(?:\.\d+)?", respuesta_llm.replace(",", "."))
        if not nums_txt:
            return False
        nums_float: List[float] = []
        for s in nums_txt:
            try:
                nums_float.append(float(s))
            except ValueError:
                continue
        if not nums_float:
            return False
        for val in valores_esperados:
            v_f = float(val)
            if not any(abs(nf - v_f) <= 0.015 for nf in nums_float):
                return False
        # Verificar que una asignación explícita ("= 99" o "resultado es 99") no contradiga un cálculo único
        if len(valores_esperados) == 1:
            v_unico = float(valores_esperados[0])
            for m_eq in re.finditer(
                r"(?:=|resultado\s+es|da\s+como\s+resultado|total\s+es)\s*(-?\d+(?:\.\d+)?)",
                respuesta_llm.replace(",", "."),
                flags=re.IGNORECASE,
            ):
                try:
                    n_eq = float(m_eq.group(1))
                    if abs(n_eq - v_unico) > 0.015:
                        return False
                except ValueError:
                    continue
        return True

    def responder_sobre_documento(
        self,
        documento_texto: str,
        pregunta: str = "",
        nombre_doc: str = "tu archivo",
        cobrar_estrellas: Optional[bool] = None,
    ) -> str:
        """
        Analiza el archivo del alumno, lo mantiene activo en sesión para recorrer múltiples
        ejercicios (1..N, 'siguiente', 'los otros', rangos 'del 2 al 4', 'el último'), cobra
        1 estrella cada 3 ejercicios únicos explicados cuando `cobrar_estrellas=True`, y valida
        todos los cálculos numéricos con AST para evitar respuestas erróneas.
        """
        self.ultimo_cobro_documento = None
        consulta = re.sub(r"\s+", " ", (pregunta or "")).strip()[:280]
        if consulta:
            bloqueo = self._verificar_restriccion_tematica(consulta)
            if bloqueo:
                return bloqueo

        if not (documento_texto or "").strip():
            self.ultima_fuente = "Local"
            return self._personalizar_respuesta_local(
                f"Leí el archivo {nombre_doc}, pero parece no tener texto legible."
            )

        q_limpia = _normalizar_ortografia_infantil(consulta)
        q_norm = _normalizar_ia(q_limpia)

        # Mantener o inicializar documento activo en memoria
        if (
            self._documento_activo is None
            or self._documento_activo.get("texto") != documento_texto
            or self._documento_activo.get("nombre") != nombre_doc
        ):
            encabezado_doc, ejercicios = self._parsear_ejercicios_documento(documento_texto)
            modulo_doc = self.detectar_modulo_automatico(documento_texto[:1500])
            self._documento_activo = {
                "nombre": nombre_doc,
                "texto": documento_texto,
                "encabezado": encabezado_doc,
                "ejercicios": ejercicios,
                "modulo": modulo_doc,
                "indice_actual": 0,
                "ejercicios_explicados": set(),
                "ejercicios_desbloqueados": 0,
                "cobrar_estrellas": bool(cobrar_estrellas) if cobrar_estrellas is not None else False,
            }
        else:
            encabezado_doc = str(self._documento_activo.get("encabezado") or "")
            ejercicios = list(self._documento_activo.get("ejercicios") or [])
            modulo_doc = str(self._documento_activo.get("modulo") or "Matemáticas")
            if cobrar_estrellas is not None:
                self._documento_activo["cobrar_estrellas"] = bool(cobrar_estrellas)

        if not ejercicios:
            ejercicios = [{"numero": 1, "etiqueta": "Ejercicio 1", "texto": documento_texto[:1400]}]
            self._documento_activo["ejercicios"] = ejercicios

        total = len(ejercicios)
        idx_actual = min(max(0, int(self._documento_activo.get("indice_actual") or 0)), total - 1)

        # Caso A: Resumen / cantidad de ejercicios
        if re.search(
            r"\b(cuantos\s+ejercicios|cuantas\s+preguntas|de\s+que\s+trata|que\s+tiene\s+el\s+archivo|resumen\s+del\s+archivo|lista\s+de\s+ejercicios)\b",
            q_norm,
        ):
            self.ultima_fuente = "Tutor Local de Documentos"
            vista = "; ".join(
                f"{e['etiqueta']}: {re.sub(chr(10), ' ', str(e['texto']))[:45]}" for e in ejercicios[:3]
            )
            msg_res = (
                f"Tu archivo «{nombre_doc}» tiene {total} ejercicios de {modulo_doc}. "
                f"Por ejemplo: {vista}. "
                f"Vamos por el {idx_actual + 1}/{total}; dime 'siguiente', 'los otros' o el número que quieras revisar."
            )
            return self._registrar_turno_chat(
                consulta or nombre_doc,
                _limpiar_respuesta_ia(self._personalizar_respuesta_local(msg_res), max_chars=520),
                es_documento=True,
            )

        seleccion_indices: List[int] = []
        ordinales = {
            "primero": 1, "primer": 1, "uno": 1, "primera": 1,
            "segundo": 2, "dos": 2, "segunda": 2,
            "tercero": 3, "tercer": 3, "tres": 3, "tercera": 3,
            "cuarto": 4, "cuatro": 4, "cuarta": 4,
            "quinto": 5, "cinco": 5, "quinta": 5,
            "sexto": 6, "seis": 6, "sexta": 6,
            "septimo": 7, "siete": 7, "septima": 7,
            "octavo": 8, "ocho": 8, "octava": 8,
            "noveno": 9, "nueve": 9, "novena": 9,
            "decimo": 10, "diez": 10, "decima": 10,
        }

        def _buscar_idx_por_numero(num_obj: int) -> Optional[int]:
            for i_e, ej_d in enumerate(ejercicios):
                if int(ej_d.get("numero") or 0) == num_obj:
                    return i_e
            if 1 <= num_obj <= total:
                return num_obj - 1
            return None

        # Caso B: Rango ("del 10 al 12")
        m_rango = re.search(r"\bdel\s+(\d{1,3})\s+al\s+(\d{1,3})\b", q_norm)
        if m_rango:
            n_ini, n_fin = int(m_rango.group(1)), int(m_rango.group(2))
            if n_ini > n_fin:
                n_ini, n_fin = n_fin, n_ini
            for n_cur in range(n_ini, min(n_fin, n_ini + 2) + 1):
                idx_enc = _buscar_idx_por_numero(n_cur)
                if idx_enc is not None and idx_enc not in seleccion_indices:
                    seleccion_indices.append(idx_enc)

        # Caso C: Último ejercicio
        if not seleccion_indices and re.search(r"\b(?:ultim[oa]s?|final)\b", q_norm):
            seleccion_indices = [total - 1]

        # Caso D: Número o lista explícita ("ejercicio 15", "2, 3 y 4", "el 30", "15")
        if not seleccion_indices:
            m_lista = re.search(
                r"\b(?:ejercicios?|problemas?|puntos?|actividades?|preguntas?|incisos?)\s+(\d{1,3}(?:\s*(?:,|y)\s*\d{1,3})+)\b",
                q_norm,
            )
            if m_lista:
                for ns in re.findall(r"\d{1,3}", m_lista.group(1))[:3]:
                    idx_enc = _buscar_idx_por_numero(int(ns))
                    if idx_enc is not None and idx_enc not in seleccion_indices:
                        seleccion_indices.append(idx_enc)

        if not seleccion_indices:
            m_num = re.search(
                r"(?:\b(?:ejercicio|problema|punto|actividad|pregunta|tema|inciso|numero|n|el|la)\s+(\d{1,3})\b|^\s*(\d{1,3})\s*$)",
                q_norm,
            )
            if m_num:
                n_val = int(m_num.group(1) or m_num.group(2))
                idx_enc = _buscar_idx_por_numero(n_val)
                if idx_enc is not None:
                    seleccion_indices = [idx_enc]
            else:
                for pal, n_ord in ordinales.items():
                    if re.search(rf"\b{pal}\b", q_norm):
                        idx_enc = _buscar_idx_por_numero(n_ord)
                        if idx_enc is not None:
                            seleccion_indices = [idx_enc]
                        break

        # Caso E: Navegación relativa ("siguiente", "los otros", "anterior", "no entendí")
        pide_siguiente = bool(
            re.search(
                r"\b(siguiente|el\s+que\s+sigue|siguientes|otro\s+ejercicio|otros\s+ejercicios|"
                r"los\s+otros|las\s+otras|otro\b|otros\b|los\s+demas|las\s+demas|mas\s+ejercicios|"
                r"continua|continuemos|sigue\s+con|todos\s+los\s+ejercicios|restantes)\b",
                q_norm,
            )
        )
        pide_plural = bool(
            re.search(r"\b(otros|otras|demas|todos|todas|restantes|mas\s+ejercicios|siguientes|varios)\b", q_norm)
        )
        pide_anterior = bool(re.search(r"\b(anterior|atras|regresa|previo)\b", q_norm))
        pide_repetir = bool(
            re.search(r"\b(no\s+entendi|no\s+comprendi|otra\s+vez|mas\s+facil|repiteme|repite|no\s+entiendo)\b", q_norm)
        )

        if not seleccion_indices:
            if pide_anterior:
                seleccion_indices = [max(0, idx_actual - 1)]
            elif pide_repetir and self._ultimo_turno_fue_documento:
                seleccion_indices = [idx_actual]
            elif pide_siguiente:
                inicio = idx_actual + 1
                if inicio >= total:
                    self.ultima_fuente = "Tutor Local de Documentos"
                    msg_fin = (
                        f"¡Felicidades! Ya llegamos al último ejercicio ({total}/{total}) de «{nombre_doc}». "
                        f"Si quieres repasar alguno dime su número (del 1 al {total}) o di 'cerrar archivo'."
                    )
                    return self._registrar_turno_chat(
                        consulta or nombre_doc,
                        _limpiar_respuesta_ia(self._personalizar_respuesta_local(msg_fin), max_chars=520),
                        es_documento=True,
                    )
                cantidad = 3 if pide_plural else 1
                seleccion_indices = list(range(inicio, min(total, inicio + cantidad)))
            elif q_norm:
                # Intentar coincidencia por palabras clave (e.g. "el de las manzanas" o "fotosintesis")
                stopwords = {
                    "ayuda", "ayudame", "explica", "explicame", "resolver", "resuelve",
                    "como", "hago", "este", "esta", "archivo", "tarea", "ejercicio",
                    "problema", "hola", "haru", "por", "favor", "documento", "guia",
                }
                kws = [w for w in re.findall(r"[a-z0-9ñ]+", q_norm) if len(w) >= 3 and w not in stopwords]
                mejor_idx = None
                mejor_score = 0
                if kws:
                    for i_e, e_d in enumerate(ejercicios):
                        e_norm = _normalizar_ia(str(e_d["texto"]))
                        sc = sum(1 for kw in kws if kw in e_norm)
                        if sc > mejor_score:
                            mejor_score = sc
                            mejor_idx = i_e
                seleccion_indices = [mejor_idx] if mejor_idx is not None else [0]
            else:
                seleccion_indices = [0]

        aviso_pack_agotado = ""
        if (
            self._documento_activo.get("cobrar_estrellas")
            and self.db
            and hasattr(self.db, "consumir_estrellas_ayuda")
        ):
            explicados: set = self._documento_activo.setdefault("ejercicios_explicados", set())
            desbloqueados = int(self._documento_activo.get("ejercicios_desbloqueados") or 0)
            slots_libres = max(0, desbloqueados - len(explicados))
            nuevos = [i for i in seleccion_indices if i not in explicados]
            faltantes = max(0, len(nuevos) - slots_libres)
            if faltantes > 0:
                estrellas_necesarias = (faltantes + self.EJERCICIOS_POR_ESTRELLA - 1) // self.EJERCICIOS_POR_ESTRELLA
                ok, saldo_restante = self.db.consumir_estrellas_ayuda(
                    estrellas_necesarias,
                    f"Ayuda escolar (+{estrellas_necesarias * self.EJERCICIOS_POR_ESTRELLA} ejercicios en '{nombre_doc}')",
                )
                if ok:
                    desbloqueados += estrellas_necesarias * self.EJERCICIOS_POR_ESTRELLA
                    self._documento_activo["ejercicios_desbloqueados"] = desbloqueados
                    self.ultimo_cobro_documento = {
                        "estrellas": estrellas_necesarias,
                        "saldo_restante": saldo_restante,
                        "ejercicios_pack": estrellas_necesarias * self.EJERCICIOS_POR_ESTRELLA,
                    }
                else:
                    if slots_libres > 0:
                        permitidos_set = set(nuevos[:slots_libres])
                        seleccion_indices = [
                            i for i in seleccion_indices if i in explicados or i in permitidos_set
                        ]
                        aviso_pack_agotado = (
                            " Ya completaste los 3 ejercicios de esta estrella; para desbloquear "
                            "los siguientes 3 necesitarás 1 estrella disponible."
                        )
                    else:
                        ya_explicados_sel = [i for i in seleccion_indices if i in explicados]
                        if not ya_explicados_sel:
                            self.ultima_fuente = "Tutor Local de Documentos"
                            msg_sin_saldo = (
                                f"¡Ya usaste tus 3 ejercicios de esta estrella! Para desbloquear otros 3 ejercicios "
                                f"de «{nombre_doc}» necesitas 1 estrella disponible. Avanza un pasito en tu misión (+1 punto) "
                                f"y seguimos enseguida."
                            )
                            return self._registrar_turno_chat(
                                consulta or nombre_doc,
                                _limpiar_respuesta_ia(
                                    self._personalizar_respuesta_local(msg_sin_saldo), max_chars=520
                                ),
                                es_documento=True,
                            )
                        seleccion_indices = ya_explicados_sel
                        aviso_pack_agotado = (
                            " Ya completaste los 3 ejercicios de esta estrella; para desbloquear "
                            "los siguientes 3 necesitarás 1 estrella disponible."
                        )
            explicados.update(seleccion_indices)

        self._documento_activo["indice_actual"] = seleccion_indices[-1]
        seleccionados = [ejercicios[i] for i in seleccion_indices]

        foco_doc = "\n".join(str(e["texto"]) for e in seleccionados)
        foco_compacto = re.sub(r"\s+", " ", foco_doc).strip()[:1600]
        modulo = self.detectar_modulo_automatico(f"{encabezado_doc} {foco_compacto} {consulta}") or modulo_doc

        # Calcular operaciones exactas POR CADA ejercicio seleccionado usando AST
        calculos_globales: List[Tuple[str, Union[int, float], str]] = []
        valores_esperados: List[Union[int, float]] = []
        explicaciones_locales: List[str] = []

        for ej in seleccionados:
            num_ej = int(ej.get("numero") or 1)
            txt_ej = str(ej.get("texto") or "").strip()
            txt_ej_limpio = self._limpiar_prefijo_ejercicio(txt_ej) or txt_ej
            calcs_ej = self._analizar_operaciones_en_texto(txt_ej)
            if calcs_ej:
                calculos_globales.extend(calcs_ej)
                for _etq, val_c, exp_c in calcs_ej:
                    valores_esperados.append(val_c)
                parte_exp = " ".join(exp_c for _etq, _v, exp_c in calcs_ej[:2])
                explicaciones_locales.append(f"Ejercicio {num_ej}/{total}: {parte_exp}")
            else:
                # Apoyo contextual sin matemáticas para este ejercicio específico
                orac = re.sub(r"\s+", " ", txt_ej_limpio).strip()[:130]
                if modulo == "Inglés":
                    pals_en = re.findall(
                        r"\b(BLUE|RED|GREEN|YELLOW|ORANGE|PURPLE|BLACK|WHITE|CAT|DOG|BIRD|FISH|APPLE|BOOK|HOUSE|SUN|MOON|WATER|ONE|TWO|THREE|FOUR|FIVE)\b",
                        txt_ej.upper(),
                    )
                    trad = {
                        "BLUE": "azul", "RED": "rojo", "GREEN": "verde", "YELLOW": "amarillo",
                        "ORANGE": "naranja", "PURPLE": "morado", "BLACK": "negro", "WHITE": "blanco",
                        "CAT": "gato", "DOG": "perro", "BIRD": "pájaro", "FISH": "pez",
                        "APPLE": "manzana", "BOOK": "libro", "HOUSE": "casa", "SUN": "sol",
                        "MOON": "luna", "WATER": "agua", "ONE": "1", "TWO": "2", "THREE": "3",
                        "FOUR": "4", "FIVE": "5",
                    }
                    pista_en = ", ".join(f"{p} = {trad[p]}" for p in pals_en[:3] if p in trad)
                    extra_en = f" Recuerda: {pista_en}." if pista_en else ""
                    explicaciones_locales.append(f"Ejercicio {num_ej}/{total} (Inglés): «{orac}».{extra_en}")
                else:
                    resp_conoc = self.db.buscar_conocimiento(f"{consulta} {txt_ej_limpio[:180]}") if self.db else None
                    if resp_conoc:
                        explicaciones_locales.append(f"Ejercicio {num_ej}/{total}: «{orac}». Pista: {resp_conoc}")
                    else:
                        explicaciones_locales.append(
                            f"Ejercicio {num_ej}/{total}: «{orac}». Identifica qué te pide la consigna, subraya las palabras clave y escríbelo en una oración corta."
                        )

        resumen_calculos = "; ".join(f"{etq} = {res} ({exp})" for etq, res, exp in calculos_globales[:5])
        guia_calculos = (
            f"\nCálculos exactos verificados con AST (OBLIGATORIO usar exactamente estos resultados sin cambiarlos): {resumen_calculos}."
            if resumen_calculos
            else ""
        )
        ctx_enc = f"Título/Consigna de la guía: «{encabezado_doc}».\n" if encabezado_doc else ""
        etiquetas_sel = ", ".join(f"{e['numero']}/{total}" for e in seleccionados)

        if consulta:
            prompt = (
                f"{ctx_enc}Archivo escolar de {modulo} ('{nombre_doc}', {total} ejercicios totales; enfocándonos ahora en ejercicio(s) {etiquetas_sel}):\n"
                f"{foco_compacto}{guia_calculos}\n"
                f"Petición del niño de primaria: '{consulta}'. "
                f"Explica ÚNICAMENTE ese(os) ejercicio(s) paso a paso de forma clara, tierna y exacta en máximo 4 oraciones, sin usar asteriscos ni Markdown."
            )
        else:
            prompt = (
                f"{ctx_enc}Archivo escolar de {modulo} ('{nombre_doc}', {total} ejercicios totales; empezando por el ejercicio {etiquetas_sel}):\n"
                f"{foco_compacto}{guia_calculos}\n"
                f"Anuncia brevemente cuántos ejercicios detectaste ({total}) y explica paso a paso el primer ejercicio de forma clara y exacta, sin Markdown."
            )

        for proveedor in (self._llamar_ollama, self._llamar_gemini):
            resp = proveedor(prompt)
            if resp and self._respuesta_llm_concuerda_con_calculos(resp, valores_esperados):
                limpia = self._personalizar_respuesta_local(
                    _limpiar_respuesta_ia(resp, max_chars=650)
                ) + aviso_pack_agotado
                res_num = calculos_globales[0][1] if calculos_globales else None
                return self._registrar_turno_chat(
                    consulta or nombre_doc, limpia, resultado_num=res_num, es_documento=True
                )

        # Respaldo 100% local exacto y determinista (AST + guía por ejercicio)
        if calculos_globales:
            self.ultima_fuente = "Tutor Local de Documentos + AST"
        elif self.db and any("Pista:" in x for x in explicaciones_locales):
            self.ultima_fuente = "Tutor Local de Documentos + SQLite"
        else:
            self.ultima_fuente = "Tutor Local de Documentos"

        intro_total = (
            f"Encontré {total} ejercicios en «{nombre_doc}». "
            if total > 1 and not consulta
            else f"Sobre «{nombre_doc}» ({total} ejercicios): " if total > 1 else f"Revisé «{nombre_doc}». "
        )
        ultimo_num_mostrado = seleccion_indices[-1] + 1
        cierre_nav = (
            f" Cuando quieras dime 'siguiente', 'los otros' o cualquier número del 1 al {total}."
            if (ultimo_num_mostrado < total and total > 1 and not aviso_pack_agotado)
            else ""
        )
        cuerpo = " ".join(explicaciones_locales)
        limpia = _limpiar_respuesta_ia(
            self._personalizar_respuesta_local(f"{intro_total}{cuerpo}{cierre_nav}{aviso_pack_agotado}"),
            max_chars=700 if aviso_pack_agotado else 650,
        )
        res_num = calculos_globales[0][1] if calculos_globales else None
        return self._registrar_turno_chat(
            consulta or nombre_doc, limpia, resultado_num=res_num, es_documento=True
        )

    def extraer_tareas_de_documento(
        self,
        documento: DocumentoEstudio,
        modulo_defecto: str = "",
        on_progreso: Optional[Callable[[float, str], None]] = None,
    ) -> List[Dict]:
        """
        Analiza el documento completo (incluso documentos mixtos con varias materias) y propone
        una lista de tareas estructuradas paso a paso, cada una con su módulo auto-detectado:
        `[{"nombre": str, "categoria": str, "pasos": List[str], "pistas": List[str], "resumen_fuente": str}]`.
        """
        def _notificar_progreso(fraccion: float, mensaje: str) -> None:
            if on_progreso:
                try:
                    on_progreso(max(0.0, min(1.0, float(fraccion))), mensaje)
                except Exception:
                    pass

        bloques = documento.dividir_en_bloques_tematicos(max_bloques=6)
        if not bloques and documento.texto_completo.strip():
            bloques = [documento.texto_completo.strip()]

        total = len(bloques)
        _notificar_progreso(0.25, f"Analizando {total} bloque(s) del documento...")

        tareas_propuestas: List[Dict] = []
        nombres_vistos = set()

        for idx, bloque in enumerate(bloques, start=1):
            limpio = re.sub(r"\s+", " ", bloque).strip()
            if len(limpio) < 12:
                _notificar_progreso(
                    0.25 + 0.62 * (idx / max(1, total)),
                    f"Sección {idx} de {total} completada.",
                )
                continue

            modulo_bloque = self.detectar_modulo_automatico(limpio, modulo_preferido=modulo_defecto)
            _notificar_progreso(
                0.25 + 0.62 * ((idx - 1) / max(1, total)),
                f"Procesando sección {idx} de {total} ({modulo_bloque})...",
            )

            lineas_bloque = [ln.strip(" -•*#\t") for ln in bloque.splitlines() if ln.strip()]
            encabezado_raw = lineas_bloque[0] if lineas_bloque else limpio[:55]
            encabezado = re.sub(r"^(?:tema|unidad|actividad|tarea|ejercicio|m[oó]dulo|gu[ií]a)\s*\d*[:.\-]\s*", "", encabezado_raw, flags=re.IGNORECASE).strip()
            if len(encabezado) > 48:
                encabezado = encabezado[:48].rsplit(" ", 1)[0].strip()
            if len(encabezado) < 4:
                encabezado = f"Actividad {idx} de {documento.titulo_sugerido[:28]}"

            prefijo_mod = f"{modulo_bloque} - "
            if not encabezado.lower().startswith(modulo_bloque.lower()[:5]):
                nombre_candidato = f"{prefijo_mod}{encabezado}"
            else:
                nombre_candidato = encabezado

            if nombre_candidato.lower() in nombres_vistos:
                nombre_candidato = f"{nombre_candidato} ({idx})"
            nombres_vistos.add(nombre_candidato.lower())

            pasos, pistas = self.descomponer_tarea_ia(
                f"{encabezado}: {limpio[:240]}",
                modulo_forzado=modulo_bloque,
            )

            tareas_propuestas.append({
                "nombre": nombre_candidato,
                "categoria": modulo_bloque,
                "pasos": pasos,
                "pistas": pistas,
                "resumen_fuente": limpio[:220],
            })
            _notificar_progreso(
                0.25 + 0.62 * (idx / max(1, total)),
                f"Sección {idx} de {total} completada.",
            )

        return tareas_propuestas
