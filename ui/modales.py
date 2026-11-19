"""
Modales Modernos en CustomTkinter: PIN Docente, Álbum de Trofeos, Comprobación Activa y Voz/Texto
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Incluye corrección de foco en Windows para `CTkToplevel`, iconografía vectorial limpia
100% offline (`icono_ctk`, `icono_skin_ctk`), bloqueo persistente de seguridad PIN,
álbum visual de recompensas y Micro-Validación Interactiva por paso (Opción B).
"""

from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

from ui.iconos import aplicar_icono_ventana_haru, icono_ctk, icono_skin_ctk


def _fijar_foco_modal(ventana: ctk.CTkToplevel) -> None:
    if not ventana.winfo_exists():
        return
    try:
        aplicar_icono_ventana_haru(ventana)
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
        self._after_foco_id = self.after(150, lambda: _fijar_foco_modal(self))
        self._after_bloqueo_id = None
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
            text="  Espacio Docente y Familia",
            image=icono_ctk("lock", self.tema["text_primary"], 20),
            compound="left",
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
            ("Borrar", 3, 0), ("0", 3, 1), ("OK", 3, 2),
        ]
        self._botones_pad = []
        for txt, fila, col in botones:
            es_ok = txt == "OK"
            es_borrar = txt == "Borrar"
            btn = ctk.CTkButton(
                pad,
                text="" if es_ok else txt,
                image=icono_ctk("check", "#ffffff", 18) if es_ok else None,
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
                font=ctk.CTkFont(size=14 if es_borrar else 18, weight="bold"),
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
            self._presionar_boton("Borrar")
        elif event.keysym in ("Return", "KP_Enter"):
            self._presionar_boton("OK")
        elif event.keysym == "Escape":
            self.cerrar()

    def _presionar_boton(self, tecla: str) -> None:
        bloqueado, _ = self.db.esta_pin_bloqueado()
        if bloqueado:
            return
        if tecla in ("Borrar", "⌫"):
            self._pin = self._pin[:-1]
            self._refrescar_puntos()
        elif tecla in ("OK", "✔"):
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
                text=f"Teclado bloqueado por seguridad: espera {seg}s",
                text_color="#dc2626",
            )
            self._after_bloqueo_id = self.after(1000, self._actualizar_estado_bloqueo)
        else:
            for b in self._botones_pad:
                b.configure(state="normal")

    def cerrar(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        for attr in ("_after_foco_id", "_after_bloqueo_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()


class ModalAlbumPremios(ctk.CTkToplevel):
    """Álbum motivacional de medallas, trajes desbloqueables y tienda de canje TDAH."""

    MEDALLAS = [
        ("leaf", "Semilla Curiosa", 5, "¡Comenzaste tu aventura de estudio junto a Haru!"),
        ("bolt", "Súper Enfoque", 12, "¡Completaste tus primeros micro-pasos con gran atención!"),
        ("sparkles", "Explorador Galáctico", 25, "¡Dominas tus misiones escolares paso a paso!"),
        ("trophy", "Campeón Dorado Haru", 45, "¡Maestro del orden, la constancia y la alegría!"),
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
            text="  Mi Álbum de Trofeos y Recompensas",
            image=icono_ctk("trophy", "#d97706", 22),
            compound="left",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=tema["text_primary"],
        ).pack(pady=(14, 4))

        disponibles = self.db.obtener_estrellas_disponibles() if self.db else estrellas
        self.lbl_resumen_top = ctk.CTkLabel(
            self.card,
            text=f"  Nivel Total: {estrellas}   •   Para Canjear: {disponibles} pts   •   Misiones: {tareas_logradas}",
            image=icono_ctk("star", tema["badge_gold_text"], 16),
            compound="left",
            fg_color=tema["badge_gold_bg"],
            text_color=tema["badge_gold_text"],
            corner_radius=14,
            padx=14,
            pady=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.lbl_resumen_top.pack(pady=(2, 8))

        barra_tabs = ctk.CTkFrame(self.card, fg_color="transparent")
        barra_tabs.pack(pady=(0, 6))

        self.btn_tab_logros = ctk.CTkButton(
            barra_tabs,
            text="Medallas y Trajes",
            image=icono_ctk("trophy", "#ffffff", 16),
            compound="left",
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
            text="Canjear Premios",
            image=icono_ctk("gift", "#ffffff", 16),
            compound="left",
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
            text="Seguir aprendiendo con Haru",
            image=icono_ctk("check", "#ffffff", 16),
            compound="left",
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
        self._after_foco_id = self.after(150, lambda: _fijar_foco_modal(self))

    def cerrar(self) -> None:
        if getattr(self, "_after_foco_id", None):
            try:
                self.after_cancel(self._after_foco_id)
            except Exception:
                pass
            self._after_foco_id = None
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
            text=f"  Nivel Total: {self.estrellas}   •   Para Canjear: {disp} pts   •   Misiones: {self.tareas_logradas}"
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
            text="  Trajes Especiales de Haru (Se desbloquean con tu Nivel Total)",
            image=icono_ctk("sparkles", self.tema["text_primary"], 16),
            compound="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(4, 4))

        for clave_sk, (req, _icono, nombre) in REQUISITOS_SKIN.items():
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
                text=f"  {nombre}",
                image=icono_skin_ctk(clave_sk, bloqueado=not desbl, size=32),
                compound="left",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
            ).pack(side="left", padx=12, pady=6)

            if desbl:
                en_uso = clave_sk == self.skin_actual
                ctk.CTkButton(
                    fila_sk,
                    text="En Uso" if en_uso else "Usar Traje",
                    image=icono_ctk("check" if en_uso else "sparkles", "#ffffff", 14),
                    compound="left",
                    width=122,
                    height=30,
                    corner_radius=10,
                    fg_color=self.tema["btn_stage_pill"] if en_uso else self.tema["btn_green"],
                    hover_color=self.tema["btn_stage_pill_hover"] if en_uso else self.tema["btn_green_hover"],
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda k=clave_sk, n=nombre: self._equipar(k, n),
                ).pack(side="right", padx=10, pady=6)
            else:
                ctk.CTkLabel(
                    fila_sk,
                    text=f"  Meta: {req} pts (faltan {req - self.estrellas})",
                    image=icono_ctk("lock", self.tema["text_secondary"], 14),
                    compound="left",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=self.tema["text_secondary"],
                ).pack(side="right", padx=12)

        ctk.CTkLabel(
            self.lista,
            text="  Medallas de Constancia",
            image=icono_ctk("trophy", "#d97706", 16),
            compound="left",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
            anchor="w",
        ).pack(fill="x", padx=8, pady=(10, 4))

        for ico_nom, titulo, meta, desc in self.MEDALLAS:
            desbloqueada = self.estrellas >= meta
            item = ctk.CTkFrame(
                self.lista,
                fg_color=self.tema["card_inner"] if desbloqueada else self.tema["card_bg"],
                border_color="#f59e0b" if desbloqueada else self.tema["card_border"],
                border_width=2,
                corner_radius=16,
            )
            item.pack(fill="x", padx=6, pady=5)

            estado_txt = "  DESBLOQUEADO" if desbloqueada else f"  Meta: {meta} pts"
            cab = ctk.CTkFrame(item, fg_color="transparent")
            cab.pack(fill="x", padx=12, pady=(8, 2))
            ctk.CTkLabel(
                cab,
                text=f"  {titulo}",
                image=icono_ctk(ico_nom, "#d97706" if desbloqueada else self.tema["text_secondary"], 17),
                compound="left",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=self.tema["text_primary"],
            ).pack(side="left")
            ctk.CTkLabel(
                cab,
                text=estado_txt,
                image=icono_ctk("check" if desbloqueada else "lock", "#15803d" if desbloqueada else self.tema["text_secondary"], 14),
                compound="left",
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
        self.lbl_aviso.configure(text=f"¡Haru ahora lleva el traje de {nombre}!", text_color="#15803d")
        self._mostrar_tab("logros")

    def _render_tienda_premios(self) -> None:
        ctk.CTkLabel(
            self.lista,
            text="Canjea tus puntos disponibles por premios reales con mamá, papá o tu profe\n(Tus medallas y trajes nunca se pierden al canjear).",
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
                text=f"  {r['titulo']}",
                image=icono_ctk("gift", self.tema["btn_purple"] if alcanza else self.tema["text_secondary"], 16),
                compound="left",
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
                text=f"Canjear ({costo} pts)" if alcanza else f"Faltan {costo - disponibles} pts",
                image=icono_ctk("star", "#ffffff", 14) if alcanza else None,
                compound="left",
                state="normal" if alcanza else "disabled",
                width=148,
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
                text="  Últimos premios canjeados:",
                image=icono_ctk("check", "#15803d", 14),
                compound="left",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.tema["text_primary"],
                anchor="w",
            ).pack(fill="x", padx=8, pady=(10, 2))
            for c in canjes:
                ctk.CTkLabel(
                    self.lista,
                    text=f"• {c['fecha_hora']} — {c['titulo_premio']} (-{c['costo_estrellas']} pts)",
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


class ModalComprobacionPaso(ctk.CTkToplevel):
    """
    Opción B — Micro-Validación Interactiva de Haru (Comprobación Activa).
    Formula una pregunta breve sobre el paso actual y acepta respuesta táctil o por voz.
    """

    def __init__(
        self,
        parent,
        reto: Dict,
        numero_paso: int,
        tema: Dict[str, str],
        validador: Callable[[str], Tuple[bool, str]],
        on_superado: Callable[[], None],
        on_hablar: Optional[Callable[[str], None]] = None,
        on_activar_voz: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.reto = reto
        self.numero_paso = numero_paso
        self.tema = tema
        self.validador = validador
        self.on_superado = on_superado
        self.on_hablar = on_hablar
        self.on_activar_voz = on_activar_voz
        self._cerrado = False
        self._resuelto = False
        self.intentos_fallidos = 0

        self.title(f"Comprobación Activa — Paso {numero_paso}")
        self.geometry("560x455")
        self.resizable(False, False)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)

        self._construir_ui()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Escape>", lambda _e: self.cerrar())
        self._after_foco_id = self.after(130, lambda: _fijar_foco_modal(self))
        self._after_hablar_id = None
        self._after_exito_id = None
        if self.on_hablar and self.reto.get("pregunta"):
            self._after_hablar_id = self.after(180, lambda: self.on_hablar(self.reto["pregunta"]) if not self._cerrado else None)

    def _construir_ui(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=self.tema["card_bg"],
            border_color=self.tema["card_border"],
            border_width=2,
            corner_radius=24,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text=f"  Comprobación Rápida con Haru — Paso {self.numero_paso}",
            image=icono_ctk("shield", self.tema["btn_green"], 22),
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(pady=(14, 6))

        marco_preg = ctk.CTkFrame(
            card,
            fg_color=self.tema["hint_bg"],
            border_color=self.tema["hint_border"],
            border_width=2,
            corner_radius=18,
        )
        marco_preg.pack(fill="x", padx=18, pady=(2, 10))

        self.lbl_pregunta = ctk.CTkLabel(
            marco_preg,
            text=self.reto.get("pregunta", "¿Completaste este paso?"),
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self.tema["text_primary"],
            wraplength=480,
            justify="center",
        )
        self.lbl_pregunta.pack(padx=14, pady=12)

        # Botones grandes de opciones táctiles
        marco_opciones = ctk.CTkFrame(card, fg_color="transparent")
        marco_opciones.pack(fill="x", padx=18, pady=(2, 8))

        opciones = list(self.reto.get("opciones", []))
        es_corto = all(len(str(op)) <= 10 for op in opciones) and len(opciones) <= 4
        if es_corto:
            fila_h = ctk.CTkFrame(marco_opciones, fg_color="transparent")
            fila_h.pack()
            for op in opciones:
                ctk.CTkButton(
                    fila_h,
                    text=str(op),
                    height=46,
                    width=max(106, min(145, 460 // max(1, len(opciones)))),
                    corner_radius=16,
                    fg_color=self.tema["btn_stage_pill"],
                    hover_color=self.tema["btn_green"],
                    font=ctk.CTkFont(size=16, weight="bold"),
                    command=lambda r=str(op): self.evaluar_respuesta(r),
                ).pack(side="left", padx=5, pady=4)
        else:
            for op in opciones:
                ctk.CTkButton(
                    marco_opciones,
                    text=str(op),
                    height=40,
                    corner_radius=14,
                    fg_color=self.tema["btn_stage_pill"],
                    hover_color=self.tema["btn_green"],
                    font=ctk.CTkFont(size=14, weight="bold"),
                    command=lambda r=str(op): self.evaluar_respuesta(r),
                ).pack(fill="x", pady=3)

        # Fila de respuesta hablada por micrófono o escrita
        fila_voz = ctk.CTkFrame(card, fg_color="transparent")
        fila_voz.pack(fill="x", padx=18, pady=(4, 4))
        fila_voz.grid_columnconfigure(1, weight=1)

        self.btn_voz = ctk.CTkButton(
            fila_voz,
            text="Decir en Voz Alta",
            image=icono_ctk("mic", "#ffffff", 16),
            compound="left",
            width=162,
            height=38,
            corner_radius=16,
            fg_color=self.tema["btn_purple"],
            hover_color=self.tema["btn_purple_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._iniciar_escucha_voz,
        )
        self.btn_voz.grid(row=0, column=0, padx=(0, 8))

        self.entrada_voz_texto = ctk.CTkEntry(
            fila_voz,
            placeholder_text="O escribe tu respuesta aquí...",
            height=38,
            corner_radius=14,
            font=ctk.CTkFont(size=13),
        )
        self.entrada_voz_texto.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.entrada_voz_texto.bind("<Return>", lambda _e: self._confirmar_texto())

        ctk.CTkButton(
            fila_voz,
            text="",
            image=icono_ctk("send", "#ffffff", 16),
            width=42,
            height=38,
            corner_radius=14,
            fg_color=self.tema["btn_green"],
            hover_color=self.tema["btn_green_hover"],
            command=self._confirmar_texto,
        ).grid(row=0, column=2)

        self.lbl_feedback = ctk.CTkLabel(
            card,
            text="Elige un botón o díselo en voz alta a Haru para ganar tu punto del paso.",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.tema["text_secondary"],
            wraplength=490,
        )
        self.lbl_feedback.pack(pady=(4, 4))

        ctk.CTkButton(
            card,
            text="Volver a revisar mi paso",
            image=icono_ctk("arrow_left", self.tema["text_secondary"], 14),
            compound="left",
            fg_color="transparent",
            hover_color=self.tema["card_inner"],
            text_color=self.tema["text_secondary"],
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.cerrar,
        ).pack(pady=(0, 10))

    def _iniciar_escucha_voz(self) -> None:
        if self._cerrado or self._resuelto:
            return
        if self.on_activar_voz:
            self.mostrar_escuchando(True)
            self.on_activar_voz()
        else:
            self.entrada_voz_texto.focus_set()

    def mostrar_escuchando(self, activo: bool) -> None:
        if self._cerrado or not self.winfo_exists():
            return
        if activo:
            self.btn_voz.configure(text="Escuchando...", fg_color="#dc2626")
            self.lbl_feedback.configure(
                text="Haru te está escuchando: di tu respuesta fuerte y claro...",
                text_color=self.tema["text_primary"],
            )
        else:
            self.btn_voz.configure(text="Decir en Voz Alta", fg_color=self.tema["btn_purple"])

    def recibir_respuesta_voz(self, texto: str) -> None:
        """Recibe la transcripción del micrófono mientras el modal está abierto."""
        if self._cerrado or self._resuelto or not self.winfo_exists():
            return
        self.mostrar_escuchando(False)
        limpio = (texto or "").strip()
        if limpio:
            self.entrada_voz_texto.delete(0, "end")
            self.entrada_voz_texto.insert(0, limpio)
            self.evaluar_respuesta(limpio)

    def _confirmar_texto(self) -> None:
        txt = self.entrada_voz_texto.get().strip()
        if txt:
            self.evaluar_respuesta(txt)

    def evaluar_respuesta(self, respuesta: str) -> bool:
        if self._cerrado or self._resuelto:
            return False
        proximo_intento = self.intentos_fallidos + 1
        try:
            correcta, mensaje = self.validador(respuesta, proximo_intento)
        except TypeError:
            correcta, mensaje = self.validador(respuesta)
        if correcta:
            self.intentos_fallidos = 0
            self._resuelto = True
            self.lbl_feedback.configure(text=mensaje, text_color="#15803d")
            self._after_exito_id = self.after(260, self._finalizar_exito)
            return True

        self.intentos_fallidos = proximo_intento
        self.lbl_feedback.configure(text=mensaje, text_color="#d97706")
        if self.on_hablar:
            self.on_hablar(mensaje)
        return False

    def _finalizar_exito(self) -> None:
        self._after_exito_id = None
        self.cerrar()
        self.on_superado()

    def cerrar(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        for attr in ("_after_foco_id", "_after_hablar_id", "_after_exito_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()


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
            text="  Cuéntale a Haru",
            image=icono_ctk("mic", tema["text_primary"], 20),
            compound="left",
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
            text="Enviar a Haru",
            image=icono_ctk("send", "#ffffff", 15),
            compound="left",
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
        self._after_foco_id = self.after(150, lambda: (_fijar_foco_modal(self), self.entrada.focus_set()))

    def cerrar(self) -> None:
        if getattr(self, "_after_foco_id", None):
            try:
                self.after_cancel(self._after_foco_id)
            except Exception:
                pass
            self._after_foco_id = None
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


class ModalAprobadorTareasDocumento(ctk.CTkToplevel):
    """
    Ventana de previsualización e importación inteligente de tareas extraídas de un
    archivo escolar (.pdf, .docx, .txt, .md, .csv) en el Panel Docente.
    Soporta documentos mixtos (etiquetando cada tarea con su Módulo auto-detectado
    como [Matemáticas] o [Inglés]), permite elegir cuáles entran o subir todas de golpe.
    """

    MODULOS = ["Matemáticas", "Lenguaje", "Ciencias", "Inglés", "Hábitos y Orden"]

    def __init__(
        self,
        parent,
        nombre_archivo: str,
        tareas_propuestas: List[Dict],
        tema: Dict[str, str],
        on_aprobar_lote: Callable[[List[Dict]], None],
    ):
        super().__init__(parent)
        self.nombre_archivo = nombre_archivo
        self.tareas_propuestas = list(tareas_propuestas or [])
        self.tema = tema
        self.on_aprobar_lote = on_aprobar_lote
        self._filas_ui: List[Dict] = []

        self.title(f"Tareas Detectadas en {nombre_archivo}")
        self.geometry("760x560")
        self.minsize(680, 480)
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

        cab = ctk.CTkFrame(card, fg_color="transparent")
        cab.pack(fill="x", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            cab,
            text=f"  Guía Analizada: {nombre_archivo}",
            image=icono_ctk("file_text", tema["btn_purple"], 20),
            compound="left",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=tema["text_primary"],
        ).pack(side="left")

        ctk.CTkLabel(
            cab,
            text=f"  Pensum guardado • {len(self.tareas_propuestas)} tareas propuestas",
            image=icono_ctk("check", "#15803d", 15),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#15803d",
        ).pack(side="right")

        ctk.CTkLabel(
            card,
            text=(
                "Haru clasificó automáticamente el módulo de cada tarea ([Matemáticas], [Inglés], etc.). "
                "Puedes ajustar cualquier título o módulo, marcar cuáles entran o subir todas de golpe:"
            ),
            font=ctk.CTkFont(size=12),
            text_color=tema["text_secondary"],
            justify="left",
            anchor="w",
            wraplength=700,
        ).pack(fill="x", padx=18, pady=(0, 8))

        self.lista_scroll = ctk.CTkScrollableFrame(
            card,
            fg_color=tema["card_inner"],
            corner_radius=16,
        )
        self.lista_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        for idx, t in enumerate(self.tareas_propuestas, start=1):
            item = ctk.CTkFrame(
                self.lista_scroll,
                fg_color=tema["card_bg"],
                border_color=tema["card_border"],
                border_width=1,
                corner_radius=14,
            )
            item.pack(fill="x", padx=6, pady=5)

            fila_top = ctk.CTkFrame(item, fg_color="transparent")
            fila_top.pack(fill="x", padx=10, pady=(8, 4))

            var_chk = ctk.BooleanVar(value=True)
            chk = ctk.CTkCheckBox(
                fila_top,
                text=f"Tarea #{idx}",
                variable=var_chk,
                width=90,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=tema["text_primary"],
                fg_color=tema["btn_green"],
            )
            chk.pack(side="left", padx=(2, 8))

            entry_tit = ctk.CTkEntry(
                fila_top,
                height=32,
                corner_radius=10,
                font=ctk.CTkFont(size=13, weight="bold"),
            )
            entry_tit.insert(0, str(t.get("nombre", f"Actividad {idx}")))
            entry_tit.pack(side="left", fill="x", expand=True, padx=(0, 8))

            cat_ini = str(t.get("categoria", "Matemáticas"))
            if cat_ini not in self.MODULOS:
                cat_ini = "Matemáticas"
            combo_mod = ctk.CTkOptionMenu(
                fila_top,
                values=self.MODULOS,
                width=155,
                height=32,
                corner_radius=10,
                fg_color=tema["btn_purple"],
                button_color=tema["btn_purple_hover"],
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            combo_mod.set(cat_ini)
            combo_mod.pack(side="right")

            pasos_preview = "  •  ".join(
                f"P{i}: {p[:58]}" for i, p in enumerate(t.get("pasos", [])[:4], start=1)
            )
            ctk.CTkLabel(
                item,
                text=pasos_preview,
                font=ctk.CTkFont(size=11),
                text_color=tema["text_secondary"],
                anchor="w",
                justify="left",
                wraplength=670,
            ).pack(fill="x", padx=14, pady=(0, 8))

            self._filas_ui.append({
                "var_chk": var_chk,
                "entry_tit": entry_tit,
                "combo_mod": combo_mod,
                "datos_base": t,
            })

        barra = ctk.CTkFrame(card, fg_color="transparent")
        barra.pack(fill="x", padx=18, pady=(2, 14))

        ctk.CTkButton(
            barra,
            text="Cancelar",
            fg_color=tema["btn_stage_pill"],
            hover_color=tema["btn_stage_pill_hover"],
            corner_radius=14,
            width=110,
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.cerrar,
        ).pack(side="left")

        ctk.CTkButton(
            barra,
            text="Subir Todas de Golpe",
            image=icono_ctk("sparkles", "#ffffff", 15),
            compound="left",
            fg_color=tema["btn_purple"],
            hover_color=tema["btn_purple_hover"],
            corner_radius=14,
            width=195,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._confirmar_importacion(forzar_todas=True),
        ).pack(side="right")

        ctk.CTkButton(
            barra,
            text="Agregar Seleccionadas",
            image=icono_ctk("check", "#ffffff", 15),
            compound="left",
            fg_color=tema["btn_green"],
            hover_color=tema["btn_green_hover"],
            corner_radius=14,
            width=195,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._confirmar_importacion(forzar_todas=False),
        ).pack(side="right", padx=8)

        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.bind("<Escape>", lambda _e: self.cerrar())
        self._after_foco_id = self.after(150, lambda: _fijar_foco_modal(self))

    def _confirmar_importacion(self, forzar_todas: bool = False) -> None:
        seleccionadas: List[Dict] = []
        for fila in self._filas_ui:
            if forzar_todas or fila["var_chk"].get():
                base = dict(fila["datos_base"])
                titulo = fila["entry_tit"].get().strip() or base.get("nombre", "Actividad Escolar")
                base["nombre"] = titulo
                base["categoria"] = fila["combo_mod"].get()
                seleccionadas.append(base)
        self.cerrar()
        if seleccionadas and self.on_aprobar_lote:
            self.on_aprobar_lote(seleccionadas)

    def cerrar(self) -> None:
        if getattr(self, "_after_foco_id", None):
            try:
                self.after_cancel(self._after_foco_id)
            except Exception:
                pass
            self._after_foco_id = None
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()

