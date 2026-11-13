"""
Motor de Iconografía Vectorial Limpia 100% Offline (PIL + SVG Inline) — Haru TDAH
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Reemplaza emojis informales estilo mensajería por íconos geométricos limpios:
- En interfaz CustomTkinter (`CTkImage`): renderizados en memoria con `Pillow` a 4x
  (supersampling `LANCZOS`), cero archivos externos y cero conexión a internet.
- En reportes formales HTML (`<svg>`): gráficos vectoriales escalables incrustados
  directamente en el documento para impresión nítida en PDF o navegador offline.
"""

import math
from functools import lru_cache
from typing import Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageDraw


def _hex_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    h = (hex_color or "#ffffff").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (255, 255, 255, alpha)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


@lru_cache(maxsize=256)
def _renderizar_icono_pil(nombre: str, color_hex: str, size: int = 20) -> Image.Image:
    """Dibuja un ícono vectorial minimalista suavizado (4x LANCZOS) en memoria."""
    esc = 4
    s = max(12, int(size)) * esc
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = _hex_rgba(color_hex, 255)
    col_suave = _hex_rgba(color_hex, 95)
    w = max(5, int(s * 0.095))
    m = int(s * 0.13)

    if nombre == "chart":
        # Barras verticales + línea ascendente con nodos (estilo analítico limpio)
        alturas = [0.42, 0.24, 0.34, 0.18, 0.30, 0.22, 0.40]
        ancho_b = max(4, int(s * 0.055))
        paso_x = (s - 2 * m) / float(len(alturas))
        for i, top_f in enumerate(alturas):
            bx = int(m + i * paso_x + paso_x * 0.2)
            by_top = int(s * top_f)
            by_bot = int(s * (0.68 if i % 2 == 0 else 0.76))
            d.rounded_rectangle((bx, by_top, bx + ancho_b, by_bot), radius=2, fill=col)

        nodos = [
            (int(s * 0.16), int(s * 0.84)),
            (int(s * 0.34), int(s * 0.62)),
            (int(s * 0.48), int(s * 0.80)),
            (int(s * 0.65), int(s * 0.52)),
            (int(s * 0.76), int(s * 0.66)),
            (int(s * 0.86), int(s * 0.38)),
        ]
        d.line(nodos, fill=col, width=w + 2, joint="curve")
        rn = max(5, int(s * 0.065))
        for nx, ny in nodos:
            d.ellipse((nx - rn, ny - rn, nx + rn, ny + rn), fill=col)

    elif nombre in ("clipboard", "missions"):
        d.rounded_rectangle((int(s * 0.20), int(s * 0.18), int(s * 0.80), int(s * 0.88)), radius=int(s * 0.09), outline=col, width=w)
        d.rounded_rectangle((int(s * 0.36), int(s * 0.10), int(s * 0.64), int(s * 0.24)), radius=int(s * 0.05), fill=col)
        for fy in (0.40, 0.56, 0.72):
            y = int(s * fy)
            d.line((int(s * 0.33), y, int(s * 0.68), y), fill=col, width=max(4, w - 1))

    elif nombre == "mic":
        d.rounded_rectangle((int(s * 0.36), int(s * 0.12), int(s * 0.64), int(s * 0.56)), radius=int(s * 0.14), fill=col)
        d.arc((int(s * 0.23), int(s * 0.28), int(s * 0.77), int(s * 0.74)), start=0, end=180, fill=col, width=w)
        d.line((int(s * 0.50), int(s * 0.74), int(s * 0.50), int(s * 0.88)), fill=col, width=w)
        d.line((int(s * 0.35), int(s * 0.88), int(s * 0.65), int(s * 0.88)), fill=col, width=w)

    elif nombre == "shield":
        pts = [
            (int(s * 0.50), int(s * 0.10)),
            (int(s * 0.84), int(s * 0.24)),
            (int(s * 0.80), int(s * 0.58)),
            (int(s * 0.50), int(s * 0.90)),
            (int(s * 0.20), int(s * 0.58)),
            (int(s * 0.16), int(s * 0.24)),
        ]
        d.polygon(pts, fill=col_suave, outline=col)
        d.line(pts + [pts[0]], fill=col, width=w, joint="curve")
        d.line(
            [(int(s * 0.36), int(s * 0.52)), (int(s * 0.46), int(s * 0.63)), (int(s * 0.66), int(s * 0.40))],
            fill=col,
            width=w,
            joint="curve",
        )

    elif nombre == "lock":
        d.arc((int(s * 0.31), int(s * 0.12), int(s * 0.69), int(s * 0.52)), start=180, end=360, fill=col, width=w)
        d.rounded_rectangle((int(s * 0.22), int(s * 0.44), int(s * 0.78), int(s * 0.88)), radius=int(s * 0.10), fill=col)
        # Ojo de cerradura recortado
        d.ellipse((int(s * 0.45), int(s * 0.58), int(s * 0.55), int(s * 0.68)), fill=(0, 0, 0, 0))

    elif nombre == "star":
        cx, cy = s * 0.5, s * 0.52
        r_ext, r_int = s * 0.40, s * 0.18
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * (math.pi / 5)
            r = r_ext if i % 2 == 0 else r_int
            pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
        d.polygon(pts, fill=col)

    elif nombre == "trophy":
        d.polygon(
            [(int(s * 0.26), int(s * 0.16)), (int(s * 0.74), int(s * 0.16)), (int(s * 0.64), int(s * 0.56)), (int(s * 0.36), int(s * 0.56))],
            fill=col,
        )
        d.arc((int(s * 0.12), int(s * 0.20), int(s * 0.36), int(s * 0.48)), start=90, end=270, fill=col, width=w)
        d.arc((int(s * 0.64), int(s * 0.20), int(s * 0.88), int(s * 0.48)), start=270, end=90, fill=col, width=w)
        d.rectangle((int(s * 0.45), int(s * 0.55), int(s * 0.55), int(s * 0.76)), fill=col)
        d.rounded_rectangle((int(s * 0.30), int(s * 0.76), int(s * 0.70), int(s * 0.88)), radius=4, fill=col)

    elif nombre == "clock":
        d.ellipse((m, m, s - m, s - m), outline=col, width=w)
        d.line([(int(s * 0.50), int(s * 0.28)), (int(s * 0.50), int(s * 0.52)), (int(s * 0.67), int(s * 0.62))], fill=col, width=w, joint="curve")

    elif nombre == "coffee":
        d.rounded_rectangle((int(s * 0.18), int(s * 0.34), int(s * 0.68), int(s * 0.78)), radius=int(s * 0.10), fill=col)
        d.arc((int(s * 0.58), int(s * 0.40), int(s * 0.86), int(s * 0.68)), start=270, end=90, fill=col, width=w)
        d.line((int(s * 0.14), int(s * 0.86), int(s * 0.74), int(s * 0.86)), fill=col, width=w)
        d.line((int(s * 0.34), int(s * 0.14), int(s * 0.34), int(s * 0.25)), fill=col, width=max(4, w - 2))
        d.line((int(s * 0.52), int(s * 0.12), int(s * 0.52), int(s * 0.25)), fill=col, width=max(4, w - 2))

    elif nombre == "play":
        d.polygon([(int(s * 0.26), int(s * 0.18)), (int(s * 0.82), int(s * 0.50)), (int(s * 0.26), int(s * 0.82))], fill=col)

    elif nombre == "check":
        d.line(
            [(int(s * 0.18), int(s * 0.54)), (int(s * 0.41), int(s * 0.76)), (int(s * 0.84), int(s * 0.26))],
            fill=col,
            width=w + 3,
            joint="curve",
        )

    elif nombre in ("wand", "sparkles"):
        # Estrella de 4 puntas limpia + destello secundario
        for cx, cy, rad in ((s * 0.44, s * 0.54, s * 0.34), (s * 0.76, s * 0.24, s * 0.16)):
            pts = []
            for i in range(8):
                ang = i * (math.pi / 4)
                r = rad if i % 2 == 0 else rad * 0.32
                pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
            d.polygon(pts, fill=col)

    elif nombre == "refresh":
        d.arc((m, m, s - m, s - m), start=35, end=315, fill=col, width=w)
        d.polygon([(int(s * 0.84), int(s * 0.14)), (int(s * 0.86), int(s * 0.42)), (int(s * 0.60), int(s * 0.34))], fill=col)

    elif nombre == "rotate_ccw":
        d.arc((m, m, s - m, s - m), start=225, end=145, fill=col, width=w)
        d.polygon([(int(s * 0.16), int(s * 0.14)), (int(s * 0.14), int(s * 0.42)), (int(s * 0.40), int(s * 0.34))], fill=col)

    elif nombre == "camera":
        d.rounded_rectangle((int(s * 0.12), int(s * 0.28), int(s * 0.88), int(s * 0.82)), radius=int(s * 0.10), outline=col, width=w)
        d.polygon([(int(s * 0.34), int(s * 0.28)), (int(s * 0.42), int(s * 0.16)), (int(s * 0.58), int(s * 0.16)), (int(s * 0.66), int(s * 0.28))], fill=col)
        d.ellipse((int(s * 0.36), int(s * 0.41), int(s * 0.64), int(s * 0.69)), outline=col, width=w)

    elif nombre == "user":
        d.ellipse((int(s * 0.33), int(s * 0.14), int(s * 0.67), int(s * 0.48)), fill=col)
        d.pieslice((int(s * 0.16), int(s * 0.52), int(s * 0.84), int(s * 1.16)), start=180, end=360, fill=col)

    elif nombre == "leaf":
        d.pieslice((int(s * 0.16), int(s * 0.14), int(s * 0.88), int(s * 0.86)), start=270, end=90, fill=col)
        d.ellipse((int(s * 0.22), int(s * 0.20), int(s * 0.78), int(s * 0.76)), fill=col)
        d.line((int(s * 0.22), int(s * 0.82), int(s * 0.66), int(s * 0.36)), fill=_hex_rgba("#ffffff", 190), width=max(4, w - 2))

    elif nombre == "sun":
        d.ellipse((int(s * 0.30), int(s * 0.30), int(s * 0.70), int(s * 0.70)), fill=col)
        for i in range(8):
            ang = i * (math.pi / 4)
            x1 = s * 0.5 + math.cos(ang) * s * 0.28
            y1 = s * 0.5 + math.sin(ang) * s * 0.28
            x2 = s * 0.5 + math.cos(ang) * s * 0.42
            y2 = s * 0.5 + math.sin(ang) * s * 0.42
            d.line((x1, y1, x2, y2), fill=col, width=max(4, w - 1))

    elif nombre == "moon":
        luna = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        dl = ImageDraw.Draw(luna)
        dl.ellipse((int(s * 0.18), int(s * 0.16), int(s * 0.82), int(s * 0.84)), fill=col)
        dl.ellipse((int(s * 0.36), int(s * 0.08), int(s * 0.94), int(s * 0.68)), fill=(0, 0, 0, 0))
        img = luna

    elif nombre == "volume":
        d.polygon(
            [(int(s * 0.16), int(s * 0.38)), (int(s * 0.34), int(s * 0.38)), (int(s * 0.54), int(s * 0.20)), (int(s * 0.54), int(s * 0.80)), (int(s * 0.34), int(s * 0.62)), (int(s * 0.16), int(s * 0.62))],
            fill=col,
        )
        d.arc((int(s * 0.46), int(s * 0.30), int(s * 0.74), int(s * 0.70)), start=300, end=60, fill=col, width=w)
        d.arc((int(s * 0.38), int(s * 0.18), int(s * 0.88), int(s * 0.82)), start=305, end=55, fill=col, width=w)

    elif nombre == "mute":
        d.polygon(
            [(int(s * 0.14), int(s * 0.38)), (int(s * 0.30), int(s * 0.38)), (int(s * 0.50), int(s * 0.20)), (int(s * 0.50), int(s * 0.80)), (int(s * 0.30), int(s * 0.62)), (int(s * 0.14), int(s * 0.62))],
            fill=col,
        )
        d.line((int(s * 0.62), int(s * 0.36), int(s * 0.86), int(s * 0.64)), fill=col, width=w)
        d.line((int(s * 0.86), int(s * 0.36), int(s * 0.62), int(s * 0.64)), fill=col, width=w)

    elif nombre == "wind":
        for yf, xf in ((0.34, 0.76), (0.52, 0.86), (0.70, 0.66)):
            y = int(s * yf)
            xe = int(s * xf)
            d.line((int(s * 0.14), y, xe, y), fill=col, width=w)
            d.arc((xe - int(s * 0.12), y - int(s * 0.14), xe + int(s * 0.10), y + int(s * 0.06)), start=240, end=90, fill=col, width=w)

    elif nombre == "plus":
        d.line((int(s * 0.50), int(s * 0.20), int(s * 0.50), int(s * 0.80)), fill=col, width=w + 2)
        d.line((int(s * 0.20), int(s * 0.50), int(s * 0.80), int(s * 0.50)), fill=col, width=w + 2)

    elif nombre == "trash":
        d.line((int(s * 0.20), int(s * 0.26), int(s * 0.80), int(s * 0.26)), fill=col, width=w)
        d.rounded_rectangle((int(s * 0.38), int(s * 0.14), int(s * 0.62), int(s * 0.26)), radius=3, outline=col, width=max(4, w - 1))
        d.rounded_rectangle((int(s * 0.26), int(s * 0.26), int(s * 0.74), int(s * 0.86)), radius=int(s * 0.07), outline=col, width=w)
        d.line((int(s * 0.42), int(s * 0.40), int(s * 0.42), int(s * 0.72)), fill=col, width=max(4, w - 2))
        d.line((int(s * 0.58), int(s * 0.40), int(s * 0.58), int(s * 0.72)), fill=col, width=max(4, w - 2))

    elif nombre == "save":
        d.rounded_rectangle((int(s * 0.18), int(s * 0.16), int(s * 0.82), int(s * 0.84)), radius=int(s * 0.08), outline=col, width=w)
        d.rectangle((int(s * 0.32), int(s * 0.16), int(s * 0.66), int(s * 0.40)), fill=col)
        d.rounded_rectangle((int(s * 0.28), int(s * 0.54), int(s * 0.72), int(s * 0.84)), radius=4, fill=col_suave, outline=col, width=max(4, w - 2))

    elif nombre == "printer":
        d.rectangle((int(s * 0.28), int(s * 0.14), int(s * 0.72), int(s * 0.34)), outline=col, width=w)
        d.rounded_rectangle((int(s * 0.14), int(s * 0.34), int(s * 0.86), int(s * 0.68)), radius=int(s * 0.08), fill=col)
        d.rectangle((int(s * 0.28), int(s * 0.58), int(s * 0.72), int(s * 0.88)), fill=_hex_rgba("#ffffff", 230), outline=col, width=max(4, w - 1))

    elif nombre == "table":
        d.rounded_rectangle((int(s * 0.14), int(s * 0.18), int(s * 0.86), int(s * 0.82)), radius=int(s * 0.07), outline=col, width=w)
        d.line((int(s * 0.14), int(s * 0.39), int(s * 0.86), int(s * 0.39)), fill=col, width=w)
        d.line((int(s * 0.14), int(s * 0.60), int(s * 0.86), int(s * 0.60)), fill=col, width=max(4, w - 2))
        d.line((int(s * 0.42), int(s * 0.18), int(s * 0.42), int(s * 0.82)), fill=col, width=max(4, w - 2))

    elif nombre == "gift":
        d.rounded_rectangle((int(s * 0.18), int(s * 0.34), int(s * 0.82), int(s * 0.48)), radius=4, outline=col, width=w)
        d.rounded_rectangle((int(s * 0.22), int(s * 0.48), int(s * 0.78), int(s * 0.86)), radius=4, outline=col, width=w)
        d.line((int(s * 0.50), int(s * 0.34), int(s * 0.50), int(s * 0.86)), fill=col, width=w)
        d.ellipse((int(s * 0.28), int(s * 0.16), int(s * 0.50), int(s * 0.35)), outline=col, width=max(4, w - 1))
        d.ellipse((int(s * 0.50), int(s * 0.16), int(s * 0.72), int(s * 0.35)), outline=col, width=max(4, w - 1))

    elif nombre == "arrow_left":
        d.line((int(s * 0.80), int(s * 0.50), int(s * 0.22), int(s * 0.50)), fill=col, width=w + 1)
        d.line([(int(s * 0.44), int(s * 0.26)), (int(s * 0.20), int(s * 0.50)), (int(s * 0.44), int(s * 0.74))], fill=col, width=w + 1, joint="curve")

    elif nombre == "send":
        pts = [(int(s * 0.14), int(s * 0.22)), (int(s * 0.88), int(s * 0.50)), (int(s * 0.14), int(s * 0.78)), (int(s * 0.28), int(s * 0.50))]
        d.polygon(pts, fill=col)

    elif nombre in ("usb", "cpu"):
        d.rounded_rectangle((int(s * 0.26), int(s * 0.26), int(s * 0.74), int(s * 0.74)), radius=int(s * 0.08), outline=col, width=w)
        for pos in (0.38, 0.62):
            p = int(s * pos)
            d.line((p, int(s * 0.10), p, int(s * 0.26)), fill=col, width=max(4, w - 1))
            d.line((p, int(s * 0.74), p, int(s * 0.90)), fill=col, width=max(4, w - 1))
            d.line((int(s * 0.10), p, int(s * 0.26), p), fill=col, width=max(4, w - 1))
            d.line((int(s * 0.74), p, int(s * 0.90), p), fill=col, width=max(4, w - 1))

    elif nombre == "eye":
        d.arc((int(s * 0.10), int(s * 0.24), int(s * 0.90), int(s * 0.88)), start=200, end=340, fill=col, width=w)
        d.arc((int(s * 0.10), int(s * 0.12), int(s * 0.90), int(s * 0.76)), start=20, end=160, fill=col, width=w)
        d.ellipse((int(s * 0.39), int(s * 0.39), int(s * 0.61), int(s * 0.61)), fill=col)

    elif nombre == "bolt":
        pts = [
            (int(s * 0.56), int(s * 0.10)),
            (int(s * 0.24), int(s * 0.54)),
            (int(s * 0.48), int(s * 0.54)),
            (int(s * 0.42), int(s * 0.90)),
            (int(s * 0.76), int(s * 0.44)),
            (int(s * 0.52), int(s * 0.44)),
        ]
        d.polygon(pts, fill=col)

    elif nombre in ("folder", "module"):
        pts = [
            (int(s * 0.12), int(s * 0.24)),
            (int(s * 0.40), int(s * 0.24)),
            (int(s * 0.48), int(s * 0.34)),
            (int(s * 0.88), int(s * 0.34)),
            (int(s * 0.88), int(s * 0.82)),
            (int(s * 0.12), int(s * 0.82)),
        ]
        d.polygon(pts, fill=col_suave, outline=col)
        d.line(pts + [pts[0]], fill=col, width=w, joint="curve")

    elif nombre in ("file_text", "document"):
        d.rounded_rectangle((int(s * 0.20), int(s * 0.12), int(s * 0.80), int(s * 0.88)), radius=int(s * 0.08), fill=col_suave, outline=col, width=w)
        for y_f in (0.36, 0.52, 0.68):
            d.line((int(s * 0.32), int(s * y_f), int(s * 0.68), int(s * y_f)), fill=col, width=max(4, w - 1))

    elif nombre == "globe":
        d.ellipse((int(s * 0.14), int(s * 0.14), int(s * 0.86), int(s * 0.86)), outline=col, width=w)
        d.ellipse((int(s * 0.32), int(s * 0.14), int(s * 0.68), int(s * 0.86)), outline=col, width=max(4, w - 1))
        d.line((int(s * 0.14), int(s * 0.50), int(s * 0.86), int(s * 0.50)), fill=col, width=max(4, w - 1))

    else:  # "dot"
        d.ellipse((int(s * 0.24), int(s * 0.24), int(s * 0.76), int(s * 0.76)), fill=col)

    return img.resize((max(12, int(size)), max(12, int(size))), Image.Resampling.LANCZOS)


