"""
Escenario Central Unificado: Haru 3D-Glossy Supersampled + Expresiones Situacionales + Camino
Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Características visuales y pedagógicas:
- 4 trajes progresivos desbloqueables con puntos (`Robot`, `Gatito`, `Osito`, `Haru Dorado`).
- 6 visemas/bocas anatómicamente coherentes:
  0 = Sonrisa cerrada serena (reposo, escucha, pausas y silencios de puntuación)
  1 = Vocal abierta (A / E) con interior y lengüita cálida
  2 = Vocal redondeada (O / U) y soplo de exhalación consciente
  3 = Vocal cerrada / consonante silábica (I / M / S)
  4 = Súper sonrisa radiante de festejo (Paso logrado / Misión completada)
  5 = Gesto curioso pensativo (Consultando IA / Pista mágica)
- 10 comportamientos y posturas corporales según la acción realizada:
  `IDLE`, `SALUDANDO`, `HABLANDO`, `ESCUCHANDO` (mano al oído + ondas reactivas al micrófono),
  `PENSANDO` (mano al mentón + burbujas vectoriales), `PASO_LOGRADO` (salto + brazos en V + estrellas),
  `CELEBRANDO` (brazos arriba + confeti + cofre abierto), `RESPIRANDO` (brazos zen + burbujas),
  `PAUSA` (descanso sereno) y `COSQUILLAS` (rebote juguetón con corazoncitos).
"""

from functools import lru_cache
import math
import random
import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageTk

# Catálogo oficial de trajes con meta de estrellas históricas para desbloqueo
REQUISITOS_SKIN: Dict[str, Tuple[int, str, str]] = {
    "ROBOT_KAWAII": (0, "01", "Robotito Celeste"),
    "GATITO_ESPACIAL": (8, "02", "Gatito Espacial"),
    "OSITO_TUTOR": (18, "03", "Osito Tutor"),
    "SUPER_HARU_DORADO": (32, "04", "Súper Haru Dorado"),
}

PALETAS_SKIN = {
    "ROBOT_KAWAII": {
        "base": (88, 184, 238, 255),
        "luz": (158, 224, 255, 255),
        "sombra": (44, 128, 185, 255),
        "oreja": (68, 158, 214, 255),
        "panza": (118, 202, 246, 255),
        "visor": (20, 48, 82, 255),
        "visor_borde": (52, 112, 168, 255),
        "neon": (122, 248, 255, 255),
        "mejilla": (255, 154, 188, 130),
    },
    "GATITO_ESPACIAL": {
        "base": (246, 188, 88, 255),
        "luz": (255, 228, 158, 255),
        "sombra": (204, 134, 42, 255),
        "oreja": (232, 152, 62, 255),
        "panza": (255, 232, 185, 255),
        "visor": (36, 32, 68, 255),
        "visor_borde": (124, 108, 192, 255),
        "neon": (148, 252, 236, 255),
        "mejilla": (255, 132, 168, 145),
    },
    "OSITO_TUTOR": {
        "base": (168, 118, 84, 255),
        "luz": (214, 168, 132, 255),
        "sombra": (118, 76, 48, 255),
        "oreja": (132, 88, 58, 255),
        "panza": (232, 204, 176, 255),
        "visor": (28, 42, 58, 255),
        "visor_borde": (88, 128, 158, 255),
        "neon": (138, 248, 255, 255),
        "mejilla": (255, 146, 168, 135),
    },
    "SUPER_HARU_DORADO": {
        "base": (245, 196, 66, 255),
        "luz": (254, 240, 138, 255),
        "sombra": (180, 122, 18, 255),
        "oreja": (217, 155, 38, 255),
        "panza": (254, 243, 199, 255),
        "visor": (30, 27, 75, 255),
        "visor_borde": (234, 179, 8, 255),
        "neon": (165, 243, 252, 255),
        "mejilla": (255, 142, 178, 150),
    },
}


def _dibujar_brazo_capsula(pal: dict, espejo: bool = False) -> Image.Image:
    """Crea un brazo 3D redondeado con pivote de hombro exacto en (130, 130)."""
    im = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Cápsula desde el hombro (y=158) hacia la manito arriba (y=30)
    d.rounded_rectangle((94, 34, 166, 162), radius=36, fill=pal["sombra"])
    d.rounded_rectangle((97, 34, 161, 154), radius=34, fill=pal["base"])
    # Dedos tiernos en el extremo superior
    d.ellipse((94, 18, 118, 48), fill=pal["base"])
    d.ellipse((118, 12, 142, 44), fill=pal["luz"])
    d.ellipse((142, 18, 166, 48), fill=pal["base"])
    if espejo:
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return im


def _config_brazos(pose_brazos: str) -> Tuple[Tuple[float, int, int], Tuple[float, int, int]]:
    """
    Devuelve ((angulo_izq, x_izq, y_izq), (angulo_der, x_der, y_der)) en el lienzo 3x (750x645).
    Con pivote fijo en (130, 130), (118, 258) ancla el hombro izquierdo en (248, 388)
    y (372, 258) ancla el hombro derecho en (502, 388) sin despegarse jamás del torso.
    """
    mapa = {
        "NEUTRO_A": ((148, 118, 258), (-148, 372, 258)),
        "NEUTRO_B": ((138, 118, 255), (-138, 372, 255)),
        "SALUDO_A": ((36, 118, 248), (-146, 372, 258)),
        "SALUDO_B": ((52, 118, 248), (-142, 372, 258)),
        "EXPLICANDO_A": ((72, 118, 254), (-116, 372, 256)),
        "EXPLICANDO_B": ((116, 118, 256), (-72, 372, 254)),
        "VICTORIA_A": ((36, 118, 246), (-36, 372, 246)),
        "VICTORIA_B": ((24, 118, 244), (-24, 372, 244)),
        "ESCUCHANDO_OIDO": ((146, 118, 258), (-18, 374, 236)),
        "PENSANDO_MENTON": ((146, 118, 258), (32, 356, 266)),
        "ZEN_INHALA": ((104, 116, 254), (-104, 374, 254)),
        "ZEN_EXHALA": ((138, 118, 258), (-138, 372, 258)),
    }
    return mapa.get(pose_brazos, mapa["NEUTRO_A"])


