"""
Zona de Juegos Cognitivos para CustomTkinter — Asistente TDAH "Haru"
Usa 100% los colores de `ui/theme.py` (CALMA, DIA, NOCHE) y los iconos de `ui/iconos.py`.
"""

import random
import tkinter as tk
from typing import Callable, Dict, Optional

import customtkinter as ctk

from ui.iconos import aplicar_icono_ventana_haru, icono_ctk


class CeldaTablero(ctk.CTkFrame):
    """Casilla vectorial en Canvas que respeta completamente el tema activo."""

    def __init__(self, parent, indice: int, tema: Dict[str, str], al_hacer_clic: Callable[[int], None]):
        super().__init__(
            parent,
            fg_color=tema["card_inner"],
            corner_radius=16,
            border_width=2,
            border_color=tema["card_border"],
            width=114,
            height=114,
        )
        self.pack_propagate(False)
        self.indice = indice
        self.tema = tema
        self.al_hacer_clic = al_hacer_clic
        self.marca = ""
        self.bloqueada = False

        self.canvas = tk.Canvas(
            self,
            width=94,
            height=94,
            bg=tema["card_inner"],
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.pack(expand=True)

        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def _on_click(self, _event=None) -> None:
        if not self.bloqueada:
            self.al_hacer_clic(self.indice)

    def _on_enter(self, _event=None) -> None:
        if not self.bloqueada and self.marca == "":
            self.configure(border_color=self.tema["hint_border"])

    def _on_leave(self, _event=None) -> None:
        if not self.bloqueada and self.marca == "":
            self.configure(border_color=self.tema["card_border"])

    def establecer_marca(self, marca: str) -> None:
        self.marca = marca
        self.canvas.delete("all")
        self.configure(fg_color=self.tema["card_inner"])
        self.canvas.configure(bg=self.tema["card_inner"])

        if marca == "X":
            color_x = self.tema["btn_purple"]
            self.configure(border_color=color_x)
            self.canvas.create_line(
                22, 22, 72, 72,
                fill=color_x, width=10, capstyle=tk.ROUND,
            )
            self.canvas.create_line(
                72, 22, 22, 72,
                fill=color_x, width=10, capstyle=tk.ROUND,
            )
        elif marca == "O":
            color_o = self.tema["btn_magenta"]
            self.configure(border_color=color_o)
            self.canvas.create_oval(
                20, 20, 74, 74,
                outline=color_o, width=10,
            )
        else:
            self.configure(border_color=self.tema["card_border"])

    def marcar_pista(self) -> None:
        if self.marca == "":
            self.configure(
                fg_color=self.tema["badge_gold_bg"],
                border_color=self.tema["badge_gold_text"],
            )
            self.canvas.configure(bg=self.tema["badge_gold_bg"])
            self.canvas.delete("all")
            self.canvas.create_oval(
                36, 36, 58, 58,
                outline=self.tema["badge_gold_text"], width=4,
            )

    def limpiar_pista(self) -> None:
        if self.marca == "":
            self.establecer_marca("")

    def marcar_victoria(self) -> None:
        self.configure(
            fg_color=self.tema["hint_bg"],
            border_color=self.tema["btn_green"],
        )
        self.canvas.configure(bg=self.tema["hint_bg"])


class ModalMenuJuegos(ctk.CTkToplevel):
    """Menú principal de la Zona de Juegos con Tres en Raya y Memorama."""

    def __init__(
        self,
        parent,
        tema: Dict[str, str],
        funcion_hablar: Optional[Callable[[str], None]] = None,
        on_victoria: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        aplicar_icono_ventana_haru(self)
        self.parent = parent
        self.tema = tema
        self.funcion_hablar = funcion_hablar
        self.on_victoria = on_victoria

        self.title("Zona de Juegos — Haru")
        self.geometry("640x460")
        self.resizable(False, False)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)

        self._construir_ui()
        self.after(120, self._fijar_foco)

    def _fijar_foco(self) -> None:
        if self.winfo_exists():
            try:
                self.lift()
                self.focus_force()
                self.grab_set()
            except Exception:
                pass

    def _construir_ui(self) -> None:
        t = self.tema

        marco = ctk.CTkFrame(
            self,
            fg_color=t["card_bg"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=24,
        )
        marco.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            marco,
            text="  Zona de Juegos",
            image=icono_ctk("trophy", t["btn_purple"], 22),
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=t["text_primary"],
        ).pack(pady=(18, 4))

        ctk.CTkLabel(
            marco,
            text="Elige un desafío corto para entrenar tu atención y planificación con Haru",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=t["text_secondary"],
        ).pack(pady=(0, 14))

        grid = ctk.CTkFrame(marco, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        grid.grid_columnconfigure((0, 1), weight=1)
        grid.grid_rowconfigure(0, weight=1)

        # Juego 1: Tres en Raya
        card1 = ctk.CTkFrame(
            grid,
            fg_color=t["card_inner"],
            border_color=t["hint_border"],
            border_width=2,
            corner_radius=20,
        )
        card1.grid(row=0, column=0, padx=8, pady=4, sticky="nsew")

        ctk.CTkLabel(
            card1,
            text="PLANIFICACIÓN",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=t["badge_gold_bg"],
            text_color=t["badge_gold_text"],
            corner_radius=10,
            padx=10,
            pady=3,
        ).pack(pady=(14, 6))

        self._dibujar_icono_tictactoe(card1)

        ctk.CTkLabel(
            card1,
            text="Tres en Raya",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=t["text_primary"],
        ).pack(pady=(6, 2))

        ctk.CTkLabel(
            card1,
            text="3 dificultades, pistas\ny racha de victorias.",
            font=ctk.CTkFont(size=12),
            text_color=t["text_secondary"],
            justify="center",
        ).pack(pady=(0, 12))

        ctk.CTkButton(
            card1,
            text="Jugar ahora",
            image=icono_ctk("play", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_green"],
            hover_color=t["btn_green_hover"],
            border_color=t["btn_green_border"],
            border_width=2,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._abrir_tictactoe,
        ).pack(fill="x", padx=18, pady=(0, 14))

        # Juego 2: Memorama
        card2 = ctk.CTkFrame(
            grid,
            fg_color=t["card_inner"],
            border_color=t["hint_border"],
            border_width=2,
            corner_radius=20,
        )
        card2.grid(row=0, column=1, padx=8, pady=4, sticky="nsew")

        ctk.CTkLabel(
            card2,
            text="MEMORIA VISUAL",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=t["badge_gold_bg"],
            text_color=t["badge_gold_text"],
            corner_radius=10,
            padx=10,
            pady=3,
        ).pack(pady=(14, 6))

        ctk.CTkLabel(
            card2,
            text="",
            image=icono_ctk("eye", t["btn_purple"], 56),
        ).pack(pady=14)

        ctk.CTkLabel(
            card2,
            text="Memorama",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=t["text_primary"],
        ).pack(pady=(6, 2))

        ctk.CTkLabel(
            card2,
            text="Encuentra parejas de íconos\ncon 2 niveles y pista visual.",
            font=ctk.CTkFont(size=12),
            text_color=t["text_secondary"],
            justify="center",
        ).pack(pady=(0, 12))

        ctk.CTkButton(
            card2,
            text="Jugar ahora",
            image=icono_ctk("play", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_green"],
            hover_color=t["btn_green_hover"],
            border_color=t["btn_green_border"],
            border_width=2,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._abrir_memorama,
        ).pack(fill="x", padx=18, pady=(0, 14))

        footer = ctk.CTkFrame(marco, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(4, 14))

        ctk.CTkButton(
            footer,
            text="Volver a mi tarea",
            image=icono_ctk("arrow_left", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
            border_width=1,
            text_color=t["text_on_stage"],
            corner_radius=16,
            height=38,
            width=170,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.destroy,
        ).pack(side="right")

    def _dibujar_icono_tictactoe(self, parent) -> None:
        t = self.tema
        cv = tk.Canvas(
            parent,
            width=82,
            height=82,
            bg=t["card_inner"],
            highlightthickness=0,
        )
        cv.pack(pady=2)
        cv.create_line(29, 10, 29, 72, fill=t["card_border"], width=3)
        cv.create_line(53, 10, 53, 72, fill=t["card_border"], width=3)
        cv.create_line(10, 29, 72, 29, fill=t["card_border"], width=3)
        cv.create_line(10, 53, 72, 53, fill=t["card_border"], width=3)

        cv.create_line(14, 14, 24, 24, fill=t["btn_purple"], width=3, capstyle=tk.ROUND)
        cv.create_line(24, 14, 14, 24, fill=t["btn_purple"], width=3, capstyle=tk.ROUND)
        cv.create_oval(35, 35, 47, 47, outline=t["btn_magenta"], width=3)
        cv.create_line(58, 58, 68, 68, fill=t["btn_purple"], width=3, capstyle=tk.ROUND)
        cv.create_line(68, 58, 58, 68, fill=t["btn_purple"], width=3, capstyle=tk.ROUND)

    def _abrir_tictactoe(self) -> None:
        self.destroy()
        ventana = VentanaTicTacToe(
            self.parent,
            tema=self.tema,
            funcion_hablar=self.funcion_hablar,
            on_victoria=self.on_victoria,
        )
        if hasattr(self.parent, "_ventana_secundaria"):
            self.parent._ventana_secundaria = ventana

    def _abrir_memorama(self) -> None:
        self.destroy()
        ventana = VentanaMemorama(
            self.parent,
            tema=self.tema,
            funcion_hablar=self.funcion_hablar,
            on_victoria=self.on_victoria,
        )
        if hasattr(self.parent, "_ventana_secundaria"):
            self.parent._ventana_secundaria = ventana


class VentanaTicTacToe(ctk.CTkToplevel):
    """Tres en Raya con 3 dificultades, pistas, deshacer (anti-farming), racha y colores del tema."""

    LINEAS_GANADORAS = (
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    )

    def __init__(
        self,
        parent,
        tema: Dict[str, str],
        funcion_hablar: Optional[Callable[[str], None]] = None,
        on_victoria: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        aplicar_icono_ventana_haru(self)
        self.tema = tema
        self.hablar = funcion_hablar
        self.on_victoria = on_victoria

        self.tablero = [""] * 9
        self.historial = []
        self.turno_jugador = True
        self.juego_activo = True
        self.dificultad = "Normal"
        self.after_id = None

        self.puntos_nino = 0
        self.puntos_haru = 0
        self.empates = 0
        self.racha = 0

        self.title("Tres en Raya — Haru")
        scr_w = self.winfo_screenwidth()
        scr_h = self.winfo_screenheight()
        ancho_win = min(560, max(500, scr_w - 60))
        alto_win = min(740, max(640, scr_h - 80))
        pos_x = max(0, (scr_w - ancho_win) // 2)
        pos_y = max(0, (scr_h - alto_win - 36) // 2)
        self.geometry(f"{ancho_win}x{alto_win}+{pos_x}+{pos_y}")
        self.minsize(500, 620)
        self.resizable(True, True)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cerrar_ventana)

        self._construir_ui()
        self.after(120, self._fijar_foco)
        self._emitir_voz("¡Vamos a jugar Tres en Raya! Tú eres la X. Es tu turno.")

    def _fijar_foco(self) -> None:
        if self.winfo_exists():
            try:
                self.lift()
                self.focus_force()
                self.grab_set()
            except Exception:
                pass

    def _emitir_voz(self, texto: str) -> None:
        if self.hablar:
            try:
                self.hablar(texto)
            except Exception as e:
                print(f"[TicTacToe] Error de voz: {e}")

    def _cancelar_temporizador(self) -> None:
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _cerrar_ventana(self) -> None:
        self._cancelar_temporizador()
        self.destroy()

    def _construir_ui(self) -> None:
        t = self.tema

        card = ctk.CTkFrame(
            self,
            fg_color=t["card_bg"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=24,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 10))

        ctk.CTkLabel(
            top,
            text="  Tres en Raya",
            image=icono_ctk("trophy", t["btn_purple"], 20),
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=t["text_primary"],
        ).pack(side="left")

        self.seg_dificultad = ctk.CTkSegmentedButton(
            top,
            values=["Fácil", "Normal", "Desafío"],
            command=self._cambiar_dificultad,
            fg_color=t["card_inner"],
            selected_color=t["btn_purple"],
            selected_hover_color=t["btn_purple_hover"],
            unselected_color=t["card_inner"],
            unselected_hover_color=t["hint_bg"],
            text_color=t["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.seg_dificultad.set("Normal")
        self.seg_dificultad.pack(side="right")

        stats = ctk.CTkFrame(card, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=(0, 10))
        stats.grid_columnconfigure((0, 1, 2), weight=1)

        self.card_nino = ctk.CTkFrame(
            stats,
            fg_color=t["card_inner"],
            corner_radius=14,
            border_width=2,
            border_color=t["btn_purple"],
        )
        self.card_nino.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkLabel(
            self.card_nino, text="TÚ (X)", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=t["btn_purple"],
        ).pack(pady=(6, 0))
        self.lbl_pts_nino = ctk.CTkLabel(
            self.card_nino, text="0", font=ctk.CTkFont(size=22, weight="bold"),
            text_color=t["text_primary"],
        )
        self.lbl_pts_nino.pack(pady=(0, 6))

        self.card_centro = ctk.CTkFrame(
            stats,
            fg_color=t["card_inner"],
            corner_radius=14,
            border_width=2,
            border_color=t["card_border"],
        )
        self.card_centro.grid(row=0, column=1, padx=6, sticky="ew")
        ctk.CTkLabel(
            self.card_centro, text="EMPATES", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=t["text_secondary"],
        ).pack(pady=(6, 0))
        self.lbl_empates = ctk.CTkLabel(
            self.card_centro, text="0", font=ctk.CTkFont(size=22, weight="bold"),
            text_color=t["text_primary"],
        )
        self.lbl_empates.pack(pady=(0, 6))

        self.card_haru = ctk.CTkFrame(
            stats,
            fg_color=t["card_inner"],
            corner_radius=14,
            border_width=2,
            border_color=t["card_border"],
        )
        self.card_haru.grid(row=0, column=2, padx=(6, 0), sticky="ew")
        ctk.CTkLabel(
            self.card_haru, text="HARU (O)", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=t["btn_magenta"],
        ).pack(pady=(6, 0))
        self.lbl_pts_haru = ctk.CTkLabel(
            self.card_haru, text="0", font=ctk.CTkFont(size=22, weight="bold"),
            text_color=t["text_primary"],
        )
        self.lbl_pts_haru.pack(pady=(0, 6))

        banner = ctk.CTkFrame(
            card,
            fg_color=t["hint_bg"],
            border_color=t["hint_border"],
            border_width=1,
            corner_radius=14,
        )
        banner.pack(fill="x", padx=20, pady=(0, 12))

        self.lbl_estado = ctk.CTkLabel(
            banner,
            text="Tu turno: elige una casilla",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=t["text_primary"],
        )
        self.lbl_estado.pack(side="left", padx=14, pady=9)

        self.lbl_racha = ctk.CTkLabel(
            banner,
            text=" Racha: 0",
            image=icono_ctk("star", t["badge_gold_text"], 14),
            compound="left",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=t["badge_gold_bg"],
            text_color=t["badge_gold_text"],
            corner_radius=10,
            padx=10,
            pady=4,
        )
        self.lbl_racha.pack(side="right", padx=10, pady=6)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=20, pady=(4, 14))

        ctk.CTkButton(
            footer,
            text="Nueva Ronda",
            image=icono_ctk("refresh", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_green"],
            hover_color=t["btn_green_hover"],
            border_color=t["btn_green_border"],
            border_width=2,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._reiniciar_juego,
        ).pack(side="left", expand=True, fill="x", padx=(0, 8))

        ctk.CTkButton(
            footer,
            text="Volver",
            image=icono_ctk("arrow_left", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
            border_width=1,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=42,
            width=110,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._cerrar_ventana,
        ).pack(side="right")

        herramientas = ctk.CTkFrame(card, fg_color="transparent")
        herramientas.pack(side="bottom", fill="x", padx=20, pady=(8, 4))
        herramientas.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            herramientas,
            text="Pedir Pista",
            image=icono_ctk("bolt", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_orange"],
            hover_color=t["btn_orange_hover"],
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._usar_pista,
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            herramientas,
            text="Deshacer",
            image=icono_ctk("rotate_ccw", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
            border_width=1,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._deshacer_jugada,
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

        marco_tablero = ctk.CTkFrame(
            card,
            fg_color=t["card_bg"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=20,
        )
        marco_tablero.pack(expand=True, padx=20, pady=2)

        self.celdas = []
        for i in range(9):
            celda = CeldaTablero(marco_tablero, i, t, self._jugada_nino)
            celda.grid(row=i // 3, column=i % 3, padx=7, pady=7)
            self.celdas.append(celda)

    def _cambiar_dificultad(self, valor: str) -> None:
        self.dificultad = valor
        self._reiniciar_juego()

    def _actualizar_indicador_turno(self, es_nino: bool) -> None:
        t = self.tema
        if es_nino:
            self.card_nino.configure(border_color=t["btn_purple"])
            self.card_haru.configure(border_color=t["card_border"])
        else:
            self.card_nino.configure(border_color=t["card_border"])
            self.card_haru.configure(border_color=t["btn_magenta"])

    def _limpiar_pistas(self) -> None:
        for celda in self.celdas:
            celda.limpiar_pista()

    def _jugada_nino(self, idx: int) -> None:
        if not self.juego_activo or not self.turno_jugador or self.tablero[idx] != "":
            return

        self._limpiar_pistas()
        self.tablero[idx] = "X"
        self.celdas[idx].establecer_marca("X")
        self.historial.append([idx, None])

        if self._verificar_estado("X"):
            return

        self.turno_jugador = False
        self._actualizar_indicador_turno(False)
        self.lbl_estado.configure(
            text="Haru está pensando su jugada...",
            text_color=self.tema["text_secondary"],
        )
        self.after_id = self.after(600, self._jugada_haru)

    def _jugada_haru(self) -> None:
        self.after_id = None
        if not self.winfo_exists() or not self.juego_activo:
            return

        idx = self._elegir_movimiento_ia()
        if idx is not None:
            self.tablero[idx] = "O"
            self.celdas[idx].establecer_marca("O")
            if self.historial:
                self.historial[-1][1] = idx

            if self._verificar_estado("O"):
                return

        self.turno_jugador = True
        self._actualizar_indicador_turno(True)
        self.lbl_estado.configure(
            text="Tu turno: elige una casilla",
            text_color=self.tema["text_primary"],
        )

    def _elegir_movimiento_ia(self) -> Optional[int]:
        libres = [i for i, v in enumerate(self.tablero) if v == ""]
        if not libres:
            return None

        if self.dificultad == "Fácil":
            if random.random() < 0.30:
                jugada = self._buscar_jugada_critica("O") or self._buscar_jugada_critica("X")
                if jugada is not None:
                    return jugada
            return random.choice(libres)

        if self.dificultad == "Normal":
            jugada = self._buscar_jugada_critica("O")
            if jugada is not None:
                return jugada
            jugada = self._buscar_jugada_critica("X")
            if jugada is not None:
                return jugada
            if 4 in libres and random.random() < 0.7:
                return 4
            return random.choice(libres)

        return self._mejor_jugada_minimax("O")

    def _buscar_jugada_critica(self, marca: str) -> Optional[int]:
        for a, b, c in self.LINEAS_GANADORAS:
            vals = [self.tablero[a], self.tablero[b], self.tablero[c]]
            if vals.count(marca) == 2 and vals.count("") == 1:
                for pos in (a, b, c):
                    if self.tablero[pos] == "":
                        return pos
        return None

    def _mejor_jugada_minimax(self, marca_objetivo: str) -> Optional[int]:
        mejor_puntaje = -999
        mejor_movimiento = None
        rival = "X" if marca_objetivo == "O" else "O"

        for i in range(9):
            if self.tablero[i] == "":
                self.tablero[i] = marca_objetivo
                puntaje = self._minimax(False, marca_objetivo, rival, 0)
                self.tablero[i] = ""
                if puntaje > mejor_puntaje:
                    mejor_puntaje = puntaje
                    mejor_movimiento = i
        return mejor_movimiento

    def _minimax(self, es_max: bool, yo: str, rival: str, profundidad: int) -> int:
        ganador = self._obtener_ganador()
        if ganador == yo:
            return 10 - profundidad
        if ganador == rival:
            return profundidad - 10
        if "" not in self.tablero:
            return 0

        if es_max:
            mejor = -999
            for i in range(9):
                if self.tablero[i] == "":
                    self.tablero[i] = yo
                    mejor = max(mejor, self._minimax(False, yo, rival, profundidad + 1))
                    self.tablero[i] = ""
            return mejor
        peor = 999
        for i in range(9):
            if self.tablero[i] == "":
                self.tablero[i] = rival
                peor = min(peor, self._minimax(True, yo, rival, profundidad + 1))
                self.tablero[i] = ""
        return peor

    def _obtener_ganador(self) -> Optional[str]:
        for a, b, c in self.LINEAS_GANADORAS:
            if self.tablero[a] and self.tablero[a] == self.tablero[b] == self.tablero[c]:
                return self.tablero[a]
        return None

    def _usar_pista(self) -> None:
        if not self.juego_activo or not self.turno_jugador:
            return
        self._limpiar_pistas()
        sugerida = self._mejor_jugada_minimax("X")
        if sugerida is not None:
            self.celdas[sugerida].marcar_pista()
            self.lbl_estado.configure(
                text="Pista activa: revisa la casilla resaltada",
                text_color=self.tema["badge_gold_text"],
            )

    def _deshacer_jugada(self) -> None:
        # Bloquea deshacer tras finalizar la ronda para evitar farming de estrellas
        if not self.juego_activo or not self.historial or not self.turno_jugador:
            return
        self._cancelar_temporizador()
        self._limpiar_pistas()

        ultimo_nino, ultimo_haru = self.historial.pop()
        if ultimo_haru is not None:
            self.tablero[ultimo_haru] = ""
            self.celdas[ultimo_haru].establecer_marca("")
        if ultimo_nino is not None:
            self.tablero[ultimo_nino] = ""
            self.celdas[ultimo_nino].establecer_marca("")

        self.juego_activo = True
        for celda in self.celdas:
            celda.bloqueada = False
        self._actualizar_indicador_turno(True)
        self.lbl_estado.configure(
            text="Jugada revertida. Es tu turno.",
            text_color=self.tema["text_primary"],
        )

    def _verificar_estado(self, marca: str) -> bool:
        t = self.tema
        for a, b, c in self.LINEAS_GANADORAS:
            if self.tablero[a] == self.tablero[b] == self.tablero[c] == marca:
                self.juego_activo = False
                for celda in self.celdas:
                    celda.bloqueada = True
                for pos in (a, b, c):
                    self.celdas[pos].marcar_victoria()

                if marca == "X":
                    self.puntos_nino += 1
                    self.racha += 1
                    self.lbl_pts_nino.configure(text=str(self.puntos_nino))
                    self.lbl_racha.configure(text=f" Racha: {self.racha}")
                    self.lbl_estado.configure(
                        text="¡Ganaste la ronda! Excelente jugada.",
                        text_color=t["btn_green"],
                    )
                    self._emitir_voz("¡Excelente, ganaste esta ronda! Muy buena estrategia.")
                    if self.on_victoria:
                        self.on_victoria()
                else:
                    self.puntos_haru += 1
                    self.racha = 0
                    self.lbl_pts_haru.configure(text=str(self.puntos_haru))
                    self.lbl_racha.configure(text=" Racha: 0")
                    self.lbl_estado.configure(
                        text="Ganó Haru. Estuviste muy cerca.",
                        text_color=t["btn_magenta"],
                    )
                    self._emitir_voz("Gané esta ronda, pero estuviste muy cerca. Intentemos otra vez.")
                return True

        if "" not in self.tablero:
            self.juego_activo = False
            self.empates += 1
            self.lbl_empates.configure(text=str(self.empates))
            for celda in self.celdas:
                celda.bloqueada = True
            self.lbl_estado.configure(
                text="Empate. Ambos jugaron muy bien.",
                text_color=t["badge_gold_text"],
            )
            self._emitir_voz("Es un empate. Qué buena partida.")
            return True

        return False

    def _reiniciar_juego(self) -> None:
        self._cancelar_temporizador()
        self.tablero = [""] * 9
        self.historial.clear()
        self.turno_jugador = True
        self.juego_activo = True
        self._actualizar_indicador_turno(True)
        self.lbl_estado.configure(
            text="Tu turno: elige una casilla",
            text_color=self.tema["text_primary"],
        )
        for celda in self.celdas:
            celda.bloqueada = False
            celda.establecer_marca("")


class VentanaMemorama(ctk.CTkToplevel):
    """Juego de Memoria Visual usando 100% los temas de ui/theme.py y los iconos de ui/iconos.py."""

    ICONOS_DISPONIBLES = [
        ("star", "btn_orange"),
        ("leaf", "btn_green"),
        ("sun", "badge_gold_text"),
        ("moon", "btn_purple"),
        ("gift", "btn_magenta"),
        ("bolt", "btn_orange"),
        ("globe", "btn_stage_pill"),
        ("trophy", "btn_purple"),
    ]

    def __init__(
        self,
        parent,
        tema: Dict[str, str],
        funcion_hablar: Optional[Callable[[str], None]] = None,
        on_victoria: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        aplicar_icono_ventana_haru(self)
        self.tema = tema
        self.hablar = funcion_hablar
        self.on_victoria = on_victoria

        self.dificultad = "Fácil"
        self.cartas = []
        self.botones = []
        self.emparejadas = set()
        self.seleccionadas = []
        self.bloqueado = False
        self.movimientos = 0
        self.espias_disponibles = 1
        self._after_ids = []

        self.title("Memorama — Haru")
        scr_w = self.winfo_screenwidth()
        scr_h = self.winfo_screenheight()
        ancho_win = min(600, max(540, scr_w - 60))
        alto_win = min(760, max(650, scr_h - 80))
        self._alto_ventana = alto_win
        pos_x = max(0, (scr_w - ancho_win) // 2)
        pos_y = max(0, (scr_h - alto_win - 36) // 2)
        self.geometry(f"{ancho_win}x{alto_win}+{pos_x}+{pos_y}")
        self.minsize(540, 640)
        self.resizable(True, True)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cerrar_ventana)

        self._construir_ui()
        self._iniciar_partida()
        self.after(120, self._fijar_foco)

    def _fijar_foco(self) -> None:
        if self.winfo_exists():
            try:
                self.lift()
                self.focus_force()
                self.grab_set()
            except Exception:
                pass

    def _emitir_voz(self, texto: str) -> None:
        if self.hablar:
            try:
                self.hablar(texto)
            except Exception as e:
                print(f"[Memorama] Error de voz: {e}")

    def _programar(self, ms: int, callback: Callable[[], None]) -> None:
        aid = self.after(ms, callback)
        self._after_ids.append(aid)

    def _cancelar_temporizadores(self) -> None:
        for aid in self._after_ids:
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()

    def _cerrar_ventana(self) -> None:
        self._cancelar_temporizadores()
        self.destroy()

    def _construir_ui(self) -> None:
        t = self.tema

        card = ctk.CTkFrame(
            self,
            fg_color=t["card_bg"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=24,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(12, 8))

        ctk.CTkLabel(
            top,
            text="  Memorama",
            image=icono_ctk("eye", t["btn_purple"], 20),
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=t["text_primary"],
        ).pack(side="left")

        self.seg_dificultad = ctk.CTkSegmentedButton(
            top,
            values=["Fácil", "Normal"],
            command=self._cambiar_dificultad,
            fg_color=t["card_inner"],
            selected_color=t["btn_purple"],
            selected_hover_color=t["btn_purple_hover"],
            unselected_color=t["card_inner"],
            unselected_hover_color=t["hint_bg"],
            text_color=t["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.seg_dificultad.set("Fácil")
        self.seg_dificultad.pack(side="right")

        stats = ctk.CTkFrame(card, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=(0, 6))
        stats.grid_columnconfigure((0, 1), weight=1)

        box_pares = ctk.CTkFrame(
            stats,
            fg_color=t["card_inner"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=14,
        )
        box_pares.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkLabel(
            box_pares, text="PAREJAS", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=t["text_secondary"],
        ).pack(pady=(6, 0))
        self.lbl_parejas = ctk.CTkLabel(
            box_pares, text="0 / 6", font=ctk.CTkFont(size=20, weight="bold"),
            text_color=t["btn_green"],
        )
        self.lbl_parejas.pack(pady=(0, 6))

        box_movs = ctk.CTkFrame(
            stats,
            fg_color=t["card_inner"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=14,
        )
        box_movs.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        ctk.CTkLabel(
            box_movs, text="MOVIMIENTOS", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=t["text_secondary"],
        ).pack(pady=(6, 0))
        self.lbl_movs = ctk.CTkLabel(
            box_movs, text="0", font=ctk.CTkFont(size=20, weight="bold"),
            text_color=t["text_primary"],
        )
        self.lbl_movs.pack(pady=(0, 6))

        self.barra = ctk.CTkProgressBar(
            card,
            height=12,
            corner_radius=8,
            fg_color=t["card_inner"],
            progress_color=t["btn_green"],
        )
        self.barra.set(0.0)
        self.barra.pack(fill="x", padx=24, pady=(2, 6))

        banner = ctk.CTkFrame(
            card,
            fg_color=t["hint_bg"],
            border_color=t["hint_border"],
            border_width=1,
            corner_radius=12,
        )
        banner.pack(fill="x", padx=20, pady=(0, 8))

        self.lbl_estado = ctk.CTkLabel(
            banner,
            text="Encuentra todas las parejas de íconos",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=t["text_primary"],
        )
        self.lbl_estado.pack(pady=8)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=20, pady=(8, 14))

        self.btn_espiar = ctk.CTkButton(
            footer,
            text="Espiar 2s (1)",
            image=icono_ctk("eye", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_orange"],
            hover_color=t["btn_orange_hover"],
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._espiar_tablero,
        )
        self.btn_espiar.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            footer,
            text="Reiniciar",
            image=icono_ctk("refresh", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_green"],
            hover_color=t["btn_green_hover"],
            border_color=t["btn_green_border"],
            border_width=2,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._iniciar_partida,
        ).pack(side="left", expand=True, fill="x", padx=(0, 8))

        ctk.CTkButton(
            footer,
            text="Volver",
            image=icono_ctk("arrow_left", t["text_on_stage"], 15),
            compound="left",
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
            border_width=1,
            text_color=t["text_on_stage"],
            corner_radius=14,
            height=40,
            width=105,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._cerrar_ventana,
        ).pack(side="right")

        self.marco_tablero = ctk.CTkFrame(
            card,
            fg_color=t["card_bg"],
            border_color=t["card_border"],
            border_width=2,
            corner_radius=20,
        )
        self.marco_tablero.pack(fill="both", expand=True, padx=20, pady=(4, 8))

    def _cambiar_dificultad(self, valor: str) -> None:
        self.dificultad = valor
        self._iniciar_partida()

    def _iniciar_partida(self) -> None:
        self._cancelar_temporizadores()
        for widget in self.marco_tablero.winfo_children():
            widget.destroy()

        t = self.tema
        num_pares = 6 if self.dificultad == "Fácil" else 8
        cols = 4

        seleccion = self.ICONOS_DISPONIBLES[:num_pares]
        self.cartas = seleccion * 2
        random.shuffle(self.cartas)
        filas = len(self.cartas) // cols
        self._tam_icono = 48 if num_pares == 6 else 42

        self.botones = []
        self.emparejadas.clear()
        self.seleccionadas.clear()
        self.bloqueado = False
        self.movimientos = 0
        self.espias_disponibles = 1

        self.lbl_parejas.configure(text=f"0 / {num_pares}")
        self.lbl_movs.configure(text="0")
        self.barra.set(0.0)
        self.lbl_estado.configure(
            text="Voltea dos tarjetas para buscar parejas",
            text_color=t["text_primary"],
        )
        self.btn_espiar.configure(state="normal", text="Espiar 2s (1)")

        grid_cartas = ctk.CTkFrame(self.marco_tablero, fg_color="transparent")
        grid_cartas.pack(fill="both", expand=True, padx=10, pady=10)
        for c in range(cols):
            grid_cartas.grid_columnconfigure(c, weight=1, uniform="mem_col")
        for r in range(filas):
            grid_cartas.grid_rowconfigure(r, weight=1, uniform="mem_row")

        for idx in range(len(self.cartas)):
            btn = ctk.CTkButton(
                grid_cartas,
                text="?",
                image=None,
                width=10,
                height=10,
                corner_radius=18,
                fg_color=t["btn_stage_pill"],
                hover_color=t["btn_stage_pill_hover"],
                border_color=t["btn_stage_border"],
                border_width=2,
                text_color=t["text_on_stage"],
                font=ctk.CTkFont(size=34 if num_pares == 6 else 30, weight="bold"),
                command=lambda i=idx: self._voltear_carta(i),
            )
            btn.grid(row=idx // cols, column=idx % cols, sticky="nsew", padx=6, pady=6)
            self.botones.append(btn)

        self._emitir_voz("¡Vamos a jugar Memorama! Encuentra las parejas de íconos.")

    def _mostrar_carta(self, idx: int) -> None:
        t = self.tema
        nombre_icono, clave_color = self.cartas[idx]
        color_icono = t.get(clave_color, t["btn_purple"])
        self.botones[idx].configure(
            text="",
            image=icono_ctk(nombre_icono, color_icono, getattr(self, "_tam_icono", 42)),
            fg_color=t["card_inner"],
            hover_color=t["card_inner"],
            border_color=color_icono,
        )

    def _ocultar_carta(self, idx: int) -> None:
        t = self.tema
        self.botones[idx].configure(
            text="?",
            image=None,
            fg_color=t["btn_stage_pill"],
            hover_color=t["btn_stage_pill_hover"],
            border_color=t["btn_stage_border"],
        )

    def _voltear_carta(self, idx: int) -> None:
        if self.bloqueado or idx in self.emparejadas or idx in self.seleccionadas:
            return

        self._mostrar_carta(idx)
        self.seleccionadas.append(idx)

        if len(self.seleccionadas) == 2:
            self.bloqueado = True
            self.movimientos += 1
            self.lbl_movs.configure(text=str(self.movimientos))
            self._programar(550, self._evaluar_pareja)

    def _evaluar_pareja(self) -> None:
        if not self.winfo_exists() or len(self.seleccionadas) < 2:
            return

        t = self.tema
        i1, i2 = self.seleccionadas
        self.seleccionadas.clear()

        if self.cartas[i1][0] == self.cartas[i2][0]:
            self.emparejadas.update((i1, i2))
            for idx in (i1, i2):
                self.botones[idx].configure(
                    fg_color=t["hint_bg"],
                    border_color=t["btn_green"],
                )

            total_pares = len(self.cartas) // 2
            hallados = len(self.emparejadas) // 2
            self.lbl_parejas.configure(text=f"{hallados} / {total_pares}")
            self.barra.set(hallados / total_pares)

            if hallados == total_pares:
                self.lbl_estado.configure(
                    text="¡Completaste todo el tablero! Excelente memoria.",
                    text_color=t["btn_green"],
                )
                self._emitir_voz("¡Excelente trabajo! Encontraste todas las parejas.")
                if self.on_victoria:
                    self.on_victoria()
            else:
                self.lbl_estado.configure(
                    text="¡Muy bien! Encontraste una pareja.",
                    text_color=t["btn_green"],
                )
        else:
            self._ocultar_carta(i1)
            self._ocultar_carta(i2)
            self.lbl_estado.configure(
                text="Casi. Recuerda dónde estaban e intenta otra vez.",
                text_color=t["text_secondary"],
            )

        self.bloqueado = False

    def _espiar_tablero(self) -> None:
        if self.bloqueado or self.espias_disponibles <= 0:
            return
        self.espias_disponibles -= 1
        self.btn_espiar.configure(state="disabled", text="Espiar 2s (0)")
        self.bloqueado = True
        self.lbl_estado.configure(
            text="Observa bien las posiciones...",
            text_color=self.tema["badge_gold_text"],
        )

        ocultas = [
            i for i in range(len(self.cartas))
            if i not in self.emparejadas and i not in self.seleccionadas
        ]
        for idx in ocultas:
            self._mostrar_carta(idx)

        def _ocultar_de_nuevo():
            if not self.winfo_exists():
                return
            for idx in ocultas:
                self._ocultar_carta(idx)
            self.bloqueado = False
            self.lbl_estado.configure(
                text="Listo. Sigue buscando parejas.",
                text_color=self.tema["text_primary"],
            )

        self._programar(2000, _ocultar_de_nuevo)
