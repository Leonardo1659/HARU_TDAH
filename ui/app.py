"""
Interfaz Principal Unificada Estilo Tableta Infantil en CustomTkinter — "Haru"
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Implementa fielmente el diseño unificado con:
- Haru 3D animado en el centro del escenario y camino de aventura hacia el cofre.
- Subtítulos interactivos tipo karaoke palabra por palabra debajo de Haru.
- Tarjeta de reloj Micro-Pomodoro + Descanso controlado arriba a la izquierda.
- Insignia de misión, puntos/trofeos, acceso Docente/Familia y Semáforo Arduino a la derecha.
- Barra inferior con `🎤 Hablar`, `< Anterior`, gran botón central `✔ ¡Paso Listo! (+1 ⭐)`,
  `🪄 Pista Mágica`, `🔄 Repetir`, `↺ Reiniciar` y `Reto Colores 📷` integrado.
- Bus reactivo `BusEventosUI` (`after(35)`) para seguridad total multihilo.
"""

import tkinter as tk
from typing import Dict, List, Optional

import customtkinter as ctk

from core.config import VOZ_POR_DEFECTO
from core.eventos import BusEventosUI
from core.herramientas_multimodales import GestorMultimodal
from core.ia import MotorIAHaru
from core.motor_tdah import MotorTDAH
from core.repositorio_db import RepositorioTDAH
from core.voz import EscuchaVozHaru, MotorVozHaru
from hardware.control_leds import ControladorHardwareLEDs
from ui.avatar_sprite import REQUISITOS_SKIN, EscenarioCentralHaru
from ui.karaoke import SubtitulosKaraoke
from ui.modales import ModalAlbumPremios, ModalEntradaVozTexto, ModalPinDocente
from ui.panel_docente import PanelDocente
from ui.reto_colores_modal import ModalRetoColores
from ui.theme import ORDEN_TEMAS, TEMAS, obtener_tema


def _decorar_paso_con_emojis(texto: str) -> str:
    """Añade íconos visuales amigables según el material mencionado en el paso (como en el mockup)."""
    low = (texto or "").lower()
    iconos = []
    if "cuaderno" in low or "libro" in low:
        iconos.append("📓")
    if "lápiz" in low or "lapiz" in low or "escribe" in low:
        iconos.append("✏️")
    if "borrador" in low:
        iconos.append("🧽")
    if "suma" in low or "número" in low or "unidades" in low:
        iconos.append("🔢")
    if "color" in low or "dibuja" in low:
        iconos.append("🎨")
    if "mochila" in low:
        iconos.append("🎒")
    if not iconos:
        iconos.append("✨")
    sufijo = " ".join(iconos[:3])
    return f"{texto} {sufijo}"