@lru_cache(maxsize=32)
def _brazo_rotado_cache(skin: str, espejo: bool, angulo: float) -> Image.Image:
    pal = PALETAS_SKIN.get(skin, PALETAS_SKIN["ROBOT_KAWAII"])
    return _dibujar_brazo_capsula(pal, espejo=espejo).rotate(
        angulo, resample=Image.Resampling.BICUBIC, expand=False, center=(130, 130)
    )


@lru_cache(maxsize=2)
def _capa_sombra_suelo() -> Image.Image:
    W, H = 750, 645
    sombra_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sombra_layer)
    ds.ellipse((238, 560, 512, 604), fill=(10, 32, 36, 95))
    ds.rounded_rectangle((248, 355, 502, 428), radius=55, fill=(12, 38, 62, 90))
    return sombra_layer.filter(ImageFilter.GaussianBlur(radius=16))


@lru_cache(maxsize=16)
def _capa_cabeza_base_cache(skin: str, mejilla_intensa: bool) -> Image.Image:
    """Pre-calcula y cachea la cabeza 3D (con brillos y mejillas difuminadas) por traje."""
    pal = PALETAS_SKIN.get(skin, PALETAS_SKIN["ROBOT_KAWAII"])
    W, H = 750, 645
    cabeza = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dcab = ImageDraw.Draw(cabeza)

    if skin == "ROBOT_KAWAII":
        dcab.rounded_rectangle((344, 102, 406, 138), radius=16, fill=pal["oreja"])
        dcab.rectangle((367, 60, 383, 110), fill=pal["luz"])
        dcab.ellipse((350, 24, 400, 74), fill=pal["sombra"])
        dcab.ellipse((352, 24, 396, 68), fill=pal["base"])
        dcab.ellipse((360, 30, 378, 46), fill=(235, 252, 255, 230))
    elif skin == "GATITO_ESPACIAL":
        dcab.polygon([(225, 172), (262, 58), (332, 134)], fill=pal["oreja"])
        dcab.polygon([(244, 156), (268, 84), (314, 134)], fill=(255, 168, 192, 255))
        dcab.polygon([(525, 172), (488, 58), (418, 134)], fill=pal["oreja"])
        dcab.polygon([(506, 156), (482, 84), (436, 134)], fill=(255, 168, 192, 255))
    elif skin == "OSITO_TUTOR":
        dcab.ellipse((202, 78, 304, 180), fill=pal["oreja"])
        dcab.ellipse((224, 100, 282, 158), fill=pal["panza"])
        dcab.ellipse((446, 78, 548, 180), fill=pal["oreja"])
        dcab.ellipse((468, 100, 526, 158), fill=pal["panza"])
    else:
        dcab.polygon(
            [(292, 126), (304, 48), (344, 92), (375, 32), (406, 92), (446, 48), (458, 126)],
            fill=(250, 204, 21, 255),
            outline=(180, 118, 18, 255),
        )
        dcab.rounded_rectangle((290, 108, 460, 134), radius=10, fill=(234, 179, 8, 255))
        dcab.ellipse((362, 68, 388, 96), fill=(56, 189, 248, 255), outline=(255, 255, 255, 230), width=3)

    dcab.rounded_rectangle((176, 202, 224, 324), radius=24, fill=pal["sombra"])
    dcab.rounded_rectangle((180, 204, 220, 316), radius=22, fill=pal["oreja"])
    dcab.rounded_rectangle((526, 202, 574, 324), radius=24, fill=pal["sombra"])
    dcab.rounded_rectangle((530, 204, 570, 316), radius=22, fill=pal["oreja"])

    dcab.rounded_rectangle((202, 120, 548, 394), radius=112, fill=pal["sombra"])
    dcab.rounded_rectangle((206, 116, 542, 382), radius=108, fill=pal["base"])

    brillo_cab = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dbc = ImageDraw.Draw(brillo_cab)
    dbc.ellipse((236, 130, 456, 228), fill=(255, 255, 255, 92))
    brillo_cab = brillo_cab.filter(ImageFilter.GaussianBlur(radius=18))
    cabeza = Image.alpha_composite(cabeza, brillo_cab)

    dcab = ImageDraw.Draw(cabeza)
    dcab.rounded_rectangle((242, 162, 508, 350), radius=68, fill=pal["visor_borde"])
    dcab.rounded_rectangle((250, 170, 500, 342), radius=62, fill=pal["visor"])

    cristal = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(cristal)
    dc.pieslice((256, 174, 430, 266), start=180, end=275, fill=(255, 255, 255, 28))
    mejilla_alpha = min(210, pal["mejilla"][3] + (35 if mejilla_intensa else 0))
    c_mej = (pal["mejilla"][0], pal["mejilla"][1], pal["mejilla"][2], mejilla_alpha)
    dc.ellipse((264, 276, 312, 310), fill=c_mej)
    dc.ellipse((438, 276, 486, 310), fill=c_mej)
    cristal = cristal.filter(ImageFilter.GaussianBlur(radius=6))
    return Image.alpha_composite(cabeza, cristal)


