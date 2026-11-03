"""
Modales Modernos en CustomTkinter: PIN Docente, Álbum de Trofeos y Entrada de Voz/Texto
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Incluye corrección de foco en Windows para `CTkToplevel`, teclado numérico táctil +
teclado físico, bloqueo persistente de seguridad PIN y álbum visual de recompensas.
"""

from typing import Callable, Dict, Optional

import customtkinter as ctk


def _fijar_foco_modal(ventana: ctk.CTkToplevel) -> None:
    if not ventana.winfo_exists():
        return
    try:
        ventana.lift()
        ventana.focus_force()
        ventana.grab_set()
    except Exception:
        pass


class ModalPinDocente(ctk.CTkToplevel):
    """Acceso protegido al Panel Docente y Familiar con PBKDF2 y bloqueo persistente."""

    def __init__(self, parent, repositorio_db, tema: Dict[str, str],
                 on_autorizado: Callable[[], None]):
        super().__init__(parent)
        self.db = repositorio_db
        self.tema = tema
        self.on_autorizado = on_autorizado
        self._pin = ""
        self._cerrado = False

        self.title("Acceso Docente / Familia")
        self.geometry("390x490")
        self.resizable(False, False)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)

        self._construir_ui()
        self.bind("<Key>", self._manejar_tecla_fisica)
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.after(150, lambda: _fijar_foco_modal(self))
        self._actualizar_estado_bloqueo()

    def _construir_ui(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=24,
        )
        card.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            card,
            text="🔐 Espacio Docente y Familia",
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(pady=(16, 4))

        pin_personalizado = self.db.obtener_preferencia("pin_personalizado", "0") == "1"
        subtitulo = (
            "Ingresa tu PIN de seguridad de 4 dígitos"
            if pin_personalizado
            else "Ingresa el PIN (inicial por defecto: 1234)"
        )
        ctk.CTkLabel(
            card,
            text=subtitulo,
            font=ctk.CTkFont(size=12),
            text_color=self.tema["text_secondary"],
        ).pack(pady=(0, 10))

        self.lbl_puntos = ctk.CTkLabel(
            card,
            text="○  ○  ○  ○",
            fg_color=self.tema["card_inner"],
            corner_radius=14,
            height=48,
            width=240,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_puntos.pack(pady=6)

        self.lbl_feedback = ctk.CTkLabel(
            card,
            text="Protección activa para evitar cambios accidentales",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_secondary"],
            wraplength=310,
        )
        self.lbl_feedback.pack(pady=(4, 8))

        pad = ctk.CTkFrame(card, fg_color="transparent")
        pad.pack(pady=4)

        botones = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("⌫", 3, 0), ("0", 3, 1), ("✔", 3, 2),
        ]
        self._botones_pad = []
        for txt, fila, col in botones:
            es_ok = txt == "✔"
            es_borrar = txt == "⌫"
            btn = ctk.CTkButton(
                pad,
                text=txt,
                width=76,
                height=50,
                corner_radius=16,
                fg_color=(
                    self.tema["btn_green"]
                    if es_ok
                    else (self.tema["btn_orange"] if es_borrar else self.tema["btn_stage_pill"])
                ),
                hover_color=(
                    self.tema["btn_green_hover"]
                    if es_ok
                    else (self.tema["btn_orange_hover"] if es_borrar else self.tema["btn_stage_pill_hover"])
                ),
                font=ctk.CTkFont(size=18, weight="bold"),
                command=lambda t=txt: self._presionar_boton(t),
            )
            btn.grid(row=fila, column=col, padx=5, pady=5)
            self._botones_pad.append(btn)

        ctk.CTkButton(
            card,
            text="Cancelar",
            fg_color="transparent",
            hover_color=self.tema["card_inner"],
            text_color=self.tema["text_secondary"],
            height=32,
            command=self.cerrar,
        ).pack(pady=(6, 10))

    def _manejar_tecla_fisica(self, event) -> None:
        if event.char and event.char.isdigit():
            self._presionar_boton(event.char)
        elif event.keysym == "BackSpace":
            self._presionar_boton("⌫")
        elif event.keysym in ("Return", "KP_Enter"):
            self._presionar_boton("✔")
        elif event.keysym == "Escape":
            self.cerrar()

    def _presionar_boton(self, tecla: str) -> None:
        bloqueado, _ = self.db.esta_pin_bloqueado()
        if bloqueado:
            return
        if tecla == "⌫":
            self._pin = self._pin[:-1]
            self._refrescar_puntos()
        elif tecla == "✔":
            self._validar_pin()
        elif tecla.isdigit() and len(self._pin) < 6:
            self._pin += tecla
            self._refrescar_puntos()
            if len(self._pin) == 4:
                self.after(90, self._validar_pin)

    def _refrescar_puntos(self) -> None:
        n = len(self._pin)
        total = max(4, n)
        puntos = ["●" if i < n else "○" for i in range(total)]
        self.lbl_puntos.configure(text="  ".join(puntos))

    def _validar_pin(self) -> None:
        if not self._pin:
            return
        exito, restantes, seg_bloqueo = self.db.registrar_intento_pin(self._pin)
        if exito:
            self.cerrar()
            self.on_autorizado()
            return

        self._pin = ""
        self._refrescar_puntos()
        if seg_bloqueo > 0:
            self._actualizar_estado_bloqueo()
        else:
            self.lbl_feedback.configure(
                text=f"PIN incorrecto. Te quedan {restantes} intentos.",
                text_color="#dc2626",
            )

    def _actualizar_estado_bloqueo(self) -> None:
        if self._cerrado or not self.winfo_exists():
            return
        bloqueado, seg = self.db.esta_pin_bloqueado()
        if bloqueado:
            for b in self._botones_pad:
                b.configure(state="disabled")
            self.lbl_feedback.configure(
                text=f"⏳ Teclado bloqueado por seguridad: espera {seg}s",
                text_color="#dc2626",
            )
            self.after(1000, self._actualizar_estado_bloqueo)
        else:
            for b in self._botones_pad:
                b.configure(state="normal")

    def cerrar(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()


class ModalAlbumPremios(ctk.CTkToplevel):
    """Álbum motivacional de medallas, trajes desbloqueables y tienda de canje TDAH."""

    MEDALLAS = [
        ("🌱 Semilla Curiosa", 5, "¡Comenzaste tu aventura de estudio junto a Haru!"),
        ("⚡ Súper Enfoque", 12, "¡Completaste tus primeros micro-pasos con gran atención!"),
        ("🚀 Explorador Galáctico", 25, "¡Dominas tus misiones escolares paso a paso!"),
        ("🏆 Campeón Dorado Haru", 45, "¡Maestro del orden, la constancia y la alegría!"),
    ]

    def __init__(self, parent, estrellas: int, tareas_logradas: int, tema: Dict[str, str],
                 repositorio_db=None,
                 skin_actual: Optional[str] = None,
                 on_equipar_skin: Optional[Callable[[str], None]] = None,
                 on_premio_canjeado: Optional[Callable[[str, int], None]] = None):
        super().__init__(parent)
        self.tema = tema
        self.db = repositorio_db
        self.estrellas = estrellas
        self.tareas_logradas = tareas_logradas
        self.skin_actual = (
            skin_actual
            or (self.db.obtener_preferencia("avatar_skin", "ROBOT_KAWAII") if self.db else "ROBOT_KAWAII")
        )
        self.on_equipar_skin = on_equipar_skin
        self.on_premio_canjeado = on_premio_canjeado

        self.title("Álbum de Trofeos, Trajes y Premios — Haru")
        self.geometry("620x560")
        self.resizable(False, False)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)

        self.card = ctk.CTkFrame(
            self,
            fg_color=tema["card_bg"],
            border_color=tema["card_border"],
            border_width=2,
            corner_radius=24,
        )
        self.card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            self.card,
            text="🏆 Mi Álbum de Trofeos y Recompensas",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=tema["text_primary"],
        ).pack(pady=(14, 4))

        disponibles = self.db.obtener_estrellas_disponibles() if self.db else estrellas
        self.lbl_resumen_top = ctk.CTkLabel(
            self.card,
            text=f"⭐ Nivel Total: {estrellas}   •   🎟️ Para Canjear: {disponibles} ⭐   •   🎯 Misiones: {tareas_logradas}",
            fg_color=tema["badge_gold_bg"],
            text_color=tema["badge_gold_text"],
            corner_radius=14,
            padx=14,
            pady=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.lbl_resumen_top.pack(pady=(2, 8))

        # Selector de pestañas (Medallas y Trajes / Canje de Premios)
        barra_tabs = ctk.CTkFrame(self.card, fg_color="transparent")
        barra_tabs.pack(pady=(0, 6))

        self.btn_tab_logros = ctk.CTkButton(
            barra_tabs,
            text="🏅 Medallas y Trajes",
            width=195,
            height=34,
            corner_radius=14,
            fg_color=tema["btn_green"],
            hover_color=tema["btn_green_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._mostrar_tab("logros"),
        )
        self.btn_tab_logros.pack(side="left", padx=5)

        self.btn_tab_tienda = ctk.CTkButton(
            barra_tabs,
            text="🎁 Canjear Premios",
            width=195,
            height=34,
            corner_radius=14,
            fg_color=tema["btn_stage_pill"],
            hover_color=tema["btn_stage_pill_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._mostrar_tab("tienda"),
        )
        self.btn_tab_tienda.pack(side="left", padx=5)

        self.lbl_aviso = ctk.CTkLabel(
            self.card,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#15803d",
            wraplength=540,
        )
        self.lbl_aviso.pack(pady=(0, 2))

        self.lista = ctk.CTkScrollableFrame(self.card, fg_color="transparent", height=320)
        self.lista.pack(fill="both", expand=True, padx=12, pady=2)

        ctk.CTkButton(
            self.card,
            text="¡Seguir aprendiendo con Haru!",
            fg_color=tema["btn_green"],
            hover_color=tema["btn_green_hover"],
            corner_radius=18,
            height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.cerrar,
        ).pack(pady=(6, 12))

        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Escape>", lambda _e: self.cerrar())
        self._mostrar_tab("logros")
        self.after(150, lambda: _fijar_foco_modal(self))

    def cerrar(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()

    def _refrescar_cabecera(self) -> None:
        if self.db:
            self.estrellas = self.db.obtener_estrellas()
            disp = self.db.obtener_estrellas_disponibles()
        else:
            disp = self.estrellas
        self.lbl_resumen_top.configure(
            text=f"⭐ Nivel Total: {self.estrellas}   •   🎟️ Para Canjear: {disp} ⭐   •   🎯 Misiones: {self.tareas_logradas}"
        )

    def _mostrar_tab(self, tab: str) -> None:
        for w in self.lista.winfo_children():
            w.destroy()

        es_logros = tab == "logros"
        self.btn_tab_logros.configure(fg_color=self.tema["btn_green"] if es_logros else self.tema["btn_stage_pill"])
        self.btn_tab_tienda.configure(fg_color=self.tema["btn_purple"] if not es_logros else self.tema["btn_stage_pill"])

        if es_logros:
            self._render_logros_y_trajes()
        else:
            self._render_tienda_premios()

    def _render_logros_y_trajes(self) -> None:
        from ui.avatar_sprite import REQUISITOS_SKIN

        ctk.CTkLabel(
            self.lista,
            text="🎭 Trajes Especiales de Haru (Se desbloquean con tu Nivel Total ⭐)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(4, 4))

        for clave_sk, (req, icono, nombre) in REQUISITOS_SKIN.items():
            desbl = self.estrellas >= req
            fila_sk = ctk.CTkFrame(
                self.lista,
                fg_color=self.tema["card_inner"] if desbl else self.tema["card_bg"],
                border_color=self.tema["btn_green"] if desbl else self.tema["card_border"],
                border_width=2 if desbl else 1,
                corner_radius=14,
            )
            fila_sk.pack(fill="x", padx=6, pady=4)

            ctk.CTkLabel(
                fila_sk,
                text=f"{icono}  {nombre}",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
            ).pack(side="left", padx=12, pady=8)

            if desbl:
                en_uso = clave_sk == self.skin_actual
                ctk.CTkButton(
                    fila_sk,
                    text="✅ En Uso" if en_uso else "✨ Usar Traje",
                    width=116,
                    height=28,
                    corner_radius=10,
                    fg_color=self.tema["btn_stage_pill"] if en_uso else self.tema["btn_green"],
                    hover_color=self.tema["btn_stage_pill_hover"] if en_uso else self.tema["btn_green_hover"],
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda k=clave_sk, n=nombre: self._equipar(k, n),
                ).pack(side="right", padx=10, pady=6)
            else:
                ctk.CTkLabel(
                    fila_sk,
                    text=f"🔒 Meta: {req} ⭐ (faltan {req - self.estrellas})",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=self.tema["text_secondary"],
                ).pack(side="right", padx=12)

        ctk.CTkLabel(
            self.lista,
            text="🏅 Medallas de Constancia",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(10, 4))

        for titulo, meta, desc in self.MEDALLAS:
            desbloqueada = self.estrellas >= meta
            item = ctk.CTkFrame(
                self.lista,
                fg_color=self.tema["card_inner"] if desbloqueada else self.tema["card_bg"],
                border_color="#f59e0b" if desbloqueada else self.tema["card_border"],
                border_width=2,
                corner_radius=16,
            )
            item.pack(fill="x", padx=6, pady=5)

            estado_txt = "✅ ¡DESBLOQUEADO!" if desbloqueada else f"🔒 Meta: {meta} ⭐"
            cab = ctk.CTkFrame(item, fg_color="transparent")
            cab.pack(fill="x", padx=12, pady=(8, 2))
            ctk.CTkLabel(
                cab,
                text=titulo,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
            ).pack(side="left")
            ctk.CTkLabel(
                cab,
                text=estado_txt,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#15803d" if desbloqueada else self.tema["text_secondary"],
            ).pack(side="right")

            ctk.CTkLabel(
                item,
                text=desc,
                font=ctk.CTkFont(size=12),
                text_color=self.tema["text_secondary"],
                anchor="w",
                wraplength=510,
                justify="left",
            ).pack(fill="x", padx=12, pady=(0, 6))

            prog = ctk.CTkProgressBar(item, height=8, progress_color="#f59e0b")
            prog.set(min(1.0, self.estrellas / float(meta)))
            prog.pack(fill="x", padx=12, pady=(0, 10))

    def _equipar(self, clave_sk: str, nombre: str) -> None:
        self.skin_actual = clave_sk
        if self.on_equipar_skin:
            self.on_equipar_skin(clave_sk)
        self.lbl_aviso.configure(text=f"🎉 ¡Haru ahora lleva el traje de {nombre}!", text_color="#15803d")
        self._mostrar_tab("logros")

    def _render_tienda_premios(self) -> None:
        ctk.CTkLabel(
            self.lista,
            text="🎁 Canjea tus estrellas disponibles por premios reales con mamá, papá o tu profe\n(¡Tus medallas y trajes nunca se pierden al canjear!)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_secondary"],
            justify="left",
            anchor="w",
            wraplength=530,
        ).pack(fill="x", padx=8, pady=(4, 8))

        disponibles = self.db.obtener_estrellas_disponibles() if self.db else self.estrellas
        catalogo = self.db.listar_recompensas_catalogo() if self.db else []

        for r in catalogo:
            costo = int(r["costo_estrellas"])
            alcanza = disponibles >= costo
            card_r = ctk.CTkFrame(
                self.lista,
                fg_color=self.tema["card_inner"] if alcanza else self.tema["card_bg"],
                border_color=self.tema["btn_purple"] if alcanza else self.tema["card_border"],
                border_width=2 if alcanza else 1,
                corner_radius=14,
            )
            card_r.pack(fill="x", padx=6, pady=5)

            col_txt = ctk.CTkFrame(card_r, fg_color="transparent")
            col_txt.pack(side="left", fill="both", expand=True, padx=12, pady=8)

            ctk.CTkLabel(
                col_txt,
                text=r["titulo"],
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
                anchor="w",
                wraplength=360,
                justify="left",
            ).pack(fill="x")
            if r.get("descripcion"):
                ctk.CTkLabel(
                    col_txt,
                    text=r["descripcion"],
                    font=ctk.CTkFont(size=11),
                    text_color=self.tema["text_secondary"],
                    anchor="w",
                    wraplength=360,
                    justify="left",
                ).pack(fill="x")

            ctk.CTkButton(
                card_r,
                text=f"🎁 Canjear ({costo} ⭐)" if alcanza else f"Faltan {costo - disponibles} ⭐",
                state="normal" if alcanza else "disabled",
                width=142,
                height=34,
                corner_radius=12,
                fg_color=self.tema["btn_purple"] if alcanza else self.tema["btn_stage_pill"],
                hover_color=self.tema["btn_purple_hover"],
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda rid=r["id"]: self._canjear(rid),
            ).pack(side="right", padx=12, pady=8)

        canjes = self.db.obtener_historial_canjes(limite=5) if self.db else []
        if canjes:
            ctk.CTkLabel(
                self.lista,
                text="✨ Últimos premios canjeados:",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.tema["text_primary"],
                anchor="w",
            ).pack(fill="x", padx=8, pady=(10, 2))
            for c in canjes:
                ctk.CTkLabel(
                    self.lista,
                    text=f"• {c['fecha_hora']} — {c['titulo_premio']} (-{c['costo_estrellas']} ⭐)",
                    font=ctk.CTkFont(size=11),
                    text_color=self.tema["text_secondary"],
                    anchor="w",
                    wraplength=520,
                ).pack(fill="x", padx=12, pady=1)

    def _canjear(self, recompensa_id: int) -> None:
        if not self.db:
            return
        ok, msg, nuevo_saldo = self.db.canjear_recompensa(recompensa_id)
        self.lbl_aviso.configure(text=msg, text_color="#15803d" if ok else "#dc2626")
        self._refrescar_cabecera()
        self._mostrar_tab("tienda")
        if ok and self.on_premio_canjeado:
            self.on_premio_canjeado(msg, nuevo_saldo)


class ModalEntradaVozTexto(ctk.CTkToplevel):
    """Cuadro interactivo amigable cuando la PC no tiene micrófono o internet."""

    def __init__(self, parent, motivo: str, tema: Dict[str, str],
                 on_enviar: Callable[[str], None]):
        super().__init__(parent)
        self.on_enviar = on_enviar
        self.title("Hablar con Haru")
        self.geometry("460x270")
        self.resizable(False, False)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)

        card = ctk.CTkFrame(
            self,
            fg_color=tema["card_bg"],
            border_color=tema["card_border"],
            border_width=2,
            corner_radius=22,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text="💬 Cuéntale a Haru",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=tema["text_primary"],
        ).pack(pady=(14, 4))

        ctk.CTkLabel(
            card,
            text=f"{motivo}\nEscribe «listo», «pista», «descanso» o cualquier pregunta escolar:",
            font=ctk.CTkFont(size=12),
            text_color=tema["text_secondary"],
            wraplength=400,
        ).pack(pady=(0, 10))

        self.entrada = ctk.CTkEntry(
            card,
            placeholder_text="Ej: ¿Cuánto es 15 más 7? / listo / pista...",
            width=390,
            height=40,
            corner_radius=16,
            font=ctk.CTkFont(size=13),
        )
        self.entrada.pack(pady=4)
        self.entrada.bind("<Return>", lambda _e: self._confirmar())

        fila = ctk.CTkFrame(card, fg_color="transparent")
        fila.pack(pady=12)
        ctk.CTkButton(
            fila,
            text="Enviar a Haru 🚀",
            fg_color=tema["btn_green"],
            hover_color=tema["btn_green_hover"],
            corner_radius=16,
            width=155,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirmar,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            fila,
            text="Cancelar",
            fg_color=tema["btn_stage_pill"],
            hover_color=tema["btn_stage_pill_hover"],
            corner_radius=16,
            width=110,
            height=38,
            command=self.cerrar,
        ).pack(side="left", padx=6)

        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Escape>", lambda _e: self.cerrar())
        self.after(150, lambda: (_fijar_foco_modal(self), self.entrada.focus_set()))

    def cerrar(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()

    def _confirmar(self) -> None:
        txt = self.entrada.get().strip()
        self.cerrar()
        if txt:
            self.on_enviar(txt)