class VentanaPrincipalHaru(ctk.CTk):
    def __init__(self, silenciar_audio_inicial: bool = False):
        super().__init__()

        # Inicializar servicios centrales desacoplados
        self.bus = BusEventosUI()
        self.db = RepositorioTDAH()
        self.ia = MotorIAHaru(repositorio_db=self.db)
        self.multimodal = GestorMultimodal()

        clave_tema_guardada = self.db.obtener_preferencia("tema_visual", "CALMA").upper()
        if clave_tema_guardada not in TEMAS:
            clave_tema_guardada = "CALMA"
        self.clave_tema = clave_tema_guardada
        self.tema: Dict[str, str] = obtener_tema(self.clave_tema)

        ctk.set_appearance_mode(self.tema["appearance"])

        voz_pref = self.db.obtener_preferencia("voz_tts", VOZ_POR_DEFECTO)
        vel_pref = self.db.obtener_preferencia("velocidad_tts", "+0%")
        self.voz = MotorVozHaru(
            bus_eventos=self.bus,
            voz=voz_pref,
            velocidad=vel_pref,
            silenciado=silenciar_audio_inicial,
        )
        self.voz.forzar_offline = self.ia.modo_privado
        self.stt = EscuchaVozHaru(
            bus_eventos=self.bus,
            forzar_modo_privado=self.ia.modo_privado,
        )

        puerto_com = self.db.obtener_preferencia("puerto_arduino", "COM15")
        self.hardware = ControladorHardwareLEDs(
            puerto_default=puerto_com,
            callback_gui=lambda leds, ev: self.bus.emitir("leds_cambio", leds=leds, evento=ev),
        )

        self.motor = MotorTDAH(
            callback_voz=self.voz.hablar,
            controlador_hardware=self.hardware,
            repositorio_db=self.db,
            motor_ia=self.ia,
            gestor_multimodal=self.multimodal,
            bus_eventos=self.bus,
        )

        # Configurar ventana principal estilo tableta horizontal
        self.title("HARU — Asistente Virtual Educativo para Niños de Primaria con TDAH")
        self.geometry("1180x730")
        self.minsize(1024, 650)
        self.configure(fg_color=self.tema["bg_bezel"])

        self._leds_estado = [False, False, False]
        self._ventana_secundaria: Optional[ctk.CTkToplevel] = None
        self._panel_docente_activo: Optional[PanelDocente] = None
        self._construir_interfaz_tableta()
        self._cargar_catalogo_misiones(seleccionar_primera=True)

        # Restaurar traje preferido del niño
        skin_guardada = self.db.obtener_preferencia("avatar_skin", "ROBOT_KAWAII")
        self._seleccionar_skin(skin_guardada, hablar=False)
        self._vincular_atajos_teclado()

        self._after_cola_id = None
        self.protocol("WM_DELETE_WINDOW", self.cerrar_aplicacion)
        self._after_cola_id = self.after(35, self._procesar_cola_eventos)

        # Saludo inicial cálido tras abrir la ventana
        if not silenciar_audio_inicial:
            self.after(
                450,
                lambda: self.voz.hablar(
                    "¡Hola amiguito! Soy Haru, tu compañero de estudio. ¡Toca Empezar Misión cuando estés listo!"
                ) if self.winfo_exists() else None,
            )

    # =========================================================================
    # CONSTRUCCIÓN DEL TABLERO UNIFICADO ESTILO TABLETA
    # =========================================================================
    def _construir_interfaz_tableta(self) -> None:
        # Marco interior redondeado de la pantalla de tableta
        self.stage = ctk.CTkFrame(
            self,
            fg_color=self.tema["bg_stage"],
            corner_radius=28,
            border_width=2,
            border_color=self.tema["card_border"],
        )
        self.stage.pack(fill="both", expand=True, padx=14, pady=12)

        self.stage.grid_columnconfigure(0, weight=0, minsize=255)
        self.stage.grid_columnconfigure(1, weight=1)
        self.stage.grid_columnconfigure(2, weight=0, minsize=315)
        self.stage.grid_rowconfigure(1, weight=1)

        self._construir_fila_superior()
        self._construir_columna_izquierda()
        self._construir_escenario_central()
        self._construir_columna_derecha()
        self._construir_fila_ia_y_pista()
        self._construir_barra_accion_inferior()

    def _construir_fila_superior(self) -> None:
        header = ctk.CTkFrame(self.stage, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=22, pady=(14, 4))
        header.grid_columnconfigure(1, weight=1)

        # Izquierda: Logo HARU + controles suaves de tema y volumen
        izq = ctk.CTkFrame(header, fg_color="transparent")
        izq.grid(row=0, column=0, sticky="w")

        self.lbl_logo = ctk.CTkLabel(
            izq,
            text="HARU 🌱",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color=self.tema["text_on_stage"],
        )
        self.lbl_logo.pack(side="left", padx=(2, 14))

        self.btn_tema = ctk.CTkButton(
            izq,
            text=self.tema["nombre"],
            width=96,
            height=32,
            corner_radius=16,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=1,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._ciclar_tema,
        )
        self.btn_tema.pack(side="left", padx=4)

        self.btn_audio = ctk.CTkButton(
            izq,
            text="🔊 Voz",
            width=74,
            height=32,
            corner_radius=16,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=1,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._alternar_silencio,
        )
        self.btn_audio.pack(side="left", padx=4)

        # Derecha: Tarjeta de Misión + Puntos + Medalla + Botón Docente/Familia
        der_wrap = ctk.CTkFrame(header, fg_color="transparent")
        der_wrap.grid(row=0, column=2, sticky="e")

        self.card_mision_top = ctk.CTkFrame(
            der_wrap,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=20,
        )
        self.card_mision_top.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            self.card_mision_top,
            text="🚩 Misión:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(side="left", padx=(12, 4), pady=8)

        self.combo_mision = ctk.CTkOptionMenu(
            self.card_mision_top,
            values=["Matemáticas - Sumas Divertidas"],
            width=235,
            height=32,
            corner_radius=12,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._al_elegir_mision_combo,
        )
        self.combo_mision.pack(side="left", padx=4, pady=8)

        self.btn_puntos_medalla = ctk.CTkButton(
            self.card_mision_top,
            text="⭐ 5 Puntos  🏅",
            height=32,
            corner_radius=14,
            fg_color=self.tema["badge_gold_bg"],
            hover_color="#fde68a",
            text_color=self.tema["badge_gold_text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._abrir_album_premios,
        )
        self.btn_puntos_medalla.pack(side="left", padx=(6, 10), pady=8)

        self.btn_docente = ctk.CTkButton(
            der_wrap,
            text="👤 Docente / Familia",
            height=42,
            corner_radius=18,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=1,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._solicitar_acceso_docente,
        )
        self.btn_docente.pack(side="left")

    def _construir_columna_izquierda(self) -> None:
        col_izq = ctk.CTkFrame(self.stage, fg_color="transparent")
        col_izq.grid(row=1, column=0, sticky="nw", padx=(22, 8), pady=4)

        # 1. Tarjeta Reloj Micro-Pomodoro + Botón Descanso
        self.card_reloj = ctk.CTkFrame(
            col_izq,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=24,
            width=235,
        )
        self.card_reloj.pack(fill="x", pady=(4, 12))

        self.marco_digitos = ctk.CTkFrame(
            self.card_reloj,
            fg_color=self.tema["card_inner"],
            corner_radius=16,
        )
        self.marco_digitos.pack(fill="x", padx=14, pady=(12, 8))

        min_ini, seg_ini = divmod(self.motor.tiempo_foco, 60)
        self.lbl_reloj = ctk.CTkLabel(
            self.marco_digitos,
            text=f"{min_ini:02d}:{seg_ini:02d}",
            font=ctk.CTkFont(family="Segoe UI", size=34, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_reloj.pack(side="left", padx=(18, 6), pady=6)

        self.lbl_dot_reloj = ctk.CTkLabel(
            self.marco_digitos,
            text="●",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#f97316",
        )
        self.lbl_dot_reloj.pack(side="right", padx=(0, 18))

        self.btn_descanso = ctk.CTkButton(
            self.card_reloj,
            text=f"Descanso ☕ ({self.motor.max_descansos_por_tarea})",
            fg_color=self.tema["btn_orange"],
            hover_color=self.tema["btn_orange_hover"],
            height=40,
            corner_radius=18,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._accion_descanso,
        )
        self.btn_descanso.pack(fill="x", padx=14, pady=(0, 12))

        # 2. Selector de Personaje Desbloqueable (🤖 | 🐱 | 🐻 | 👑)
        self.card_skins = ctk.CTkFrame(
            col_izq,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=20,
        )
        self.card_skins.pack(fill="x", pady=(0, 10))

        fila_sk = ctk.CTkFrame(self.card_skins, fg_color="transparent")
        fila_sk.pack(padx=6, pady=8)

        self._botones_skin: Dict[str, ctk.CTkButton] = {}
        for clave_sk, (_req, icono, _nom) in REQUISITOS_SKIN.items():
            b = ctk.CTkButton(
                fila_sk,
                text=icono,
                width=48,
                height=44,
                corner_radius=14,
                fg_color=self.tema["card_inner"],
                hover_color=self.tema["btn_stage_pill_hover"],
                text_color=self.tema["text_primary"],
                font=ctk.CTkFont(family="Segoe UI Emoji", size=19),
                command=lambda k=clave_sk: self._seleccionar_skin(k, hablar=True),
            )
            b.pack(side="left", padx=3)
            self._botones_skin[clave_sk] = b

        # 3. Estado emocional de Haru
        self.lbl_estado_haru = ctk.CTkLabel(
            col_izq,
            text="🟢 Haru: Atento y Feliz",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_on_stage"],
        )
        self.lbl_estado_haru.pack(anchor="w", padx=6, pady=(0, 8))

        # 4. Botón de Respiración Consciente Guiada
        self.btn_respirar = ctk.CTkButton(
            col_izq,
            text="🧘 Respirar con Haru",
            fg_color=self.tema["card_bg"],
            hover_color=self.tema["card_inner"],
            text_color=self.tema["text_primary"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=18,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._accion_respirar,
        )
        self.btn_respirar.pack(fill="x", pady=(2, 4))

    def _construir_escenario_central(self) -> None:
        centro = ctk.CTkFrame(self.stage, fg_color="transparent")
        centro.grid(row=1, column=1, sticky="nsew", padx=4, pady=2)
        centro.grid_columnconfigure(0, weight=1)
        centro.grid_rowconfigure(0, weight=1)

        self.escenario_haru = EscenarioCentralHaru(
            centro,
            tema=self.tema,
            on_click_haru=self._al_tocar_haru,
        )
        self.escenario_haru.grid(row=0, column=0, sticky="nsew")

        # Subtítulos Karaoke justo debajo de Haru
        self.karaoke = SubtitulosKaraoke(centro, tema=self.tema)
        self.karaoke.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 6))
        self.karaoke.preparar_texto(
            "¡Hola amiguito! Soy Haru, tu compañero de estudio. ¡Toca Empezar Misión para comenzar!"
        )

    def _construir_columna_derecha(self) -> None:
        col_der = ctk.CTkFrame(self.stage, fg_color="transparent")
        col_der.grid(row=1, column=2, sticky="ne", padx=(8, 22), pady=4)

        # 1. Tarjeta Semáforo Arduino UNO R3 (Inicio / Avance / Meta)
        self.card_semaforo = ctk.CTkFrame(
            col_der,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=22,
            width=295,
        )
        self.card_semaforo.pack(fill="x", pady=(4, 12))

        cab_sem = ctk.CTkFrame(self.card_semaforo, fg_color="transparent")
        cab_sem.pack(fill="x", padx=16, pady=(10, 2))
        self.lbl_tit_semaforo = ctk.CTkLabel(
            cab_sem,
            text="Semáforo",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_tit_semaforo.pack(side="left")
        self.lbl_sub_semaforo = ctk.CTkLabel(
            cab_sem,
            text="⚡ Simulación" if self.hardware.en_simulacion else f"🔌 {self.hardware.puerto_actual}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.tema["text_secondary"],
        )
        self.lbl_sub_semaforo.pack(side="right")

        self.canvas_leds = tk.Canvas(
            self.card_semaforo,
            width=265,
            height=74,
            bg=self.tema["card_bg"],
            bd=0,
            highlightthickness=0,
        )
        self.canvas_leds.pack(padx=12, pady=(0, 8))
        self._dibujar_leds_semaforo()

        # 2. Burbuja Grande de Instrucción del Paso Actual
        self.card_paso = ctk.CTkFrame(
            col_der,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=24,
            width=295,
        )
        self.card_paso.pack(fill="both", expand=True)

        self.lbl_num_paso = ctk.CTkLabel(
            self.card_paso,
            text="📍 Paso 1 de 3",
            fg_color=self.tema["card_inner"],
            text_color=self.tema["text_primary"],
            corner_radius=12,
            padx=12,
            pady=4,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.lbl_num_paso.pack(anchor="w", padx=16, pady=(14, 8))

        self.lbl_texto_paso = ctk.CTkLabel(
            self.card_paso,
            text="Saca tu cuaderno de matemáticas, tu lápiz y tu borrador sobre la mesa. 📓 ✏️ 🧽",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=self.tema["text_primary"],
            wraplength=260,
            justify="left",
            anchor="nw",
        )
        self.lbl_texto_paso.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _construir_fila_ia_y_pista(self) -> None:
        fila_media = ctk.CTkFrame(self.stage, fg_color="transparent")
        fila_media.grid(row=2, column=0, columnspan=3, sticky="ew", padx=22, pady=(2, 6))
        fila_media.grid_columnconfigure(1, weight=1)

        # Izquierda: Pregúntale a Haru IA
        self.marco_input_ia = ctk.CTkFrame(
            fila_media,
            fg_color=self.tema["input_bg"],
            border_color=self.tema["input_border"],
            border_width=2,
            corner_radius=22,
        )
        self.marco_input_ia.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.entry_ia = ctk.CTkEntry(
            self.marco_input_ia,
            placeholder_text="Pregúntale a Haru IA... 💬",
            width=235,
            height=38,
            border_width=0,
            fg_color="transparent",
            text_color=self.tema["text_primary"],
            font=ctk.CTkFont(size=13),
        )
        self.entry_ia.pack(side="left", padx=(14, 4), pady=3)
        self.entry_ia.bind("<Return>", lambda _e: self._enviar_pregunta_ia())

        self.btn_enviar_ia = ctk.CTkButton(
            self.marco_input_ia,
            text="➤",
            width=38,
            height=34,
            corner_radius=16,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._enviar_pregunta_ia,
        )
        self.btn_enviar_ia.pack(side="right", padx=(2, 6), pady=4)

        # Centro: Burbuja de Pista de Apoyo / Respuesta IA
        self.card_pista = ctk.CTkFrame(
            fila_media,
            fg_color=self.tema["hint_bg"],
            border_color=self.tema["hint_border"],
            border_width=2,
            corner_radius=20,
        )
        self.card_pista.grid(row=0, column=1, sticky="ew", padx=6)

        self.lbl_pista = ctk.CTkLabel(
            self.card_pista,
            text="💡 Pista de apoyo: Busca en tu mochila únicamente el cuaderno de cuadros y un lápiz.",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
            wraplength=470,
            justify="center",
        )
        self.lbl_pista.pack(fill="x", padx=16, pady=9)

        # Derecha: Botón Magenta Reto Colores 📷
        self.btn_reto_colores = ctk.CTkButton(
            fila_media,
            text="Reto Colores 📷",
            fg_color=self.tema["btn_magenta"],
            hover_color=self.tema["btn_magenta_hover"],
            height=44,
            width=185,
            corner_radius=22,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._abrir_reto_colores,
        )
        self.btn_reto_colores.grid(row=0, column=2, sticky="e", padx=(10, 0))

    def _construir_barra_accion_inferior(self) -> None:
        barra = ctk.CTkFrame(self.stage, fg_color="transparent")
        barra.grid(row=3, column=0, columnspan=3, sticky="ew", padx=22, pady=(4, 14))
        barra.grid_columnconfigure(1, weight=1)

        # Controles Izquierdos: Hablar + Anterior
        izq = ctk.CTkFrame(barra, fg_color="transparent")
        izq.grid(row=0, column=0, sticky="w")

        self.btn_hablar = ctk.CTkButton(
            izq,
            text="🎤 Hablar",
            width=112,
            height=46,
            corner_radius=22,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=2,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._accion_hablar_microfono,
        )
        self.btn_hablar.pack(side="left", padx=(0, 8))

        self.btn_anterior = ctk.CTkButton(
            izq,
            text="◀ Anterior",
            width=118,
            height=46,
            corner_radius=22,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=2,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.motor.retroceder_paso,
        )
        self.btn_anterior.pack(side="left")

        # Centro: Gran Botón Principal Verde (¡Empezar Misión! / ¡Paso Listo! (+1 ⭐))
        self.btn_paso_listo = ctk.CTkButton(
            barra,
            text="✔  ¡Empezar Misión!",
            height=58,
            width=330,
            corner_radius=29,
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            border_width=3,
            border_color=self.tema["btn_green_border"],
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            command=self._accion_boton_principal,
        )
        self.btn_paso_listo.grid(row=0, column=1)

        # Controles Derechos: Pista Mágica + Repetir + Reiniciar
        der = ctk.CTkFrame(barra, fg_color="transparent")
        der.grid(row=0, column=2, sticky="e")

        self.btn_pista = ctk.CTkButton(
            der,
            text="🪄 Pista Mágica",
            width=136,
            height=46,
            corner_radius=22,
            fg_color=self.tema["btn_purple"],
            hover_color=self.tema["btn_purple_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.motor.dar_pista_async,
        )
        self.btn_pista.pack(side="left", padx=4)

        self.btn_repetir = ctk.CTkButton(
            der,
            text="🔄 Repetir",
            width=106,
            height=46,
            corner_radius=22,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=2,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.motor.repetir_paso,
        )
        self.btn_repetir.pack(side="left", padx=4)

        self.btn_reiniciar = ctk.CTkButton(
            der,
            text="↺ Reiniciar",
            width=106,
            height=46,
            corner_radius=22,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=2,
            border_color=self.tema["btn_stage_border"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.motor.reiniciar,
        )
        self.btn_reiniciar.pack(side="left", padx=(4, 0))

    # =========================================================================
    # SEMÁFORO DE 3 LEDs ARDUINO UNO R3 (INICIO, AVANCE, META)
    # =========================================================================
    def _dibujar_leds_semaforo(self) -> None:
        self.canvas_leds.delete("all")
        self.canvas_leds.configure(bg=self.tema["card_bg"])
        definiciones = [
            (52, "Inicio", "#22c55e", "#bbf7d0", "#cbd5e1"),
            (132, "Avance", "#eab308", "#fef08a", "#cbd5e1"),
            (212, "Meta", "#ef4444", "#fecaca", "#cbd5e1"),
        ]
        for idx, (cx, etiqueta, col_on, halo_on, col_off) in enumerate(definiciones):
            encendido = self._leds_estado[idx] if idx < len(self._leds_estado) else False
            if encendido:
                self.canvas_leds.create_oval(cx - 23, 6, cx + 23, 52, fill=halo_on, outline="")
                self.canvas_leds.create_oval(cx - 17, 12, cx + 17, 46, fill=col_on, outline="#ffffff", width=2)
                self.canvas_leds.create_oval(cx - 9, 16, cx - 1, 24, fill="#ffffff", outline="")
            else:
                self.canvas_leds.create_oval(cx - 17, 12, cx + 17, 46, fill=col_off, outline="#94a3b8", width=2)
            self.canvas_leds.create_text(
                cx, 62,
                text=etiqueta,
                fill=self.tema["text_secondary"],
                font=("Segoe UI", 10, "bold"),
            )

    # =========================================================================
    # ACCIONES INTERACTIVAS DEL NIÑO Y DEL DOCENTE
    # =========================================================================
    def _accion_boton_principal(self) -> None:
        if self.motor.estado == MotorTDAH.ESTADO_IDLE:
            self.motor.iniciar_tarea()
        elif self.motor.estado == MotorTDAH.ESTADO_COMPLETADA:
            self._avanzar_siguiente_mision()
        elif self.motor.estado == MotorTDAH.ESTADO_PAUSA_ACTIVA:
            self.motor.reanudar_desde_pausa_activa()
            self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
        else:
            self.motor.avanzar_paso()

    def _avanzar_siguiente_mision(self) -> None:
        """Pasa suavemente a la siguiente misión del catálogo sin repetir siempre la misma."""
        nombres = list(getattr(self, "_mapa_tareas", {}).keys())
        if not nombres:
            self.motor.reiniciar()
            return
        idx_actual = nombres.index(self.motor.tarea_actual) if self.motor.tarea_actual in nombres else -1
        siguiente_nombre = nombres[(idx_actual + 1) % len(nombres)]
        datos = self._mapa_tareas[siguiente_nombre]
        self.voz.detener()
        self.motor.cargar_tarea(datos["nombre"], datos["pasos"], datos["pistas"])
        self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_SALUDANDO)
        msg = f"¡Nueva misión lista: {datos['nombre']}! Toca Empezar Misión cuando quieras comenzar, o sigamos charlando."
        self.voz.hablar(msg)
        self._aplicar_snapshot_motor(self.motor.obtener_snapshot_ui())

    def _accion_descanso(self) -> None:
        estaba_pausado = self.motor.reloj_en_pausa_manual or self.motor.estado == MotorTDAH.ESTADO_PAUSA_ACTIVA
        pausado, _ = self.motor.solicitar_descanso_alumno()
        if pausado:
            self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_PAUSA)
            self.lbl_estado_haru.configure(text="☕ Haru: Descansando contigo")
        elif estaba_pausado and self.motor.estado == MotorTDAH.ESTADO_EN_PASO:
            self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
            self.lbl_estado_haru.configure(text="🟢 Haru: Atento y Feliz")

    def _accion_respirar(self) -> None:
        self.escenario_haru.iniciar_respiracion_guiada(16.0)
        self.lbl_estado_haru.configure(text="🧘 Haru: Respirando en calma")
        self.voz.hablar(
            "Vamos a respirar juntos. Inhala profundo por la nariz como oliendo una flor... "
            "y ahora sopla despacito como apagando una velita. ¡Qué tranquilidad!"
        )

    def _al_tocar_haru(self) -> None:
        self.multimodal.reproducir_sonido_paso()
        self.voz.hablar("¡Jajaja, eso me dio cosquillas! ¡Vamos súper bien con nuestra misión!")

    @staticmethod
    def _ventana_viva(ventana: Optional[tk.Misc]) -> bool:
        try:
            return bool(ventana is not None and ventana.winfo_exists())
        except Exception:
            return False

    def _enfocar_si_abierta(self, ventana: Optional[tk.Toplevel]) -> bool:
        if self._ventana_viva(ventana):
            try:
                ventana.lift()
                ventana.focus_force()
            except Exception:
                pass
            return True
        return False

    def _vincular_atajos_teclado(self) -> None:
        """Atajos accesibles que no interfieren con cajas de texto ni ventanas modales/docente."""
        def _atajos_bloqueados() -> bool:
            if self._ventana_viva(self._ventana_secundaria) or self._ventana_viva(self._panel_docente_activo):
                return True
            foco = self.focus_get()
            if foco is None:
                return False
            try:
                if foco.winfo_toplevel() is not self:
                    return True
            except Exception:
                return True
            return foco.winfo_class() in ("Entry", "Text", "TEntry")

        def _al_espacio(_e):
            if not _atajos_bloqueados():
                self._accion_boton_principal()

        def _al_pista(_e):
            if not _atajos_bloqueados():
                self.motor.dar_pista_async()

        def _al_repetir(_e):
            if not _atajos_bloqueados():
                self.motor.repetir_paso()

        self.bind("<space>", _al_espacio)
        self.bind("<KeyPress-p>", _al_pista)
        self.bind("<KeyPress-P>", _al_pista)
        self.bind("<KeyPress-r>", _al_repetir)
        self.bind("<KeyPress-R>", _al_repetir)
        self.bind("<Escape>", lambda _e: self.voz.detener())
        self.card_pista.bind(
            "<Configure>",
            lambda e: self.lbl_pista.configure(wraplength=max(260, e.width - 36)),
        )
        self.card_paso.bind(
            "<Configure>",
            lambda e: self.lbl_texto_paso.configure(wraplength=max(220, e.width - 34)),
        )

    def _refrescar_botones_skin(self) -> None:
        estrellas = self.motor.estrellas_totales
        activa = self.escenario_haru.skin
        for k, btn in self._botones_skin.items():
            req, icono, _nom = REQUISITOS_SKIN.get(k, (0, "🤖", "Haru"))
            desbl = estrellas >= req
            btn.configure(
                text=icono if desbl else f"{icono}🔒",
                fg_color=self.tema["btn_green"] if k == activa else self.tema["card_inner"],
                text_color="#ffffff" if k == activa else self.tema["text_primary"],
            )

    def _seleccionar_skin(self, clave_skin: str, hablar: bool = False) -> None:
        if clave_skin not in REQUISITOS_SKIN:
            clave_skin = "ROBOT_KAWAII"
        req, _icono, nombre = REQUISITOS_SKIN[clave_skin]
        if self.motor.estrellas_totales < req:
            if not hablar:
                clave_skin = "ROBOT_KAWAII"
            else:
                faltan = req - self.motor.estrellas_totales
                msg = f"¡Te faltan {faltan} estrellitas para desbloquear a {nombre}! ¡Completa tus pasos para ganarlo!"
                self.lbl_pista.configure(text=f"🔒 {msg}")
                self.voz.hablar(msg)
                return

        self.escenario_haru.cambiar_skin(clave_skin)
        self.db.guardar_preferencia("avatar_skin", clave_skin)
        self._refrescar_botones_skin()
        if hablar:
            frases = {
                "ROBOT_KAWAII": "¡Traje de Robotito Celeste activado!",
                "GATITO_ESPACIAL": "¡Miau! ¡Traje de Gatito Espacial listo!",
                "OSITO_TUTOR": "¡Qué tierno! ¡Traje de Osito Tutor activado!",
                "SUPER_HARU_DORADO": "¡Increíble! ¡Súper Haru Dorado con corona activado!",
            }
            self.voz.hablar(frases.get(clave_skin, f"¡Traje de {nombre} listo!"))

    def _enviar_pregunta_ia(self) -> None:
        pregunta = self.entry_ia.get().strip()[:360]
        if not pregunta:
            return
        self.entry_ia.delete(0, "end")
        self.motor.consultar_ia_async(pregunta)

    def _accion_hablar_microfono(self) -> None:
        self.voz.detener()
        self.stt.escuchar_en_hilo()

    def _procesar_comando_hablado(self, texto: str) -> None:
        low = texto.lower().strip()
        palabras = low.split()
        es_comando_corto = len(palabras) <= 5 and "?" not in low and "¿" not in low

        if es_comando_corto and any(
            frase in low for frase in ("paso listo", "siguiente paso", "empezar misión", "empezar mision", "siguiente misión", "siguiente mision")
        ):
            self._accion_boton_principal()
        elif es_comando_corto and low in ("listo", "siguiente", "empezar", "ya está", "ya esta"):
            self._accion_boton_principal()
        elif es_comando_corto and ("pista" in low or low in ("ayuda", "ayúdame", "ayudame")):
            self.motor.dar_pista_async()
        elif es_comando_corto and ("repite" in low or "repetir" in low):
            self.motor.repetir_paso()
        elif es_comando_corto and ("descanso" in low or "pausa" in low):
            self._accion_descanso()
        elif es_comando_corto and ("respirar" in low or "calma" in low):
            self._accion_respirar()
        else:
            self.motor.consultar_ia_async(texto)

    def _abrir_reto_colores(self) -> None:
        if self._enfocar_si_abierta(self._ventana_secundaria):
            return
        self.voz.hablar("¡Hora del reto de colores! Muéstrame un objeto amarillo, rojo, azul o verde.")

        def _dar_premio(color_encontrado: str):
            self.motor._otorgar_estrellas(2)
            self.multimodal.reproducir_sonido_victoria()
            self.escenario_haru.disparar_reaccion(EscenarioCentralHaru.ESTADO_PASO_LOGRADO, 3.0)
            self.voz.hablar(f"¡Bravísimo! Encontraste el color {color_encontrado.lower()} y ganaste dos estrellas extra.")
            self._aplicar_snapshot_motor(self.motor.obtener_snapshot_ui())

        self._ventana_secundaria = ModalRetoColores(self, tema=self.tema, on_premio=_dar_premio)

    def _abrir_album_premios(self) -> None:
        if self._enfocar_si_abierta(self._ventana_secundaria):
            return
        resumen = self.db.obtener_estadisticas_resumen()

        def _al_canjear(mensaje_canje: str, _nuevo_saldo: int):
            self.multimodal.reproducir_sonido_victoria()
            self.escenario_haru.disparar_reaccion(EscenarioCentralHaru.ESTADO_PASO_LOGRADO, 2.8)
            self.lbl_pista.configure(text=f"🎁 {mensaje_canje}")
            self.voz.hablar(mensaje_canje)
            self._aplicar_snapshot_motor(self.motor.obtener_snapshot_ui())

        self._ventana_secundaria = ModalAlbumPremios(
            self,
            estrellas=resumen["estrellas_totales"],
            tareas_logradas=resumen["tareas_completadas"],
            tema=self.tema,
            repositorio_db=self.db,
            skin_actual=self.escenario_haru.skin,
            on_equipar_skin=lambda sk: self._seleccionar_skin(sk, hablar=True),
            on_premio_canjeado=_al_canjear,
        )

    def _solicitar_acceso_docente(self) -> None:
        if self._enfocar_si_abierta(self._panel_docente_activo) or self._enfocar_si_abierta(self._ventana_secundaria):
            return
        self._ventana_secundaria = ModalPinDocente(
            self,
            repositorio_db=self.db,
            tema=self.tema,
            on_autorizado=self._abrir_panel_docente,
        )

    def _abrir_panel_docente(self) -> None:
        if self._enfocar_si_abierta(self._panel_docente_activo):
            return
        self._panel_docente_activo = PanelDocente(
            self,
            motor_tdah=self.motor,
            repositorio_db=self.db,
            motor_ia=self.ia,
            controlador_hardware=self.hardware,
            motor_voz=self.voz,
            motor_stt=self.stt,
            tema=self.tema,
            callback_recargar=lambda: self._cargar_catalogo_misiones(seleccionar_primera=False),
        )

    @staticmethod
    def _etiqueta_combo_mision(nombre: str) -> str:
        return nombre if len(nombre) <= 34 else (nombre[:32].rstrip() + "…")

    def _cargar_catalogo_misiones(self, seleccionar_primera: bool = False) -> None:
        tareas = self.db.listar_tareas()
        self._mapa_tareas = {t["nombre"]: t for t in tareas}
        self._mapa_combo_etiqueta = {}
        etiquetas = []
        for nombre in self._mapa_tareas:
            etq = self._etiqueta_combo_mision(nombre)
            # Garantizar unicidad si dos títulos muy largos comparten prefijo
            if etq in self._mapa_combo_etiqueta:
                etq = f"{nombre[:29].rstrip()}… ({len(etiquetas) + 1})"
            self._mapa_combo_etiqueta[etq] = nombre
            etiquetas.append(etq)

        if not etiquetas:
            etiquetas = ["Matemáticas - Sumas Divertidas"]
            self._mapa_combo_etiqueta[etiquetas[0]] = etiquetas[0]

        self.combo_mision.configure(values=etiquetas)

        objetivo = self.motor.tarea_actual if self.motor.tarea_actual in self._mapa_tareas else next(iter(self._mapa_tareas), etiquetas[0])
        etq_obj = next((k for k, v in self._mapa_combo_etiqueta.items() if v == objetivo), etiquetas[0])
        self.combo_mision.set(etq_obj)
        if seleccionar_primera and objetivo in self._mapa_tareas:
            datos = self._mapa_tareas[objetivo]
            self.motor.cargar_tarea(datos["nombre"], datos["pasos"], datos["pistas"])

        self._aplicar_snapshot_motor(self.motor.obtener_snapshot_ui())

    def _al_elegir_mision_combo(self, etiqueta_elegida: str) -> None:
        nombre_real = getattr(self, "_mapa_combo_etiqueta", {}).get(etiqueta_elegida, etiqueta_elegida)
        datos = getattr(self, "_mapa_tareas", {}).get(nombre_real)
        if datos:
            self.voz.detener()
            self.motor.cargar_tarea(datos["nombre"], datos["pasos"], datos["pistas"])
            self.karaoke.preparar_texto(
                f"Misión lista: {datos['nombre']}. ¡Presiona Empezar Misión cuando quieras!"
            )

    def _alternar_silencio(self) -> None:
        self.voz.silenciado = not self.voz.silenciado
        if self.voz.silenciado:
            self.voz.detener()
            self.btn_audio.configure(text="🔇 Silencio")
        else:
            self.btn_audio.configure(text="🔊 Voz")

    # =========================================================================
    # CAMBIO DE TEMA COMPLETO (CALMA / DÍA / NOCHE SIN PARCHES BLANCOS)
    # =========================================================================
    def _ciclar_tema(self) -> None:
        idx = (ORDEN_TEMAS.index(self.clave_tema) + 1) % len(ORDEN_TEMAS)
        self.aplicar_tema_por_clave(ORDEN_TEMAS[idx])

    def aplicar_tema_por_clave(self, nueva_clave: str) -> None:
        apariencia_previa = self.tema["appearance"]
        self.clave_tema = nueva_clave if nueva_clave in TEMAS else "CALMA"
        self.tema = obtener_tema(self.clave_tema)
        self.db.guardar_preferencia("tema_visual", self.clave_tema)
        if self.tema["appearance"] != apariencia_previa:
            ctk.set_appearance_mode(self.tema["appearance"])

        t = self.tema
        self.configure(fg_color=t["bg_bezel"])
        self.stage.configure(fg_color=t["bg_stage"], border_color=t["card_border"])
        self.lbl_logo.configure(text_color=t["text_on_stage"])
        self.btn_tema.configure(
            text=t["nombre"],
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
        )
        self.btn_audio.configure(
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
        )

        self.card_mision_top.configure(fg_color=t["card_bg"], border_color=t["card_border"])
        self.combo_mision.configure(fg_color=t["btn_stage_pill"], button_color=t["btn_stage_pill_hover"])
        self.btn_puntos_medalla.configure(fg_color=t["badge_gold_bg"], text_color=t["badge_gold_text"])
        self.btn_docente.configure(
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
        )

        self.card_reloj.configure(fg_color=t["card_bg"], border_color=t["card_border"])
        self.marco_digitos.configure(fg_color=t["card_inner"])
        self.lbl_reloj.configure(text_color=t["text_primary"])
        self.btn_descanso.configure(fg_color=t["btn_orange"], hover_color=t["btn_orange_hover"])

        self.card_skins.configure(fg_color=t["card_bg"], border_color=t["card_border"])
        self._seleccionar_skin(self.escenario_haru.skin, hablar=False)
        self.lbl_estado_haru.configure(text_color=t["text_on_stage"])
        self.btn_respirar.configure(
            fg_color=t["card_bg"],
            hover_color=t["card_inner"],
            text_color=t["text_primary"],
            border_color=t["card_border"],
        )

        self.escenario_haru.aplicar_tema(t)
        self.karaoke.aplicar_tema(t)

        self.card_semaforo.configure(fg_color=t["card_bg"], border_color=t["card_border"])
        self.lbl_tit_semaforo.configure(text_color=t["text_primary"])
        self.lbl_sub_semaforo.configure(text_color=t["text_secondary"])
        self._dibujar_leds_semaforo()

        self.card_paso.configure(fg_color=t["card_bg"], border_color=t["card_border"])
        self.lbl_num_paso.configure(fg_color=t["card_inner"], text_color=t["text_primary"])
        self.lbl_texto_paso.configure(text_color=t["text_primary"])

        self.marco_input_ia.configure(fg_color=t["input_bg"], border_color=t["input_border"])
        self.entry_ia.configure(text_color=t["text_primary"])
        self.btn_enviar_ia.configure(fg_color=t["btn_stage_pill"], hover_color=t["btn_stage_pill_hover"])

        self.card_pista.configure(fg_color=t["hint_bg"], border_color=t["hint_border"])
        self.lbl_pista.configure(text_color=t["text_primary"])
        self.btn_reto_colores.configure(fg_color=t["btn_magenta"], hover_color=t["btn_magenta_hover"])

        for btn_sec in (self.btn_hablar, self.btn_anterior, self.btn_repetir, self.btn_reiniciar):
            btn_sec.configure(
                fg_color=t["btn_stage_pill"],
                hover_color=t["btn_stage_pill_hover"],
                border_color=t["btn_stage_border"],
            )
        self.btn_pista.configure(fg_color=t["btn_purple"], hover_color=t["btn_purple_hover"])
        self.btn_paso_listo.configure(
            fg_color=t["btn_green"],
            hover_color=t["btn_green_hover"],
            border_color=t["btn_green_border"],
        )

    # =========================================================================
    # BUS REACTIVO DE EVENTOS (SINCRONIZACIÓN HILO SEGURO A 35ms)
    # =========================================================================
    def _procesar_cola_eventos(self) -> None:
        if not self.winfo_exists():
            return

        for ev in self.bus.extraer_pendientes(max_items=50):
            tipo = ev.tipo
            d = ev.datos

            if tipo == "motor_ui":
                self._aplicar_snapshot_motor(d["snapshot"])

            elif tipo == "leds_cambio":
                self._leds_estado = list(d.get("leds", [False, False, False]))
                self.lbl_sub_semaforo.configure(
                    text="⚡ Simulación" if self.hardware.en_simulacion else f"🔌 {self.hardware.puerto_actual}"
                )
                self._dibujar_leds_semaforo()

            elif tipo == "avatar_reaccion":
                self.escenario_haru.disparar_reaccion(
                    d.get("reaccion", EscenarioCentralHaru.ESTADO_SALUDANDO),
                    float(d.get("duracion", 2.2)),
                )

            elif tipo == "logro_desbloqueado":
                self.multimodal.reproducir_sonido_victoria()
                self.escenario_haru.mostrar_banner_logro(d.get("titulo", "🏆 ¡Nuevo logro!"), 4.6)
                self._refrescar_botones_skin()

            elif tipo == "tts_inicio":
                self.karaoke.preparar_texto(d.get("texto", ""), modo_voz=d.get("modo", "neuronal"))
                self.escenario_haru.actualizar_habla(True, boca=0)
                if self.motor.estado != MotorTDAH.ESTADO_COMPLETADA and self.escenario_haru.estado != EscenarioCentralHaru.ESTADO_RESPIRANDO:
                    self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_HABLANDO, boca=0)
                self.lbl_estado_haru.configure(text="🎙️ Haru: Hablando contigo...")

            elif tipo == "tts_palabra":
                self.karaoke.resaltar_palabra(d.get("indice", 0), palabra=d.get("palabra", ""))
                self.escenario_haru.actualizar_habla(True, boca=d.get("boca", 1))

            elif tipo == "tts_boca":
                self.escenario_haru.actualizar_habla(True, boca=d.get("boca", 0))

            elif tipo == "tts_fin":
                self.karaoke.finalizar_frase()
                self.escenario_haru.actualizar_habla(False, boca=0)
                if self.motor.estado == MotorTDAH.ESTADO_COMPLETADA:
                    # Tras terminar de felicitar, Haru queda en reposo sereno (Modo Compañero)
                    self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
                    self.lbl_estado_haru.configure(text="💬 Haru: Modo Compañero (¡Hablemos!)")
                elif self.motor.reloj_en_pausa_manual or self.motor.estado == MotorTDAH.ESTADO_PAUSA_ACTIVA:
                    self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_PAUSA)
                    self.lbl_estado_haru.configure(text="☕ Haru: Descansando contigo")
                elif self.escenario_haru.estado != EscenarioCentralHaru.ESTADO_RESPIRANDO:
                    self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
                    self.lbl_estado_haru.configure(text="🟢 Haru: Atento y Feliz")

            elif tipo == "ia_pensando":
                self.btn_enviar_ia.configure(state="disabled", text="⏳")
                self.btn_pista.configure(state="disabled", text="⏳ Pensando...")
                self.lbl_pista.configure(text=f"✨ {d.get('mensaje', 'Pensando...')}")
                self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_PENSANDO)
                self.lbl_estado_haru.configure(text="🤔 Haru: Pensando tu respuesta...")

            elif tipo == "ia_respuesta":
                self.btn_enviar_ia.configure(state="normal", text="➤")
                self.btn_pista.configure(state="normal", text="🪄 Pista Mágica")
                self.lbl_pista.configure(text=f"🤖 Haru IA: {d.get('respuesta', '')}")

            elif tipo == "ia_pista_lista":
                self.btn_enviar_ia.configure(state="normal", text="➤")
                self.btn_pista.configure(state="normal", text="🪄 Pista Mágica")
                self.lbl_pista.configure(text=f"💡 {d.get('pista', '')}")

            elif tipo == "stt_inicio":
                self.btn_hablar.configure(text="🎙️ Escuchando...", fg_color="#dc2626")
                self.escenario_haru.actualizar_nivel_mic(0.0)
                self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_ESCUCHANDO)
                self.lbl_estado_haru.configure(text="👂 Haru: Te estoy escuchando...")

            elif tipo == "stt_nivel":
                nivel = float(d.get("nivel", 0.0))
                self.escenario_haru.actualizar_nivel_mic(nivel)
                barras = "▂▄▆█"[: max(1, min(4, int(nivel * 5) + 1))]
                self.btn_hablar.configure(text=f"🎙️ {barras}")

            elif tipo == "stt_procesando":
                self.btn_hablar.configure(text="⏳ Pensando...", fg_color=self.tema["btn_orange"])
                self.escenario_haru.actualizar_nivel_mic(0.0)
                self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_PENSANDO)
                self.lbl_estado_haru.configure(text="🤔 Haru: Entendiendo tu voz...")

            elif tipo == "stt_resultado":
                self.btn_hablar.configure(text="🎤 Hablar", fg_color=self.tema["btn_stage_pill"])
                self.escenario_haru.actualizar_nivel_mic(0.0)
                self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
                texto_voz = d.get("texto", "")
                if texto_voz:
                    self._procesar_comando_hablado(texto_voz)

            elif tipo == "stt_vacio":
                self.btn_hablar.configure(text="🎤 Hablar", fg_color=self.tema["btn_stage_pill"])
                self.escenario_haru.actualizar_nivel_mic(0.0)
                self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
                self.lbl_pista.configure(text=f"🎤 {d.get('mensaje', '')}")

            elif tipo == "stt_fallback_texto":
                self.btn_hablar.configure(text="🎤 Hablar", fg_color=self.tema["btn_stage_pill"])
                self.escenario_haru.actualizar_nivel_mic(0.0)
                self.escenario_haru.actualizar_estado(EscenarioCentralHaru.ESTADO_IDLE)
                if not self._enfocar_si_abierta(self._ventana_secundaria):
                    self._ventana_secundaria = ModalEntradaVozTexto(
                        self,
                        motivo=d.get("motivo", ""),
                        tema=self.tema,
                        on_enviar=self._procesar_comando_hablado,
                    )

        self._after_cola_id = self.after(35, self._procesar_cola_eventos)

    def _aplicar_snapshot_motor(self, snap: Dict) -> None:
        estado = snap["estado"]
        min_r = snap["minutos"]
        seg_r = snap["segundos"]
        self.lbl_reloj.configure(text=f"{min_r:02d}:{seg_r:02d}")

        if snap["reloj_pausado"] or estado == MotorTDAH.ESTADO_PAUSA_ACTIVA:
            self.lbl_dot_reloj.configure(text_color="#f59e0b")
            self.btn_descanso.configure(text="▶ Reanudar Estudio")
        else:
            self.lbl_dot_reloj.configure(text_color="#22c55e" if estado == MotorTDAH.ESTADO_EN_PASO else "#f97316")
            self.btn_descanso.configure(text=f"Descanso ☕ ({snap['descansos_disponibles']})")

        self.btn_puntos_medalla.configure(text=f"⭐ {snap['estrellas_totales']} Puntos  🏅")
        self._refrescar_botones_skin()

        mapa_etq = getattr(self, "_mapa_combo_etiqueta", {})
        etq_actual = next((k for k, v in mapa_etq.items() if v == snap["tarea"]), self._etiqueta_combo_mision(snap["tarea"]))
        if self.combo_mision.get() != etq_actual:
            self.combo_mision.set(etq_actual)

        completada = estado == MotorTDAH.ESTADO_COMPLETADA
        self.escenario_haru.actualizar_progreso_camino(
            paso_actual=snap["paso_actual"],
            total_pasos=snap["total_pasos"],
            completada=completada,
        )

        if estado == MotorTDAH.ESTADO_IDLE:
            self.lbl_num_paso.configure(text=f"🎯 Lista • {snap['total_pasos']} pasos")
            paso_ini = snap["pasos_lista"][0] if snap["pasos_lista"] else snap["texto_paso"]
            self.lbl_texto_paso.configure(text=_decorar_paso_con_emojis(paso_ini))
            self.lbl_pista.configure(text=f"💡 Pista de apoyo: {snap['pista_paso']}")
            self.btn_paso_listo.configure(text="✔  ¡Empezar Misión!")
        elif estado == MotorTDAH.ESTADO_COMPLETADA:
            self.lbl_num_paso.configure(text="🏆 ¡Misión Superada! • Modo Compañero")
            self.lbl_texto_paso.configure(
                text=(
                    f"¡Felicitaciones! Ganaste +{snap['estrellas_sesion']} ⭐ hoy. 🎉\n"
                    f"Ahora estoy en reposo contigo: pregúntame lo que quieras, canjea premios o pasa a otra misión."
                )
            )
            if not self.lbl_pista.cget("text").startswith(("🤖", "🎁")):
                self.lbl_pista.configure(
                    text="💬 Modo Compañero libre: háblame con 🎤 o escríbeme sobre tareas, curiosidades o cómo te sientes."
                )
            self.btn_paso_listo.configure(text="🚀  ¡Siguiente Misión!")
        elif estado == MotorTDAH.ESTADO_PAUSA_ACTIVA:
            self.lbl_num_paso.configure(text="🧘 Pausa Activa Saludable")
            self.lbl_texto_paso.configure(
                text="¡Momento de estirar los brazos, tomar agüita o jugar al Reto de Colores! 💧 🌈"
            )
            self.btn_paso_listo.configure(text="▶  ¡Listo, Volver al Paso!")
        else:
            self.lbl_num_paso.configure(text=f"📍 Paso {snap['paso_actual']} de {snap['total_pasos']}")
            self.lbl_texto_paso.configure(text=_decorar_paso_con_emojis(snap["texto_paso"]))
            if snap["pista_paso"] and not self.lbl_pista.cget("text").startswith("🤖"):
                self.lbl_pista.configure(text=f"💡 Pista de apoyo: {snap['pista_paso']}")
            txt_btn = "✔  Siguiente Paso" if snap.get("paso_ya_premiado") else "✔  ¡Paso Listo! (+1 ⭐)"
            self.btn_paso_listo.configure(text=txt_btn)

    def cerrar_aplicacion(self) -> None:
        try:
            self.motor.guardar_sesion_parcial_si_aplica()
            if self._after_cola_id is not None:
                self.after_cancel(self._after_cola_id)
                self._after_cola_id = None
            self.escenario_haru.detener_animacion()
            self.motor.detener_temporizador()
            self.voz.cerrar()
            self.hardware.cerrar()
        except Exception:
            pass
        self.destroy()
