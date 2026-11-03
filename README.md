# 🌱 HARU — Asistente Virtual Educativo para Niños de Primaria con TDAH

**Universidad Salesiana de Bolivia — Ingeniería de Sistemas**  
**Proyecto Integrador: Diseño de un asistente virtual para la organización de tareas y el apoyo académico guiado de niños de primaria con TDAH**

### 👥 Integrantes del Equipo
* Conde Merma Javier Leonardo
* Espinoza Condori Ángel Fernando
* Limachi Llusco Lizeth Gabriela
* Mendoza Conde Rolando Junior
* Nacho Hilari Alexander Aron
* Calle Mamani María Elena
* Mollo Ampuero José Fernando

---

## ✨ Novedades de la Arquitectura Moderna

1. **Interfaz Unificada Estilo Tableta Infantil (`CustomTkinter` + `Pillow 3D`):**
   * **Haru al centro del tablero** con acabado 3D suave, parpadeo natural, saludo interactivo, sincronización labial (lip-sync), guía visual de respiración consciente (`🧘 Respirar`) y 3 trajes (`🤖 Robotito`, `🐱 Gatito`, `🐻 Osito`).
   * **Subtítulos interactivos tipo Karaoke** justo debajo de Haru que iluminan cada palabra en tiempo real mientras habla.
   * **Camino de Aventura Curvo (`1 ➔ 2 ➔ 3 ➔ 🏆 Cofre del Tesoro`)** que celebra con confeti al completar la misión.
   * **3 Temas Visuales Completos sin parches blancos:** `🌿 Calma` (verde jade suave, predeterminado), `☀️ Día` y `🌙 Noche`.
2. **Voz Neuronal Humana Gratuita (`edge-tts` — `es-BO-SofiaNeural`):**
   * Voz neuronal boliviana cálida y expresiva con marcas `WordBoundary` reales, caché local en disco, ~22 frases esenciales pregrabadas en `assets/voz_precargada/` para sonar neuronal incluso **sin internet**, reproducción nativa MCI de Windows (`winmm.dll`) sin requerir `pygame` y respaldo SAPI5 de Windows 100% offline.
3. **Micrófono sin Compiladores C++ (`sounddevice` + `SpeechRecognition`):**
   * Elimina por completo `PyAudio` (cero errores de Microsoft C++ Build Tools en laptops de compañeros), mostrando nivel de voz en vivo y cayendo limpiamente a cuadro de texto si una PC no tiene micrófono.
4. **Motor de Inteligencia Artificial en 4 Capas + Privacidad Infantil (Ley N.º 548):**
   * **Capa 1 (0 ms):** Calculadora aritmética segura con árbol sintáctico `ast` (sin `eval` ni `SymPy`) + Base Escolar SQLite.
   * **Capa 2 (Local Opcional):** Auto-detección de **Ollama** (`127.0.0.1:11434`) para IA generativa 100% local.
   * **Capa 3 (Cloud Gratuita):** **Google Gemini Flash** vía REST estándar (`urllib.request`, compatible con claves `AQ....` y `AIza...`), desactivable con 1 clic mediante el interruptor **`🔒 Modo Privado (Solo Local)`**.
   * **Capa 4 (Respaldo Empático):** Andamiaje psicopedagógico paso a paso sin red.
5. **Panel Docente y Familiar Intuitivo + Reto de Colores Integrado (`OpenCV`):**
   * Panel lateral espacioso en `CustomTkinter` con constructor visual de pasos y pistas, generador automático con IA, gráfico de concentración/descansos, exportación **CSV (Excel)** e **Informe Psicopedagógico HTML**, PIN cifrado con **PBKDF2-HMAC-SHA256** y bloqueo persistente.
   * **Reto Sensorial de Colores (`OpenCV`)** renderizado directamente dentro de un modal moderno de `CustomTkinter` (con modo interactivo automático si la PC no tiene cámara web).

---

## 🚀 Cómo Ejecutar (Sin Ventana Negra de Terminal)

1. **Solo la primera vez** en una computadora nueva: haz doble clic en **`INSTALAR_DEPENDENCIAS.bat`**.
2. Para abrir Haru: haz doble clic en **`INICIAR_HARU.vbs`** (o **`INICIAR_HARU.bat`**). Se abrirá directamente la tableta educativa de Haru sin mostrar consola negra.

### Comandos Útiles para Desarrollo y Defensa
```bash
# Ejecutar diagnóstico completo (verifica módulos, micrófono, voz, SQLite y Gemini API)
python tools/diagnostico.py

# Ejecutar suite de pruebas unitarias e integración
python -m unittest discover -s tests -v

# Crear archivo .zip limpio para enviar a compañeros (excluye automáticamente .env y bases .db)
python tools/empaquetar_zip.py
```

---

## 📂 Estructura del Proyecto

```text
implementos2/
├── haru.pyw                      # Lanzador gráfico silencioso (High-DPI + logs seguros)
├── main_haru_tdah.py             # Punto de entrada estándar Python
├── INICIAR_HARU.vbs              # Inicio directo con 0 parpadeo de consola en Windows
├── INICIAR_HARU.bat              # Inicio alternativo compatible con pythonw
├── INSTALAR_DEPENDENCIAS.bat     # Instalador de 1 clic (sin C++ Build Tools)
├── requirements.txt              # Dependencias ligeras con wheels precompilados
├── .env.example                  # Plantilla segura de variables de entorno
├── core/
│   ├── config.py                 # Rutas portables Path y lector .env ligero
│   ├── eventos.py                # Bus seguro multihilo (queue.Queue)
│   ├── motor_tdah.py             # Motor pedagógico Micro-Pomodoro, pasos y descansos
│   ├── repositorio_db.py         # SQLite WAL, PIN PBKDF2, analítica y reportes CSV/HTML
│   ├── herramientas_multimodales.py # Sonidos winsound + visión HSV OpenCV
│   ├── ia/                       # Calculadora AST + Ollama + Gemini REST + Modo Privado
│   └── voz/                      # TTS Neuronal (Edge-TTS + MCI + Karaoke) y STT (sounddevice)
├── ui/
│   ├── app.py                    # Tableta principal unificada en CustomTkinter
│   ├── avatar_sprite.py          # Haru 3D supersampled + respiración + camino al cofre
│   ├── karaoke.py                # Subtítulos interactivos palabra por palabra
│   ├── panel_docente.py          # Dashboard intuitivo para docentes y familia
│   ├── reto_colores_modal.py     # Cámara OpenCV integrada dentro de CustomTkinter
│   ├── modales.py                # PIN Docente, Álbum de Trofeos y diálogo de voz/texto
│   └── theme.py                  # Paletas completas Calma, Día y Noche
├── hardware/
│   └── control_leds.py           # Control serial Arduino UNO R3 + simulación automática
├── arduino/
│   └── barra_progreso_tdah.ino   # Firmware C++ para los 3 LEDs físicos (Pines 2, 3 y 4)
├── tools/
│   ├── diagnostico.py            # Verificador integral del sistema y API Key
│   ├── pregenerar_voz_offline.py # Generador de las ~22 frases neuronales offline
│   └── empaquetar_zip.py         # Empaquetador limpio sin secretos (.env excluido)
└── tests/
    └── test_motor_tdah.py        # Suite automatizada de pruebas unitarias e integración
```
