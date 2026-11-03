"""
Barra Interactiva de Subtítulos Tipo Karaoke Sincronizada con la Voz de Haru
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Resalta palabra por palabra al ritmo exacto de los eventos `WordBoundary` de
`edge-tts` (o del temporizador proporcional en modo local), reforzando la lectura
guiada y la atención sostenida en niños de primaria con TDAH.
"""

import re
import tkinter as tk
from typing import Dict, List, Tuple

import customtkinter as ctk


class SubtitulosKaraoke(ctk.CTkFrame):
    def __init__(self, master, tema: Dict[str, str], **kwargs):
        super().__init__(
            master,
            fg_color=tema["karaoke_bg"],
            border_color=tema["karaoke_border"],
            border_width=2,
            corner_radius=18,
            **kwargs,
        )
        self.tema = tema
        self._rangos_palabras: List[Tuple[str, str]] = []
        self._palabras_norm: List[str] = []
        self._cursor_busqueda: int = 0
        self._texto_actual = ""

        self.lbl_icono = ctk.CTkLabel(
            self,
            text="🔊",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=16, weight="bold"),
            text_color=tema["karaoke_active"],
            width=26,
        )
        self.lbl_icono.pack(side="left", padx=(12, 4), pady=8)

        self.txt = tk.Text(
            self,
            height=2,
            wrap="word",
            bd=0,
            highlightthickness=0,
            relief="flat",
            bg=tema["karaoke_bg"],
            fg=tema["karaoke_pending"],
            font=("Segoe UI", 12, "bold"),
            padx=4,
            pady=4,
            cursor="arrow",
            state="disabled",
        )
        self.txt.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=6)
        self._configurar_tags()

    def _configurar_tags(self) -> None:
        self.txt.tag_configure("center", justify="center")
        self.txt.tag_configure(
            "hablada",
            foreground=self.tema["karaoke_spoken"],
            font=("Segoe UI", 12, "bold"),
        )
        self.txt.tag_configure(
            "activa",
            foreground=self.tema["karaoke_active"],
            font=("Segoe UI", 13, "bold", "underline"),
        )
        self.txt.tag_configure(
            "pendiente",
            foreground=self.tema["karaoke_pending"],
            font=("Segoe UI", 12, "bold"),
        )

    def aplicar_tema(self, tema: Dict[str, str]) -> None:
        self.tema = tema
        self.configure(fg_color=tema["karaoke_bg"], border_color=tema["karaoke_border"])
        self.lbl_icono.configure(text_color=tema["karaoke_active"])
        self.txt.configure(bg=tema["karaoke_bg"], fg=tema["karaoke_pending"])
        self._configurar_tags()
        if self._texto_actual:
            self.preparar_texto(self._texto_actual)

    def preparar_texto(self, texto: str, modo_voz: str = "neuronal") -> None:
        """Carga una frase nueva y calcula las posiciones de cada palabra pronunciable."""
        self._texto_actual = (texto or "").strip()
        icono = "🎙️" if modo_voz == "neuronal" else "💬"
        self.lbl_icono.configure(text=icono)

        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", self._texto_actual, ("center", "pendiente"))

        self._rangos_palabras = []
        self._palabras_norm = []
        self._cursor_busqueda = 0
        # Indexar cada palabra con letras o dígitos para sincronizar con WordBoundary
        for match in re.finditer(r"[\wÁÉÍÓÚÜÑáéíóúüñ0-9]+", self._texto_actual):
            ini = f"1.0+{match.start()}c"
            fin = f"1.0+{match.end()}c"
            self._rangos_palabras.append((ini, fin))
            self._palabras_norm.append(match.group(0).lower().strip("_"))

        self.txt.configure(state="disabled")

    def resaltar_palabra(self, indice: int, palabra: str = "") -> None:
        """Ilumina la palabra activa sin desfasarse ante signos matemáticos o emojis."""
        if not self._rangos_palabras:
            return

        idx = max(0, min(indice, len(self._rangos_palabras) - 1))
        pal_limpia = re.sub(r"[^\wáéíóúüñ0-9]", "", (palabra or "").lower())
        if pal_limpia:
            ini_busq = max(0, self._cursor_busqueda)
            fin_busq = min(len(self._palabras_norm), ini_busq + 5)
            for cand_i in range(ini_busq, fin_busq):
                if self._palabras_norm[cand_i] == pal_limpia:
                    idx = cand_i
                    break

        self._cursor_busqueda = idx

        self.txt.configure(state="normal")
        self.txt.tag_remove("hablada", "1.0", "end")
        self.txt.tag_remove("activa", "1.0", "end")
        self.txt.tag_remove("pendiente", "1.0", "end")

        ini_act, fin_act = self._rangos_palabras[idx]
        if idx > 0:
            self.txt.tag_add("hablada", "1.0", ini_act)
        self.txt.tag_add("activa", ini_act, fin_act)
        self.txt.tag_add("pendiente", fin_act, "end")
        self.txt.see(ini_act)
        self.txt.configure(state="disabled")

    def finalizar_frase(self) -> None:
        if not self._texto_actual:
            return
        self.lbl_icono.configure(text="✨")
        self.txt.configure(state="normal")
        self.txt.tag_remove("activa", "1.0", "end")
        self.txt.tag_remove("pendiente", "1.0", "end")
        self.txt.tag_add("hablada", "1.0", "end")
        self.txt.configure(state="disabled")

