"""
Panel Docente y Familiar Intuitivo en CustomTkinter — Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Proyecto Integrador

Diseñado con navegación lateral clara y distribución espaciosa en 4 módulos:
1. Misiones y Pasos: Constructor visual tarjeta por tarjeta, ingesta asíncrona de documentos con barra de progreso y Descomponedor IA.
2. Progreso y Descansos: KPIs, gráfico visual de foco/pausas, bitácora y exportación CSV/HTML.
3. Voz, Reloj e IA: Selector de voces neuronales (Bolivia/Latam), Pomodoro, recordatorio de inactividad configurable, Comprobación Activa, Ollama Local con LED/selector, Modo Privado y Gemini.
4. Seguridad y Perfil: Cambio de PIN cifrado (PBKDF2), Perfil Pedagógico del Estudiante, Semáforo Visual y marco legal.
"""

import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from core.archivos_estudio import cargar_archivo_estudio
from core.config import VOCES_DISPONIBLES
from ui.iconos import aplicar_icono_ventana_haru, icono_ctk
from ui.modales import ModalAprobadorTareasDocumento


class PanelDocente(ctk.CTkToplevel):
    def __init__(self, parent, motor_tdah, repositorio_db=None, motor_ia=None,
                 controlador_hardware=None, motor_voz=None, motor_stt=None,
                 tema: Optional[Dict[str, str]] = None,
                 callback_recargar: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        aplicar_icono_ventana_haru(self)
        self.motor = motor_tdah
        self.db = repositorio_db or getattr(motor_tdah, "db", None)
        self.ia = motor_ia or getattr(motor_tdah, "ia", None)
        self.hardware = controlador_hardware or getattr(motor_tdah, "hardware", None)
        self.voz = motor_voz
        self.stt = motor_stt
        self.callback_recargar = callback_recargar

        from ui.theme import TEMAS
        self.tema = tema or TEMAS["CALMA"]

        self.title("Panel Docente y Familiar — Gestión Pedagógica Haru (TDAH)")
        self.geometry("1160x720")
        self.minsize(980, 620)
        self.configure(fg_color=self.tema["bg_stage"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.cerrar_panel)

        self.tareas_cache: Dict[str, Dict] = {}
        self._pasos_borrador: List[Dict[str, str]] = []
        self._seccion_activa = ""
        self.modulo_activo = "Todos"
        self._botones_modulo: Dict[str, ctk.CTkButton] = {}
        self._botones_nav: Dict[str, ctk.CTkButton] = {}
        self._status_toast_after = None
        self._procesando_doc_activo: bool = False
        self._progreso_doc_actual: float = 0.0
        self._ultimo_pulso_doc_ts: float = 0.0
        self._cola_progreso_doc: queue.SimpleQueue = queue.SimpleQueue()
        self._after_progreso_doc_id = None
        self._after_ocultar_progreso_id = None
        self._after_ollama_poll_id = None

        self._recargar_cache_tareas()
        self._construir_estructura_principal()
        self.mostrar_seccion("misiones")

        self._after_foco_id = self.after(160, self._fijar_foco_windows)

    def _fijar_foco_windows(self) -> None:
        self._after_foco_id = None
        if not self.winfo_exists():
            return
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _recargar_cache_tareas(self) -> None:
        self.tareas_cache = {}
        if self.db:
            for t in self.db.listar_tareas():
                self.tareas_cache[t["nombre"]] = t

    # =========================================================================
    # ESTRUCTURA GENERAL (SIDEBAR + ÁREA DE CONTENIDO)
    # =========================================================================
    def _construir_estructura_principal(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=228)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Barra Lateral Izquierda ---
        self.sidebar = ctk.CTkFrame(
            self,
            width=228,
            fg_color=self.tema["bg_bezel"],
            corner_radius=0,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="  Docente y Familia",
            image=icono_ctk("user", "#ffffff", 20),
            compound="left",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#ffffff",
        ).pack(anchor="w", padx=18, pady=(22, 2))

        ctk.CTkLabel(
            self.sidebar,
            text="Gestión Pedagógica TDAH",
            font=ctk.CTkFont(size=12),
            text_color=self.tema["text_muted_stage"],
        ).pack(anchor="w", padx=20, pady=(0, 16))

        # Tarjeta rápida de estado del alumno
        resumen = self.db.obtener_estadisticas_resumen() if self.db else {"estrellas_totales": 5, "tareas_completadas": 0}
        card_mini = ctk.CTkFrame(
            self.sidebar,
            fg_color=self.tema["bg_stage"],
            corner_radius=16,
        )
        card_mini.pack(fill="x", padx=16, pady=(0, 18))
        self.lbl_resumen_lateral = ctk.CTkLabel(
            card_mini,
            text=f"  {resumen['estrellas_totales']} Puntos  •  {resumen['tareas_completadas']} Misiones",
            image=icono_ctk("star", "#fde047", 15),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff",
            pady=10,
        )
        self.lbl_resumen_lateral.pack()

        secciones = [
            ("misiones", "clipboard", "  1. Misiones y Pasos"),
            ("progreso", "chart", "  2. Progreso y Descansos"),
            ("voz_ia", "mic", "  3. Voz, Reloj e IA"),
            ("seguridad", "shield", "  4. Seguridad y Perfil"),
        ]
        for clave, ico_nav, titulo in secciones:
            btn = ctk.CTkButton(
                self.sidebar,
                text=titulo,
                image=icono_ctk(ico_nav, "#ffffff", 18),
                compound="left",
                anchor="w",
                height=46,
                corner_radius=14,
                fg_color="transparent",
                hover_color=self.tema["btn_stage_pill_hover"],
                text_color="#ffffff",
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda c=clave: self.mostrar_seccion(c),
            )
            btn.pack(fill="x", padx=14, pady=5)
            self._botones_nav[clave] = btn

        # Aviso toast en la barra lateral
        self.lbl_toast = ctk.CTkLabel(
            self.sidebar,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fde047",
            wraplength=210,
            justify="left",
        )
        self.lbl_toast.pack(padx=18, pady=14)

        ctk.CTkButton(
            self.sidebar,
            text="Volver al Tablero del Niño",
            image=icono_ctk("arrow_left", "#ffffff", 16),
            compound="left",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            height=42,
            corner_radius=16,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.cerrar_panel,
        ).pack(side="bottom", fill="x", padx=16, pady=20)

        # --- Contenedor Principal Derecho ---
        self.contenedor = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        self.contenedor.grid(row=0, column=1, sticky="nsew", padx=18, pady=16)
        self.contenedor.grid_columnconfigure(0, weight=1)
        self.contenedor.grid_rowconfigure(0, weight=1)

    def notificar(self, texto: str) -> None:
        if not self.winfo_exists():
            return
        self.lbl_toast.configure(text=texto)
        if self._status_toast_after:
            try:
                self.after_cancel(self._status_toast_after)
            except Exception:
                pass
        self._status_toast_after = self.after(4500, lambda: self.lbl_toast.configure(text="") if self.winfo_exists() else None)

    def _actualizar_resumen_lateral(self) -> None:
        if not self.db or not hasattr(self, "lbl_resumen_lateral") or not self.lbl_resumen_lateral.winfo_exists():
            return
        resumen = self.db.obtener_estadisticas_resumen()
        self.lbl_resumen_lateral.configure(
            text=f"  {resumen['estrellas_totales']} Puntos  •  {resumen['tareas_completadas']} Misiones"
        )

    def cerrar_panel(self) -> None:
        if getattr(self, "_after_foco_id", None):
            try:
                self.after_cancel(self._after_foco_id)
            except Exception:
                pass
            self._after_foco_id = None
        if self._status_toast_after:
            try:
                self.after_cancel(self._status_toast_after)
            except Exception:
                pass
            self._status_toast_after = None
        if getattr(self, "_after_progreso_doc_id", None):
            try:
                self.after_cancel(self._after_progreso_doc_id)
            except Exception:
                pass
            self._after_progreso_doc_id = None
        if getattr(self, "_after_ocultar_progreso_id", None):
            try:
                self.after_cancel(self._after_ocultar_progreso_id)
            except Exception:
                pass
            self._after_ocultar_progreso_id = None
        if getattr(self, "_after_ollama_poll_id", None):
            try:
                self.after_cancel(self._after_ollama_poll_id)
            except Exception:
                pass
            self._after_ollama_poll_id = None
        self._procesando_doc_activo = False
        if self.callback_recargar:
            try:
                self.callback_recargar()
            except Exception:
                pass
        if self.winfo_exists():
            self.destroy()

    def mostrar_seccion(self, clave: str) -> None:
        self._actualizar_resumen_lateral()
        self._seccion_activa = clave
        for k, btn in self._botones_nav.items():
            btn.configure(
                fg_color=self.tema["btn_green"] if k == clave else "transparent"
            )

        for widget in self.contenedor.winfo_children():
            widget.destroy()

        if clave == "misiones":
            self._vista_misiones()
        elif clave == "progreso":
            self._vista_progreso()
        elif clave == "voz_ia":
            self._vista_voz_ia()
        elif clave == "seguridad":
            self._vista_seguridad_arduino()

    # =========================================================================
    # SECCIÓN 1: MISIONES ESCOLARES Y CONSTRUCTOR VISUAL DE MICRO-PASOS
    # =========================================================================
    MODULOS_CURRICULARES = ("Matemáticas", "Lenguaje", "Ciencias", "Inglés", "Hábitos y Orden")
    GRADOS_PRIMARIA = (
        "1.° de Primaria",
        "2.° de Primaria",
        "3.° de Primaria",
        "4.° de Primaria",
        "5.° de Primaria",
        "6.° de Primaria",
    )

    def _vista_misiones(self) -> None:
        marco = ctk.CTkFrame(self.contenedor, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="nsew")
        marco.grid_columnconfigure(0, weight=0, minsize=255)
        marco.grid_columnconfigure(1, weight=1)
        marco.grid_rowconfigure(0, weight=0)
        marco.grid_rowconfigure(1, weight=0)
        marco.grid_rowconfigure(2, weight=1)

        # Barra Superior de 5 Módulos Curriculares + Progreso Visual + Subir Archivo/Pensum
        barra_modulos = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=18,
        )
        barra_modulos.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(
            barra_modulos,
            text="  Módulos:",
            image=icono_ctk("folder", self.tema["text_primary"], 16),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(side="left", padx=(12, 6), pady=8)

        self.contenedor_pills_modulos = ctk.CTkFrame(barra_modulos, fg_color="transparent")
        self.contenedor_pills_modulos.pack(side="left", fill="x", expand=True, pady=6)
        self._botones_modulo = {}
        self._refrescar_barra_modulos()

        self.btn_subir_archivo = ctk.CTkButton(
            barra_modulos,
            text="Subir Archivo / Pensum",
            image=icono_ctk("file_text", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_purple"],
            hover_color=self.tema["btn_purple_hover"],
            corner_radius=14,
            height=34,
            width=192,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._accion_subir_archivo_pensum,
        )
        self.btn_subir_archivo.pack(side="right", padx=12, pady=6)

        # Barra de carga visible para procesamiento de archivo / pensum
        self.panel_progreso_doc = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["btn_purple"],
            border_width=2,
            corner_radius=14,
        )
        self.panel_progreso_doc.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        fila_prog_top = ctk.CTkFrame(self.panel_progreso_doc, fg_color="transparent")
        fila_prog_top.pack(fill="x", padx=14, pady=(8, 2))
        self.lbl_progreso_doc = ctk.CTkLabel(
            fila_prog_top,
            text="Procesando documento escolar...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        )
        self.lbl_progreso_doc.pack(side="left", fill="x", expand=True)
        self.lbl_progreso_doc_pct = ctk.CTkLabel(
            fila_prog_top,
            text="0%",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["btn_green"],
        )
        self.lbl_progreso_doc_pct.pack(side="right")
        self.barra_progreso_doc = ctk.CTkProgressBar(
            self.panel_progreso_doc,
            height=12,
            corner_radius=6,
            progress_color=self.tema["btn_green"],
            fg_color=self.tema["card_inner"],
        )
        self.barra_progreso_doc.set(0.0)
        self.barra_progreso_doc.pack(fill="x", padx=14, pady=(2, 10))
        self.panel_progreso_doc.grid_remove()

        # Columna Izquierda: Lista de misiones disponibles
        col_izq = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=20,
        )
        col_izq.grid(row=2, column=0, sticky="nsew", padx=(0, 12))

        self.lbl_titulo_catalogo = ctk.CTkLabel(
            col_izq,
            text="  Catálogo de Misiones",
            image=icono_ctk("clipboard", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_titulo_catalogo.pack(anchor="w", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            col_izq,
            text="Toca un módulo arriba o una misión para editarla:",
            font=ctk.CTkFont(size=12),
            text_color=self.tema["text_secondary"],
        ).pack(anchor="w", padx=16, pady=(0, 8))

        fila_cat_acciones = ctk.CTkFrame(col_izq, fg_color="transparent")
        fila_cat_acciones.pack(fill="x", padx=14, pady=(0, 8))
        fila_cat_acciones.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            fila_cat_acciones,
            text="Nueva Misión",
            image=icono_ctk("plus", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            corner_radius=14,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._preparar_nueva_mision,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        if self.db and hasattr(self.db, "restaurar_misiones_predeterminadas"):
            ctk.CTkButton(
                fila_cat_acciones,
                text="Base",
                image=icono_ctk("refresh", "#ffffff", 14),
                compound="left",
                fg_color=self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_stage_pill_hover"],
                corner_radius=14,
                width=78,
                height=36,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=self._restaurar_misiones_base,
            ).grid(row=0, column=1)

        self.scroll_catalogo = ctk.CTkScrollableFrame(col_izq, fg_color="transparent")
        self.scroll_catalogo.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        # Columna Derecha: Editor visual paso a paso + IA
        col_der = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=20,
        )
        col_der.grid(row=2, column=1, sticky="nsew")
        col_der.grid_columnconfigure(0, weight=1)
        col_der.grid_rowconfigure(2, weight=1)

        # 1. Generador automático con IA + Micrófono Docente en Vivo
        caja_ia = ctk.CTkFrame(
            col_der,
            fg_color=self.tema["hint_bg"],
            border_color=self.tema["hint_border"],
            border_width=1,
            corner_radius=16,
        )
        caja_ia.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        caja_ia.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            caja_ia,
            text="  Generador IA: escribe o dicta con el micrófono un tema y Haru elegirá su módulo automáticamente",
            image=icono_ctk("sparkles", self.tema["btn_purple"], 16),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 4))

        self.entry_tema_ia = ctk.CTkEntry(
            caja_ia,
            placeholder_text="Ej: Sumas llevando / Colors and animals in English / El ciclo del agua...",
            height=36,
            corner_radius=12,
        )
        self.entry_tema_ia.grid(row=1, column=0, sticky="ew", padx=(12, 6), pady=(0, 10))
        self.entry_tema_ia.bind("<Return>", lambda _e: self._generar_pasos_con_ia())

        self.btn_dictar_ia = ctk.CTkButton(
            caja_ia,
            text="Dictar",
            image=icono_ctk("mic", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            corner_radius=12,
            height=36,
            width=96,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._dictar_tema_ia_microfono,
        )
        self.btn_dictar_ia.grid(row=1, column=1, padx=(0, 6), pady=(0, 10))

        self.btn_generar_ia = ctk.CTkButton(
            caja_ia,
            text="Generar Pasos",
            image=icono_ctk("sparkles", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_purple"],
            hover_color=self.tema["btn_purple_hover"],
            corner_radius=12,
            height=36,
            width=148,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generar_pasos_con_ia,
        )
        self.btn_generar_ia.grid(row=1, column=2, padx=(0, 12), pady=(0, 10))

        # 2. Datos básicos (Nombre y Módulo Curricular)
        fila_meta = ctk.CTkFrame(col_der, fg_color="transparent")
        fila_meta.grid(row=1, column=0, sticky="ew", padx=16, pady=4)
        fila_meta.grid_columnconfigure(0, weight=1)

        self.entry_nombre_tarea = ctk.CTkEntry(
            fila_meta,
            placeholder_text="Título de la misión escolar...",
            height=38,
            corner_radius=12,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.entry_nombre_tarea.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.combo_categoria = ctk.CTkOptionMenu(
            fila_meta,
            values=["Matemáticas", "Lenguaje", "Ciencias", "Inglés", "Hábitos y Orden"],
            width=165,
            height=38,
            corner_radius=12,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
            command=lambda mod: self.seleccionar_modulo_curricular(mod, cargar_primera=False),
        )
        self.combo_categoria.grid(row=0, column=1)

        # 3. Lista scrollable de tarjetas de Pasos + Pistas
        self.scroll_pasos = ctk.CTkScrollableFrame(
            col_der,
            fg_color=self.tema["card_inner"],
            corner_radius=16,
            label_text="Micro-Pasos Secuenciales y Pistas de Apoyo",
            label_font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.scroll_pasos.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        self.scroll_pasos.grid_columnconfigure(0, weight=1)

        # 4. Barra de acciones inferiores del editor
        barra_inf = ctk.CTkFrame(col_der, fg_color="transparent")
        barra_inf.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 14))

        ctk.CTkButton(
            barra_inf,
            text="Paso",
            image=icono_ctk("plus", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            corner_radius=14,
            height=38,
            width=98,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._agregar_tarjeta_paso,
        ).pack(side="left")

        ctk.CTkButton(
            barra_inf,
            text="Eliminar",
            image=icono_ctk("trash", "#ffffff", 15),
            compound="left",
            fg_color="#dc2626",
            hover_color="#b91c1c",
            corner_radius=14,
            height=38,
            width=110,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._eliminar_mision_actual,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            barra_inf,
            text="Guardar y Activar",
            image=icono_ctk("check", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            corner_radius=14,
            height=40,
            width=172,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._guardar_mision(activar_en_haru=True),
        ).pack(side="right")

        ctk.CTkButton(
            barra_inf,
            text="Guardar",
            image=icono_ctk("save", "#ffffff", 15),
            compound="left",
            fg_color=self.tema["btn_orange"],
            hover_color=self.tema["btn_orange_hover"],
            corner_radius=14,
            height=40,
            width=108,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._guardar_mision(activar_en_haru=False),
        ).pack(side="right", padx=6)

        self._poblar_lista_catalogo()
        # Cargar en el editor la misión actualmente activa en Haru
        inicial = self.tareas_cache.get(self.motor.tarea_actual) or (
            next(iter(self.tareas_cache.values())) if self.tareas_cache else None
        )
        if inicial:
            self._cargar_mision_en_editor(inicial)
        else:
            self._preparar_nueva_mision()

    def _refrescar_barra_modulos(self) -> None:
        if not hasattr(self, "contenedor_pills_modulos") or not self.contenedor_pills_modulos.winfo_exists():
            return
        for w in self.contenedor_pills_modulos.winfo_children():
            w.destroy()
        self._botones_modulo = {}

        progreso = (
            self.db.obtener_progreso_modulos()
            if (self.db and hasattr(self.db, "obtener_progreso_modulos"))
            else {m: (0, 1) for m in self.MODULOS_CURRICULARES}
        )

        opciones = [("Todos", "Todos")]
        for mod in self.MODULOS_CURRICULARES:
            hechas, total = progreso.get(mod, (0, 0))
            etq_corta = "Hábitos" if mod == "Hábitos y Orden" else mod
            opciones.append((mod, f"{etq_corta} ({hechas}/{total})"))

        for clave_mod, texto_btn in opciones:
            activo = self.modulo_activo == clave_mod
            btn = ctk.CTkButton(
                self.contenedor_pills_modulos,
                text=texto_btn,
                height=30,
                corner_radius=12,
                fg_color=self.tema["btn_green"] if activo else self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_green_hover"] if activo else self.tema["btn_stage_pill_hover"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda m=clave_mod: self.seleccionar_modulo_curricular(m, cargar_primera=True),
            )
            btn.pack(side="left", padx=3)
            self._botones_modulo[clave_mod] = btn

    def seleccionar_modulo_curricular(self, modulo: str, cargar_primera: bool = True) -> None:
        """Filtra el catálogo para mostrar únicamente las tareas del Módulo Curricular elegido."""
        if modulo != "Todos" and self.db and hasattr(self.db, "normalizar_modulo"):
            modulo = self.db.normalizar_modulo(modulo)
        self.modulo_activo = modulo
        if hasattr(self, "combo_categoria") and self.combo_categoria.winfo_exists() and modulo in self.MODULOS_CURRICULARES:
            self.combo_categoria.set(modulo)
        if hasattr(self, "lbl_titulo_catalogo") and self.lbl_titulo_catalogo.winfo_exists():
            sufijo = "" if modulo == "Todos" else f": {modulo}"
            self.lbl_titulo_catalogo.configure(text=f"  Misiones{sufijo}")
        self._poblar_lista_catalogo()
        if cargar_primera and modulo != "Todos":
            tareas_mod = [
                d for d in self.tareas_cache.values()
                if (self.db.normalizar_modulo(d.get("categoria", "")) if self.db else d.get("categoria")) == modulo
            ]
            if tareas_mod:
                self._cargar_mision_en_editor(tareas_mod[0])

    def _poblar_lista_catalogo(self) -> None:
        if not hasattr(self, "scroll_catalogo") or not self.scroll_catalogo.winfo_exists():
            return
        for w in self.scroll_catalogo.winfo_children():
            w.destroy()
        self._recargar_cache_tareas()
        self._refrescar_barra_modulos()

        for nombre, datos in self.tareas_cache.items():
            cat_norm = (
                self.db.normalizar_modulo(datos.get("categoria", ""))
                if (self.db and hasattr(self.db, "normalizar_modulo"))
                else datos.get("categoria", "")
            )
            if self.modulo_activo != "Todos" and cat_norm != self.modulo_activo:
                continue

            es_activa = nombre == self.motor.tarea_actual
            item = ctk.CTkFrame(
                self.scroll_catalogo,
                fg_color=self.tema["card_inner"] if es_activa else self.tema["card_bg"],
                border_color=self.tema["btn_green"] if es_activa else self.tema["card_border"],
                border_width=2 if es_activa else 1,
                corner_radius=14,
            )
            item.pack(fill="x", padx=4, pady=5)

            ctk.CTkLabel(
                item,
                text=f" {nombre}" if es_activa else nombre,
                image=icono_ctk("dot", "#22c55e", 11) if es_activa else None,
                compound="left",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=self.tema["text_primary"],
                wraplength=215,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 2))

            pie = ctk.CTkFrame(item, fg_color="transparent")
            pie.pack(fill="x", padx=10, pady=(0, 8))

            ctk.CTkLabel(
                pie,
                text=f"{cat_norm} • {len(datos['pasos'])} pasos",
                font=ctk.CTkFont(size=11),
                text_color=self.tema["text_secondary"],
            ).pack(side="left")

            ctk.CTkButton(
                pie,
                text="Editar",
                width=62,
                height=26,
                corner_radius=10,
                fg_color=self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_stage_pill_hover"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda d=datos: self._cargar_mision_en_editor(d),
            ).pack(side="right")

    def _preparar_nueva_mision(self) -> None:
        self.entry_nombre_tarea.delete(0, "end")
        cat_inicial = self.modulo_activo if self.modulo_activo in self.MODULOS_CURRICULARES else "Matemáticas"
        self.combo_categoria.set(cat_inicial)
        self._pasos_borrador = [
            {"paso": "Prepara sobre tu mesa solo el cuaderno y lápiz que usarás.", "pista": "Guarda otros objetos para evitar distracciones."},
            {"paso": "Realiza la primera parte del ejercicio con calma.", "pista": "Si tienes dudas, usa la barra de preguntas de Haru IA."},
            {"paso": "Revisa tu respuesta y presiona ¡Paso Listo!", "pista": "¡Excelente esfuerzo! Ya estás en la meta."},
        ]
        self._renderizar_tarjetas_pasos()

    def _cargar_mision_en_editor(self, datos: Dict) -> None:
        self.entry_nombre_tarea.delete(0, "end")
        self.entry_nombre_tarea.insert(0, datos["nombre"])
        cat_norm = (
            self.db.normalizar_modulo(datos.get("categoria", "Matemáticas"))
            if (self.db and hasattr(self.db, "normalizar_modulo"))
            else datos.get("categoria", "Matemáticas")
        )
        self.combo_categoria.set(cat_norm)
        pasos = datos.get("pasos", [])
        pistas = datos.get("pistas", [])
        self._pasos_borrador = [
            {"paso": p, "pista": pistas[i] if i < len(pistas) else ""}
            for i, p in enumerate(pasos)
        ]
        self._renderizar_tarjetas_pasos()

    def _sincronizar_borrador_desde_widgets(self) -> None:
        nuevos = []
        for item in getattr(self, "_widgets_pasos", []):
            nuevos.append({
                "paso": item["entry_paso"].get().strip(),
                "pista": item["entry_pista"].get().strip(),
            })
        if nuevos:
            self._pasos_borrador = nuevos

    def _renderizar_tarjetas_pasos(self) -> None:
        for w in self.scroll_pasos.winfo_children():
            w.destroy()
        self._widgets_pasos = []

        for idx, datos_p in enumerate(self._pasos_borrador):
            card_p = ctk.CTkFrame(
                self.scroll_pasos,
                fg_color=self.tema["card_bg"],
                border_color=self.tema["card_border"],
                border_width=1,
                corner_radius=14,
            )
            card_p.pack(fill="x", padx=6, pady=5)
            card_p.grid_columnconfigure(1, weight=1)

            cab = ctk.CTkFrame(card_p, fg_color="transparent")
            cab.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(6, 2))

            ctk.CTkLabel(
                cab,
                text=f"Paso {idx + 1}",
                fg_color=self.tema["btn_stage_pill"],
                text_color="#ffffff",
                corner_radius=10,
                padx=10,
                pady=2,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left")

            if len(self._pasos_borrador) > 1:
                ctk.CTkButton(
                    cab, text="✕", width=28, height=24, corner_radius=8,
                    fg_color="#ef4444", hover_color="#dc2626",
                    command=lambda i=idx: self._quitar_paso(i),
                ).pack(side="right", padx=2)
            if idx < len(self._pasos_borrador) - 1:
                ctk.CTkButton(
                    cab, text="↓", width=28, height=24, corner_radius=8,
                    fg_color=self.tema["btn_stage_pill"],
                    command=lambda i=idx: self._mover_paso(i, 1),
                ).pack(side="right", padx=2)
            if idx > 0:
                ctk.CTkButton(
                    cab, text="↑", width=28, height=24, corner_radius=8,
                    fg_color=self.tema["btn_stage_pill"],
                    command=lambda i=idx: self._mover_paso(i, -1),
                ).pack(side="right", padx=2)

            ctk.CTkLabel(
                card_p, text="Instrucción:", font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.tema["text_primary"],
            ).grid(row=1, column=0, sticky="w", padx=(12, 6), pady=3)
            e_paso = ctk.CTkEntry(card_p, height=32, corner_radius=10)
            e_paso.insert(0, datos_p["paso"])
            e_paso.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=3)

            ctk.CTkLabel(
                card_p, text="Pista:", font=ctk.CTkFont(size=12),
                text_color=self.tema["text_secondary"],
            ).grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(2, 8))
            e_pista = ctk.CTkEntry(card_p, height=30, corner_radius=10)
            e_pista.insert(0, datos_p["pista"])
            e_pista.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(2, 8))

            self._widgets_pasos.append({"entry_paso": e_paso, "entry_pista": e_pista})

    def _agregar_tarjeta_paso(self) -> None:
        self._sincronizar_borrador_desde_widgets()
        n = len(self._pasos_borrador) + 1
        self._pasos_borrador.append({
            "paso": f"Escribe aquí la acción concreta del paso {n}.",
            "pista": "Consejo breve para ayudar al niño si se detiene.",
        })
        self._renderizar_tarjetas_pasos()

    def _quitar_paso(self, idx: int) -> None:
        self._sincronizar_borrador_desde_widgets()
        if len(self._pasos_borrador) > 1:
            self._pasos_borrador.pop(idx)
            self._renderizar_tarjetas_pasos()

    def _mover_paso(self, idx: int, delta: int) -> None:
        self._sincronizar_borrador_desde_widgets()
        nuevo = idx + delta
        if 0 <= nuevo < len(self._pasos_borrador):
            self._pasos_borrador[idx], self._pasos_borrador[nuevo] = (
                self._pasos_borrador[nuevo],
                self._pasos_borrador[idx],
            )
            self._renderizar_tarjetas_pasos()

    def _dictar_tema_ia_microfono(self) -> None:
        """Permite al docente dictar por micrófono el tema de la tarea para autogenerar pasos y módulo."""
        if self.voz:
            self.voz.detener()
        if not self.stt:
            self.notificar("El módulo de micrófono no está disponible en esta sesión.")
            return

        def _al_estado(tipo_est: str, msg: str) -> None:
            def _ui_est():
                if not self.winfo_exists() or not hasattr(self, "btn_dictar_ia"):
                    return
                if tipo_est == "escuchando":
                    self.btn_dictar_ia.configure(text="Escuchando...", fg_color="#dc2626")
                    self.notificar("Habla ahora: di el tema de la tarea escolar...")
                elif tipo_est == "procesando":
                    self.btn_dictar_ia.configure(text="Pensando...", fg_color=self.tema["btn_orange"])
                else:
                    self.btn_dictar_ia.configure(text="Dictar", fg_color=self.tema["btn_stage_pill"])
                    self.notificar(msg)

            self.after(0, _ui_est)

        def _al_resultado(texto_dictado: str) -> None:
            def _ui_res():
                if not self.winfo_exists() or not hasattr(self, "btn_dictar_ia"):
                    return
                self.btn_dictar_ia.configure(text="Dictar", fg_color=self.tema["btn_stage_pill"])
                limpio = (texto_dictado or "").strip()
                if limpio:
                    self.entry_tema_ia.delete(0, "end")
                    self.entry_tema_ia.insert(0, limpio)
                    self.entry_nombre_tarea.delete(0, "end")
                    self.entry_nombre_tarea.insert(0, limpio)
                    self._generar_pasos_con_ia()

            self.after(0, _ui_res)

        self.stt.escuchar_en_hilo(callback_resultado=_al_resultado, callback_estado=_al_estado)

    def _generar_pasos_con_ia(self) -> None:
        tema = self.entry_tema_ia.get().strip() or self.entry_nombre_tarea.get().strip()
        if not tema:
            self.notificar("Escribe o dicta con el micrófono un tema para generar los pasos.")
            return
        if not self.ia:
            return

        # Auto-clasificar el módulo curricular según lo que el docente escribió o dictó
        modulo_detectado = (
            self.ia.detectar_modulo_automatico(tema, modulo_preferido=self.combo_categoria.get())
            if hasattr(self.ia, "detectar_modulo_automatico")
            else self.combo_categoria.get()
        )
        self.combo_categoria.set(modulo_detectado)
        self.seleccionar_modulo_curricular(modulo_detectado, cargar_primera=False)

        self.btn_generar_ia.configure(state="disabled", text="Generando...")

        def _worker():
            pasos, pistas = self.ia.descomponer_tarea_ia(tema, modulo_forzado=modulo_detectado)

            def _aplicar():
                if not self.winfo_exists():
                    return
                self.btn_generar_ia.configure(state="normal", text="Generar Pasos")
                if not self.entry_nombre_tarea.get().strip():
                    self.entry_nombre_tarea.insert(0, f"{modulo_detectado} - {tema}")
                self._pasos_borrador = [
                    {"paso": p, "pista": pistas[i] if i < len(pistas) else ""}
                    for i, p in enumerate(pasos)
                ]
                self._renderizar_tarjetas_pasos()
                self.notificar(
                    f"Módulo [{modulo_detectado}] seleccionado automáticamente • {len(pasos)} pasos ({self.ia.ultima_fuente})."
                )

            self.after(0, _aplicar)

        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_progreso_documento(self, fraccion: float, mensaje: str) -> None:
        val = max(0.0, min(1.0, float(fraccion)))
        self._progreso_doc_actual = val
        if not self.winfo_exists():
            return
        if hasattr(self, "panel_progreso_doc") and self.panel_progreso_doc.winfo_exists():
            self.panel_progreso_doc.grid()
        if hasattr(self, "barra_progreso_doc") and self.barra_progreso_doc.winfo_exists():
            self.barra_progreso_doc.set(val)
        if hasattr(self, "lbl_progreso_doc") and self.lbl_progreso_doc.winfo_exists():
            self.lbl_progreso_doc.configure(text=mensaje)
        if hasattr(self, "lbl_progreso_doc_pct") and self.lbl_progreso_doc_pct.winfo_exists():
            self.lbl_progreso_doc_pct.configure(text=f"{int(round(val * 100))}%")

    def _ocultar_progreso_documento(self) -> None:
        if not self.winfo_exists():
            return
        if hasattr(self, "panel_progreso_doc") and self.panel_progreso_doc.winfo_exists():
            self.panel_progreso_doc.grid_remove()
        if hasattr(self, "btn_subir_archivo") and self.btn_subir_archivo.winfo_exists():
            self.btn_subir_archivo.configure(state="normal", text="Subir Archivo / Pensum")

    def _tick_pulso_progreso_doc(self) -> None:
        if not self.winfo_exists():
            self._after_progreso_doc_id = None
            return

        evento_final = None
        while not self._cola_progreso_doc.empty():
            try:
                ev = self._cola_progreso_doc.get_nowait()
            except queue.Empty:
                break
            tipo = ev[0]
            if tipo == "progreso":
                _, frac, msg = ev
                self._ultimo_pulso_doc_ts = time.time()
                self._mostrar_progreso_documento(frac, msg)
            elif tipo == "fin":
                evento_final = ev

        if evento_final is not None:
            self._after_progreso_doc_id = None
            _, doc, tareas_propuestas, error_inesperado, abrir_modal, on_completado = evento_final
            self._finalizar_procesamiento_doc(
                doc,
                tareas_propuestas,
                error_inesperado,
                abrir_modal,
                on_completado,
            )
            return

        if not self._procesando_doc_activo:
            self._after_progreso_doc_id = None
            return

        ahora = time.time()
        if (ahora - self._ultimo_pulso_doc_ts) >= 0.35 and self._progreso_doc_actual < 0.92:
            self._ultimo_pulso_doc_ts = ahora
            nuevo = min(0.92, self._progreso_doc_actual + 0.015)
            msg_actual = "Procesando documento escolar..."
            if hasattr(self, "lbl_progreso_doc") and self.lbl_progreso_doc.winfo_exists():
                msg_actual = self.lbl_progreso_doc.cget("text")
            self._mostrar_progreso_documento(nuevo, msg_actual)
        self._after_progreso_doc_id = self.after(90, self._tick_pulso_progreso_doc)

    def _reportar_progreso_doc_hilo(self, fraccion: float, mensaje: str) -> None:
        """Encola actualizaciones de progreso desde el hilo secundario sin tocar widgets Tk."""
        self._cola_progreso_doc.put(("progreso", fraccion, mensaje))

    def _finalizar_procesamiento_doc(
        self,
        doc,
        tareas_propuestas: List[Dict],
        error_inesperado: str,
        abrir_modal: bool,
        on_completado: Optional[Callable[[List[Dict]], None]],
    ) -> None:
        self._procesando_doc_activo = False
        if hasattr(self, "btn_subir_archivo") and self.btn_subir_archivo.winfo_exists():
            self.btn_subir_archivo.configure(state="normal", text="Subir Archivo / Pensum")

        if error_inesperado:
            self._ocultar_progreso_documento()
            if abrir_modal and self.winfo_exists():
                messagebox.showwarning("Error al procesar archivo", error_inesperado, parent=self)
            if on_completado:
                on_completado([])
            return

        if not doc or not doc.exito:
            self._ocultar_progreso_documento()
            if abrir_modal and self.winfo_exists() and doc:
                messagebox.showwarning("Archivo no legible", doc.mensaje_error, parent=self)
            if on_completado:
                on_completado([])
            return

        msg_fin = (
            f"¡Listo! {len(tareas_propuestas)} tarea(s) listas para revisar."
            if tareas_propuestas
            else "No se detectaron tareas nuevas en el archivo."
        )
        self._mostrar_progreso_documento(1.0, msg_fin)

        if tareas_propuestas:
            mod_principal = tareas_propuestas[0].get("categoria", "Matemáticas")
            self.seleccionar_modulo_curricular(mod_principal, cargar_primera=False)

        if abrir_modal and tareas_propuestas and self.winfo_exists():
            ModalAprobadorTareasDocumento(
                self,
                nombre_archivo=doc.nombre_archivo,
                tareas_propuestas=tareas_propuestas,
                tema=self.tema,
                on_aprobar_lote=self._importar_lote_tareas_documento,
            )
        elif abrir_modal and not tareas_propuestas and self.winfo_exists():
            messagebox.showinfo(
                "Sin tareas detectadas",
                "El documento se leyó, pero no se identificaron actividades escolares claras para importar.",
                parent=self,
            )

        if self.winfo_exists():
            self._after_ocultar_progreso_id = self.after(900, self._ocultar_progreso_documento)
        if on_completado:
            on_completado(tareas_propuestas)

    def _accion_subir_archivo_pensum(self) -> None:
        """Abre el selector de archivos escolares (.pdf, .docx, .txt, .md, .csv) para extraer pensum y tareas."""
        ruta = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar Guía Escolar o Pensum (.pdf, .docx, .txt, .md, .csv)",
            filetypes=[
                ("Documentos Escolares", "*.pdf *.docx *.txt *.md *.csv *.tsv"),
                ("Archivos PDF y Word", "*.pdf *.docx"),
                ("Texto y Listas", "*.txt *.md *.csv *.tsv"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if not ruta:
            return
        self.procesar_archivo_pensum_async(ruta, abrir_modal=True)

    def procesar_archivo_pensum_async(
        self,
        ruta_archivo: str,
        abrir_modal: bool = True,
        on_completado: Optional[Callable[[List[Dict]], None]] = None,
    ) -> None:
        """Procesa un documento escolar en segundo plano mostrando una barra de carga en vivo."""
        if self._procesando_doc_activo:
            self.notificar("Ya se está analizando un documento, espera un momento...")
            return

        if getattr(self, "_after_ocultar_progreso_id", None):
            try:
                self.after_cancel(self._after_ocultar_progreso_id)
            except Exception:
                pass
            self._after_ocultar_progreso_id = None

        while not self._cola_progreso_doc.empty():
            try:
                self._cola_progreso_doc.get_nowait()
            except queue.Empty:
                break

        self._procesando_doc_activo = True
        self._ultimo_pulso_doc_ts = time.time()
        if hasattr(self, "btn_subir_archivo") and self.btn_subir_archivo.winfo_exists():
            self.btn_subir_archivo.configure(state="disabled", text="Analizando...")

        nombre_base = os.path.basename(ruta_archivo)
        self._mostrar_progreso_documento(0.08, f"Leyendo archivo '{nombre_base}'...")
        self._after_progreso_doc_id = self.after(90, self._tick_pulso_progreso_doc)

        pref_mod = self.modulo_activo if self.modulo_activo in self.MODULOS_CURRICULARES else ""

        def _worker():
            doc = None
            tareas_propuestas: List[Dict] = []
            error_inesperado = ""
            try:
                doc = cargar_archivo_estudio(ruta_archivo)
                if doc.exito:
                    self._reportar_progreso_doc_hilo(
                        0.18,
                        f"Documento leído ({doc.nombre_archivo}). Detectando materias y pasos...",
                    )
                    if self.ia and hasattr(self.ia, "extraer_tareas_de_documento"):
                        tareas_propuestas = self.ia.extraer_tareas_de_documento(
                            doc,
                            modulo_defecto=pref_mod,
                            on_progreso=self._reportar_progreso_doc_hilo,
                        )
                    self._reportar_progreso_doc_hilo(0.92, "Guardando resumen curricular en base local...")
                    if self.db and hasattr(self.db, "guardar_pensum_modulo"):
                        modulos_doc = {t.get("categoria", "Matemáticas") for t in tareas_propuestas}
                        if not modulos_doc and self.ia:
                            modulos_doc = {self.ia.detectar_modulo_automatico(doc.texto_completo)}
                        for mod_d in modulos_doc:
                            self.db.guardar_pensum_modulo(mod_d, doc.nombre_archivo, doc.resumen_pensum)
            except Exception as exc:
                error_inesperado = str(exc)

            self._cola_progreso_doc.put(
                ("fin", doc, tareas_propuestas, error_inesperado, abrir_modal, on_completado)
            )

        threading.Thread(target=_worker, daemon=True).start()

    def procesar_archivo_pensum(self, ruta_archivo: str, abrir_modal: bool = True) -> List[Dict]:
        """
        Lee el documento del tutor, guarda el pensum por módulo en SQLite para que Haru
        conozca el currículo del niño, auto-clasifica cada tarea detectada (incluso en
        documentos mixtos) y abre el modal de aprobación.
        """
        doc = cargar_archivo_estudio(ruta_archivo)
        if not doc.exito:
            if abrir_modal and self.winfo_exists():
                messagebox.showwarning("Archivo no legible", doc.mensaje_error, parent=self)
            return []

        pref_mod = self.modulo_activo if self.modulo_activo in self.MODULOS_CURRICULARES else ""
        tareas_propuestas = (
            self.ia.extraer_tareas_de_documento(doc, modulo_defecto=pref_mod)
            if (self.ia and hasattr(self.ia, "extraer_tareas_de_documento"))
            else []
        )

        # Guardar el pensum en SQLite para cada módulo detectado en el documento
        if self.db and hasattr(self.db, "guardar_pensum_modulo"):
            modulos_doc = {t.get("categoria", "Matemáticas") for t in tareas_propuestas}
            if not modulos_doc and self.ia:
                modulos_doc = {self.ia.detectar_modulo_automatico(doc.texto_completo)}
            for mod_d in modulos_doc:
                self.db.guardar_pensum_modulo(mod_d, doc.nombre_archivo, doc.resumen_pensum)

        # Seleccionar automáticamente en el Panel Docente el módulo principal detectado
        if tareas_propuestas:
            mod_principal = tareas_propuestas[0].get("categoria", "Matemáticas")
            self.seleccionar_modulo_curricular(mod_principal, cargar_primera=False)

        if abrir_modal and tareas_propuestas and self.winfo_exists():
            ModalAprobadorTareasDocumento(
                self,
                nombre_archivo=doc.nombre_archivo,
                tareas_propuestas=tareas_propuestas,
                tema=self.tema,
                on_aprobar_lote=self._importar_lote_tareas_documento,
            )
        return tareas_propuestas

    def _importar_lote_tareas_documento(self, lote_aprobado: List[Dict]) -> None:
        if not lote_aprobado or not self.db:
            return
        total = self.db.guardar_lote_tareas(lote_aprobado)
        primera = lote_aprobado[0]
        mod_primero = self.db.normalizar_modulo(primera.get("categoria", "Matemáticas"))
        self.seleccionar_modulo_curricular(mod_primero, cargar_primera=True)
        if self.motor and primera.get("pasos"):
            self.motor.cargar_tarea(
                primera.get("nombre", "Misión del Documento"),
                primera.get("pasos", []),
                primera.get("pistas", []),
            )
        if self.callback_recargar:
            self.callback_recargar()
        modulos_unicos = sorted({self.db.normalizar_modulo(x.get("categoria", "")) for x in lote_aprobado})
        self.notificar(
            f"¡{total} tareas agregadas automáticamente a: {', '.join(modulos_unicos)}!"
        )
        if self.voz and total > 0:
            self.voz.hablar(
                f"¡Listo! Aprendí {total} tareas nuevas de tu documento. "
                f"Dejé preparada la misión {primera.get('nombre', '')} con {len(primera.get('pasos', []))} pasos para empezar."
            )

    def _guardar_mision(self, activar_en_haru: bool = False) -> None:
        self._sincronizar_borrador_desde_widgets()
        nombre = self.entry_nombre_tarea.get().strip()[:100]
        if not nombre:
            messagebox.showwarning("Falta título", "Escribe un título para identificar esta misión escolar.", parent=self)
            return

        pasos = [p["paso"][:220] for p in self._pasos_borrador if p["paso"]]
        pistas = [p["pista"][:220] for p in self._pasos_borrador if p["paso"]]
        if not pasos:
            messagebox.showwarning("Sin pasos", "Agrega al menos un paso concreto para el estudiante.", parent=self)
            return

        # Si el texto del título/pasos pertenece claramente a un módulo (ej. Inglés o Matemáticas),
        # auto-seleccionar su módulo correspondiente
        texto_conjunto = f"{nombre} {' '.join(pasos)}"
        categoria_elegida = self.combo_categoria.get()
        if self.ia and hasattr(self.ia, "detectar_modulo_automatico"):
            modulo_auto = self.ia.detectar_modulo_automatico(texto_conjunto, modulo_preferido=categoria_elegida)
            categoria_elegida = modulo_auto
            self.combo_categoria.set(categoria_elegida)

        if self.db:
            self.db.guardar_tarea(nombre, pasos, pistas, categoria=categoria_elegida)

        self.seleccionar_modulo_curricular(categoria_elegida, cargar_primera=False)
        if self.callback_recargar:
            self.callback_recargar()

        if activar_en_haru:
            self.motor.cargar_tarea(nombre, pasos, pistas)
            if self.callback_recargar:
                self.callback_recargar()
            self.notificar(f"Misión «{nombre}» enviada al módulo [{categoria_elegida}] y activada en Haru.")
        else:
            if self.motor.tarea_actual == nombre and self.motor.estado == self.motor.ESTADO_IDLE:
                self.motor.cargar_tarea(nombre, pasos, pistas)
                if self.callback_recargar:
                    self.callback_recargar()
            self.notificar(f"Misión «{nombre}» guardada en el módulo [{categoria_elegida}].")

    def _restaurar_misiones_base(self) -> None:
        if not self.db or not hasattr(self.db, "restaurar_misiones_predeterminadas"):
            return
        self.db.restaurar_misiones_predeterminadas()
        self.modulo_activo = "Todos"
        self._poblar_lista_catalogo()
        if self.callback_recargar:
            self.callback_recargar()
        self.notificar("Las 5 misiones escolares base por módulo fueron restauradas.")

    def _eliminar_mision_actual(self) -> None:
        nombre = self.entry_nombre_tarea.get().strip()
        if not nombre or not self.db:
            return
        if len(self.db.listar_tareas()) <= 1:
            messagebox.showwarning(
                "Última misión activa",
                "Debe existir al menos una misión en el catálogo para el estudiante.\n"
                "Crea otra misión o usa «Base» antes de eliminar esta.",
                parent=self,
            )
            return
        if not messagebox.askyesno("Confirmar eliminación", f"¿Deseas eliminar la misión «{nombre}»?", parent=self):
            return
        era_activa = self.motor.tarea_actual == nombre
        if self.db.eliminar_tarea(nombre):
            self._poblar_lista_catalogo()
            restantes = self.db.listar_tareas()
            if era_activa and restantes:
                primera = restantes[0]
                self.motor.cargar_tarea(primera["nombre"], primera["pasos"], primera["pistas"])
            if self.callback_recargar:
                self.callback_recargar()
            if restantes:
                self._cargar_mision_en_editor(restantes[0])
            else:
                self._preparar_nueva_mision()
            self.notificar(f"Misión «{nombre}» eliminada.")

    # =========================================================================
    # SECCIÓN 2: SEGUIMIENTO PSICOPEDAGÓGICO, GRÁFICO, ECONOMÍA DE FICHAS Y EXPORTACIÓN
    # =========================================================================
    @staticmethod
    def _fmt_dur(segundos: int) -> str:
        seg = max(0, int(segundos))
        if seg < 60:
            return f"{seg}s"
        m, s = divmod(seg, 60)
        if m < 60:
            return f"{m}m {s:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}m"

    @staticmethod
    def _truncar(texto: str, max_len: int = 44) -> str:
        limpio = " ".join((texto or "").split())
        if len(limpio) <= max_len:
            return limpio
        return limpio[: max_len - 1].rstrip() + "…"

    def _vista_progreso(self) -> None:
        marco = ctk.CTkScrollableFrame(self.contenedor, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="nsew")
        marco.grid_columnconfigure((0, 1, 2, 3), weight=1)

        resumen = self.db.obtener_estadisticas_resumen() if self.db else {
            "tareas_completadas": 0, "total_pasos_logrados": 0,
            "total_segundos_foco": 0, "total_pausas_alumno": 0,
            "promedio_cada_cuanto_descansa_seg": 0, "estrellas_totales": 5,
            "estrellas_disponibles": 5, "total_canjes": 0,
        }

        prom_desc = int(resumen["promedio_cada_cuanto_descansa_seg"])
        txt_prom = f"Cada {self._fmt_dur(prom_desc)}" if prom_desc > 0 else "Sin pausas aún"

        kpis = [
            ("check", "Misiones Logradas", str(resumen["tareas_completadas"]), f"{resumen['total_pasos_logrados']} micro-pasos superados"),
            ("clock", "Foco Acumulado", self._fmt_dur(resumen["total_segundos_foco"]), "Tiempo efectivo en tarea"),
            ("coffee", "Descansos Alumno", str(resumen["total_pausas_alumno"]), txt_prom),
            ("star", "Economía de Fichas", f"{resumen.get('estrellas_disponibles', resumen['estrellas_totales'])} disp.", f"{resumen['estrellas_totales']} totales • {resumen.get('total_canjes', 0)} canjes"),
        ]
        for idx, (ico_kpi, titulo, valor, sub) in enumerate(kpis):
            c = ctk.CTkFrame(
                marco,
                fg_color=self.tema["card_bg"],
                border_color=self.tema["card_border"],
                border_width=2,
                corner_radius=18,
            )
            c.grid(row=0, column=idx, sticky="nsew", padx=6, pady=(0, 12))
            ctk.CTkLabel(
                c,
                text=f" {titulo}",
                image=icono_ctk(ico_kpi, self.tema["text_secondary"], 15),
                compound="left",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.tema["text_secondary"],
            ).pack(pady=(12, 2))
            ctk.CTkLabel(c, text=valor, font=ctk.CTkFont(size=22, weight="bold"), text_color=self.tema["text_primary"]).pack()
            ctk.CTkLabel(c, text=sub, font=ctk.CTkFont(size=11), text_color=self.tema["text_secondary"], wraplength=200).pack(pady=(2, 12), padx=6)

        # Botones de Exportación (CSV Excel + Informe HTML Imprimible)
        barra_exp = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=18,
        )
        barra_exp.grid(row=1, column=0, columnspan=4, sticky="ew", padx=6, pady=(0, 12))

        ctk.CTkLabel(
            barra_exp,
            text="  Exportar Informes:",
            image=icono_ctk("chart", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(side="left", padx=16, pady=12)

        ctk.CTkButton(
            barra_exp,
            text="Informe Visual (HTML / PDF)",
            image=icono_ctk("printer", "#ffffff", 16),
            compound="left",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            corner_radius=14,
            width=242,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._exportar_html,
        ).pack(side="right", padx=(6, 16), pady=10)

        ctk.CTkButton(
            barra_exp,
            text="Tabla Excel (CSV)",
            image=icono_ctk("table", "#ffffff", 16),
            compound="left",
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            corner_radius=14,
            width=185,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._exportar_csv,
        ).pack(side="right", padx=6, pady=10)

        if self.db and hasattr(self.db, "limpiar_historial_progreso"):
            ctk.CTkButton(
                barra_exp,
                text="Limpiar Historial",
                image=icono_ctk("trash", "#ffffff", 15),
                compound="left",
                fg_color=self.tema["btn_orange"],
                hover_color=self.tema["btn_orange_hover"],
                corner_radius=14,
                width=168,
                height=38,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=self._confirmar_limpiar_historial,
            ).pack(side="right", padx=6, pady=10)

        # Gráfico visual de las últimas sesiones
        sesiones = self.db.obtener_historial_sesiones(limite=12) if self.db else []
        card_graf = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=18,
        )
        card_graf.grid(row=2, column=0, columnspan=4, sticky="ew", padx=6, pady=(0, 12))

        ctk.CTkLabel(
            card_graf,
            text="  Evolución de Tiempo de Concentración y Descansos por Sesión",
            image=icono_ctk("chart", self.tema["text_primary"], 19),
            compound="left",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=16, pady=(12, 4))

        lienzo_graf = tk.Canvas(
            card_graf,
            height=155,
            bg=self.tema["card_inner"],
            bd=0,
            highlightthickness=0,
        )
        lienzo_graf.pack(fill="x", padx=16, pady=(0, 14))
        lienzo_graf.bind("<Configure>", lambda _e, cv=lienzo_graf, s=sesiones: self._dibujar_grafico_sesiones(cv, s))

        # Historial detallado de sesiones y bitácora de descansos lado a lado (anti-desbordamiento)
        mitad = ctk.CTkFrame(marco, fg_color="transparent")
        mitad.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(0, 12))
        mitad.grid_columnconfigure((0, 1), weight=1)

        card_ses = ctk.CTkFrame(mitad, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=18)
        card_ses.grid(row=0, column=0, sticky="nsew", padx=(6, 6), pady=4)
        ctk.CTkLabel(
            card_ses,
            text="  Últimas Sesiones Guiadas",
            image=icono_ctk("clock", self.tema["text_primary"], 16),
            compound="left",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=14, pady=(12, 6))

        if not sesiones:
            ctk.CTkLabel(card_ses, text="Aún no hay sesiones finalizadas. ¡Completa una misión con Haru!", text_color=self.tema["text_secondary"], wraplength=380).pack(padx=14, pady=16)
        else:
            for s in sesiones[:6]:
                fila = ctk.CTkFrame(card_ses, fg_color=self.tema["card_inner"], corner_radius=10)
                fila.pack(fill="x", padx=12, pady=3)
                titulo_corto = self._truncar(s["nombre_tarea"], 36)
                est_tag = "[OK]" if (s.get("estado_final") or "COMPLETADA") == "COMPLETADA" else "[Parcial]"
                ctk.CTkLabel(
                    fila,
                    text=f"{est_tag} {titulo_corto}  •  {s['pasos_completados']}/{s['total_pasos']} pasos  •  {self._fmt_dur(s['segundos_concentracion'])}  •  Descansos: {s.get('pausas_manuales', 0)}",
                    font=ctk.CTkFont(size=12),
                    text_color=self.tema["text_primary"],
                    anchor="w",
                    justify="left",
                    wraplength=420,
                ).pack(fill="x", padx=10, pady=6)

        card_bit = ctk.CTkFrame(mitad, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=18)
        card_bit.grid(row=0, column=1, sticky="nsew", padx=(6, 6), pady=4)
        ctk.CTkLabel(
            card_bit,
            text="  Bitácora de Descansos del Alumno",
            image=icono_ctk("coffee", self.tema["text_primary"], 16),
            compound="left",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=14, pady=(12, 6))

        bitacora = self.db.obtener_bitacora_descansos(limite=6) if self.db else []
        if not bitacora:
            ctk.CTkLabel(card_bit, text="El estudiante todavía no presionó el botón de descanso.", text_color=self.tema["text_secondary"], wraplength=380).pack(padx=14, pady=16)
        else:
            for b in bitacora:
                fila = ctk.CTkFrame(card_bit, fg_color=self.tema["card_inner"], corner_radius=10)
                fila.pack(fill="x", padx=12, pady=3)
                titulo_corto = self._truncar(b["nombre_tarea"], 38)
                ctk.CTkLabel(
                    fila,
                    text=f"Paso {b['paso_actual']} ({self._fmt_dur(b['segundos_transcurridos'])}) — {titulo_corto}",
                    font=ctk.CTkFont(size=12),
                    text_color=self.tema["text_primary"],
                    anchor="w",
                    justify="left",
                    wraplength=420,
                ).pack(fill="x", padx=10, pady=6)

        # Gestión de Premios Reales Pactados (Economía de Fichas TDAH)
        if self.db and hasattr(self.db, "listar_recompensas_catalogo"):
            card_premios = ctk.CTkFrame(
                marco,
                fg_color=self.tema["card_bg"],
                border_color=self.tema["card_border"],
                border_width=2,
                corner_radius=18,
            )
            card_premios.grid(row=4, column=0, columnspan=4, sticky="ew", padx=6, pady=(0, 12))
            ctk.CTkLabel(
                card_premios,
                text="  Catálogo de Premios Pactados con Familia / Docente (Economía de Fichas TDAH)",
                image=icono_ctk("gift", self.tema["text_primary"], 17),
                compound="left",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
            ).pack(anchor="w", padx=16, pady=(12, 4))

            form_pr = ctk.CTkFrame(card_premios, fg_color="transparent")
            form_pr.pack(fill="x", padx=16, pady=(0, 8))

            ent_titulo_pr = ctk.CTkEntry(form_pr, placeholder_text="Nuevo premio real (ej. Elegir juego de mesa familiar)", width=340, height=34, corner_radius=10)
            ent_titulo_pr.pack(side="left", padx=(0, 6), fill="x", expand=True)

            ent_costo_pr = ctk.CTkEntry(form_pr, placeholder_text="Puntos (ej. 15)", width=120, height=34, corner_radius=10)
            ent_costo_pr.insert(0, "15")
            ent_costo_pr.pack(side="left", padx=(0, 8))

            def _agregar_premio_adulto():
                tit = ent_titulo_pr.get().strip()
                try:
                    cst = int(ent_costo_pr.get().strip())
                except ValueError:
                    messagebox.showwarning("Costo inválido", "Escribe un número entero de puntos (1 a 500).", parent=self)
                    return
                if not tit:
                    messagebox.showwarning("Falta premio", "Escribe el nombre del premio pactado.", parent=self)
                    return
                self.db.agregar_recompensa_catalogo(tit, cst, "Premio personalizado pactado con adulto")
                self.notificar(f"Premio «{self._truncar(tit, 28)}» ({cst} pts) añadido.")
                self.mostrar_seccion("progreso")

            ent_titulo_pr.bind("<Return>", lambda _e: _agregar_premio_adulto())
            ent_costo_pr.bind("<Return>", lambda _e: _agregar_premio_adulto())

            ctk.CTkButton(
                form_pr,
                text="Añadir Premio",
                image=icono_ctk("plus", "#ffffff", 14),
                compound="left",
                fg_color=self.tema["btn_green"],
                hover_color=self.tema["btn_green_hover"],
                corner_radius=10,
                height=34,
                width=136,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=_agregar_premio_adulto,
            ).pack(side="left", padx=(0, 6))

            if hasattr(self.db, "restaurar_recompensas_predeterminadas"):
                ctk.CTkButton(
                    form_pr,
                    text="Sugeridos (6–32 pts)",
                    image=icono_ctk("refresh", "#ffffff", 14),
                    compound="left",
                    fg_color=self.tema["btn_stage_pill"],
                    hover_color=self.tema["btn_stage_pill_hover"],
                    corner_radius=10,
                    height=34,
                    width=162,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda: (
                        self.db.restaurar_recompensas_predeterminadas(),
                        self.notificar("Premios psicopedagógicos sugeridos (6 a 32 pts) restaurados."),
                        self.mostrar_seccion("progreso"),
                    ),
                ).pack(side="left")

            for pr in self.db.listar_recompensas_catalogo():
                fila_p = ctk.CTkFrame(card_premios, fg_color=self.tema["card_inner"], corner_radius=10)
                fila_p.pack(fill="x", padx=16, pady=3)
                ctk.CTkLabel(
                    fila_p,
                    text=f"  {self._truncar(pr['titulo'], 58)}   —   Costo: {pr['costo_estrellas']} pts",
                    image=icono_ctk("gift", self.tema["text_primary"], 14),
                    compound="left",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=self.tema["text_primary"],
                    anchor="w",
                ).pack(side="left", padx=12, pady=6)
                ctk.CTkButton(
                    fila_p,
                    text="Quitar",
                    width=68,
                    height=26,
                    corner_radius=8,
                    fg_color=self.tema["btn_orange"],
                    hover_color=self.tema["btn_orange_hover"],
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda pid=pr["id"]: (self.db.eliminar_recompensa_catalogo(pid), self.mostrar_seccion("progreso")),
                ).pack(side="right", padx=10, pady=5)
            ctk.CTkFrame(card_premios, fg_color="transparent", height=6).pack()

    def _dibujar_grafico_sesiones(self, cv: tk.Canvas, sesiones: List[Dict]) -> None:
        cv.delete("all")
        w = max(360, cv.winfo_width())
        h = max(130, cv.winfo_height())

        if not sesiones:
            cv.create_text(
                w / 2, h / 2,
                text="Aquí aparecerán las barras de tiempo de foco y descansos cuando se completen misiones.",
                fill=self.tema["text_secondary"],
                font=("Segoe UI", 11),
            )
            return

        datos = list(reversed(sesiones[:8]))
        max_seg = max(30, max(max(0, int(d["segundos_concentracion"])) for d in datos))
        margen_x = 36
        ancho_util = max(120, w - margen_x * 2)
        paso_x = ancho_util / max(1, len(datos))
        ancho_barra = max(10, min(20, int(paso_x * 0.28)))
        max_chars = max(7, min(14, int(paso_x / 7.5)))

        for i, s in enumerate(datos):
            cx = margen_x + paso_x * (i + 0.5)
            seg_val = max(0, int(s["segundos_concentracion"]))
            alto_barra = int((seg_val / float(max_seg)) * (h - 54))
            y_top = h - 28 - max(8, alto_barra)
            color_b = "#22c55e" if (s.get("estado_final") or "COMPLETADA") == "COMPLETADA" else "#f59e0b"
            cv.create_rectangle(cx - ancho_barra, y_top, cx + ancho_barra, h - 28, fill=color_b, outline="")
            cv.create_text(
                cx, y_top - 10,
                text=f"{self._fmt_dur(seg_val)} ({s.get('pausas_manuales', 0)}p)",
                fill=self.tema["text_primary"],
                font=("Segoe UI", 8, "bold"),
            )
            etiqueta = self._truncar(s["nombre_tarea"], max_chars)
            cv.create_text(
                cx, h - 13,
                text=etiqueta,
                fill=self.tema["text_secondary"],
                font=("Segoe UI", 8),
            )

    def _confirmar_limpiar_historial(self) -> None:
        if not self.db or not hasattr(self.db, "limpiar_historial_progreso"):
            return
        confirmar = messagebox.askyesno(
            "Limpiar historial de sesiones",
            "¿Deseas borrar el historial de sesiones, descansos y canjes de prueba?\n\n"
            "(Tus misiones creadas y el PIN de seguridad se conservarán intactos).",
            parent=self,
        )
        if not confirmar:
            return
        reiniciar_pts = messagebox.askyesno(
            "¿Reiniciar también puntos a 5?",
            "¿Quieres reiniciar también los puntos del estudiante a los 5 iniciales (nuevo estudiante)?\n\n"
            "• Sí: Reinicia a 5 puntos y traje base.\n"
            "• No: Conserva los puntos ganados por el niño.",
            parent=self,
        )
        self.db.limpiar_historial_progreso(reiniciar_estrellas=reiniciar_pts)
        self.motor.estrellas_totales = self.db.obtener_estrellas()
        if self.callback_recargar:
            self.callback_recargar()
        self.mostrar_seccion("progreso")
        self.notificar("Historial de sesiones limpiado correctamente.")

    def _exportar_csv(self) -> None:
        if not self.db:
            return
        ruta = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar Reporte Excel (CSV)",
            defaultextension=".csv",
            initialfile="reporte_haru_tdah.csv",
            filetypes=[("Archivo CSV (Excel)", "*.csv")],
        )
        if ruta:
            self.db.exportar_reporte_csv(ruta)
            self.notificar("Reporte CSV exportado con éxito.")

    def _exportar_html(self) -> None:
        if not self.db:
            return
        ruta = filedialog.asksaveasfilename(
            parent=self,
            title="Guardar Informe Psicopedagógico HTML",
            defaultextension=".html",
            initialfile="informe_psicopedagogico_haru.html",
            filetypes=[("Página Web HTML", "*.html")],
        )
        if ruta:
            self.db.exportar_reporte_html(ruta)
            self.notificar("Informe HTML generado y abierto.")
            try:
                webbrowser.open(f"file:///{os.path.abspath(ruta).replace(chr(92), '/')}")
            except Exception:
                pass

    # =========================================================================
    # SECCIÓN 3: VOZ NEURONAL, TEMPORIZADOR POMODORO E INTELIGENCIA ARTIFICIAL
    # =========================================================================
    def _vista_voz_ia(self) -> None:
        marco = ctk.CTkScrollableFrame(self.contenedor, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="nsew")
        marco.grid_columnconfigure((0, 1), weight=1)

        # --- Tarjeta 1: Voz Neuronal ---
        card_voz = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_voz.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))

        ctk.CTkLabel(
            card_voz,
            text="  Voz Neuronal de Haru (Edge-TTS)",
            image=icono_ctk("mic", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card_voz, text="Voces humanas cálidas gratuitas con subtítulos karaoke en vivo:", font=ctk.CTkFont(size=12), text_color=self.tema["text_secondary"]).pack(anchor="w", padx=18, pady=(0, 10))

        voz_actual_id = self.db.obtener_preferencia("voz_tts", "es-BO-SofiaNeural") if self.db else "es-BO-SofiaNeural"
        etiqueta_actual = next((k for k, v in VOCES_DISPONIBLES.items() if v == voz_actual_id), list(VOCES_DISPONIBLES.keys())[0])

        self.combo_voz = ctk.CTkOptionMenu(
            card_voz,
            values=list(VOCES_DISPONIBLES.keys()),
            width=280,
            height=36,
            corner_radius=12,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
        )
        self.combo_voz.set(etiqueta_actual)
        self.combo_voz.pack(anchor="w", padx=18, pady=6)

        vel_map = {"Pausada y Calma (-10%)": "-10%", "Natural (+0%)": "+0%", "Alegre y Ágil (+8%)": "+8%"}
        vel_actual = self.db.obtener_preferencia("velocidad_tts", "+0%") if self.db else "+0%"
        etiqueta_vel = next((k for k, v in vel_map.items() if v == vel_actual), "Natural (+0%)")

        self.combo_vel = ctk.CTkOptionMenu(
            card_voz,
            values=list(vel_map.keys()),
            width=280,
            height=36,
            corner_radius=12,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
        )
        self.combo_vel.set(etiqueta_vel)
        self.combo_vel.pack(anchor="w", padx=18, pady=6)

        def _guardar_y_probar_voz():
            vid = VOCES_DISPONIBLES.get(self.combo_voz.get(), "es-BO-SofiaNeural")
            vel = vel_map.get(self.combo_vel.get(), "+0%")
            if self.db:
                self.db.guardar_preferencia("voz_tts", vid)
                self.db.guardar_preferencia("velocidad_tts", vel)
            if self.voz:
                self.voz.configurar_voz(voz=vid, velocidad=vel)
                self.voz.hablar("¡Hola! Así suena mi voz neuronal lista para acompañar tus tareas.")
            self.notificar(f"Voz actualizada a {self.combo_voz.get()}.")

        ctk.CTkButton(
            card_voz,
            text="Guardar y Probar Voz",
            image=icono_ctk("volume", "#ffffff", 16),
            compound="left",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            corner_radius=14,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=_guardar_y_probar_voz,
        ).pack(anchor="w", padx=18, pady=(10, 12))

        # --- Subsección Ollama Local debajo de Voz Neuronal ---
        ctk.CTkFrame(card_voz, height=2, fg_color=self.tema["card_border"]).pack(
            fill="x", padx=18, pady=(4, 10)
        )
        self.panel_ollama = ctk.CTkFrame(
            card_voz,
            fg_color=self.tema["card_inner"],
            corner_radius=14,
        )
        self.panel_ollama.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        ctk.CTkLabel(
            self.panel_ollama,
            text="  IA Local Privada (Ollama)",
            image=icono_ctk("bolt", self.tema["text_primary"], 16),
            compound="left",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=14, pady=(12, 6))

        fila_led = ctk.CTkFrame(self.panel_ollama, fg_color="transparent")
        fila_led.pack(fill="x", padx=14, pady=2)
        self.led_ollama = ctk.CTkFrame(
            fila_led,
            width=14,
            height=14,
            corner_radius=7,
            fg_color="#64748b",
            border_width=1,
            border_color=self.tema["card_border"],
        )
        self.led_ollama.pack_propagate(False)
        self.led_ollama.pack(side="left", padx=(0, 8))

        self.lbl_ollama_estado = ctk.CTkLabel(
            fila_led,
            text="Sin verificar",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_ollama_estado.pack(side="left")

        self.lbl_ollama_modelo = ctk.CTkLabel(
            self.panel_ollama,
            text="Modelo local: Ninguno detectado",
            font=ctk.CTkFont(size=12),
            text_color=self.tema["text_secondary"],
            justify="left",
            wraplength=330,
        )
        self.lbl_ollama_modelo.pack(anchor="w", padx=14, pady=(4, 8))

        fila_ollama_ctrl = ctk.CTkFrame(self.panel_ollama, fg_color="transparent")
        fila_ollama_ctrl.pack(fill="x", padx=14, pady=(0, 12))

        self.combo_modelo_ollama = ctk.CTkOptionMenu(
            fila_ollama_ctrl,
            values=["Sin modelo local"],
            width=185,
            height=32,
            corner_radius=10,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
            command=self._seleccionar_modelo_ollama,
        )
        self.combo_modelo_ollama.set("Sin modelo local")
        self.combo_modelo_ollama.configure(state="disabled")
        self.combo_modelo_ollama.pack(side="left", padx=(0, 8))

        self.btn_refrescar_ollama = ctk.CTkButton(
            fila_ollama_ctrl,
            text="Verificar",
            image=icono_ctk("refresh", "#ffffff", 14),
            compound="left",
            height=32,
            width=108,
            corner_radius=10,
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._verificar_ollama_async(forzar=True),
        )
        self.btn_refrescar_ollama.pack(side="left")

        # --- Tarjeta 2: Temporizador Micro-Pomodoro y Comprobación Activa ---
        card_rel = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_rel.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))

        ctk.CTkLabel(
            card_rel,
            text="  Ritmo Micro-Pomodoro y Comprobación",
            image=icono_ctk("clock", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card_rel, text="Ajusta los bloques de atención, descansos y validación interactiva:", font=ctk.CTkFont(size=12), text_color=self.tema["text_secondary"]).pack(anchor="w", padx=18, pady=(0, 8))

        grid_t = ctk.CTkFrame(card_rel, fg_color="transparent")
        grid_t.pack(fill="x", padx=18, pady=4)

        ctk.CTkLabel(grid_t, text="Minutos de Foco:", text_color=self.tema["text_primary"]).grid(row=0, column=0, sticky="w", pady=4)
        self.ent_foco = ctk.CTkEntry(grid_t, width=70, corner_radius=10)
        self.ent_foco.insert(0, str(max(1, self.motor.tiempo_foco // 60)))
        self.ent_foco.grid(row=0, column=1, padx=10, pady=4)

        ctk.CTkLabel(grid_t, text="Minutos de Pausa:", text_color=self.tema["text_primary"]).grid(row=1, column=0, sticky="w", pady=4)
        self.ent_pausa = ctk.CTkEntry(grid_t, width=70, corner_radius=10)
        self.ent_pausa.insert(0, str(max(1, self.motor.tiempo_pausa // 60)))
        self.ent_pausa.grid(row=1, column=1, padx=10, pady=4)

        ctk.CTkLabel(grid_t, text="Máx. Descansos / Misión:", text_color=self.tema["text_primary"]).grid(row=2, column=0, sticky="w", pady=4)
        self.ent_max_desc = ctk.CTkEntry(grid_t, width=70, corner_radius=10)
        self.ent_max_desc.insert(0, str(self.motor.max_descansos_por_tarea))
        self.ent_max_desc.grid(row=2, column=1, padx=10, pady=4)

        ctk.CTkLabel(grid_t, text="Aviso Inactividad (min):", text_color=self.tema["text_primary"]).grid(row=3, column=0, sticky="w", pady=4)
        self.ent_inactividad = ctk.CTkEntry(grid_t, width=70, corner_radius=10)
        self.ent_inactividad.insert(0, str(self.motor.umbral_inactividad_seg // 60))
        self.ent_inactividad.grid(row=3, column=1, padx=10, pady=4)

        # Presets psicopedagógicos TDAH por edad escolar
        fila_presets = ctk.CTkFrame(card_rel, fg_color="transparent")
        fila_presets.pack(fill="x", padx=18, pady=(4, 2))

        for txt_pr, mf_p, mp_p, md_p in (
            ("6–8 años (8m/2m)", 8, 2, 3),
            ("Estándar (10m/2m)", 10, 2, 2),
            ("10–12 años (15m/3m)", 15, 3, 2),
        ):
            ctk.CTkButton(
                fila_presets,
                text=txt_pr,
                fg_color=self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_stage_pill_hover"],
                corner_radius=10,
                height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda a=mf_p, b=mp_p, c=md_p, t=txt_pr: self._cargar_preset_pomodoro(a, b, c, t),
            ).pack(side="left", padx=(0, 6), pady=2)

        self.sw_comprobacion = ctk.CTkSwitch(
            card_rel,
            text="Comprobación Activa en cada paso (Pregunta rápida o voz)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
            command=lambda: (
                self.motor.set_comprobacion_activa(bool(self.sw_comprobacion.get())),
                self.notificar(
                    "Comprobación Activa habilitada al presionar Paso Listo."
                    if self.sw_comprobacion.get()
                    else "Avance directo activado (sin pregunta intermedia)."
                ),
            ),
        )
        if getattr(self.motor, "comprobacion_activa", True):
            self.sw_comprobacion.select()
        self.sw_comprobacion.pack(anchor="w", padx=18, pady=(6, 2))

        self.sw_demo = ctk.CTkSwitch(
            card_rel,
            text="Modo Demo Defensa (25s foco / 10s pausa)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
            command=lambda: self.motor.set_modo_demo(bool(self.sw_demo.get())),
        )
        if self.motor.modo_demo:
            self.sw_demo.select()
        self.sw_demo.pack(anchor="w", padx=18, pady=(2, 8))

        ctk.CTkButton(
            card_rel,
            text="Aplicar Configuración de Reloj",
            fg_color=self.tema["btn_orange"],
            hover_color=self.tema["btn_orange_hover"],
            corner_radius=14,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._aplicar_tiempos,
        ).pack(anchor="w", padx=18, pady=(4, 16))

        # --- Tarjeta 3 (Ancho completo): IA en Capas y Privacidad Ley N.º 548 ---
        card_ia = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_ia.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(
            card_ia,
            text="  Motor de Inteligencia Artificial en Capas y Privacidad (Ley N.º 548)",
            image=icono_ctk("shield", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=18, pady=(16, 4))

        self.lbl_estado_ia = ctk.CTkLabel(
            card_ia,
            text=self.ia.obtener_estado_ia() if self.ia else "Motor IA Local Activo",
            fg_color=self.tema["card_inner"],
            corner_radius=12,
            padx=14,
            pady=6,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_estado_ia.pack(anchor="w", padx=18, pady=6)

        self.sw_privado = ctk.CTkSwitch(
            card_ia,
            text="Modo Privado Estricto (Solo IA Local / Matemática AST / Ollama — No envía consultas a la nube)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
            command=self._alternar_modo_privado,
        )
        if self.ia and self.ia.modo_privado:
            self.sw_privado.select()
        self.sw_privado.pack(anchor="w", padx=18, pady=8)

        fila_key = ctk.CTkFrame(card_ia, fg_color="transparent")
        fila_key.pack(fill="x", padx=18, pady=(4, 16))

        ctk.CTkLabel(fila_key, text="Clave Gemini (.env):", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.tema["text_primary"]).pack(side="left", padx=(0, 8))
        self.entry_api_key = ctk.CTkEntry(fila_key, width=220, height=36, corner_radius=12, show="•")
        if self.ia and self.ia.api_key:
            self.entry_api_key.insert(0, self.ia.api_key)
        self.entry_api_key.pack(side="left", fill="x", expand=True, padx=4)
        self.entry_api_key.bind("<Return>", lambda _e: self._guardar_key_ia())

        self._mostrando_key = False

        def _ver_key():
            self._mostrando_key = not self._mostrando_key
            self.entry_api_key.configure(show="" if self._mostrando_key else "•")

        ctk.CTkButton(
            fila_key,
            text="",
            image=icono_ctk("eye", "#ffffff", 16),
            width=40,
            height=36,
            corner_radius=10,
            fg_color=self.tema["btn_stage_pill"],
            command=_ver_key,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            fila_key,
            text="Guardar en .env",
            image=icono_ctk("save", "#ffffff", 15),
            compound="left",
            height=36,
            corner_radius=12,
            fg_color=self.tema["btn_stage_pill"],
            command=self._guardar_key_ia,
        ).pack(side="left", padx=4)
        self.btn_probar_ia = ctk.CTkButton(
            fila_key,
            text="Probar Conexión Cloud",
            image=icono_ctk("bolt", "#ffffff", 15),
            compound="left",
            height=36,
            corner_radius=12,
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._probar_conexion_ia,
        )
        self.btn_probar_ia.pack(side="left", padx=6)

        if self.ia and hasattr(self.ia, "obtener_info_ollama"):
            try:
                info_ollama = self.ia.obtener_info_ollama(forzar=False)
                self._aplicar_estado_ollama_ui(info_ollama)
            except Exception:
                pass
            if getattr(self.ia, "_ollama_check_ts", 0.0) == 0.0:
                self._verificar_ollama_async(forzar=True)

    def _cargar_preset_pomodoro(self, mf: int, mp: int, md: int, etiqueta: str = "Preset", mi: int = 3) -> None:
        if hasattr(self, "ent_foco") and self.ent_foco.winfo_exists():
            self.ent_foco.delete(0, "end")
            self.ent_foco.insert(0, str(mf))
        if hasattr(self, "ent_pausa") and self.ent_pausa.winfo_exists():
            self.ent_pausa.delete(0, "end")
            self.ent_pausa.insert(0, str(mp))
        if hasattr(self, "ent_max_desc") and self.ent_max_desc.winfo_exists():
            self.ent_max_desc.delete(0, "end")
            self.ent_max_desc.insert(0, str(md))
        if hasattr(self, "ent_inactividad") and self.ent_inactividad.winfo_exists():
            self.ent_inactividad.delete(0, "end")
            self.ent_inactividad.insert(0, str(mi))
        if hasattr(self, "sw_demo") and self.sw_demo.winfo_exists():
            self.sw_demo.deselect()
        self.motor.configurar_tiempos_personalizados(mf, mp, md, min_inactividad=mi)
        self.notificar(f"Perfil {etiqueta} guardado: {mf}m foco / {mp}m pausa ({md} descansos, aviso {mi}m).")

    def _aplicar_tiempos(self) -> None:
        try:
            mf = int(self.ent_foco.get())
            mp = int(self.ent_pausa.get())
            md = int(self.ent_max_desc.get())
            mi = int(self.ent_inactividad.get()) if hasattr(self, "ent_inactividad") else 3
            if hasattr(self, "sw_demo") and self.sw_demo.winfo_exists():
                self.sw_demo.deselect()
            self.motor.configurar_tiempos_personalizados(mf, mp, md, min_inactividad=mi)
            self.notificar(f"Tiempos aplicados: {mf}m foco / {mp}m pausa / {md} descansos (inactividad: {mi}m).")
        except ValueError:
            messagebox.showwarning("Valor inválido", "Ingresa números enteros para minutos y descansos.", parent=self)

    def _alternar_modo_privado(self) -> None:
        if not self.ia:
            return
        activo = bool(self.sw_privado.get())
        self.ia.set_modo_privado(activo)
        if self.voz is not None:
            self.voz.forzar_offline = activo
        if self.stt is not None:
            self.stt.forzar_modo_privado = activo
        self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia())
        self.notificar(
            "Modo Privado Estricto activo (100% local, cero red)."
            if activo
            else "Modo Híbrido activo (IA y Voz Neuronal habilitadas)."
        )

    def _guardar_key_ia(self) -> None:
        if not self.ia:
            return
        self.ia.configurar_api_key(self.entry_api_key.get().strip())
        self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia())
        self.notificar("Clave guardada localmente en .env (excluida al empaquetar .zip).")

    def _probar_conexion_ia(self) -> None:
        if not self.ia:
            return
        self.ia.configurar_api_key(self.entry_api_key.get().strip())
        self.btn_probar_ia.configure(state="disabled", text="Probando...")

        def _worker():
            ok, detalle = self.ia.probar_conexion_cloud()
            self.after(0, lambda: (
                self.btn_probar_ia.configure(state="normal", text="Probar Conexión Cloud"),
                self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia()),
                messagebox.showinfo("Diagnóstico Gemini API", detalle, parent=self) if ok else messagebox.showwarning("Diagnóstico Gemini API", detalle, parent=self),
            ) if self.winfo_exists() else None)

        threading.Thread(target=_worker, daemon=True).start()

    def _aplicar_estado_ollama_ui(self, info: Dict[str, object]) -> None:
        """Actualiza el LED visual y el modelo local detectado de Ollama de forma segura."""
        if not self.winfo_exists():
            return
        conectado = bool(info and info.get("conectado"))
        modelo_activo = str(info.get("modelo_activo") or "") if info else ""
        modelos = [str(m) for m in (info.get("modelos_disponibles") or []) if str(m).strip()] if info else []

        if conectado and modelo_activo:
            if hasattr(self, "led_ollama") and self.led_ollama.winfo_exists():
                self.led_ollama.configure(fg_color="#22c55e")
            if hasattr(self, "lbl_ollama_estado") and self.lbl_ollama_estado.winfo_exists():
                self.lbl_ollama_estado.configure(text="Conectado (IA Local Activa)", text_color="#22c55e")
            if hasattr(self, "lbl_ollama_modelo") and self.lbl_ollama_modelo.winfo_exists():
                self.lbl_ollama_modelo.configure(text=f"Modelo conectado: {modelo_activo}")
            if hasattr(self, "combo_modelo_ollama") and self.combo_modelo_ollama.winfo_exists():
                valores = modelos if modelos else [modelo_activo]
                self.combo_modelo_ollama.configure(values=valores, state="normal")
                self.combo_modelo_ollama.set(modelo_activo)
        else:
            if hasattr(self, "led_ollama") and self.led_ollama.winfo_exists():
                self.led_ollama.configure(fg_color="#ef4444")
            if hasattr(self, "lbl_ollama_estado") and self.lbl_ollama_estado.winfo_exists():
                self.lbl_ollama_estado.configure(text="Desconectado", text_color=self.tema["text_secondary"])
            if hasattr(self, "lbl_ollama_modelo") and self.lbl_ollama_modelo.winfo_exists():
                self.lbl_ollama_modelo.configure(text="No se detectó Ollama local (127.0.0.1:11434).")
            if hasattr(self, "combo_modelo_ollama") and self.combo_modelo_ollama.winfo_exists():
                self.combo_modelo_ollama.configure(values=["Sin modelo local"], state="disabled")
                self.combo_modelo_ollama.set("Sin modelo local")

        if self.ia and hasattr(self, "lbl_estado_ia") and self.lbl_estado_ia.winfo_exists():
            self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia())

    def _seleccionar_modelo_ollama(self, modelo_elegido: str) -> None:
        if not self.ia or not modelo_elegido or modelo_elegido == "Sin modelo local":
            return
        if hasattr(self.ia, "configurar_modelo_ollama"):
            self.ia.configurar_modelo_ollama(modelo_elegido)
        if hasattr(self, "lbl_ollama_modelo") and self.lbl_ollama_modelo.winfo_exists():
            self.lbl_ollama_modelo.configure(text=f"Modelo conectado: {modelo_elegido}")
        if hasattr(self, "lbl_estado_ia") and self.lbl_estado_ia.winfo_exists():
            self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia())
        self.notificar(f"Modelo Ollama seleccionado: {modelo_elegido}")

    def _verificar_ollama_async(self, forzar: bool = True) -> None:
        if not self.ia or not hasattr(self.ia, "obtener_info_ollama") or not self.winfo_exists():
            return
        if hasattr(self, "led_ollama") and self.led_ollama.winfo_exists():
            self.led_ollama.configure(fg_color="#eab308")
        if hasattr(self, "lbl_ollama_estado") and self.lbl_ollama_estado.winfo_exists():
            self.lbl_ollama_estado.configure(text="Verificando Ollama...", text_color=self.tema["text_primary"])
        if hasattr(self, "btn_refrescar_ollama") and self.btn_refrescar_ollama.winfo_exists():
            self.btn_refrescar_ollama.configure(state="disabled")

        cola_ollama: queue.SimpleQueue = queue.SimpleQueue()

        def _worker():
            info: Dict[str, object] = {"conectado": False, "modelo_activo": "", "modelos_disponibles": []}
            try:
                info = self.ia.obtener_info_ollama(forzar=forzar)
            except Exception:
                pass
            cola_ollama.put(info)

        def _revisar_cola():
            if not self.winfo_exists():
                self._after_ollama_poll_id = None
                return
            try:
                info = cola_ollama.get_nowait()
            except queue.Empty:
                self._after_ollama_poll_id = self.after(80, _revisar_cola)
                return
            self._after_ollama_poll_id = None
            if hasattr(self, "btn_refrescar_ollama") and self.btn_refrescar_ollama.winfo_exists():
                self.btn_refrescar_ollama.configure(state="normal")
            self._aplicar_estado_ollama_ui(info)

        self._after_ollama_poll_id = self.after(80, _revisar_cola)
        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # SECCIÓN 4: SEGURIDAD PIN, PERFIL PEDAGÓGICO, SEMÁFORO VISUAL Y MARCO NORMATIVO
    # =========================================================================
    def _guardar_perfil_estudiante(self) -> None:
        if not hasattr(self, "ent_nombre_estudiante") or not hasattr(self, "combo_grado_primaria"):
            return
        nombre = self.ent_nombre_estudiante.get().strip()[:60]
        grado = self.combo_grado_primaria.get().strip()
        if grado not in self.GRADOS_PRIMARIA:
            grado = "3.° de Primaria"
        if self.db:
            self.db.guardar_preferencia("nombre_estudiante", nombre)
            self.db.guardar_preferencia("grado_primaria", grado)
        if self.ia and hasattr(self.ia, "actualizar_perfil_estudiante"):
            self.ia.actualizar_perfil_estudiante(nombre, grado)
        self.notificar(f"Perfil pedagógico guardado: {nombre or 'Estudiante'} ({grado}).")

    def _vista_seguridad_arduino(self) -> None:
        """Vista 4: Seguridad (PIN PBKDF2), Perfil Pedagógico y Semáforo Visual.

        Nota: el nombre del método se conserva como alias compatible con la
        suite de pruebas heredada tras reemplazar el hardware físico por el
        Semáforo Visual nativo.
        """
        marco = ctk.CTkScrollableFrame(self.contenedor, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="nsew")
        marco.grid_columnconfigure((0, 1), weight=1)

        # --- Tarjeta PIN ---
        card_pin = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_pin.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))

        ctk.CTkLabel(
            card_pin,
            text="  Cambiar PIN de Acceso Adulto",
            image=icono_ctk("lock", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card_pin, text="Cifrado con PBKDF2-HMAC-SHA256 + bloqueo anti-intentos:", font=ctk.CTkFont(size=12), text_color=self.tema["text_secondary"]).pack(anchor="w", padx=18, pady=(0, 10))

        self.ent_pin_actual = ctk.CTkEntry(card_pin, placeholder_text="PIN actual (ej. 1234)", show="•", width=240, height=36, corner_radius=12)
        self.ent_pin_actual.pack(anchor="w", padx=18, pady=4)
        self.ent_pin_nuevo = ctk.CTkEntry(card_pin, placeholder_text="Nuevo PIN (4 a 6 dígitos)", show="•", width=240, height=36, corner_radius=12)
        self.ent_pin_nuevo.pack(anchor="w", padx=18, pady=4)

        def _actualizar_pin():
            if not self.db:
                return
            act = self.ent_pin_actual.get().strip()
            nvo = self.ent_pin_nuevo.get().strip()
            exito, restantes, seg_bloq = self.db.registrar_intento_pin(act)
            if not exito:
                if seg_bloq > 0:
                    messagebox.showerror(
                        "Acceso bloqueado temporalmente",
                        f"Demasiados intentos fallidos. Espera {seg_bloq}s antes de reintentar.",
                        parent=self,
                    )
                else:
                    messagebox.showerror(
                        "PIN incorrecto",
                        f"El PIN actual no coincide ({restantes} intentos restantes).",
                        parent=self,
                    )
                return
            if not nvo.isdigit() or not (4 <= len(nvo) <= 6):
                messagebox.showwarning("Formato inválido", "El nuevo PIN debe tener entre 4 y 6 números.", parent=self)
                return
            self.db.cambiar_pin_docente(nvo)
            self.ent_pin_actual.delete(0, "end")
            self.ent_pin_nuevo.delete(0, "end")
            self.notificar("PIN actualizado y cifrado con éxito.")

        self.ent_pin_actual.bind("<Return>", lambda _e: self.ent_pin_nuevo.focus_set())
        self.ent_pin_nuevo.bind("<Return>", lambda _e: _actualizar_pin())
        ctk.CTkButton(card_pin, text="Actualizar PIN Seguro", image=icono_ctk("check", "#ffffff", 15), compound="left", fg_color=self.tema["btn_green"], hover_color=self.tema["btn_green_hover"], corner_radius=14, height=38, font=ctk.CTkFont(size=13, weight="bold"), command=_actualizar_pin).pack(anchor="w", padx=18, pady=(8, 16))

        # --- Tarjeta Perfil Pedagógico del Estudiante y Semáforo Visual ---
        card_hw = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_hw.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))

        ctk.CTkLabel(
            card_hw,
            text="  Perfil Pedagógico del Estudiante y Semáforo Visual",
            image=icono_ctk("user", self.tema["text_primary"], 18),
            compound="left",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=18, pady=(16, 4))

        self.lbl_hw_estado = ctk.CTkLabel(
            card_hw,
            text=" Guía Visual Nativa Activa • Adaptación de vocabulario por grado",
            image=icono_ctk("dot", "#22c55e", 11),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_secondary"],
        )
        self.lbl_hw_estado.pack(anchor="w", padx=18, pady=(0, 8))

        nombre_est_actual = self.db.obtener_preferencia("nombre_estudiante", "") if self.db else ""
        grado_est_actual = (
            self.db.obtener_preferencia("grado_primaria", "3.° de Primaria")
            if self.db
            else "3.° de Primaria"
        )
        if grado_est_actual not in self.GRADOS_PRIMARIA:
            grado_est_actual = "3.° de Primaria"

        form_perfil = ctk.CTkFrame(card_hw, fg_color="transparent")
        form_perfil.pack(fill="x", padx=18, pady=4)
        form_perfil.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form_perfil,
            text="Nombre del Niño/a:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)

        self.ent_nombre_estudiante = ctk.CTkEntry(
            form_perfil,
            placeholder_text="Ej. Mateo, Lucía...",
            width=210,
            height=34,
            corner_radius=10,
        )
        if nombre_est_actual:
            self.ent_nombre_estudiante.insert(0, nombre_est_actual)
        self.ent_nombre_estudiante.grid(row=0, column=1, sticky="ew", pady=4)
        self.ent_nombre_estudiante.bind("<Return>", lambda _e: self._guardar_perfil_estudiante())

        ctk.CTkLabel(
            form_perfil,
            text="Grado de Primaria:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)

        self.combo_grado_primaria = ctk.CTkOptionMenu(
            form_perfil,
            values=list(self.GRADOS_PRIMARIA),
            width=210,
            height=34,
            corner_radius=10,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
        )
        self.combo_grado_primaria.set(grado_est_actual)
        self.combo_grado_primaria.grid(row=1, column=1, sticky="w", pady=4)

        self.btn_guardar_perfil_estudiante = ctk.CTkButton(
            card_hw,
            text="Guardar Perfil del Estudiante",
            image=icono_ctk("save", "#ffffff", 15),
            compound="left",
            height=36,
            corner_radius=12,
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._guardar_perfil_estudiante,
        )
        self.btn_guardar_perfil_estudiante.pack(anchor="w", padx=18, pady=(6, 8))

        ctk.CTkLabel(
            card_hw,
            text="Prueba en vivo del Semáforo Visual (Inicio / Avance / Meta):",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.tema["text_secondary"],
        ).pack(anchor="w", padx=18, pady=(2, 2))

        fila_leds = ctk.CTkFrame(card_hw, fg_color="transparent")
        fila_leds.pack(fill="x", padx=18, pady=(4, 16))
        self.botones_semaforo_visual: Dict[str, ctk.CTkButton] = {}
        if self.hardware:
            for txt, col_led, fn in [
                ("Inicio", "#22c55e", lambda: self.hardware.actualizar_progreso(1, 3)),
                ("Avance", "#eab308", lambda: self.hardware.actualizar_progreso(2, 3)),
                ("Meta", "#ef4444", lambda: self.hardware.celebrar_victoria()),
                ("Apagar", "#94a3b8", lambda: self.hardware.apagar_todo()),
            ]:
                btn_sem = ctk.CTkButton(
                    fila_leds,
                    text=txt,
                    image=icono_ctk("dot", col_led, 10),
                    compound="left",
                    width=80,
                    height=32,
                    corner_radius=10,
                    fg_color=self.tema["btn_stage_pill"],
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=fn,
                )
                btn_sem.pack(side="left", padx=3)
                self.botones_semaforo_visual[txt] = btn_sem

        # --- Tarjeta Marco Legal Boliviano ---
        card_leg = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_leg.grid(row=1, column=0, columnspan=2, sticky="ew")

        ctk.CTkLabel(
            card_leg,
            text="  Respaldo Normativo y Pedagógico — Universidad Salesiana de Bolivia",
            image=icono_ctk("shield", self.tema["text_primary"], 17),
            compound="left",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=18, pady=(14, 4))
        texto_normas = (
            "• Ley N.º 070 (Avelino Siñani - Elizardo Pérez) y R.M. N.º 0069/2025: Educación inclusiva y adaptaciones curriculares para estudiantes con TDAH.\n"
            "• Ley N.º 548 (Código Niña, Niño y Adolescente): Cero almacenamiento de grabaciones de voz ni datos biométricos; Modo Privado 100% local disponible.\n"
            "• Ley N.º 164 (Tecnologías de Información y Comunicación): Uso soberano de herramientas accesibles y software portable.\n"
            "• Inspiración Salesiana (Sistema Preventivo): Acompañamiento cercano, paciente y alegre centrado en el bienestar integral del niño."
        )
        ctk.CTkLabel(card_leg, text=texto_normas, font=ctk.CTkFont(size=12), text_color=self.tema["text_secondary"], justify="left", wraplength=740).pack(anchor="w", padx=18, pady=(0, 16))