def icono_ctk(nombre: str, color: str = "#ffffff", size: int = 18,
              color_dark: Optional[str] = None) -> ctk.CTkImage:
    """Devuelve un `CTkImage` nítido en alta densidad (High-DPI) listo para botones y etiquetas."""
    img_light = _renderizar_icono_pil(nombre, color, size)
    img_dark = _renderizar_icono_pil(nombre, color_dark or color, size)
    return ctk.CTkImage(light_image=img_light, dark_image=img_dark, size=(size, size))


@lru_cache(maxsize=32)
def _miniatura_skin_pil(clave_skin: str, bloqueado: bool, size: int) -> Image.Image:
    from ui.avatar_sprite import _renderizar_haru_3d

    base = _renderizar_haru_3d(clave_skin, "FELIZ", 0, "NEUTRO_A", 0)
    recorte = base.crop((34, 8, 226, 200)).resize((size, size), Image.Resampling.LANCZOS)
    if bloqueado:
        # Atenuar suavemente y superponer candado vectorial limpio abajo a la derecha
        r, g, b, a = recorte.split()
        a = a.point(lambda p: int(p * 0.55))
        recorte = Image.merge("RGBA", (r, g, b, a))
        candado = _renderizar_icono_pil("lock", "#0f172a", max(12, int(size * 0.46)))
        placa = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        dp = ImageDraw.Draw(placa)
        r_bg = max(7, int(size * 0.26))
        cx, cy = size - r_bg - 1, size - r_bg - 1
        dp.ellipse((cx - r_bg, cy - r_bg, cx + r_bg, cy + r_bg), fill=(254, 243, 199, 245))
        recorte = Image.alpha_composite(recorte, placa)
        cw, ch = candado.size
        recorte.alpha_composite(candado, (max(0, cx - cw // 2), max(0, cy - ch // 2)))
    return recorte


def icono_skin_ctk(clave_skin: str, bloqueado: bool = False, size: int = 30) -> ctk.CTkImage:
    """Mini-retrato vectorial 3D real de Haru para los selectores de traje sin emojis."""
    mini = _miniatura_skin_pil(clave_skin, bloqueado, size)
    return ctk.CTkImage(light_image=mini, dark_image=mini, size=(size, size))


# =============================================================================
# ÍCONOS SVG INLINE 100% OFFLINE PARA REPORTES HTML IMPRIMIBLES
# =============================================================================
def svg_icono_html(nombre: str, size: int = 20, color: str = "currentColor") -> str:
    """Genera etiquetas `<svg>` autónomas que funcionan sin conexión a internet."""
    atributos = (
        f'width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="vertical-align:-4px;flex-shrink:0;"'
    )
    if nombre == "chart_trend":
        # Exacto al ícono analítico limpio de barras + línea ascendente con nodos
        return (
            f'<svg {atributos}>'
            f'<rect x="4" y="8" width="1.8" height="7" rx="0.9" fill="{color}"/>'
            f'<rect x="7" y="4" width="1.8" height="9" rx="0.9" fill="{color}"/>'
            f'<rect x="10" y="6" width="1.8" height="9" rx="0.9" fill="{color}"/>'
            f'<rect x="13" y="3" width="1.8" height="8" rx="0.9" fill="{color}"/>'
            f'<rect x="16" y="5" width="1.8" height="7" rx="0.9" fill="{color}"/>'
            f'<rect x="19" y="7" width="1.8" height="5" rx="0.9" fill="{color}"/>'
            f'<polyline points="3.5,20 8,14.5 11.5,18.5 15.5,12 18.2,15.2 21,9.5" '
            f'stroke="{color}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="3.5" cy="20" r="2.1" fill="{color}"/>'
            f'<circle cx="8" cy="14.5" r="2.1" fill="{color}"/>'
            f'<circle cx="11.5" cy="18.5" r="2.1" fill="{color}"/>'
            f'<circle cx="15.5" cy="12" r="2.1" fill="{color}"/>'
            f'<circle cx="18.2" cy="15.2" r="2.1" fill="{color}"/>'
            f'<circle cx="21" cy="9.5" r="2.1" fill="{color}"/>'
            f'</svg>'
        )
    if nombre == "check_circle":
        return (
            f'<svg {atributos} stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<circle cx="12" cy="12" r="9"/><polyline points="8.5 12.5 11 15 16 9.5"/></svg>'
        )
    if nombre == "steps":
        return (
            f'<svg {atributos} stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="4" y="4" width="16" height="16" rx="3"/>'
            f'<line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>'
        )
    if nombre == "clock":
        return (
            f'<svg {atributos} stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>'
        )
    if nombre == "coffee":
        return (
            f'<svg {atributos} stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M17 8h1a3 3 0 0 1 0 6h-1"/><path d="M3 8h14v7a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z"/>'
            f'<line x1="6" y1="3" x2="6" y2="5"/><line x1="10" y1="3" x2="10" y2="5"/></svg>'
        )
    if nombre == "star":
        return (
            f'<svg {atributos}><polygon points="12,2.5 14.9,8.4 21.4,9.3 16.7,13.9 17.8,20.4 12,17.3 6.2,20.4 7.3,13.9 2.6,9.3 9.1,8.4" fill="{color}"/></svg>'
        )
    if nombre == "gift":
        return (
            f'<svg {atributos} stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/>'
            f'<path d="M7.5 8a2.5 2.5 0 0 1 0-5C11 3 12 8 12 8"/><path d="M16.5 8a2.5 2.5 0 0 0 0-5C13 3 12 8 12 8"/></svg>'
        )
    return ""


# =============================================================================
# ÍCONO OFICIAL DE VENTANA Y BARRA DE TAREAS WINDOWS (assets/img/HARU.jpeg)
# =============================================================================
_APPID_REGISTRADO = False
_CACHE_PHOTO_ICONOS = {}


def obtener_ruta_haru_jpeg():
    from core.config import ASSETS_DIR
    ruta = ASSETS_DIR / "img" / "HARU.jpeg"
    if ruta.exists():
        return ruta
    alt = ASSETS_DIR / "img" / "haru_foto.jpg"
    return alt if alt.exists() else ruta


def asegurar_icono_haru_ico():
    """
    Convierte `assets/img/HARU.jpeg` en un archivo `.ico` multirresolución
    (`16x16` a `256x256`) para la esquina superior de las ventanas, la barra de
    tareas de Windows y el ejecutable `Haru.exe`.
    """
    from core.config import ASSETS_DIR, DATA_DIR

    ruta_ico = ASSETS_DIR / "img" / "haru_icon.ico"
    if ruta_ico.exists() and ruta_ico.stat().st_size > 1024:
        return ruta_ico

    ruta_jpg = obtener_ruta_haru_jpeg()
    if not ruta_jpg.exists():
        return None

    try:
        with Image.open(ruta_jpg) as src:
            rgba = src.convert("RGBA")
            w, h = rgba.size
            lado = min(w, h)
            x0 = (w - lado) // 2
            y0 = (h - lado) // 2
            cuadro = rgba.crop((x0, y0, x0 + lado, y0 + lado)).resize(
                (256, 256), Image.Resampling.LANCZOS
            )
            # Máscara de esquinas redondeadas suaves para verse impecable en Windows 11
            mascara = Image.new("L", (256, 256), 0)
            dm = ImageDraw.Draw(mascara)
            dm.rounded_rectangle((4, 4, 251, 251), radius=46, fill=255)
            icono_final = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            icono_final.paste(cuadro, (0, 0), mascara)

            destino = ruta_ico
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                icono_final.save(
                    destino,
                    format="ICO",
                    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
                )
                return destino
            except Exception:
                destino_fallback = DATA_DIR / "haru_icon.ico"
                icono_final.save(
                    destino_fallback,
                    format="ICO",
                    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)],
                )
                return destino_fallback
    except Exception:
        return None


def aplicar_icono_ventana_haru(ventana) -> None:
    """
    Aplica `HARU.jpeg` (`haru_icon.ico`) tanto en la esquina superior izquierda
    de la ventana como en la barra de tareas inferior de Windows, anulando el
    ícono azul por defecto que CustomTkinter inyecta a los 200ms.
    """
    global _APPID_REGISTRADO
    import ctypes
    import sys
    from PIL import ImageTk

    if sys.platform == "win32" and not _APPID_REGISTRADO:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "UniversidadSalesiana.Haru.AsistenteTDAH.2.0"
            )
            _APPID_REGISTRADO = True
        except Exception:
            pass

    ruta_ico = asegurar_icono_haru_ico()
    ruta_jpg = obtener_ruta_haru_jpeg()

    def _fijar_ahora() -> None:
        try:
            if not ventana.winfo_exists():
                return
        except Exception:
            return
        try:
            if ruta_ico and ruta_ico.exists():
                ventana.iconbitmap(default=str(ruta_ico))
                ventana.iconbitmap(str(ruta_ico))
        except Exception:
            pass
        try:
            if ruta_jpg and ruta_jpg.exists():
                root_key = str(ventana.winfo_toplevel())
                if root_key not in _CACHE_PHOTO_ICONOS:
                    with Image.open(ruta_jpg) as im:
                        rgba = im.convert("RGBA")
                        p32 = ImageTk.PhotoImage(rgba.resize((32, 32), Image.Resampling.LANCZOS), master=ventana)
                        p64 = ImageTk.PhotoImage(rgba.resize((64, 64), Image.Resampling.LANCZOS), master=ventana)
                        _CACHE_PHOTO_ICONOS[root_key] = (p64, p32)
                p64, p32 = _CACHE_PHOTO_ICONOS[root_key]
                ventana.wm_iconphoto(True, p64, p32)
        except Exception:
            pass

    _fijar_ahora()
    # CustomTkinter sobrescribe el ícono a los ~200ms con su cuadro azul;
    # re-aplicamos a los 220ms y 450ms para que siempre quede HARU.jpeg.
    try:
        ventana.after(220, _fijar_ahora)
        ventana.after(450, _fijar_ahora)
    except Exception:
        pass


