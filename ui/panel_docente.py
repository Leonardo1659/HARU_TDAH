"""
Panel Docente y Familiar Intuitivo en CustomTkinter — Asistente TDAH "Haru"
Universidad Salesiana de Bolivia - Proyecto Integrador

Diseñado con navegación lateral clara y distribución espaciosa en 4 módulos:
1. 📝 Misiones y Pasos: Constructor visual tarjeta por tarjeta + Descomponedor IA.
2. 📊 Progreso y Descansos: KPIs, gráfico visual de foco/pausas, bitácora y exportación CSV/HTML.
3. 🎙️ Voz, Reloj e IA: Selector de voces neuronales (Bolivia/Latam), Pomodoro, Modo Privado y Gemini.
4. 🔐 Seguridad y Arduino: Cambio de PIN cifrado (PBKDF2), control de placa Arduino UNO R3 y marco legal.
"""

import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from core.config import VOCES_DISPONIBLES


class PanelDocente(ctk.CTkToplevel):
    def __init__(self, parent, motor_tdah, repositorio_db=None, motor_ia=None,
                 controlador_hardware=None, motor_voz=None, motor_stt=None,
                 tema: Optional[Dict[str, str]] = None,
                 callback_recargar: Optional[Callable[[], None]] = None):
        super().__init__(parent)
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
        self._botones_nav: Dict[str, ctk.CTkButton] = {}
        self._status_toast_after = None

        self._recargar_cache_tareas()
        self._construir_estructura_principal()
        self.mostrar_seccion("misiones")

        self.after(160, self._fijar_foco_windows)

    def _fijar_foco_windows(self) -> None:
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
            text="🎓 Docente y Familia",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff",
        ).pack(anchor="w", padx=20, pady=(22, 2))

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
            text=f"⭐ {resumen['estrellas_totales']} Puntos   •   ✅ {resumen['tareas_completadas']} Misiones",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff",
            pady=10,
        )
        self.lbl_resumen_lateral.pack()

        secciones = [
            ("misiones", "📝  1. Misiones y Pasos"),
            ("progreso", "📊  2. Progreso y Descansos"),
            ("voz_ia", "🎙️  3. Voz, Reloj e IA"),
            ("seguridad", "🔐  4. Seguridad y Arduino"),
        ]
        for clave, titulo in secciones:
            btn = ctk.CTkButton(
                self.sidebar,
                text=titulo,
                anchor="w",
                height=46,
                corner_radius=14,
                fg_color="transparent",
                hover_color=self.tema["btn_stage_pill_hover"],
                text_color="#ffffff",
                font=ctk.CTkFont(size=14, weight="bold"),
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
            text="⬅ Volver al Tablero del Niño",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            height=42,
            corner_radius=16,
            font=ctk.CTkFont(size=13, weight="bold"),
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
            text=f"⭐ {resumen['estrellas_totales']} Puntos   •   ✅ {resumen['tareas_completadas']} Misiones"
        )

    def cerrar_panel(self) -> None:
        if self._status_toast_after:
            try:
                self.after_cancel(self._status_toast_after)
            except Exception:
                pass
            self._status_toast_after = None
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
    def _vista_misiones(self) -> None:
        marco = ctk.CTkFrame(self.contenedor, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="nsew")
        marco.grid_columnconfigure(0, weight=0, minsize=255)
        marco.grid_columnconfigure(1, weight=1)
        marco.grid_rowconfigure(0, weight=1)

        # Columna Izquierda: Lista de misiones disponibles
        col_izq = ctk.CTkFrame(
            marco,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=20,
        )
        col_izq.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        ctk.CTkLabel(
            col_izq,
            text="📚 Catálogo de Misiones",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(anchor="w", padx=16, pady=(14, 2))

        ctk.CTkLabel(
            col_izq,
            text="Toca una misión para editarla o enviarla a Haru:",
            font=ctk.CTkFont(size=12),
            text_color=self.tema["text_secondary"],
        ).pack(anchor="w", padx=16, pady=(0, 8))

        fila_cat_acciones = ctk.CTkFrame(col_izq, fg_color="transparent")
        fila_cat_acciones.pack(fill="x", padx=14, pady=(0, 8))
        fila_cat_acciones.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            fila_cat_acciones,
            text="➕ Nueva Misión",
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
                text="🔄 Base",
                fg_color=self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_stage_pill_hover"],
                corner_radius=14,
                width=74,
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
        col_der.grid(row=0, column=1, sticky="nsew")
        col_der.grid_columnconfigure(0, weight=1)
        col_der.grid_rowconfigure(2, weight=1)

        # 1. Generador automático con IA
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
            text="✨ Generador IA: escribe un tema escolar para autocompletar pasos y pistas",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        self.entry_tema_ia = ctk.CTkEntry(
            caja_ia,
            placeholder_text="Ej: Sumas llevando de dos cifras / Los planetas del Sistema Solar...",
            height=36,
            corner_radius=12,
        )
        self.entry_tema_ia.grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(0, 10))
        self.entry_tema_ia.bind("<Return>", lambda _e: self._generar_pasos_con_ia())

        self.btn_generar_ia = ctk.CTkButton(
            caja_ia,
            text="✨ Generar Pasos",
            fg_color=self.tema["btn_purple"],
            hover_color=self.tema["btn_purple_hover"],
            corner_radius=12,
            height=36,
            width=150,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generar_pasos_con_ia,
        )
        self.btn_generar_ia.grid(row=1, column=1, padx=(0, 12), pady=(0, 10))

        # 2. Datos básicos (Nombre y Materia)
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
            values=["Matemáticas", "Lenguaje", "Ciencias", "Hábitos y Orden", "Estudios Sociales", "Arte", "Personalizada"],
            width=165,
            height=38,
            corner_radius=12,
            fg_color=self.tema["btn_stage_pill"],
            button_color=self.tema["btn_stage_pill_hover"],
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
            text="➕ Paso",
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
            text="🗑 Eliminar",
            fg_color="#dc2626",
            hover_color="#b91c1c",
            corner_radius=14,
            height=38,
            width=106,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._eliminar_mision_actual,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            barra_inf,
            text="🚀 Guardar y Activar",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            corner_radius=14,
            height=40,
            width=165,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._guardar_mision(activar_en_haru=True),
        ).pack(side="right")

        ctk.CTkButton(
            barra_inf,
            text="💾 Guardar",
            fg_color=self.tema["btn_orange"],
            hover_color=self.tema["btn_orange_hover"],
            corner_radius=14,
            height=40,
            width=102,
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

    def _poblar_lista_catalogo(self) -> None:
        for w in self.scroll_catalogo.winfo_children():
            w.destroy()
        self._recargar_cache_tareas()

        for nombre, datos in self.tareas_cache.items():
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
                text=f"{'🟢 ' if es_activa else ''}{nombre}",
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
                text=f"{datos['categoria']} • {len(datos['pasos'])} pasos",
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
        self.combo_categoria.set("Personalizada")
        self._pasos_borrador = [
            {"paso": "Prepara sobre tu mesa solo el cuaderno y lápiz que usarás.", "pista": "Guarda otros objetos para evitar distracciones."},
            {"paso": "Realiza la primera parte del ejercicio con calma.", "pista": "Si tienes dudas, usa la barra de preguntas de Haru IA."},
            {"paso": "Revisa tu respuesta y presiona ¡Paso Listo!", "pista": "¡Excelente esfuerzo! Ya estás en la meta."},
        ]
        self._renderizar_tarjetas_pasos()

    def _cargar_mision_en_editor(self, datos: Dict) -> None:
        self.entry_nombre_tarea.delete(0, "end")
        self.entry_nombre_tarea.insert(0, datos["nombre"])
        self.combo_categoria.set(datos.get("categoria", "Personalizada"))
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
                card_p, text="💡 Pista:", font=ctk.CTkFont(size=12),
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

    def _generar_pasos_con_ia(self) -> None:
        tema = self.entry_tema_ia.get().strip() or self.entry_nombre_tarea.get().strip()
        if not tema:
            self.notificar("Escribe primero un tema en el recuadro superior para generar los pasos.")
            return
        if not self.ia:
            return

        self.btn_generar_ia.configure(state="disabled", text="⏳ Generando...")

        def _worker():
            pasos, pistas = self.ia.descomponer_tarea_ia(tema)

            def _aplicar():
                if not self.winfo_exists():
                    return
                self.btn_generar_ia.configure(state="normal", text="✨ Generar Pasos")
                if not self.entry_nombre_tarea.get().strip():
                    self.entry_nombre_tarea.insert(0, tema)
                self._pasos_borrador = [
                    {"paso": p, "pista": pistas[i] if i < len(pistas) else ""}
                    for i, p in enumerate(pasos)
                ]
                self._renderizar_tarjetas_pasos()
                self.notificar(f"✨ {len(pasos)} micro-pasos creados ({self.ia.ultima_fuente}).")

            self.after(0, _aplicar)

        threading.Thread(target=_worker, daemon=True).start()

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

        categoria = self.combo_categoria.get()
        if self.db:
            self.db.guardar_tarea(nombre, pasos, pistas, categoria=categoria)

        self._poblar_lista_catalogo()
        if self.callback_recargar:
            self.callback_recargar()

        if activar_en_haru:
            self.motor.cargar_tarea(nombre, pasos, pistas)
            if self.callback_recargar:
                self.callback_recargar()
            self.notificar(f"🚀 Misión «{nombre}» enviada al tablero de Haru.")
        else:
            # Si se editó la misión que está actualmente en reposo en el tablero del niño, sincronizar sus pasos al instante
            if self.motor.tarea_actual == nombre and self.motor.estado == self.motor.ESTADO_IDLE:
                self.motor.cargar_tarea(nombre, pasos, pistas)
                if self.callback_recargar:
                    self.callback_recargar()
            self.notificar(f"💾 Misión «{nombre}» guardada correctamente.")

    def _restaurar_misiones_base(self) -> None:
        if not self.db or not hasattr(self.db, "restaurar_misiones_predeterminadas"):
            return
        self.db.restaurar_misiones_predeterminadas()
        self._poblar_lista_catalogo()
        if self.callback_recargar:
            self.callback_recargar()
        self.notificar("📚 Las 4 misiones escolares base fueron restauradas.")

    def _eliminar_mision_actual(self) -> None:
        nombre = self.entry_nombre_tarea.get().strip()
        if not nombre or not self.db:
            return
        if len(self.db.listar_tareas()) <= 1:
            messagebox.showwarning(
                "Última misión activa",
                "Debe existir al menos una misión en el catálogo para el estudiante.\n"
                "Crea otra misión o usa «🔄 Base» antes de eliminar esta.",
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
                self._cargar_mision_en_editor(restantes[0]["nombre"])
            else:
                self._preparar_nueva_mision()
            self.notificar(f"🗑 Misión «{nombre}» eliminada.")

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
            ("🎯 Misiones Logradas", str(resumen["tareas_completadas"]), f"{resumen['total_pasos_logrados']} micro-pasos superados"),
            ("⏱️ Foco Acumulado", self._fmt_dur(resumen["total_segundos_foco"]), "Tiempo efectivo en tarea"),
            ("☕ Descansos Alumno", str(resumen["total_pausas_alumno"]), txt_prom),
            ("⭐ Economía de Fichas", f"{resumen.get('estrellas_disponibles', resumen['estrellas_totales'])} disp.", f"{resumen['estrellas_totales']} totales • {resumen.get('total_canjes', 0)} canjes"),
        ]
        for idx, (titulo, valor, sub) in enumerate(kpis):
            c = ctk.CTkFrame(
                marco,
                fg_color=self.tema["card_bg"],
                border_color=self.tema["card_border"],
                border_width=2,
                corner_radius=18,
            )
            c.grid(row=0, column=idx, sticky="nsew", padx=6, pady=(0, 12))
            ctk.CTkLabel(c, text=titulo, font=ctk.CTkFont(size=12, weight="bold"), text_color=self.tema["text_secondary"]).pack(pady=(12, 2))
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
            text="📑 Exportar Informes:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(side="left", padx=16, pady=12)

        ctk.CTkButton(
            barra_exp,
            text="🖨️ Informe Visual (HTML / PDF)",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            corner_radius=14,
            width=235,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._exportar_html,
        ).pack(side="right", padx=(6, 16), pady=10)

        ctk.CTkButton(
            barra_exp,
            text="📥 Tabla Excel (CSV)",
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
                text="🧹 Limpiar Historial",
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
            text="📊 Evolución de Tiempo de Concentración y Descansos por Sesión",
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
        ctk.CTkLabel(card_ses, text="🕒 Últimas Sesiones Guiadas", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=14, pady=(12, 6))

        if not sesiones:
            ctk.CTkLabel(card_ses, text="Aún no hay sesiones finalizadas. ¡Completa una misión con Haru!", text_color=self.tema["text_secondary"], wraplength=380).pack(padx=14, pady=16)
        else:
            for s in sesiones[:6]:
                fila = ctk.CTkFrame(card_ses, fg_color=self.tema["card_inner"], corner_radius=10)
                fila.pack(fill="x", padx=12, pady=3)
                titulo_corto = self._truncar(s["nombre_tarea"], 36)
                est_tag = "✔" if (s.get("estado_final") or "COMPLETADA") == "COMPLETADA" else "⏳"
                ctk.CTkLabel(
                    fila,
                    text=f"{est_tag} {titulo_corto}  •  {s['pasos_completados']}/{s['total_pasos']} pasos  •  {self._fmt_dur(s['segundos_concentracion'])}  •  ☕ {s.get('pausas_manuales', 0)}",
                    font=ctk.CTkFont(size=12),
                    text_color=self.tema["text_primary"],
                    anchor="w",
                    justify="left",
                    wraplength=420,
                ).pack(fill="x", padx=10, pady=6)

        card_bit = ctk.CTkFrame(mitad, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=18)
        card_bit.grid(row=0, column=1, sticky="nsew", padx=(6, 6), pady=4)
        ctk.CTkLabel(card_bit, text="☕ Bitácora de Descansos del Alumno", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=14, pady=(12, 6))

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
                text="🎁 Catálogo de Premios Pactados con Familia / Docente (Economía de Fichas TDAH)",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
            ).pack(anchor="w", padx=16, pady=(12, 4))

            form_pr = ctk.CTkFrame(card_premios, fg_color="transparent")
            form_pr.pack(fill="x", padx=16, pady=(0, 8))

            ent_icono = ctk.CTkEntry(form_pr, placeholder_text="🎁", width=54, height=34, corner_radius=10)
            ent_icono.insert(0, "🌟")
            ent_icono.pack(side="left", padx=(0, 6))

            ent_titulo_pr = ctk.CTkEntry(form_pr, placeholder_text="Nuevo premio real (ej. Elegir juego de mesa familiar)", width=300, height=34, corner_radius=10)
            ent_titulo_pr.pack(side="left", padx=(0, 6), fill="x", expand=True)

            ent_costo_pr = ctk.CTkEntry(form_pr, placeholder_text="Estrellas (ej. 15)", width=120, height=34, corner_radius=10)
            ent_costo_pr.insert(0, "15")
            ent_costo_pr.pack(side="left", padx=(0, 8))

            def _agregar_premio_adulto():
                tit = ent_titulo_pr.get().strip()
                ico = ent_icono.get().strip() or "🎁"
                try:
                    cst = int(ent_costo_pr.get().strip())
                except ValueError:
                    messagebox.showwarning("Costo inválido", "Escribe un número entero de estrellas (1 a 500).", parent=self)
                    return
                if not tit:
                    messagebox.showwarning("Falta premio", "Escribe el nombre del premio pactado.", parent=self)
                    return
                titulo_completo = tit if tit[0] > "\u2600" else f"{ico} {tit}"
                self.db.agregar_recompensa_catalogo(titulo_completo, cst, "Premio personalizado pactado con adulto")
                self.notificar(f"🎁 Premio «{self._truncar(titulo_completo, 28)}» ({cst} ⭐) añadido.")
                self.mostrar_seccion("progreso")

            ent_titulo_pr.bind("<Return>", lambda _e: _agregar_premio_adulto())
            ent_costo_pr.bind("<Return>", lambda _e: _agregar_premio_adulto())

            ctk.CTkButton(
                form_pr,
                text="＋ Añadir Premio",
                fg_color=self.tema["btn_green"],
                hover_color=self.tema["btn_green_hover"],
                corner_radius=10,
                height=34,
                width=128,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=_agregar_premio_adulto,
            ).pack(side="left", padx=(0, 6))

            if hasattr(self.db, "restaurar_recompensas_predeterminadas"):
                ctk.CTkButton(
                    form_pr,
                    text="🔄 Sugeridos (6–32 ⭐)",
                    fg_color=self.tema["btn_stage_pill"],
                    hover_color=self.tema["btn_stage_pill_hover"],
                    corner_radius=10,
                    height=34,
                    width=148,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    command=lambda: (
                        self.db.restaurar_recompensas_predeterminadas(),
                        self.notificar("🎁 Premios psicopedagógicos sugeridos (6 a 32 ⭐) restaurados."),
                        self.mostrar_seccion("progreso"),
                    ),
                ).pack(side="left")

            for pr in self.db.listar_recompensas_catalogo():
                fila_p = ctk.CTkFrame(card_premios, fg_color=self.tema["card_inner"], corner_radius=10)
                fila_p.pack(fill="x", padx=16, pady=3)
                ctk.CTkLabel(
                    fila_p,
                    text=f"{self._truncar(pr['titulo'], 58)}   —   Costo: {pr['costo_estrellas']} ⭐",
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
                text=f"{self._fmt_dur(seg_val)} (☕{s.get('pausas_manuales', 0)})",
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
            "¿Reiniciar también estrellas a 5 ⭐?",
            "¿Quieres reiniciar también los puntos del estudiante a las 5 ⭐ iniciales (nuevo estudiante)?\n\n"
            "• Sí: Reinicia a 5 ⭐ y traje base.\n"
            "• No: Conserva las estrellas ganadas por el niño.",
            parent=self,
        )
        self.db.limpiar_historial_progreso(reiniciar_estrellas=reiniciar_pts)
        self.motor.estrellas_totales = self.db.obtener_estrellas()
        if self.callback_recargar:
            self.callback_recargar()
        self.mostrar_seccion("progreso")
        self.notificar("🧹 Historial de sesiones limpiado correctamente.")

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
            self.notificar("📥 Reporte CSV exportado con éxito.")

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
            self.notificar("🖨️ Informe HTML generado y abierto.")
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

        ctk.CTkLabel(card_voz, text="🎙️ Voz Neuronal de Haru (Edge-TTS)", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=18, pady=(16, 4))
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
            self.notificar(f"🎙️ Voz actualizada a {self.combo_voz.get()}.")

        ctk.CTkButton(
            card_voz,
            text="🔊 Guardar y Probar Voz",
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            corner_radius=14,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=_guardar_y_probar_voz,
        ).pack(anchor="w", padx=18, pady=(10, 16))

        # --- Tarjeta 2: Temporizador Micro-Pomodoro y Límite de Descansos ---
        card_rel = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_rel.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))

        ctk.CTkLabel(card_rel, text="⏱️ Ritmo Micro-Pomodoro y Descansos", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card_rel, text="Ajusta los bloques de atención y cuántos descansos puede pedir el niño:", font=ctk.CTkFont(size=12), text_color=self.tema["text_secondary"]).pack(anchor="w", padx=18, pady=(0, 8))

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

        # Presets psicopedagógicos TDAH por edad escolar
        fila_presets = ctk.CTkFrame(card_rel, fg_color="transparent")
        fila_presets.pack(fill="x", padx=18, pady=(4, 2))

        def _cargar_preset_pomodoro(mf: int, mp: int, md: int, etiqueta: str):
            self.ent_foco.delete(0, "end")
            self.ent_foco.insert(0, str(mf))
            self.ent_pausa.delete(0, "end")
            self.ent_pausa.insert(0, str(mp))
            self.ent_max_desc.delete(0, "end")
            self.ent_max_desc.insert(0, str(md))
            self.sw_demo.deselect()
            self.motor.configurar_tiempos_personalizados(mf, mp, md)
            self.notificar(f"⏱️ Perfil {etiqueta} guardado: {mf}m foco / {mp}m pausa ({md} descansos).")

        for txt_pr, mf_p, mp_p, md_p in (
            ("🐣 6–8 años (8m/2m)", 8, 2, 3),
            ("⭐ Estándar (10m/2m)", 10, 2, 2),
            ("🚀 10–12 años (15m/3m)", 15, 3, 2),
        ):
            ctk.CTkButton(
                fila_presets,
                text=txt_pr,
                fg_color=self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_stage_pill_hover"],
                corner_radius=10,
                height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda a=mf_p, b=mp_p, c=md_p, t=txt_pr: _cargar_preset_pomodoro(a, b, c, t),
            ).pack(side="left", padx=(0, 6), pady=2)

        self.sw_demo = ctk.CTkSwitch(
            card_rel,
            text="⚡ Modo Demo Defensa (25s foco / 10s pausa)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_primary"],
            command=lambda: self.motor.set_modo_demo(bool(self.sw_demo.get())),
        )
        if self.motor.modo_demo:
            self.sw_demo.select()
        self.sw_demo.pack(anchor="w", padx=18, pady=(6, 8))

        def _aplicar_tiempos():
            try:
                mf = int(self.ent_foco.get())
                mp = int(self.ent_pausa.get())
                md = int(self.ent_max_desc.get())
                self.sw_demo.deselect()
                self.motor.configurar_tiempos_personalizados(mf, mp, md)
                self.notificar(f"⏱️ Tiempos aplicados: {mf}m foco / {mp}m pausa / {md} descansos.")
            except ValueError:
                messagebox.showwarning("Valor inválido", "Ingresa números enteros para minutos y descansos.", parent=self)

        ctk.CTkButton(
            card_rel,
            text="Aplicar Configuración de Reloj",
            fg_color=self.tema["btn_orange"],
            hover_color=self.tema["btn_orange_hover"],
            corner_radius=14,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=_aplicar_tiempos,
        ).pack(anchor="w", padx=18, pady=(4, 16))

        # --- Tarjeta 3 (Ancho completo): IA en Capas y Privacidad Ley N.º 548 ---
        card_ia = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_ia.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(card_ia, text="🧠 Motor de Inteligencia Artificial en Capas y Privacidad (Ley N.º 548)", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=18, pady=(16, 4))

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
            text="🔒 Modo Privado Estricto (Solo IA Local / Matemática AST / Ollama — No envía consultas a la nube)",
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
        self.entry_api_key = ctk.CTkEntry(fila_key, width=330, height=36, corner_radius=12, show="•")
        if self.ia and self.ia.api_key:
            self.entry_api_key.insert(0, self.ia.api_key)
        self.entry_api_key.pack(side="left", padx=4)
        self.entry_api_key.bind("<Return>", lambda _e: self._guardar_key_ia())

        self._mostrando_key = False

        def _ver_key():
            self._mostrando_key = not self._mostrando_key
            self.entry_api_key.configure(show="" if self._mostrando_key else "•")

        ctk.CTkButton(fila_key, text="👁", width=40, height=36, corner_radius=10, fg_color=self.tema["btn_stage_pill"], command=_ver_key).pack(side="left", padx=4)
        ctk.CTkButton(fila_key, text="💾 Guardar en .env", height=36, corner_radius=12, fg_color=self.tema["btn_stage_pill"], command=self._guardar_key_ia).pack(side="left", padx=4)
        self.btn_probar_ia = ctk.CTkButton(fila_key, text="⚡ Probar Conexión Cloud", height=36, corner_radius=12, fg_color=self.tema["btn_green"], hover_color=self.tema["btn_green_hover"], font=ctk.CTkFont(size=12, weight="bold"), command=self._probar_conexion_ia)
        self.btn_probar_ia.pack(side="left", padx=6)

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
            "🔒 Modo Privado Estricto activo (100% local, cero red)."
            if activo
            else "☁️ Modo Híbrido activo (IA y Voz Neuronal habilitadas)."
        )

    def _guardar_key_ia(self) -> None:
        if not self.ia:
            return
        self.ia.configurar_api_key(self.entry_api_key.get().strip())
        self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia())
        self.notificar("💾 Clave guardada localmente en .env (excluida al empaquetar .zip).")

    def _probar_conexion_ia(self) -> None:
        if not self.ia:
            return
        self.ia.configurar_api_key(self.entry_api_key.get().strip())
        self.btn_probar_ia.configure(state="disabled", text="⏳ Probando...")

        def _worker():
            ok, detalle = self.ia.probar_conexion_cloud()
            self.after(0, lambda: (
                self.btn_probar_ia.configure(state="normal", text="⚡ Probar Conexión Cloud"),
                self.lbl_estado_ia.configure(text=self.ia.obtener_estado_ia()),
                messagebox.showinfo("Diagnóstico Gemini API", detalle, parent=self) if ok else messagebox.showwarning("Diagnóstico Gemini API", detalle, parent=self),
            ) if self.winfo_exists() else None)

        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # SECCIÓN 4: SEGURIDAD PIN, ARDUINO UNO R3 Y MARCO NORMATIVO
    # =========================================================================
    def _vista_seguridad_arduino(self) -> None:
        marco = ctk.CTkScrollableFrame(self.contenedor, fg_color="transparent")
        marco.grid(row=0, column=0, sticky="nsew")
        marco.grid_columnconfigure((0, 1), weight=1)

        # --- Tarjeta PIN ---
        card_pin = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_pin.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))

        ctk.CTkLabel(card_pin, text="🔐 Cambiar PIN de Acceso Adulto", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=18, pady=(16, 4))
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
            self.notificar("🔐 PIN actualizado y cifrado con éxito.")

        self.ent_pin_actual.bind("<Return>", lambda _e: self.ent_pin_nuevo.focus_set())
        self.ent_pin_nuevo.bind("<Return>", lambda _e: _actualizar_pin())
        ctk.CTkButton(card_pin, text="Actualizar PIN Seguro", fg_color=self.tema["btn_green"], hover_color=self.tema["btn_green_hover"], corner_radius=14, height=38, font=ctk.CTkFont(size=13, weight="bold"), command=_actualizar_pin).pack(anchor="w", padx=18, pady=(8, 16))

        # --- Tarjeta Hardware Arduino UNO R3 ---
        card_hw = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_hw.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))

        ctk.CTkLabel(card_hw, text="🔌 Semáforo Físico Arduino UNO R3", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=18, pady=(16, 4))

        en_sim = getattr(self.hardware, "en_simulacion", True)
        puerto_txt = getattr(self.hardware, "puerto_actual", "Simulación Virtual")
        self.lbl_hw_estado = ctk.CTkLabel(
            card_hw,
            text=f"{'🟡 Modo Simulación Activo' if en_sim else '🟢 Placa Física Conectada'} ({puerto_txt})",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_secondary"],
        )
        self.lbl_hw_estado.pack(anchor="w", padx=18, pady=(0, 8))

        puerto_pref = self.db.obtener_preferencia("puerto_arduino", "COM15") if self.db else "COM15"
        puertos = (self.hardware.listar_puertos_disponibles() if self.hardware else []) or ["COM15", "COM3", "COM4", "COM5"]
        if puerto_pref and puerto_pref not in puertos:
            puertos = [puerto_pref] + list(puertos)
        fila_p = ctk.CTkFrame(card_hw, fg_color="transparent")
        fila_p.pack(fill="x", padx=18, pady=4)

        self.combo_com = ctk.CTkOptionMenu(fila_p, values=puertos, width=130, height=34, corner_radius=10, fg_color=self.tema["btn_stage_pill"])
        self.combo_com.set(puerto_pref if puerto_pref in puertos else puertos[0])
        self.combo_com.pack(side="left", padx=(0, 8))

        self.btn_reconectar_hw = ctk.CTkButton(
            fila_p,
            text="🔄 Conectar",
            width=116,
            height=34,
            corner_radius=10,
            fg_color=self.tema["btn_orange"],
            hover_color=self.tema["btn_orange_hover"],
        )

        def _reconectar():
            if not self.hardware:
                return
            p = self.combo_com.get()
            if self.db:
                self.db.guardar_preferencia("puerto_arduino", p)
            self.btn_reconectar_hw.configure(state="disabled", text="⏳ Buscando...")

            def _worker_hw():
                ok = self.hardware.conectar(p)
                self.after(
                    0,
                    lambda: (
                        self.btn_reconectar_hw.configure(state="normal", text="🔄 Conectar"),
                        self.lbl_hw_estado.configure(
                            text=f"{'🟢 Conectado en ' + p if ok else '🟡 Sin placa en ' + p + ' (Simulación)'}"
                        ),
                        self.notificar("🔌 Estado de Arduino actualizado."),
                    )
                    if self.winfo_exists()
                    else None,
                )

            threading.Thread(target=_worker_hw, daemon=True, name="HaruArduinoProbe").start()

        self.btn_reconectar_hw.configure(command=_reconectar)
        self.btn_reconectar_hw.pack(side="left")

        fila_leds = ctk.CTkFrame(card_hw, fg_color="transparent")
        fila_leds.pack(fill="x", padx=18, pady=(10, 16))
        if self.hardware:
            for txt, fn in [
                ("🟢 Inicio", lambda: self.hardware.actualizar_progreso(1, 3)),
                ("🟡 Avance", lambda: self.hardware.actualizar_progreso(2, 3)),
                ("🔴 Meta", lambda: self.hardware.celebrar_victoria()),
                ("⭕ Apagar", lambda: self.hardware.apagar_todo()),
            ]:
                ctk.CTkButton(fila_leds, text=txt, width=78, height=32, corner_radius=10, fg_color=self.tema["btn_stage_pill"], font=ctk.CTkFont(size=11, weight="bold"), command=fn).pack(side="left", padx=3)

        # --- Tarjeta Marco Legal Boliviano ---
        card_leg = ctk.CTkFrame(marco, fg_color=self.tema["card_bg"], border_color=self.tema["card_border"], border_width=2, corner_radius=20)
        card_leg.grid(row=1, column=0, columnspan=2, sticky="ew")

        ctk.CTkLabel(card_leg, text="⚖️ Respaldo Normativo y Pedagógico — Universidad Salesiana de Bolivia", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.tema["text_primary"]).pack(anchor="w", padx=18, pady=(14, 4))
        texto_normas = (
            "• Ley N.º 070 (Avelino Siñani - Elizardo Pérez) y R.M. N.º 0069/2025: Educación inclusiva y adaptaciones curriculares para estudiantes con TDAH.\n"
            "• Ley N.º 548 (Código Niña, Niño y Adolescente): Cero almacenamiento de grabaciones de voz ni datos biométricos; Modo Privado 100% local disponible.\n"
            "• Ley N.º 164 (Tecnologías de Información y Comunicación): Uso soberano de herramientas accesibles y software portable.\n"
            "• Inspiración Salesiana (Sistema Preventivo): Acompañamiento cercano, paciente y alegre centrado en el bienestar integral del niño."
        )
        ctk.CTkLabel(card_leg, text=texto_normas, font=ctk.CTkFont(size=12), text_color=self.tema["text_secondary"], justify="left", wraplength=740).pack(anchor="w", padx=18, pady=(0, 16))
