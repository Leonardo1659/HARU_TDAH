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

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from core.config import ENV_PATH, MODELO_GEMINI_DEFECTO, OLLAMA_URL_BASE, cargar_env_local
from core.ia.calculadora_ast import resolver_pregunta_matematica

SYSTEM_INSTRUCTION_HARU = (
    "Eres Haru, un tierno, cálido y paciente compañero virtual educativo para niños de "
    "primaria (6 a 11 años) con TDAH en Bolivia. Tus respuestas deben ser muy breves "
    "(máximo 2 a 3 oraciones cortas, sin listas largas ni símbolos Markdown como **), "
    "alegres, motivadoras, fáciles de entender y sin tecnicismos. Nunca entregues toda "
    "la tarea resuelta sin explicar; guía al niño paso a paso con cariño. "
    "No pidas ni repitas datos personales del niño."
)


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
                return f"🔒 Modo Privado Activo: Ollama Local ({modelo_ollama}) + Motor Exacto"
            return "🔒 Modo Privado Activo: 100% Local (Matemática AST + Base Escolar)"
        partes = []
        if self.api_key:
            mod = self._modelo_gemini_activo or MODELO_GEMINI_DEFECTO
            partes.append(f"☁️ Gemini Cloud ({mod})")
        if modelo_ollama:
            partes.append(f"🦙 Ollama ({modelo_ollama})")
        partes.append("🧠 Motor Pedagógico Local")
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
    # 1. TUTOR ACADÉMICO GUIADO EN CAPAS
    # =========================================================================
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

        if modo_charla_libre or not paso_actual:
            contexto = (
                f"El niño de primaria ya está en modo descanso/charla libre tras terminar '{tarea_actual[:80]}'. "
                "Puede preguntarte sobre tareas escolares, curiosidades, emociones o temas cotidianos apropiados para su edad. "
            )
        else:
            contexto = (
                f"Tarea actual: '{tarea_actual[:90]}'. Paso actual: '{paso_actual[:140]}'. "
                if tarea_actual
                else ""
            )
        prompt = (
            f"{contexto}Mensaje del niño de primaria: '{pregunta_limpia}'. "
            f"Responde como Haru en español neutro/boliviano, en máximo 2 oraciones cortitas, cálidas y claras, sin usar asteriscos."
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
                "¡Qué interesante lo que me cuentas! Me encanta charlar contigo en este ratito tranquilo; "
                "puedes preguntarme cuentas matemáticas, temas de ciencias, un chiste o elegir otra misión cuando gustes."
            )
        return (
            f"¡Qué buena pregunta! Para avanzar sin distraernos en «{(tarea_actual or 'tu misión')[:60]}», "
            f"hagamos primero este pasito: {(paso_actual or 'leer con calma el ejercicio')[:120]}. "
            f"¡Si quieres, también podemos pedir apoyo a tu profe o familia!"
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
    # 3. DESCOMPONEDOR AUTOMÁTICO DE TAREAS PARA EL PANEL DOCENTE
    # =========================================================================
    def descomponer_tarea_ia(self, tema_tarea: str) -> Tuple[List[str], List[str]]:
        tema = re.sub(r"\s+", " ", (tema_tarea or "")).strip()[:150] or "Actividad Escolar"
        prompt = (
            f"Como especialista en psicopedagogía TDAH para niños de primaria, divide la tarea "
            f"'{tema}' en exactamente 4 micro-pasos secuenciales muy concretos y 4 pistas breves. "
            f"Responde ÚNICAMENTE con un objeto JSON válido con las claves 'pasos' (4 strings) "
            f"y 'pistas' (4 strings)."
        )

        for proveedor in (self._llamar_ollama, self._llamar_gemini):
            respuesta = proveedor(prompt)
            if respuesta:
                try:
                    inicio = respuesta.find("{")
                    fin = respuesta.rfind("}")
                    if inicio != -1 and fin != -1:
                        datos = json.loads(respuesta[inicio:fin + 1])
                        pasos = [_limpiar_respuesta_ia(str(x), max_chars=180) for x in datos.get("pasos", []) if str(x).strip()]
                        pistas = [_limpiar_respuesta_ia(str(x), max_chars=180) for x in datos.get("pistas", []) if str(x).strip()]
                        if len(pasos) >= 2:
                            while len(pistas) < len(pasos):
                                pistas.append("Avanza con calma un pedacito a la vez.")
                            return pasos[:6], pistas[:len(pasos[:6])]
                except Exception:
                    pass

        self.ultima_fuente = "Plantilla Psicopedagógica Local"
        t_low = tema.lower()
        if any(w in t_low for w in ["matem", "suma", "resta", "multiplica", "divisi", "fracci", "problema", "calcul"]):
            pasos = [
                f"Prepara únicamente tu cuaderno de matemáticas, lápiz y borrador para «{tema}».",
                "Copia el primer ejercicio dejando buen espacio entre cada número.",
                "Resuelve la operación paso a paso revisando unidades y decenas.",
                "Comprueba tu respuesta con Haru y marca tu avance con alegría.",
            ]
            pistas = [
                "Despeja tu mesa para ver solo el cuaderno y el lápiz.",
                "Alinea las columnas de números una debajo de otra.",
                "Si tienes dudas con una cuenta, escríbela en la barra de Haru IA.",
                "¡Muy bien! Revisar al final evita pequeños descuidos.",
            ]
        elif any(w in t_low for w in ["lengua", "lectura", "cuento", "escrib", "oraci", "redac", "poema", "libro"]):
            pasos = [
                f"Abre tu libro o cuaderno de lenguaje en el tema «{tema}».",
                "Lee en voz alta el primer fragmento siguiendo las palabras con tu dedo.",
                "Subraya con tu color favorito las 3 ideas o palabras clave.",
                "Escribe una oración corta explicando con tus palabras lo aprendido.",
            ]
            pistas = [
                "Acomódate en un sitio iluminado y tranquilo.",
                "Si una palabra es larga, léela despacio por sílabas.",
                "Busca de quién trata el texto y qué acción realiza.",
                "Di primero la frase en voz alta antes de escribirla.",
            ]
        elif any(w in t_low for w in ["cienci", "natural", "planta", "animal", "agua", "cuerpo", "planeta", "experimento"]):
            pasos = [
                f"Saca tu cuaderno y 3 lápices de colores para trabajar «{tema}».",
                "Observa las imágenes o el concepto principal del tema.",
                "Dibuja un esquema central sencillo con flechas de colores.",
                "Escribe el nombre de cada parte importante con letra clara.",
            ]
            pistas = [
                "Usar pocos colores a la vez mantiene tu atención enfocada.",
                "Mira primero los títulos y dibujos principales.",
                "Un dibujo grande al centro ayuda a recordar mejor.",
                "Revisa que cada flecha tenga su etiqueta corta.",
            ]
        else:
            pasos = [
                f"Prepara sobre tu mesa solo los materiales para «{tema}».",
                f"Realiza la primera parte de «{tema}» con calma durante unos minutos.",
                "Completa la segunda parte avanzando un detalle a la vez.",
                "Revisa tu trabajo terminado y guarda tus útiles en orden.",
            ]
            pistas = [
                "Un escritorio despejado ayuda a tu cerebro a concentrarse.",
                "Enfócate únicamente en empezar este primer pedacito.",
                "¡Ya vas por la mitad! Respira profundo y sigue así.",
                "Ordenar al final te convierte en un campeón organizado.",
            ]
        return pasos, pistas
