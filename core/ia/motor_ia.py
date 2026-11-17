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
from typing import Dict, List, Optional, Tuple, Union

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


def _normalizar_ia(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (texto or "").lower())
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip()


def _limpiar_respuesta_ia(texto: str, max_chars: int = 340) -> str:
    """Elimina marcas Markdown (`**`, `#`, backticks) y evita desbordes en tarjetas UI."""
    limpio = re.sub(r"```[\s\S]*?```", " ", texto or "")
    limpio = re.sub(r"[`*_#]+", "", limpio)
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


class MotorIAHaru:
    MODELOS_CANDIDATOS = [
        MODELO_GEMINI_DEFECTO,
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ]

    def __init__(self, repositorio_db=None):
        self.db = repositorio_db
        cargar_env_local()
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._modelo_gemini_activo: Optional[str] = None
        self._ollama_modelo_cache: Optional[str] = None
        self._ollama_check_ts: float = 0.0
        self.ultima_fuente: str = "Local"
        self.ultimo_error_cloud: str = ""

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
                if modelos:
                    # Preferir modelos rápidos/ligeros si existen
                    for pref in ("qwen", "gemma", "llama3.2", "phi", "mistral"):
                        for m in modelos:
                            if pref in m.lower():
                                self._ollama_modelo_cache = m
                                return m
                    self._ollama_modelo_cache = modelos[0]
                    return modelos[0]
        except Exception:
            pass

        self._ollama_modelo_cache = None
        return None

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
    # PROVEEDORES DE IA (OLLAMA LOCAL Y GEMINI REST)
    # =========================================================================
    def _llamar_ollama(self, prompt: str, system_prompt: str = SYSTEM_INSTRUCTION_HARU) -> Optional[str]:
        modelo = self.detectar_ollama_local()
        if not modelo:
            return None
        try:
            payload = {
                "model": modelo,
                "system": system_prompt,
                "prompt": prompt,
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

        payload_contenido = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.45, "maxOutputTokens": 600},
        }

        # Si la clave empieza con AQ., priorizar el endpoint Vertex AI Express Mode
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
                    "system_instruction": system_prompt,
                    "input": prompt,
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
                        # Pasar al siguiente endpoint base (ej. de ai_studio a vertex_express)
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
        txt_low = (texto or "").lower()
        limpio = re.sub(r"[^a-záéíóúñ0-9+\-×*/\s]", " ", txt_low)
        tokens = set(limpio.split())

        puntajes: Dict[str, int] = {
            "Inglés": 0,
            "Matemáticas": 0,
            "Lenguaje": 0,
            "Ciencias": 0,
            "Hábitos y Orden": 0,
        }

        # Palabras e indicadores de Inglés
        kw_ingles_fuerte = {
            "ingles", "inglés", "english", "hello", "goodbye", "vocabulary",
            "colors", "animals", "numbers", "blue", "red", "yellow", "green",
            "orange", "purple", "cat", "dog", "bird", "rabbit", "lion",
            "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "mother", "father", "sister", "brother", "family",
            "apple", "banana", "school", "teacher", "student", "book", "pencil",
            "good", "morning", "afternoon", "night", "champion", "words",
        }
        for w in kw_ingles_fuerte:
            if w in tokens:
                puntajes["Inglés"] += 3 if w in ("ingles", "inglés", "english", "vocabulary") else 2
        if any(fr in txt_low for fr in ("en inglés", "en ingles", "in english", "how do you say", "repeat after me")):
            puntajes["Inglés"] += 5

        # Palabras e indicadores de Matemáticas
        kw_mate = {
            "matematica", "matematicas", "matemáticas", "matemática", "suma", "sumas",
            "sumar", "resta", "restas", "restar", "multiplica", "multiplicacion",
            "multiplicación", "multiplicar", "divide", "division", "división", "dividir",
            "fraccion", "fracción", "fracciones", "numero", "numeros", "número", "números",
            "calculo", "cálculo", "calcular", "decena", "decenas", "unidad", "unidades",
            "centena", "geometria", "geometría", "triangulo", "cuadrado", "rectangulo",
            "operacion", "operaciones", "aritmetica", "aritmética",
        }
        for w in kw_mate:
            if w in tokens:
                puntajes["Matemáticas"] += 2
        if re.search(r"\b\d+\s*[+\-×x*/]\s*\d+\b", txt_low):
            puntajes["Matemáticas"] += 4

        # Palabras e indicadores de Lenguaje
        kw_lenguaje = {
            "lenguaje", "lectura", "leer", "cuento", "cuentos", "fabula", "fábula",
            "poema", "poesia", "poesía", "oracion", "oración", "oraciones", "parrafo",
            "párrafo", "verbo", "verbos", "sustantivo", "sustantivos", "adjetivo",
            "adjetivos", "silaba", "sílaba", "silabas", "sílabas", "ortografia",
            "ortografía", "redaccion", "redacción", "abecedario", "sinonimo",
            "sinónimo", "antonimo", "antónimo", "personaje", "narracion",
        }
        for w in kw_lenguaje:
            if w in tokens:
                puntajes["Lenguaje"] += 2

        # Palabras e indicadores de Ciencias
        kw_ciencias = {
            "ciencias", "ciencia", "naturales", "planta", "plantas", "fotosintesis",
            "fotosíntesis", "agua", "evaporacion", "evaporación", "nube", "lluvia",
            "planeta", "planetas", "solar", "tierra", "ecosistema", "naturaleza",
            "cuerpo", "humano", "experimento", "dinosaurio", "dinosaurios", "celula",
            "célula", "energia", "energía", "vertebrados", "invertebrados", "reciclaje",
        }
        for w in kw_ciencias:
            if w in tokens:
                puntajes["Ciencias"] += 2
        if "ciclo del agua" in txt_low or "sistema solar" in txt_low or "seres vivos" in txt_low:
            puntajes["Ciencias"] += 4

        # Palabras e indicadores de Hábitos y Orden
        kw_habitos = {
            "habito", "hábito", "habitos", "hábitos", "orden", "organizacion",
            "organización", "mochila", "estuche", "cartuchera", "horario", "rutina",
            "escritorio", "limpieza", "puntualidad", "responsabilidad", "alistar",
            "guardar", "ordenar",
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
    # 1. TUTOR ACADÉMICO GUIADO EN CAPAS + GUARDRAILS + DOCUMENTOS
    # =========================================================================
    def _verificar_restriccion_tematica(self, texto: str) -> Optional[str]:
        """Bloquea con respeto temas no aptos o ajenos a un tutor escolar de primaria."""
        norm = _normalizar_ia(texto)
        if not norm:
            return None

        if re.search(
            r"\b(novia|novio|enamorar(?:me|se)?|enamorad[oa]|besar|beso|ligar|conquistar|"
            r"cita\s+romantica|tener\s+pareja|sexo|sexual|desnud\w*|porno\w*|erotic\w*|"
            r"contenido\s+para\s+adultos|paginas?\s+para\s+adultos)\b",
            norm,
        ):
            self.ultima_fuente = "Filtro Guardián Infantil"
            return (
                "Soy Haru, tu compañero educativo para primaria, así que no converso sobre novios, romance ni temas de adultos. "
                "Si quieres ayuda con tus tareas, cómo concentrarte o dudas de clase, ¡aquí estoy para ti!"
            )

        if re.search(
            r"\b(free\s*fire|fortnite|warzone|valorant|call\s+of\s+duty|gta|roblox|"
            r"brawl\s+stars|clash\s+royale|pubg|headshot|diamantes\s+gratis|minecraft\s+pvp|"
            r"tiktok|apuestas?|casino|hackear|cheats?)\b",
            norm,
        ):
            self.ultima_fuente = "Filtro Guardián Infantil"
            return (
                "Estoy aquí para ayudarte en tus materias de primaria y hábitos de estudio, no doy trucos ni consejos de videojuegos o redes. "
                "¡Avancemos tus pasitos de tarea primero para que luego disfrutes tu tiempo libre tranquilo!"
            )

        if re.search(
            r"\b(pelear(?:me|se)?|golpear|matar|pistola|arma|cuchillo|droga\w*|alcohol|"
            r"cerveza|cigarrillo|vape\w*|hacer\s+trampa|copiar\s+en\s+el\s+examen|pasame\s+las\s+respuestas)\b",
            norm,
        ):
            self.ultima_fuente = "Filtro Guardián Infantil"
            return (
                "Como tu tutor escolar cuido tu seguridad y aprendizaje honesto, por eso no ayudo con violencia, armas, sustancias ni trampas. "
                "Cuéntame qué ejercicio o materia quieres aprender y lo resolvemos paso a paso."
            )
        return None

    def _responder_vida_cotidiana_y_estudio(self, pregunta: str) -> Optional[str]:
        """Responde dudas cotidianas útiles (hora, fecha, hábitos de estudio, concentración)."""
        norm = _normalizar_ia(pregunta)
        if not norm:
            return None

        if re.search(r"\b(que\s+hora\s+(es|son)|dime\s+la\s+hora|hora\s+actual|sabes\s+la\s+hora|tienes\s+la\s+hora)\b", norm):
            ahora = datetime.now()
            periodo = "de la mañana" if ahora.hour < 12 else ("de la tarde" if ahora.hour < 19 else "de la noche")
            self.ultima_fuente = "Reloj y Guía Diaria Haru"
            return f"Son las {ahora.strftime('%H:%M')} {periodo}. ¡Buen momento para hacer un pasito con calma o tomar un descanso breve!"

        if re.search(r"\b(que\s+dia\s+es\s+(hoy|ahora)|cual\s+es\s+la\s+fecha|fecha\s+de\s+hoy|en\s+que\s+fecha\s+estamos)\b", norm):
            ahora = datetime.now()
            dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
            meses = (
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
            )
            self.ultima_fuente = "Reloj y Guía Diaria Haru"
            return f"Hoy es {dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]} de {ahora.year}. ¡Organicemos tus tareas del día paso a paso!"

        pide_consejo = any(
            w in norm for w in ("como", "mejorar", "consejo", "tips", "ayuda", "puedo", "organizar", "sacar")
        )
        if re.search(r"\b(mejorar\s+(?:en\s+)?(?:mis|los)\s+estudios|estudiar\s+mejor|rendir\s+mejor|sacar\s+buenas\s+notas|mejorar\s+(?:mis\s+)?calificaciones|habitos\s+de\s+estudio|como\s+estudio)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return (
                "Para mejorar en tus estudios: 1) despeja tu mesa dejando solo un cuaderno, "
                "2) divide cada tarea en bloques cortos de 10 minutos con 2 minutos de descanso, "
                "y 3) al terminar, explícate en voz alta con tus propias palabras lo que aprendiste."
            )

        if pide_consejo and re.search(r"\b(concentr\w*|no\s+distra\w*|atencion|enfocar\w*|foco|organizar\s+(?:mis\s+)?tareas)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return (
                "Para concentrarte mejor: aparta juguetes o pantallas de tu escritorio, usa el reloj de Haru por 10 minutos "
                "y enfócate únicamente en el paso actual antes de pasar al siguiente."
            )

        if pide_consejo and re.search(r"\b(examen\w*|evaluacion\w*|memori\w*|no\s+olvid\w*|acordarme)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return (
                "Para recordar mejor para un examen: lee cada idea en voz alta, dibuja o escribe un ejemplo propio en tu cuaderno "
                "y descansa bien la noche anterior para que tu cerebro ordene lo aprendido."
            )

        if pide_consejo and re.search(r"\b(nervios\w*|frustrad\w*|enojad\w*|triste|no\s+me\s+sale|estres)\b", norm):
            self.ultima_fuente = "Tutor Pedagógico Haru"
            return (
                "Cuando te sientas frustrado o nervioso es normal: toca el botón Respirar para tomar 3 respiraciones suaves, "
                "toma un poquito de agua y luego resolvamos juntos solo el primer pedacito del ejercicio."
            )

        return None

    @staticmethod
    def _explicar_operacion_primaria(a: float, op: str, b: float, res: float) -> str:
        a_s = str(int(a)) if a == int(a) else str(round(a, 2))
        b_s = str(int(b)) if b == int(b) else str(round(b, 2))
        r_s = str(int(res)) if res == int(res) else str(round(res, 2))
        if op == "+":
            if abs(a) >= 10 and abs(b) >= 10 and a == int(a) and b == int(b):
                u_sum = (int(a) % 10) + (int(b) % 10)
                return f"Para sumar {a_s} + {b_s}, alinea unidades ({int(a)%10}+{int(b)%10}={u_sum}) y luego las decenas: da {r_s}."
            return f"Para sumar {a_s} + {b_s}, parte desde {a_s} y agrega {b_s}: el resultado es {r_s}."
        if op == "-":
            if abs(a) >= 10 and abs(b) >= 10 and a == int(a) and b == int(b):
                return f"Para restar {a_s} - {b_s}, resta primero las unidades y luego las decenas en columna: queda {r_s}."
            return f"Para restar {a_s} - {b_s}, quita {b_s} a {a_s}: el resultado es {r_s}."
        if op == "*":
            return f"Para multiplicar {a_s} × {b_s}, suma {a_s} veces el número {b_s}: obtienes {r_s}."
        if op == "/":
            return f"Para dividir {a_s} ÷ {b_s}, reparte {a_s} en {b_s} grupos iguales: a cada grupo le toca {r_s}."
        return f"La operación {a_s} {op} {b_s} da como resultado {r_s}."

    def _analizar_operaciones_en_texto(self, texto: str) -> List[Tuple[str, Union[int, float], str]]:
        """Detecta y evalúa de forma segura (`ast`) operaciones aritméticas en guías o ejercicios."""
        limpio = (texto or "").replace("×", "*").replace("÷", "/")
        limpio = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", " * ", limpio)
        resultados: List[Tuple[str, Union[int, float], str]] = []
        vistos = set()
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)", limpio):
            a_str, op, b_str = m.group(1), m.group(2), m.group(3)
            expr = f"{a_str} {op} {b_str}"
            if expr in vistos:
                continue
            try:
                val = evaluar_ast_seguro(expr)
            except Exception:
                continue
            vistos.add(expr)
            op_vis = {"*": "×", "/": "÷"}.get(op, op)
            etq = f"{a_str} {op_vis} {b_str}"
            val_num: Union[int, float] = int(val) if val == int(val) else round(float(val), 2)
            explicacion = self._explicar_operacion_primaria(float(a_str), op, float(b_str), float(val))
            resultados.append((etq, val_num, explicacion))
        return resultados

    def _extraer_bloque_ejercicio_documento(self, documento_texto: str, pregunta: str) -> str:
        """Localiza el ejercicio o sección exacta del documento que el niño preguntó."""
        lineas = [ln.strip() for ln in (documento_texto or "").splitlines() if ln.strip()]
        if not lineas:
            return ""
        q_norm = _normalizar_ia(pregunta)
        if not q_norm:
            return "\n".join(lineas[:8])[:1400]

        ordinales = {
            "primero": 1, "primer": 1, "uno": 1,
            "segundo": 2, "dos": 2,
            "tercero": 3, "tercer": 3, "tres": 3,
            "cuarto": 4, "cuatro": 4,
            "quinto": 5, "cinco": 5,
            "sexto": 6, "seis": 6,
        }
        num_pedida: Optional[int] = None
        m_num = re.search(r"\b(?:ejercicio|problema|punto|actividad|pregunta|tema|inciso|el|la|numero|n)?\s*(\d{1,2})\b", q_norm)
        if m_num:
            num_pedida = int(m_num.group(1))
        else:
            for pal, n_ord in ordinales.items():
                if re.search(rf"\b{pal}\b", q_norm):
                    num_pedida = n_ord
                    break

        if num_pedida is not None:
            patron_item = re.compile(
                rf"^\s*(?:ejercicio|problema|actividad|pregunta|punto|tema)?\s*{num_pedida}\s*[).:\-]|^\s*#+\s*.*?\b{num_pedida}\b",
                re.IGNORECASE,
            )
            for idx, ln in enumerate(lineas):
                if patron_item.search(ln):
                    return "\n".join(lineas[idx : idx + 3])[:1400]
            # Si las líneas enumeran ejercicios sin prefijo numérico claro
            ejercicios_crudos = [
                ln for ln in lineas
                if len(ln) >= 6 and not ln.lower().startswith(("nombre:", "curso:", "fecha:", "guía", "guia"))
            ]
            if 1 <= num_pedida <= len(ejercicios_crudos):
                return ejercicios_crudos[num_pedida - 1][:1400]

        stopwords = {
            "ayuda", "ayudame", "explica", "explicame", "resolver", "resuelve",
            "como", "hago", "este", "esta", "archivo", "tarea", "ejercicio", "hola", "haru", "por", "favor",
        }
        kws = [w for w in re.findall(r"[a-z0-9ñ]+", q_norm) if len(w) >= 3 and w not in stopwords]
        if kws:
            mejor_idx = 0
            mejor_score = 0
            for idx, ln in enumerate(lineas):
                ln_norm = _normalizar_ia(ln)
                score = sum(1 for kw in kws if kw in ln_norm)
                if score > mejor_score:
                    mejor_score = score
                    mejor_idx = idx
            if mejor_score > 0:
                return "\n".join(lineas[mejor_idx : mejor_idx + 3])[:1400]

        return "\n".join(lineas[:8])[:1400]

    def responder_consulta_escolar(
        self,
        pregunta: str,
        tarea_actual: str = "",
        paso_actual: str = "",
        modo_charla_libre: bool = False,
    ) -> str:
        pregunta_limpia = re.sub(r"\s+", " ", (pregunta or "")).strip()[:360]
        if not pregunta_limpia:
            self.ultima_fuente = "Local"
            return "¡Hola! Escribe o dime tu duda y la resolvemos juntos con calma."

        bloqueo = self._verificar_restriccion_tematica(pregunta_limpia)
        if bloqueo:
            return bloqueo

        # Capa 1A: Calculadora aritmética segura (AST)
        respuesta_mate = resolver_pregunta_matematica(pregunta_limpia)
        if respuesta_mate:
            self.ultima_fuente = "Calculadora Segura AST"
            return respuesta_mate

        # Capa 1B: Base de conocimiento escolar y conversacional SQLite
        if self.db:
            resp_local = self.db.buscar_conocimiento(pregunta_limpia)
            if resp_local:
                self.ultima_fuente = "Conocimiento Escolar SQLite"
                return resp_local

        # Capa 1C: Hora, fecha, técnicas de estudio y guía cotidiana segura
        resp_cotidiana = self._responder_vida_cotidiana_y_estudio(pregunta_limpia)
        if resp_cotidiana:
            return resp_cotidiana

        contexto_pensum = self._obtener_contexto_pensum(f"{tarea_actual} {pregunta_limpia}")
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
            f"{contexto_pensum}{contexto}Mensaje del niño de primaria: '{pregunta_limpia}'. "
            f"Responde como Haru en español claro, en 2 o 3 oraciones breves, prácticas y sin Markdown."
        )

        # Capa 2: Ollama local (si está activo en la PC)
        resp_ollama = self._llamar_ollama(prompt)
        if resp_ollama:
            return _limpiar_respuesta_ia(resp_ollama)

        # Capa 3: Gemini Cloud REST (si hay clave y no está en Modo Privado)
        resp_gemini = self._llamar_gemini(prompt)
        if resp_gemini:
            return _limpiar_respuesta_ia(resp_gemini)

        # Capa 4: Respaldo pedagógico o conversacional empático local
        self.ultima_fuente = "Andamiaje Local"
        if modo_charla_libre or not paso_actual:
            return (
                "¡Qué interesante lo que me cuentas! Podemos charlar sobre tus metas de estudio, "
                "preguntarme la hora, resolver cuentas o elegir una nueva misión cuando gustes."
            )
        return (
            f"¡Buena pregunta! Para avanzar en «{(tarea_actual or 'tu misión')[:60]}», "
            f"hagamos primero este pasito: {(paso_actual or 'leer con calma el ejercicio')[:120]}. "
            f"Si quieres que resuelva una cuenta o lea un archivo de ejercicios, dímelo con gusto."
        )

    # =========================================================================
    # 2. GENERADOR DE PISTAS CONTEXTUALES (ANDAMIAJE TDAH)
    # =========================================================================
    def generar_pista_contextual(self, nombre_tarea: str, texto_paso: str, num_paso: int) -> str:
        prompt = (
            f"El niño de primaria con TDAH está en el Paso {num_paso} de '{(nombre_tarea or '')[:80]}': "
            f"'{(texto_paso or '')[:150]}'. Dale una sola pista práctica y tierna de máximo 18 palabras, sin asteriscos."
        )
        pista_ollama = self._llamar_ollama(prompt)
        if pista_ollama:
            return _limpiar_respuesta_ia(pista_ollama, max_chars=200)

        pista_gemini = self._llamar_gemini(prompt)
        if pista_gemini:
            return _limpiar_respuesta_ia(pista_gemini, max_chars=200)

        self.ultima_fuente = "Andamiaje Local"
        paso_low = (texto_paso or "").lower()
        if any(w in paso_low for w in ["saca", "prepara", "mochila", "cuaderno", "lápiz", "lapiz", "mesa"]):
            return "Pista mágica: Pon en tu mesa solo lo que pide este paso y guarda lo demás para no distraerte."
        if any(w in paso_low for w in ["lee", "lectura", "párrafo", "parrafo", "cuento", "libro"]):
            return "Pista de lectura: Sigue cada renglón con tu dedito o una regla para mantener el foco."
        if any(w in paso_low for w in ["suma", "resta", "multiplica", "ejercicio", "número", "numero", "calcula"]):
            return "Pista matemática: Resuelve una columna a la vez. ¡Puedes comprobar cuentas en la barra de Haru IA!"
        if any(w in paso_low for w in ["escribe", "oración", "oracion", "copia", "anota"]):
            return "Pista de escritura: Di primero tu idea en voz alta y luego escríbela despacio palabra por palabra."
        if any(w in paso_low for w in ["dibuja", "pinta", "color", "colorea"]):
            return "Pista creativa: ¡No tiene que ser perfecto! Empieza con trazos grandes usando tu color favorito."
        return f"¡Tú puedes con el paso {num_paso}! Haz solo esta pequeña acción y presiona ¡Paso Listo!"

    # =========================================================================
    # 3. DESCOMPONEDOR AUTOMÁTICO DE TAREAS Y EXTRACTOR MULTIMODAL DE DOCUMENTOS
    # =========================================================================
    def _descomponer_local_concreto(self, tema: str, modulo: str) -> Tuple[List[str], List[str]]:
        """Genera 4 micro-pasos verificables con ejercicios/datos reales sin frases de relleno."""
        ops = self._analizar_operaciones_en_texto(tema)
        t_norm = _normalizar_ia(tema)

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
            m_pal = re.findall(r"\b(BLUE|RED|GREEN|YELLOW|ORANGE|CAT|DOG|BIRD|LION|ONE|TWO|THREE|FOUR|FIVE|APPLE|BOOK)\b", tema.upper())
            pal1 = m_pal[0] if m_pal else "BLUE"
            pal2 = m_pal[1] if len(m_pal) > 1 else "CAT"
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
                ej1, ej2 = "1/2 (la mitad de un círculo)", "1/4 (un cuarto pintado)"
                pasos = [
                    f"Prepara tu cuaderno y regla para practicar «{tema[:42]}».",
                    f"Dibuja un círculo dividido en 2 partes iguales y pinta {ej1}.",
                    f"Dibuja un cuadrado dividido en 4 partes iguales y pinta {ej2}.",
                    "Escribe debajo de cada dibujo qué número es el numerador (arriba) y el denominador (abajo).",
                ]
                pistas = [
                    "Usa monedas o tapas si te ayuda a dibujar círculos ordenados.",
                    "1/2 significa que partimos el entero en 2 y tomamos 1 parte.",
                    "1/4 significa que partimos en 4 partes iguales y pintamos 1.",
                    "Recuerda: el denominador abajo dice en cuántas partes se divide el entero.",
                ]
            elif "multiplica" in t_norm or "tabla" in t_norm:
                pasos = [
                    "Prepara tu cuaderno y escribe estas dos multiplicaciones: 3 × 4 y 6 × 5.",
                    "Resuelve 3 × 4 sumando 3 grupos de 4 (4 + 4 + 4) y anota el resultado.",
                    "Resuelve 6 × 5 contando de 5 en 5 seis veces y anota el resultado.",
                    "Inventa una multiplicación más con tu número favorito y compruébala en tu cuaderno.",
                ]
                pistas = [
                    "Deja dos cuadritos de espacio entre cada ejercicio.",
                    "Contar grupos iguales hace la multiplicación mucho más fácil.",
                    "Usa tus dedos para llevar la cuenta: 5, 10, 15, 20...",
                    "Revisa que tus resultados de 3 × 4 y 6 × 5 estén claros.",
                ]
            elif "divi" in t_norm:
                pasos = [
                    "Prepara tu cuaderno y escribe las divisiones 12 ÷ 3 y 20 ÷ 4.",
                    "Resuelve 12 ÷ 3 imaginando que repartes 12 dulces entre 3 amigos.",
                    "Resuelve 20 ÷ 4 repartiendo 20 lápices en 4 grupos iguales.",
                    "Comprueba tus respuestas multiplicando cada resultado por el divisor.",
                ]
                pistas = [
                    "Dibuja 3 círculos en borrador si quieres repartir los 12 elementos.",
                    "Cuenta cuántos quedaron dentro de cada grupo.",
                    "Pregunta: ¿qué número por 4 nos da 20?",
                    "Si 4 × 5 = 20, entonces 20 ÷ 4 = 5.",
                ]
            elif "resta" in t_norm:
                pasos = [
                    "Abre tu cuaderno en hoja limpia y escribe las restas 28 - 13 y 45 - 19.",
                    "Calcula primero 28 - 13 restando unidades (8 - 3) y decenas (2 - 1).",
                    "Ahora calcula 45 - 19 prestando 1 decena al 5 para restar 15 - 9.",
                    "Revisa ambas restas sumando el resultado con el número que quitaste.",
                ]
                pistas = [
                    "Alinea siempre las unidades a la derecha y decenas a la izquierda.",
                    "8 menos 3 da 5, y 2 menos 1 da 1.",
                    "Al pedir prestado a la decena, el 4 queda en 3 y el 5 sube a 15.",
                    "Comprobar con una suma asegura que no hubo descuidos.",
                ]
            else:
                pasos = [
                    f"Abre tu cuaderno de matemáticas y escribe dos sumas de práctica para «{tema[:38]}»: 16 + 8 y 24 + 15.",
                    "Resuelve 16 + 8 sumando primero 6 + 8 y llevando 1 a la decena.",
                    "Resuelve 24 + 15 alineando las columnas de unidades (4 + 5) y decenas (2 + 1).",
                    "Verifica con calma el resultado de 16 + 8 y 24 + 15 antes de guardar tu lápiz.",
                ]
                pistas = [
                    "Mantén sobre la mesa solo cuaderno, lápiz y borrador.",
                    "6 + 8 = 14: deja el 4 abajo y lleva 1 decena arriba.",
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
        instruccion_idioma = (
            "Como es del módulo de Inglés para niños hispanohablantes de primaria, redacta las instrucciones "
            "en español cálido e incluye las palabras clave en inglés en MAYÚSCULAS (ej. BLUE, CAT, One, Two, Three). "
            if modulo == "Inglés"
            else ""
        )
        prompt = (
            f"{contexto_pensum}Como especialista en psicopedagogía TDAH para niños de primaria en el módulo '{modulo}', "
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

    def responder_sobre_documento(
        self, documento_texto: str, pregunta: str = "", nombre_doc: str = "tu archivo"
    ) -> str:
        """Analiza el archivo del alumno y explica/resuelve paso a paso el ejercicio consultado."""
        consulta = re.sub(r"\s+", " ", (pregunta or "")).strip()[:280]
        if consulta:
            bloqueo = self._verificar_restriccion_tematica(consulta)
            if bloqueo:
                return bloqueo

        if not (documento_texto or "").strip():
            self.ultima_fuente = "Local"
            return f"Leí el archivo {nombre_doc}, pero parece no tener texto legible."

        foco_doc = self._extraer_bloque_ejercicio_documento(documento_texto, consulta) or documento_texto[:1400]
        foco_compacto = re.sub(r"\s+", " ", foco_doc).strip()[:1600]
        modulo = self.detectar_modulo_automatico(f"{foco_compacto} {consulta}")
        calculos = self._analizar_operaciones_en_texto(foco_compacto)
        resumen_calculos = "; ".join(f"{etq} = {res} ({exp})" for etq, res, exp in calculos[:3])

        guia_calculos = (
            f"\nCálculos exactos verificados del ejercicio (úsalos para no equivocarte): {resumen_calculos}."
            if resumen_calculos
            else ""
        )
        if consulta:
            prompt = (
                f"Fragmento relevante del archivo escolar de {modulo} ('{nombre_doc}'):\n\"{foco_compacto}\".{guia_calculos}\n"
                f"Petición exacta del niño de primaria: '{consulta}'. "
                f"Ayúdalo de verdad a resolver o comprender exactamente ese ejercicio paso a paso en 2 a 4 oraciones claras, sin usar asteriscos ni Markdown."
            )
        else:
            prompt = (
                f"Contenido del archivo escolar de {modulo} ('{nombre_doc}'):\n\"{foco_compacto}\".{guia_calculos}\n"
                f"Explícale al niño de primaria qué ejercicios pide su archivo y cómo resolver el primer ejercicio paso a paso en 2 a 4 oraciones claras, sin Markdown."
            )

        for proveedor in (self._llamar_ollama, self._llamar_gemini):
            resp = proveedor(prompt)
            if resp:
                return _limpiar_respuesta_ia(resp, max_chars=430)

        # Respaldo 100% local que SÍ resuelve y guía ejercicios reales del documento
        if calculos:
            self.ultima_fuente = "Tutor Local de Documentos + AST"
            partes_exp = [exp for _etq, _res, exp in calculos[:2]]
            return _limpiar_respuesta_ia(
                f"Revisé «{nombre_doc}». {' '.join(partes_exp)} ¡Anota el procedimiento con calma en tu cuaderno!",
                max_chars=430,
            )

        if self.db:
            resp_conoc = self.db.buscar_conocimiento(f"{consulta} {foco_compacto[:220]}")
            if resp_conoc:
                self.ultima_fuente = "Tutor Local de Documentos + SQLite"
                return _limpiar_respuesta_ia(
                    f"Sobre tu archivo «{nombre_doc}»: {resp_conoc} Empieza copiando la idea clave en tu cuaderno.",
                    max_chars=430,
                )

        self.ultima_fuente = "Tutor Local de Documentos"
        oraciones = [s.strip() for s in re.split(r"(?<=[.!?\n])\s*", foco_doc) if len(s.strip()) > 8]
        foco_1 = oraciones[0][:150] if oraciones else foco_compacto[:150]
        if modulo == "Inglés":
            pals_en = re.findall(r"\b(BLUE|RED|GREEN|YELLOW|CAT|DOG|ONE|TWO|THREE|FOUR|FIVE)\b", foco_compacto.upper())
            trad = {"BLUE": "azul", "RED": "rojo", "GREEN": "verde", "YELLOW": "amarillo", "CAT": "gato", "DOG": "perro", "ONE": "1", "TWO": "2", "THREE": "3"}
            pista_en = ", ".join(f"{p} = {trad[p]}" for p in pals_en[:3] if p in trad)
            extra = f" Recuerda: {pista_en}." if pista_en else ""
            return _limpiar_respuesta_ia(
                f"En tu guía de Inglés «{nombre_doc}» el ejercicio dice: «{foco_1}».{extra} Escribe cada palabra en inglés y dilo en voz alta.",
                max_chars=430,
            )
        if "?" in foco_compacto or any(w in _normalizar_ia(foco_compacto) for w in ("subraya", "explica", "escribe", "completa", "dibuja", "lee")):
            return _limpiar_respuesta_ia(
                f"Para resolver este punto de «{nombre_doc}» («{foco_1}»): identifica primero qué dato te pide (persona, acción o número), "
                f"subraya las palabras clave en tu hoja y responde en una oración corta.",
                max_chars=430,
            )
        return _limpiar_respuesta_ia(
            f"Revisé «{nombre_doc}» ({modulo}). Para resolver «{foco_1}», separa primero los datos que te da el enunciado "
            f"y escríbeme la pregunta o cuenta específica que quieras comprobar.",
            max_chars=430,
        )

    def extraer_tareas_de_documento(
        self, documento: DocumentoEstudio, modulo_defecto: str = ""
    ) -> List[Dict]:
        """
        Analiza el documento completo (incluso documentos mixtos con varias materias) y propone
        una lista de tareas estructuradas paso a paso, cada una con su módulo auto-detectado:
        `[{"nombre": str, "categoria": str, "pasos": List[str], "pistas": List[str], "resumen_fuente": str}]`.
        """
        bloques = documento.dividir_en_bloques_tematicos(max_bloques=6)
        if not bloques and documento.texto_completo.strip():
            bloques = [documento.texto_completo.strip()]

        tareas_propuestas: List[Dict] = []
        nombres_vistos = set()

        for idx, bloque in enumerate(bloques, start=1):
            limpio = re.sub(r"\s+", " ", bloque).strip()
            if len(limpio) < 12:
                continue

            # Auto-detectar el módulo curricular específico de este bloque (soporta guías mixtas)
            modulo_bloque = self.detectar_modulo_automatico(limpio, modulo_preferido=modulo_defecto)

            # Extraer un título breve y limpio a partir del primer renglón o encabezado del bloque
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

        return tareas_propuestas