@lru_cache(maxsize=128)
def _renderizar_haru_maestro(
    skin: str,
    ojos: str,
    boca: int,
    pose_brazos: str,
    inclinacion: int = 0,
) -> Image.Image:
    """
    Compone y cachea en memoria el sprite maestro de Haru (500x430) reutilizando
    las capas pre-difuminadas para que cualquier cambio de escala sea instantáneo (<1 ms).
    """
    pal = PALETAS_SKIN.get(skin, PALETAS_SKIN["ROBOT_KAWAII"])
    W, H = 750, 645
    lienzo = _capa_sombra_suelo().copy()

    # 2. Brazos traseros/laterales con pivote fijo en el hombro
    (ang_i, xi, yi), (ang_d, xd, yd) = _config_brazos(pose_brazos)
    brazo_izq = _brazo_rotado_cache(skin, False, ang_i)
    lienzo.alpha_composite(brazo_izq, (xi, yi))

    brazo_der = _brazo_rotado_cache(skin, True, ang_d)
    if pose_brazos != "PENSANDO_MENTON":
        lienzo.alpha_composite(brazo_der, (xd, yd))

    # 3. Torso redondeado 3D
    d = ImageDraw.Draw(lienzo)
    d.rounded_rectangle((236, 346, 514, 534), radius=88, fill=pal["sombra"])
    d.rounded_rectangle((242, 342, 506, 522), radius=84, fill=pal["base"])
    d.rounded_rectangle((292, 404, 458, 502), radius=42, fill=pal["panza"])
    if skin == "SUPER_HARU_DORADO":
        d.ellipse((353, 430, 397, 474), fill=(250, 204, 21, 255), outline=(255, 255, 255, 220), width=4)

    # 4. Cabeza base pre-difuminada + Expresión facial luminosa en sub-región (250..500, 180..350)
    cabeza = _capa_cabeza_base_cache(skin, boca == 4).copy()
    sub_x, sub_y, sub_w, sub_h = 250, 180, 250, 170
    neon_glow = Image.new("RGBA", (sub_w, sub_h), (0, 0, 0, 0))
    dg = ImageDraw.Draw(neon_glow)
    df = ImageDraw.Draw(cabeza)
    c_neon = pal["neon"]
    c_aura = (c_neon[0], c_neon[1], c_neon[2], 110)

    for draw_target, color, extra_w, ox, oy_off in ((dg, c_aura, 8, -sub_x, -sub_y), (df, c_neon, 0, 0, 0)):
        if ojos == "FELIZ":
            draw_target.arc((286 + ox, 212 + oy_off, 352 + ox, 278 + oy_off), start=195, end=345, fill=color, width=15 + extra_w)
            draw_target.arc((398 + ox, 212 + oy_off, 464 + ox, 278 + oy_off), start=195, end=345, fill=color, width=15 + extra_w)
        elif ojos == "PARPADEO":
            draw_target.rounded_rectangle((288 + ox, 240 + oy_off, 350 + ox, 252 + oy_off), radius=6, fill=color)
            draw_target.rounded_rectangle((400 + ox, 240 + oy_off, 462 + ox, 252 + oy_off), radius=6, fill=color)
        elif ojos == "CALMA":
            draw_target.arc((288 + ox, 222 + oy_off, 350 + ox, 268 + oy_off), start=18, end=162, fill=color, width=12 + extra_w)
            draw_target.arc((400 + ox, 222 + oy_off, 462 + ox, 268 + oy_off), start=18, end=162, fill=color, width=12 + extra_w)
        else:
            oy = (-6 if ojos == "PENSANDO" else 0) + oy_off
            draw_target.ellipse(
                (292 + ox - extra_w // 2, 208 + oy - extra_w // 2, 346 + ox + extra_w // 2, 266 + oy + extra_w // 2),
                fill=color,
            )
            draw_target.ellipse(
                (404 + ox - extra_w // 2, 208 + oy - extra_w // 2, 458 + ox + extra_w // 2, 266 + oy + extra_w // 2),
                fill=color,
            )

        if boca == 0:
            draw_target.arc((344 + ox, 262 + oy_off, 406 + ox, 304 + oy_off), start=18, end=162, fill=color, width=12 + extra_w)
        elif boca == 1:
            draw_target.pieslice((340 + ox, 266 + oy_off, 410 + ox, 320 + oy_off), start=0, end=180, fill=color)
        elif boca == 2:
            draw_target.ellipse(
                (357 + ox - extra_w // 2, 272 + oy_off - extra_w // 2, 393 + ox + extra_w // 2, 308 + oy_off + extra_w // 2),
                fill=color,
            )
        elif boca == 3:
            draw_target.rounded_rectangle(
                (346 + ox - extra_w // 2, 278 + oy_off - extra_w // 2, 404 + ox + extra_w // 2, 298 + oy_off + extra_w // 2),
                radius=10,
                fill=color,
            )
        elif boca == 4:
            draw_target.pieslice((332 + ox, 260 + oy_off, 418 + ox, 324 + oy_off), start=0, end=180, fill=color)
        else:
            draw_target.ellipse(
                (366 + ox - extra_w // 2, 278 + oy_off - extra_w // 2, 392 + ox + extra_w // 2, 300 + oy_off + extra_w // 2),
                fill=color,
            )

    neon_glow = neon_glow.filter(ImageFilter.GaussianBlur(radius=8))
    cabeza.alpha_composite(neon_glow, (sub_x, sub_y))

    df_top = ImageDraw.Draw(cabeza)
    if ojos == "FELIZ":
        df_top.arc((286, 212, 352, 278), start=195, end=345, fill=c_neon, width=15)
        df_top.arc((398, 212, 464, 278), start=195, end=345, fill=c_neon, width=15)
    elif ojos in ("ATENTO", "PENSANDO"):
        dx_pup = 6 if ojos == "PENSANDO" else 0
        dy_pup = -10 if ojos == "PENSANDO" else 0
        df_top.ellipse((304 + dx_pup, 216 + dy_pup, 320 + dx_pup, 232 + dy_pup), fill=(255, 255, 255, 245))
        df_top.ellipse((416 + dx_pup, 216 + dy_pup, 432 + dx_pup, 232 + dy_pup), fill=(255, 255, 255, 245))

    if boca == 0:
        df_top.arc((344, 262, 406, 304), start=18, end=162, fill=c_neon, width=12)
    elif boca == 1:
        df_top.pieslice((346, 270, 404, 316), start=0, end=180, fill=(18, 52, 86, 235))
        df_top.pieslice((356, 290, 394, 316), start=0, end=180, fill=(255, 138, 165, 240))
    elif boca == 2:
        df_top.ellipse((364, 279, 386, 301), fill=(18, 52, 86, 235))
    elif boca == 3:
        df_top.rounded_rectangle((352, 283, 398, 293), radius=5, fill=(18, 52, 86, 215))
    elif boca == 4:
        df_top.pieslice((338, 265, 412, 320), start=0, end=180, fill=(18, 52, 86, 235))
        df_top.pieslice((350, 288, 400, 320), start=0, end=180, fill=(255, 138, 165, 245))

    if inclinacion != 0:
        cabeza = cabeza.rotate(
            inclinacion * 5.5,
            resample=Image.Resampling.BICUBIC,
            center=(375, 275),
        )

    lienzo = Image.alpha_composite(lienzo, cabeza)
    if pose_brazos == "PENSANDO_MENTON":
        lienzo.alpha_composite(brazo_der, (xd, yd))

    return lienzo.resize((520, 447), resample=Image.Resampling.LANCZOS)


def _renderizar_haru_3d(
    skin: str,
    ojos: str,
    boca: int,
    pose_brazos: str,
    inclinacion: int = 0,
    alto_px: int = 215,
) -> Image.Image:
    """
    Genera un sprite RGBA con acabado 3D suave a partir del lienzo maestro cacheado,
    escalable instantáneamente según el tamaño de la ventana o pantalla completa.
    """
    maestro = _renderizar_haru_maestro(skin, ojos, boca, pose_brazos, inclinacion)
    alto_final = max(180, min(580, int(alto_px)))
    ancho_final = max(210, int(round(alto_final * (750.0 / 645.0))))
    if (ancho_final, alto_final) == maestro.size:
        return maestro
    return maestro.resize((ancho_final, alto_final), resample=Image.Resampling.BILINEAR)


def _renderizar_cofre_tesoro(abierto: bool = False, escala: float = 1.0) -> Image.Image:
    """Dibuja un cofre del tesoro dorado estilo 3D al final del camino de pasos."""
    W, H = 240, 210
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((18, 146, 222, 196), radius=22, fill=(180, 118, 18, 255))
    d.rounded_rectangle((22, 138, 218, 186), radius=20, fill=(245, 188, 52, 255))

    d.rounded_rectangle((42, 86, 198, 166), radius=18, fill=(166, 88, 22, 255))
    d.rounded_rectangle((48, 90, 192, 160), radius=14, fill=(217, 130, 36, 255))
    d.rectangle((48, 90, 68, 160), fill=(250, 204, 68, 255))
    d.rectangle((172, 90, 192, 160), fill=(250, 204, 68, 255))

    if abierto:
        d.ellipse((56, 28, 184, 114), fill=(254, 240, 138, 240))
        d.rounded_rectangle((44, 22, 196, 74), radius=24, fill=(245, 180, 42, 255))
    else:
        d.rounded_rectangle((42, 46, 198, 102), radius=28, fill=(234, 152, 38, 255))
        d.rounded_rectangle((48, 50, 192, 96), radius=24, fill=(250, 196, 62, 255))

    d.rounded_rectangle((104, 82, 136, 120), radius=10, fill=(254, 240, 138, 255))
    d.ellipse((114, 92, 126, 104), fill=(120, 62, 14, 255))

    w_out = max(72, min(160, int(round(84 * escala))))
    h_out = max(64, min(140, int(round(74 * escala))))
    return img.resize((w_out, h_out), resample=Image.Resampling.LANCZOS)


class EscenarioCentralHaru(tk.Canvas):
    """
    Lienzo central sin costuras que coordina:
    - Sincronización labial fonética real (`hablando_activo` + `boca_actual` 0..5).
    - Movimientos corporales contextuales a cada acción del niño.
    - Camino curvo de aventura (`1 -> 2 -> 3 -> Cofre del Tesoro`).
    """

    ESTADO_IDLE = "IDLE"
    ESTADO_SALUDANDO = "SALUDANDO"
    ESTADO_HABLANDO = "HABLANDO"
    ESTADO_ESCUCHANDO = "ESCUCHANDO"
    ESTADO_PENSANDO = "PENSANDO"
    ESTADO_PASO_LOGRADO = "PASO_LOGRADO"
    ESTADO_CELEBRANDO = "CELEBRANDO"
    ESTADO_RESPIRANDO = "RESPIRANDO"
    ESTADO_PAUSA = "PAUSA"
    ESTADO_COSQUILLAS = "COSQUILLAS"

    def __init__(self, master, tema: Dict[str, str],
                 on_click_haru: Optional[Callable[[], None]] = None,
                 **kwargs):
        super().__init__(
            master,
            bg=tema["bg_stage"],
            bd=0,
            highlightthickness=0,
            relief="flat",
            **kwargs,
        )
        self.tema = tema
        self.on_click_haru = on_click_haru

        self.skin = "ROBOT_KAWAII"
        self.estado = self.ESTADO_IDLE
        self.hablando_activo = False
        self.boca_actual = 0
        self.nivel_mic = 0.0
        self.paso_actual = 0
        self.total_pasos = 3
        self.mision_completada = False

        self._t = 0.0
        self._activo = True
        self._after_anim_id = None
        self._after_resize_id = None
        self._ultimo_tamano_lienzo: Tuple[int, int] = (0, 0)
        self._respiracion_restante = 0.0
        self._reaccion_temporal: str = ""
        self._reaccion_restante: float = 0.0
        self._banner_logro_texto: str = ""
        self._banner_logro_restante: float = 0.0

        self._cache_sprites: Dict[Tuple[str, str, int, str, int, int], ImageTk.PhotoImage] = {}
        self._cache_cofres: Dict[Tuple[bool, int], ImageTk.PhotoImage] = {}
        self._cofre_cerrado = ImageTk.PhotoImage(_renderizar_cofre_tesoro(False, 1.0))
        self._cofre_abierto = ImageTk.PhotoImage(_renderizar_cofre_tesoro(True, 1.0))

        self._confeti: List[Dict] = [
            {
                "rx": random.uniform(0.10, 0.90),
                "y": random.uniform(0, 260),
                "vy": random.uniform(3.2, 6.2),
                "color": random.choice(["#fde047", "#f472b6", "#38bdf8", "#4ade80", "#c084fc"]),
            }
            for _ in range(30)
        ]

        self.bind("<Configure>", self._al_configurar_lienzo)
        self.bind("<Button-1>", self._manejar_clic)
        self._ciclo_animacion()

    def _al_configurar_lienzo(self, event) -> None:
        """Agrupa eventos rápidos de redimensionado (<Configure>) para evitar tirones al maximizar o estirar."""
        w, h = int(getattr(event, "width", 0)), int(getattr(event, "height", 0))
        uw, uh = self._ultimo_tamano_lienzo
        if abs(w - uw) < 4 and abs(h - uh) < 4:
            return
        self._ultimo_tamano_lienzo = (w, h)
        if self._after_resize_id is not None:
            try:
                self.after_cancel(self._after_resize_id)
            except Exception:
                pass
        self._after_resize_id = self.after(18, self._ejecutar_redibujado_resize)

    def _ejecutar_redibujado_resize(self) -> None:
        self._after_resize_id = None
        if self._activo:
            self._redibujar()

    def aplicar_tema(self, tema: Dict[str, str]) -> None:
        self.tema = tema
        self.configure(bg=tema["bg_stage"])
        self._redibujar()

    def cambiar_skin(self, nueva_skin: str) -> None:
        if nueva_skin in PALETAS_SKIN:
            self.skin = nueva_skin
            self.disparar_reaccion(self.ESTADO_SALUDANDO, 1.8)
            self._redibujar()

    def disparar_reaccion(self, tipo_reaccion: str, duracion_seg: float = 2.2) -> None:
        """Activa una animación corporal especial (salto de paso logrado, cosquillas, saludo)."""
        self._reaccion_temporal = tipo_reaccion
        self._reaccion_restante = max(0.3, duracion_seg)

    def mostrar_banner_logro(self, texto: str, duracion_seg: float = 4.2) -> None:
        """Muestra una insignia flotante dorada sobre Haru al desbloquear medalla o traje."""
        self._banner_logro_texto = texto
        self._banner_logro_restante = duracion_seg
        self.disparar_reaccion(self.ESTADO_PASO_LOGRADO, 3.0)

    def actualizar_habla(self, hablando: bool, boca: Optional[int] = None) -> None:
        """Sincroniza el estado real de locución sin sobrescribir festejos o respiración."""
        self.hablando_activo = hablando
        if boca is not None:
            self.boca_actual = max(0, min(5, int(boca)))
        elif not hablando:
            self.boca_actual = 0

    def actualizar_nivel_mic(self, nivel: float) -> None:
        self.nivel_mic = max(0.0, min(1.0, float(nivel)))

    def actualizar_estado(self, nuevo_estado: str, boca: Optional[int] = None) -> None:
        if nuevo_estado == self.ESTADO_HABLANDO:
            self.hablando_activo = True
            if self.estado not in (self.ESTADO_CELEBRANDO, self.ESTADO_RESPIRANDO):
                self.estado = self.ESTADO_HABLANDO
        else:
            self.estado = nuevo_estado
            if nuevo_estado in (self.ESTADO_ESCUCHANDO, self.ESTADO_PENSANDO):
                # Si el niño le habla o pregunta algo, Haru atiende al instante
                self._reaccion_restante = 0.0
                self._reaccion_temporal = ""
            if nuevo_estado in (self.ESTADO_IDLE, self.ESTADO_PAUSA, self.ESTADO_ESCUCHANDO):
                self.hablando_activo = False
        if boca is not None:
            self.boca_actual = max(0, min(5, int(boca)))
        elif not self.hablando_activo and nuevo_estado not in (self.ESTADO_CELEBRANDO, self.ESTADO_PENSANDO):
            self.boca_actual = 0

    def actualizar_progreso_camino(self, paso_actual: int, total_pasos: int, completada: bool) -> None:
        self.paso_actual = max(0, paso_actual)
        self.total_pasos = max(1, total_pasos)
        self.mision_completada = completada

    def iniciar_respiracion_guiada(self, segundos: float = 16.0) -> None:
        self._respiracion_restante = segundos
        self.estado = self.ESTADO_RESPIRANDO

    @staticmethod
    def _calcular_escala_escenario(w: int, h: int) -> Tuple[int, float]:
        """
        Calcula el alto óptimo en píxeles de Haru y el factor de escala según el
        tamaño actual del lienzo, de modo que en pantalla completa Haru crezca y
        ocupe el escenario con presencia protagónica.
        """
        alto_objetivo = min(h * 0.72, w * 0.66)
        alto_q = int(round(max(245.0, min(500.0, alto_objetivo)) / 32.0) * 32)
        escala = alto_q / 215.0
        return alto_q, escala

    def obtener_sprite(
        self, ojos: str, boca: int, pose_brazos: str, inclinacion: int = 0, alto_px: int = 245
    ) -> ImageTk.PhotoImage:
        clave = (self.skin, ojos, boca, pose_brazos, inclinacion, int(alto_px))
        if clave not in self._cache_sprites:
            if len(self._cache_sprites) > 220:
                self._cache_sprites.clear()
            pil_img = _renderizar_haru_3d(self.skin, ojos, boca, pose_brazos, inclinacion, alto_px=int(alto_px))
            self._cache_sprites[clave] = ImageTk.PhotoImage(pil_img)
        return self._cache_sprites[clave]

    def _obtener_cofre_escalado(self, abierto: bool, escala: float) -> ImageTk.PhotoImage:
        esc_q = int(round(max(1.0, min(1.8, escala)) * 10))
        clave = (abierto, esc_q)
        if clave not in self._cache_cofres:
            self._cache_cofres[clave] = ImageTk.PhotoImage(_renderizar_cofre_tesoro(abierto, esc_q / 10.0))
        return self._cache_cofres[clave]

    def _manejar_clic(self, event) -> None:
        w = max(320, self.winfo_width())
        h = max(260, self.winfo_height())
        _alto_q, escala = self._calcular_escala_escenario(w, h)
        cx, cy = w * 0.48, h * 0.41
        if abs(event.x - cx) < (125 * escala) and abs(event.y - cy) < (110 * escala):
            self.disparar_reaccion(self.ESTADO_COSQUILLAS, 2.0)
            if self.on_click_haru:
                self.on_click_haru()

    def detener_animacion(self) -> None:
        self._activo = False
        if self._after_anim_id is not None:
            try:
                self.after_cancel(self._after_anim_id)
            except Exception:
                pass
            self._after_anim_id = None
        if self._after_resize_id is not None:
            try:
                self.after_cancel(self._after_resize_id)
            except Exception:
                pass
            self._after_resize_id = None

    def resolver_pose_actual(self) -> Tuple[str, str, int, str, int, float]:
        """
        Determina de forma determinista `(accion_efectiva, ojos, boca, pose_brazos, inclinacion, offset_y)`
        combinando estado base, reacción temporal y locución activa.
        Nota: `self.mision_completada` mantiene el Cofre del Tesoro abierto, pero NO bloquea a Haru
        saltando eternamente; tras el festejo temporal Haru queda en reposo conversacional (`IDLE`).
        """
        if self._respiracion_restante > 0 or self.estado == self.ESTADO_RESPIRANDO:
            accion = self.ESTADO_RESPIRANDO
        elif self._reaccion_restante > 0 and self._reaccion_temporal:
            accion = self._reaccion_temporal
        elif self.estado == self.ESTADO_ESCUCHANDO:
            accion = self.ESTADO_ESCUCHANDO
        elif self.hablando_activo:
            accion = self.ESTADO_CELEBRANDO if self.estado == self.ESTADO_CELEBRANDO else self.ESTADO_HABLANDO
        elif self.estado == self.ESTADO_PENSANDO:
            accion = self.ESTADO_PENSANDO
        elif self.estado == self.ESTADO_CELEBRANDO:
            accion = self.ESTADO_CELEBRANDO
        elif self.estado == self.ESTADO_PAUSA:
            accion = self.ESTADO_PAUSA
        else:
            accion = self.ESTADO_IDLE

        parpadeo = (int(self._t * 5) % 46) == 0
        alternador_rapido = int(self._t * 3.6) % 2
        alternador_suave = 0 if math.sin(self._t * 1.6) >= 0 else 1

        # 1. Movimiento vertical (flotación / salto / respiración)
        bob = math.sin(self._t * 1.8) * 6.5
        inclinacion = 0

        if accion == self.ESTADO_PASO_LOGRADO:
            bob = -abs(math.sin(self._t * 5.2)) * 22.0
            ojos = "FELIZ"
            pose_brazos = "VICTORIA_A" if alternador_rapido == 0 else "VICTORIA_B"
            boca = self.boca_actual if (self.hablando_activo and self.boca_actual > 0) else 4
        elif accion == self.ESTADO_CELEBRANDO:
            bob = -abs(math.sin(self._t * 4.4)) * 18.0
            ojos = "FELIZ"
            pose_brazos = "VICTORIA_A" if alternador_rapido == 0 else "VICTORIA_B"
            inclinacion = 1 if alternador_suave == 0 else -1
            boca = self.boca_actual if (self.hablando_activo and self.boca_actual > 0) else 4
        elif accion == self.ESTADO_COSQUILLAS:
            bob = -abs(math.sin(self._t * 6.5)) * 14.0
            ojos = "FELIZ"
            pose_brazos = "SALUDO_A" if alternador_rapido == 0 else "SALUDO_B"
            inclinacion = 1 if alternador_rapido == 0 else -1
            boca = self.boca_actual if (self.hablando_activo and self.boca_actual > 0) else 4
        elif accion == self.ESTADO_SALUDANDO:
            ojos = "FELIZ"
            pose_brazos = "SALUDO_A" if alternador_rapido == 0 else "SALUDO_B"
            inclinacion = 1
            boca = self.boca_actual if self.hablando_activo else 0
        elif accion == self.ESTADO_ESCUCHANDO:
            bob = math.sin(self._t * 2.2) * 4.0
            ojos = "PARPADEO" if parpadeo else "ATENTO"
            pose_brazos = "ESCUCHANDO_OIDO"
            inclinacion = -1
            boca = 0
        elif accion == self.ESTADO_PENSANDO:
            bob = math.sin(self._t * 2.0) * 5.0
            ojos = "PENSANDO"
            pose_brazos = "PENSANDO_MENTON"
            inclinacion = 1
            boca = 5
        elif accion == self.ESTADO_RESPIRANDO:
            ciclo = (self._t * 0.7) % (2 * math.pi)
            inhalando = math.cos(ciclo) >= 0
            bob = -math.sin(ciclo) * 10.0
            ojos = "CALMA"
            pose_brazos = "ZEN_INHALA" if inhalando else "ZEN_EXHALA"
            if self.hablando_activo:
                boca = self.boca_actual
            else:
                boca = 0 if inhalando else 2
        elif accion == self.ESTADO_PAUSA:
            bob = math.sin(self._t * 1.1) * 4.5
            ojos = "CALMA"
            pose_brazos = "NEUTRO_A"
            boca = self.boca_actual if self.hablando_activo else 0
        elif accion == self.ESTADO_HABLANDO:
            ojos = "PARPADEO" if parpadeo else "FELIZ"
            pose_brazos = "EXPLICANDO_A" if int(self._t * 2.4) % 2 == 0 else "EXPLICANDO_B"
            inclinacion = 1 if math.sin(self._t * 1.9) > 0.65 else (-1 if math.sin(self._t * 1.9) < -0.65 else 0)
            boca = self.boca_actual
        else:
            # ESTADO_IDLE: reposo sereno con boca cerrada (sonrisa suave 0)
            ojos = "PARPADEO" if parpadeo else ("FELIZ" if (int(self._t) % 10 < 6) else "ATENTO")
            pose_brazos = "NEUTRO_A" if alternador_suave == 0 else "NEUTRO_B"
            boca = 0

        return accion, ojos, boca, pose_brazos, inclinacion, bob

    def _ciclo_animacion(self) -> None:
        if not self._activo or not self.winfo_exists():
            return
        dt = 0.045
        self._t += 0.08
        if self._reaccion_restante > 0:
            self._reaccion_restante = max(0.0, self._reaccion_restante - dt)
            if self._reaccion_restante == 0.0:
                self._reaccion_temporal = ""
        if self._banner_logro_restante > 0:
            self._banner_logro_restante = max(0.0, self._banner_logro_restante - dt)
        if self._respiracion_restante > 0:
            self._respiracion_restante = max(0.0, self._respiracion_restante - dt)
            if self._respiracion_restante == 0.0 and self.estado == self.ESTADO_RESPIRANDO:
                self.estado = self.ESTADO_IDLE

        self._redibujar()
        self._after_anim_id = self.after(45, self._ciclo_animacion)

    def _redibujar(self) -> None:
        self.delete("all")
        w = max(320, self.winfo_width())
        h = max(250, self.winfo_height())
        alto_sprite, escala = self._calcular_escala_escenario(w, h)

        # 1. Estrellas 3D decorativas flotantes alrededor de Haru (escalan con la pantalla)
        estrellas_pos = [
            (w * 0.18, h * 0.14, 15 * escala, 0.0),
            (w * 0.79, h * 0.19, 11 * escala, 1.7),
            (w * 0.27, h * 0.07, 7.5 * escala, 3.1),
            (w * 0.71, h * 0.08, 8.5 * escala, 4.4),
        ]
        for sx, sy, radio, fase in estrellas_pos:
            dy = math.sin(self._t * 1.4 + fase) * (4.5 * escala)
            self._dibujar_estrella(sx, sy + dy, radio, "#fbbf24", "#fef08a")

        # 2. Camino curvo de aventura en la parte inferior del escenario
        self._dibujar_camino_aventura(w, h, escala)

        # 3. Resolver postura, visema labial y efectos contextuales de Haru
        accion, ojos, boca, pose_brazos, inclinacion, bob = self.resolver_pose_actual()
        cx = w * 0.48
        cy = h * 0.41 + (bob * escala)

        # Efectos ambientales detrás/alrededor de Haru según la acción
        if accion == self.ESTADO_RESPIRANDO:
            ciclo = (self._t * 0.7) % (2 * math.pi)
            factor = (math.sin(ciclo) + 1.0) / 2.0
            r_aura = int((88 + factor * 46) * escala)
            self.create_oval(
                cx - r_aura, cy - r_aura, cx + r_aura, cy + r_aura,
                outline="#99f6e4", width=max(3, int(4 * escala)), dash=(8, 5),
            )
            texto_resp = "Inhala profundo..." if math.cos(ciclo) >= 0 else "Suelta el aire despacito..."
            self.create_text(
                cx, max(22, cy - int(122 * escala)),
                text=texto_resp,
                fill=self.tema["karaoke_active"],
                font=("Segoe UI", max(13, int(12 * escala)), "bold"),
            )
        elif accion == self.ESTADO_ESCUCHANDO:
            amplitud_voz = int(self.nivel_mic * 36 * escala)
            r1 = int((94 + math.sin(self._t * 5.0) * 10) * escala + amplitud_voz)
            r2 = r1 + int(18 * escala)
            self.create_oval(cx - r1, cy - r1, cx + r1, cy + r1, outline="#fde047", width=max(3, int(3 * escala)))
            self.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, outline="#67e8f9", width=2, dash=(6, 6))
        elif accion == self.ESTADO_PENSANDO:
            # Burbujitas vectoriales limpias de pensamiento subiendo desde la sien derecha de Haru
            dy_b = ((self._t * 14) % 24) * escala
            self.create_oval(
                cx + 76 * escala, cy - 72 * escala - dy_b * 0.3,
                cx + 88 * escala, cy - 60 * escala - dy_b * 0.3,
                fill="#e0f2fe", outline="#38bdf8", width=2,
            )
            self.create_oval(
                cx + 92 * escala, cy - 96 * escala - dy_b * 0.5,
                cx + 110 * escala, cy - 78 * escala - dy_b * 0.5,
                fill="#fef9c3", outline="#facc15", width=2,
            )
            self._dibujar_estrella(cx + 116 * escala, cy - 114 * escala - dy_b * 0.6, 11 * escala, "#fde047", "#ffffff")
        elif accion == self.ESTADO_PAUSA:
            dy_p = math.sin(self._t * 1.5) * 8 * escala
            # Burbujas vectoriales serenas de pausa activa (cero emojis)
            self.create_oval(
                cx + 80 * escala, cy - 92 * escala + dy_p,
                cx + 102 * escala, cy - 70 * escala + dy_p,
                fill="#fef3c7", outline="#f59e0b", width=2,
            )
            self.create_oval(
                cx - 102 * escala, cy - 82 * escala - dy_p,
                cx - 82 * escala, cy - 62 * escala - dy_p,
                fill="#ccfbf1", outline="#14b8a6", width=2,
            )

        sprite = self.obtener_sprite(ojos, boca, pose_brazos, inclinacion, alto_px=alto_sprite)
        self.create_image(cx, cy, image=sprite)

        # Partículas vectoriales frontales alegres para PASO_LOGRADO y COSQUILLAS
        if accion == self.ESTADO_PASO_LOGRADO:
            for i in range(6):
                ang = self._t * 2.2 + i * (math.pi / 3)
                rx = cx + math.cos(ang) * (116 * escala)
                ry = cy - 10 * escala + math.sin(ang) * (82 * escala)
                self._dibujar_estrella(rx, ry, 10 * escala, "#fde047", "#ffffff")
        elif accion == self.ESTADO_COSQUILLAS:
            for i, col_p in enumerate(("#fbbf24", "#38bdf8", "#f472b6")):
                dy_c = ((self._t * 28 + i * 22) % 55) * escala
                px_c = cx + (i - 1) * (68 * escala)
                self._dibujar_estrella(px_c, cy - 75 * escala - dy_c, 9 * escala, col_p, "#ffffff")

        # 5. Confeti de celebración al completar misión
        if accion == self.ESTADO_CELEBRANDO:
            r_conf = max(4, int(4 * escala))
            for p in self._confeti:
                p["y"] = (p["y"] + p["vy"]) % max(180, h)
                px = p["rx"] * w + math.sin(self._t + p["y"] * 0.04) * 10
                self.create_oval(px - r_conf, p["y"] - r_conf, px + r_conf, p["y"] + r_conf, fill=p["color"], outline="")

        # 6. Insignia flotante cuando el niño desbloquea una medalla o nuevo traje
        if self._banner_logro_restante > 0 and self._banner_logro_texto:
            bw = min(w - 30, int(390 * min(1.3, escala)))
            bx0, by0 = cx - bw / 2, 12
            bx1, by1 = cx + bw / 2, 48
            self.create_rectangle(bx0, by0, bx1, by1, fill="#fef08a", outline="#f59e0b", width=3)
            self.create_text(
                cx, (by0 + by1) / 2,
                text=self._banner_logro_texto,
                fill="#713f12",
                font=("Segoe UI", 11, "bold"),
            )

    def _dibujar_camino_aventura(self, w: int, h: int, escala: float = 1.0) -> None:
        """Dibuja la senda curva numerada hasta el Cofre del Tesoro adaptada al tamaño del escenario."""
        n = max(1, min(6, self.total_pasos))
        puntos_curva = []
        x_ini = w * 0.10
        x_fin = w * 0.87
        y_base = h * 0.83
        esc_camino = max(1.0, min(1.45, escala * 0.88))

        for i in range(28):
            u = i / 27.0
            px = x_ini + (x_fin - x_ini) * u
            py = y_base + math.sin(u * math.pi * 1.35) * (22.0 * esc_camino)
            puntos_curva.extend([px, py])

        if len(puntos_curva) >= 4:
            self.create_line(
                *puntos_curva,
                fill=self.tema["path_border"],
                width=int(34 * esc_camino),
                smooth=True,
                capstyle="round",
            )
            self.create_line(
                *puntos_curva,
                fill=self.tema["path_road"],
                width=int(26 * esc_camino),
                smooth=True,
                capstyle="round",
            )

        rx_cas = 22 * esc_camino
        ry_cas = 15 * esc_camino
        font_sz = max(11, int(11 * esc_camino))

        for idx in range(n):
            u = (idx + 0.35) / (n + 0.85)
            px = x_ini + (x_fin - x_ini) * u
            py = y_base + math.sin(u * math.pi * 1.35) * (22.0 * esc_camino)
            num_paso = idx + 1

            if self.mision_completada or (self.paso_actual > num_paso):
                color_casilla = self.tema["step_done"]
                borde_casilla = "#ffffff"
                etiqueta = f"✓ {num_paso}"
                color_txt = "#064e3b"
            elif self.paso_actual == num_paso:
                color_casilla = self.tema["step_current"]
                borde_casilla = "#ffffff"
                etiqueta = str(num_paso)
                color_txt = "#713f12"
            else:
                color_casilla = self.tema["step_pending"]
                borde_casilla = self.tema["path_border"]
                etiqueta = str(num_paso)
                color_txt = "#134e4a"

            self.create_oval(
                px - rx_cas, py - ry_cas, px + rx_cas, py + ry_cas,
                fill=color_casilla,
                outline=borde_casilla,
                width=2,
            )
            self.create_text(
                px, py,
                text=etiqueta,
                fill=color_txt,
                font=("Segoe UI", font_sz, "bold"),
            )

        img_cofre = self._obtener_cofre_escalado(self.mision_completada, esc_camino)
        self.create_image(x_fin + 8 * esc_camino, y_base - 14 * esc_camino, image=img_cofre)

    def _dibujar_estrella(self, cx: float, cy: float, r_ext: float,
                          relleno: str, borde: str) -> None:
        pts = []
        r_int = r_ext * 0.48
        for i in range(10):
            ang = -math.pi / 2 + i * (math.pi / 5)
            r = r_ext if i % 2 == 0 else r_int
            pts.extend([cx + math.cos(ang) * r, cy + math.sin(ang) * r])
        self.create_polygon(pts, fill=relleno, outline=borde, width=1.5, smooth=True)
