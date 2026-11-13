"""
Modal Integrado de Cámara Web en CustomTkinter — Reto Sensorial de Colores (OpenCV)
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Integra el video de OpenCV directamente dentro de una tarjeta moderna de CustomTkinter
usando `PIL.Image` + `ctk.CTkImage` (sin abrir ventanas externas de sistema `cv2.imshow`).
Si la PC no dispone de cámara física, habilita un modo interactivo simulado en el mismo
modal para garantizar portabilidad del 100% entre compañeros.
"""

from typing import Callable, Dict, Optional

import customtkinter as ctk
from PIL import Image

from core.herramientas_multimodales import OPENCV_DISPONIBLE, analizar_frame_colores
from ui.iconos import aplicar_icono_ventana_haru, icono_ctk

if OPENCV_DISPONIBLE:
    import cv2


class ModalRetoColores(ctk.CTkToplevel):
    FRAMES_META = 20

    def __init__(self, parent, tema: Dict[str, str],
                 on_premio: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        aplicar_icono_ventana_haru(self)
        self.tema = tema
        self.on_premio = on_premio
        self.cap = None
        self._cerrado = False
        self._ultimo_color = ""
        self._racha = 0
        self._completado = False

        self.title("Reto Sensorial de Colores — Haru")
        self.geometry("640x600")
        self.minsize(580, 540)
        self.resizable(True, True)
        self.configure(fg_color=tema["bg_stage"])
        self.transient(parent)

        self._construir_ui()
        self.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.after(150, self._fijar_foco_windows)
        self.after(220, self._iniciar_captura)

    def _fijar_foco_windows(self) -> None:
        if self._cerrado or not self.winfo_exists():
            return
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

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
            text="  ¡Reto Sensorial de Colores! (+2 Puntos)",
            image=icono_ctk("camera", self.tema["text_primary"], 22),
            compound="left",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self.tema["text_primary"],
        ).pack(pady=(14, 4))

        self.lbl_instruccion = ctk.CTkLabel(
            card,
            text="Muestra frente a la cámara un útil escolar AMARILLO, ROJO, AZUL o VERDE",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self.tema["text_secondary"],
        )
        self.lbl_instruccion.pack(pady=(0, 8))

        # Insignias vectoriales limpias de colores objetivo
        chips = ctk.CTkFrame(card, fg_color="transparent")
        chips.pack(pady=(0, 8))
        for texto, color_bg, color_fg in [
            ("Amarillo", "#fef08a", "#854d0e"),
            ("Rojo", "#fecdd3", "#9f1239"),
            ("Azul", "#bae6fd", "#075985"),
            ("Verde", "#bbf7d0", "#166534"),
        ]:
            ctk.CTkLabel(
                chips,
                text=f" {texto}",
                image=icono_ctk("dot", color_fg, 13),
                compound="left",
                fg_color=color_bg,
                text_color=color_fg,
                corner_radius=12,
                padx=12,
                pady=4,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=5)

        # Contenedor inferior fijo (empaquetado con side="bottom" para que NUNCA se corte)
        self.fila_acciones = ctk.CTkFrame(card, fg_color="transparent")
        self.fila_acciones.pack(side="bottom", fill="x", padx=20, pady=(4, 14))

        self.btn_volver = ctk.CTkButton(
            self.fila_acciones,
            text="Volver a mi tarea",
            image=icono_ctk("arrow_left", "#ffffff", 16),
            compound="left",
            fg_color=self.tema["btn_stage_pill"],
            hover_color=self.tema["btn_stage_pill_hover"],
            border_width=1,
            border_color=self.tema["btn_stage_border"],
            corner_radius=16,
            width=170,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.cerrar,
        )
        self.btn_volver.pack(side="right")

        self.barra = ctk.CTkProgressBar(
            card,
            width=440,
            height=14,
            corner_radius=8,
            progress_color=self.tema["btn_green"],
        )
        self.barra.set(0.0)
        self.barra.pack(side="bottom", pady=(0, 8))

        # Barra de progreso de enfoque del color
        self.lbl_estado = ctk.CTkLabel(
            card,
            text="Esperando un objeto de color...",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.tema["text_primary"],
        )
        self.lbl_estado.pack(side="bottom", pady=(4, 4))

        # Visor de video integrado (se adapta al espacio central sin empujar los botones fuera)
        self.marco_video = ctk.CTkFrame(
            card,
            width=460,
            height=265,
            fg_color="#0f172a",
            corner_radius=18,
        )
        self.marco_video.pack(fill="both", expand=True, padx=20, pady=6)
        self.marco_video.pack_propagate(False)

        self.lbl_video = ctk.CTkLabel(
            self.marco_video,
            text="  Conectando cámara web...",
            image=icono_ctk("camera", "#e2e8f0", 20),
            compound="left",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_video.pack(fill="both", expand=True)

    def _iniciar_captura(self) -> None:
        if self._cerrado:
            return
        if OPENCV_DISPONIBLE:
            try:
                self.cap = cv2.VideoCapture(0, getattr(cv2, "CAP_DSHOW", 0))
                if not self.cap or not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(0)
            except Exception:
                self.cap = None

        if not self.cap or not self.cap.isOpened():
            self._activar_modo_sin_camara()
            return

        self._ciclo_frame()

    def _activar_modo_sin_camara(self) -> None:
        self.lbl_video.configure(
            image=None,
            text=(
                "No se detectó cámara web en esta PC\n\n"
                "Modo Interactivo Activo:\n"
                "Busca un objeto de color en tu escritorio y toca el botón del color que encontraste:"
            ),
        )
        self.lbl_estado.configure(text="Elige el color del útil escolar que tienes en la mano:")
        for nombre, col, hov in [
            ("Amarillo", "#eab308", "#ca8a04"),
            ("Rojo", "#ef4444", "#dc2626"),
            ("Azul", "#0284c7", "#0369a1"),
            ("Verde", "#16a34a", "#15803d"),
        ]:
            ctk.CTkButton(
                self.fila_acciones,
                text=nombre,
                image=icono_ctk("dot", "#ffffff", 12),
                compound="left",
                width=96,
                height=36,
                corner_radius=14,
                fg_color=col,
                hover_color=hov,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda c=nombre.upper(): self._completar_reto(c),
            ).pack(side="left", padx=4)

    def _ciclo_frame(self) -> None:
        if self._cerrado or self._completado or not self.winfo_exists():
            return
        if not self.cap or not self.cap.isOpened():
            return

        ok, frame_bgr = self.cap.read()
        if ok and frame_bgr is not None:
            frame_rgb, color = analizar_frame_colores(frame_bgr)
            vw = max(360, self.marco_video.winfo_width() - 12)
            vh = max(210, self.marco_video.winfo_height() - 12)
            pil_img = Image.fromarray(frame_rgb).resize((vw, vh), Image.Resampling.BILINEAR)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(vw, vh))
            self.lbl_video.configure(image=ctk_img, text="")
            self.lbl_video._ctk_img_ref = ctk_img  # Evitar recolección de basura

            if color and color == self._ultimo_color:
                self._racha += 1
            elif color:
                self._ultimo_color = color
                self._racha = 1
            else:
                self._racha = max(0, self._racha - 1)

            progreso = min(1.0, self._racha / float(self.FRAMES_META))
            self.barra.set(progreso)

            if color:
                self.lbl_estado.configure(text=f"¡Viendo color {color}! Manténlo quietito...")
            else:
                self.lbl_estado.configure(text="Acerca tu objeto de color al centro de la cámara...")

            if self._racha >= self.FRAMES_META:
                self._completar_reto(color)
                return

        self.after(40, self._ciclo_frame)

    def _completar_reto(self, color: str) -> None:
        if self._completado:
            return
        self._completado = True
        self.barra.set(1.0)
        self.lbl_estado.configure(text=f"¡Increíble! Encontraste el color {color} (+2 Puntos)")
        self._liberar_camara()
        if self.on_premio:
            self.on_premio(color)
        self.after(950, self.cerrar)

    def _liberar_camara(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def cerrar(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        self._liberar_camara()
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()

