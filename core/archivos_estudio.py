"""
Lectura Local, Rápida y Estructurada de Archivos de Estudio y Pensum — Haru TDAH
Universidad Salesiana de Bolivia - Ingeniería de Sistemas

Extrae texto y bloques temáticos de documentos escolares (.txt, .md, .csv, .tsv,
.docx y .pdf con texto seleccionable) 100% en local y sin requerir compiladores
C++ ni enviar archivos fuera de la computadora.
"""

from __future__ import annotations

import csv
import re
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import List
from xml.etree import ElementTree

EXTENSIONES_ADMITIDAS = {".txt", ".md", ".csv", ".tsv", ".docx", ".pdf"}
MAX_BYTES_ARCHIVO = 12 * 1024 * 1024  # 12 MB
MAX_CARACTERES_CONTEXTO = 32000


class ErrorArchivoEstudio(ValueError):
    """El archivo no pudo procesarse como documento o pensum escolar."""


@dataclass(frozen=True)
class DocumentoEstudio:
    ruta: Path
    nombre: str
    extension: str
    texto: str
    exito: bool = True
    mensaje_error: str = ""

    @property
    def nombre_archivo(self) -> str:
        return self.nombre

    @property
    def texto_completo(self) -> str:
        return self.texto

    @property
    def resumen_pensum(self) -> str:
        return self.resumen(max_chars=1800)

    @property
    def titulo_sugerido(self) -> str:
        base = Path(self.nombre).stem.replace("_", " ").replace("-", " ").strip()
        return base[:42] if base else "Guía Escolar"

    def resumen(self, max_chars: int = 320) -> str:
        compacto = re.sub(r"\s+", " ", self.texto).strip()
        if len(compacto) <= max_chars:
            return compacto
        return compacto[: max_chars - 1].rstrip() + "…"

    def dividir_en_bloques_tematicos(self, max_bloques: int = 8) -> List[str]:
        """
        Divide el documento en secciones o ejercicios independientes para permitir
        que Haru proponga múltiples tareas paso a paso (incluso de materias mixtas).
        """
        texto_norm = self.texto.replace("\r\n", "\n").strip()
        if not texto_norm:
            return []

        # 1. Intentar separar por encabezados explícitos (ej. "1.", "Tema:", "Actividad", "Misión", "##")
        patron_corte = re.compile(
            r"\n(?=(?:#{1,3}\s+|\d{1,2}[\.\)]\s+[A-ZÁÉÍÓÚÑ¡¿]|(?:TEMA|ACTIVIDAD|EJERCICIO|TAREA|MÓDULO|MODULO|UNIDAD|LECCIÓN|LECCION|SECTION|UNIT)\b))",
            re.IGNORECASE,
        )
        partes_brutas = [p.strip() for p in patron_corte.split(texto_norm) if p and len(p.strip()) >= 15]

        # 2. Si no hubo encabezados claros, separar por párrafos dobles sustanciales
        if len(partes_brutas) <= 1:
            parrafos = [p.strip() for p in re.split(r"\n{2,}", texto_norm) if len(p.strip()) >= 18]
            if len(parrafos) >= 2:
                partes_brutas = parrafos
            else:
                lineas = [ln.strip() for ln in texto_norm.splitlines() if len(ln.strip()) >= 18]
                partes_brutas = lineas if len(lineas) >= 2 else [texto_norm]

        # Agrupar fragmentos muy cortos con el siguiente para no crear tareas vacías
        bloques: List[str] = []
        acumulado = ""
        for frag in partes_brutas:
            if not acumulado:
                acumulado = frag
            elif len(acumulado) < 55 and len(bloques) < max_bloques:
                acumulado = f"{acumulado}\n{frag}"
            else:
                bloques.append(acumulado[:1400])
                acumulado = frag
            if len(bloques) >= max_bloques:
                break
        if acumulado and len(bloques) < max_bloques:
            bloques.append(acumulado[:1400])

        return bloques[:max_bloques]


def cargar_documento_estudio(ruta: str | Path) -> DocumentoEstudio:
    """Extrae texto limpio de un archivo escolar (.txt, .md, .csv, .tsv, .docx, .pdf)."""
    archivo = Path(ruta)
    if not archivo.exists() or not archivo.is_file():
        raise ErrorArchivoEstudio("No encontré ese archivo. Intenta seleccionarlo otra vez.")

    ext = archivo.suffix.lower()
    if ext not in EXTENSIONES_ADMITIDAS:
        raise ErrorArchivoEstudio(
            "Formato no compatible. Usa TXT, MD, CSV, DOCX o PDF con texto seleccionable."
        )

    if archivo.stat().st_size > MAX_BYTES_ARCHIVO:
        raise ErrorArchivoEstudio(
            "El archivo supera 12 MB. Elige un documento o guía más ligera para mantener Haru rápido."
        )

    try:
        if ext in {".txt", ".md"}:
            texto = _leer_texto_plano(archivo)
        elif ext in {".csv", ".tsv"}:
            texto = _leer_tabla(archivo, "\t" if ext == ".tsv" else ",")
        elif ext == ".docx":
            texto = _leer_docx(archivo)
        elif ext == ".pdf":
            texto = _leer_pdf_optimizado(archivo)
        else:
            texto = ""
    except ErrorArchivoEstudio:
        raise
    except Exception as exc:
        raise ErrorArchivoEstudio(
            "No pude leer el contenido del archivo. Prueba guardarlo como TXT, DOCX o PDF digital."
        ) from exc

    texto = re.sub(r"[ \t]+", " ", texto or "")
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if not texto:
        raise ErrorArchivoEstudio(
            "No encontré texto seleccionable. Si es un PDF escaneado como imagen, usa DOCX o TXT."
        )

    if len(texto) > MAX_CARACTERES_CONTEXTO:
        texto = texto[:MAX_CARACTERES_CONTEXTO].rstrip() + "\n\n[Documento truncado para respuesta rápida.]"

    return DocumentoEstudio(
        ruta=archivo,
        nombre=archivo.name,
        extension=ext,
        texto=texto,
        exito=True,
        mensaje_error="",
    )


def cargar_archivo_estudio(ruta: str | Path) -> DocumentoEstudio:
    """Versión segura para la interfaz gráfica que retorna `DocumentoEstudio(exito=False)` ante errores."""
    try:
        return cargar_documento_estudio(ruta)
    except ErrorArchivoEstudio as e:
        p = Path(ruta) if ruta else Path("archivo")
        return DocumentoEstudio(
            ruta=p,
            nombre=p.name,
            extension=p.suffix.lower(),
            texto="",
            exito=False,
            mensaje_error=str(e),
        )
    except Exception as e:
        p = Path(ruta) if ruta else Path("archivo")
        return DocumentoEstudio(
            ruta=p,
            nombre=p.name,
            extension=p.suffix.lower(),
            texto="",
            exito=False,
            mensaje_error=f"No se pudo abrir el archivo: {e}",
        )


def _leer_texto_plano(archivo: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return archivo.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return archivo.read_text(encoding="utf-8", errors="ignore")


def _leer_tabla(archivo: Path, delimitador: str) -> str:
    filas: List[str] = []
    with archivo.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        lector = csv.reader(f, delimiter=delimitador)
        for i, fila in enumerate(lector):
            limpia = [celda.strip() for celda in fila if celda.strip()]
            if limpia:
                filas.append(" | ".join(limpia))
            if i >= 120:
                break
    return "\n".join(filas)


def _leer_docx(archivo: Path) -> str:
    """Lee párrafos, tablas, tabulaciones y saltos de línea de un archivo Word (.docx) sin dependencias externas."""
    with zipfile.ZipFile(archivo, "r") as zf:
        xml_bytes = zf.read("word/document.xml")
    raiz = ElementTree.fromstring(xml_bytes)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

    def _texto_parrafo(p_elem) -> str:
        partes: List[str] = []
        for elem in p_elem.iter():
            tag = elem.tag
            if tag == f"{ns}t" and elem.text:
                partes.append(elem.text)
            elif tag == f"{ns}tab":
                partes.append(" ")
            elif tag in (f"{ns}br", f"{ns}cr"):
                partes.append("\n")
        return "".join(partes).strip()

    lineas: List[str] = []
    body = raiz.find(f"{ns}body")
    if body is None:
        for p in raiz.iter(f"{ns}p"):
            t = _texto_parrafo(p)
            if t:
                lineas.append(t)
        return "\n".join(lineas)

    for hijo in body:
        if hijo.tag == f"{ns}p":
            t = _texto_parrafo(hijo)
            if t:
                lineas.append(t)
        elif hijo.tag == f"{ns}tbl":
            for tr in hijo.findall(f".//{ns}tr"):
                celdas = []
                for tc in tr.findall(f".//{ns}tc"):
                    txt_celda = " ".join(
                        t for p in tc.findall(f".//{ns}p") if (t := _texto_parrafo(p))
                    ).strip()
                    if txt_celda:
                        celdas.append(txt_celda)
                if celdas:
                    lineas.append(" | ".join(celdas))
        else:
            for p in hijo.iter(f"{ns}p"):
                t = _texto_parrafo(p)
                if t:
                    lineas.append(t)
    return "\n".join(lineas)


def _decodificar_literal_pdf(cadena_bytes: bytes) -> str:
    """Decodifica secuencias de escape octales y paréntesis en literales de texto PDF."""
    out = bytearray()
    i = 0
    n = len(cadena_bytes)
    while i < n:
        b = cadena_bytes[i]
        if b == 92 and i + 1 < n:  # backslash '\'
            sig = cadena_bytes[i + 1]
            if sig in (110, 114, 116):  # \n, \r, \t
                out.append(32)
                i += 2
                continue
            if 48 <= sig <= 55:  # octal \ddd
                oct_str = bytes([sig])
                i += 2
                for _ in range(2):
                    if i < n and 48 <= cadena_bytes[i] <= 55:
                        oct_str += bytes([cadena_bytes[i]])
                        i += 1
                    else:
                        break
                out.append(int(oct_str, 8) & 0xFF)
                continue
            out.append(sig)
            i += 2
        else:
            out.append(b)
            i += 1
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return out.decode("latin-1", errors="ignore")


def _extraer_cmap_tounicode(bloques_fuente: List[bytes]) -> dict[bytes, str]:
    """Extrae mapas `ToUnicode` (`beginbfchar`/`beginbfrange`) para decodificar cadenas `<HEX>` en PDF."""
    mapa: dict[bytes, str] = {}
    for bloque in bloques_fuente:
        if b"beginbfchar" not in bloque and b"beginbfrange" not in bloque:
            continue
        texto_cmap = bloque.decode("latin-1", errors="ignore")
        for m_sec in re.finditer(r"beginbfchar\s*(.*?)\s*endbfchar", texto_cmap, re.DOTALL):
            for src_hex, dst_hex in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m_sec.group(1)):
                try:
                    src_b = bytes.fromhex(src_hex if len(src_hex) % 2 == 0 else "0" + src_hex)
                    dst_b = bytes.fromhex(dst_hex if len(dst_hex) % 2 == 0 else "0" + dst_hex)
                    mapa[src_b] = dst_b.decode("utf-16-be", errors="ignore") if len(dst_b) >= 2 else chr(dst_b[0])
                except Exception:
                    continue
        for m_sec in re.finditer(r"beginbfrange\s*(.*?)\s*endbfrange", texto_cmap, re.DOTALL):
            for start_h, end_h, dst_h in re.findall(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m_sec.group(1)
            ):
                try:
                    ancho = max(1, (len(start_h) + 1) // 2)
                    ini = int(start_h, 16)
                    fin = min(ini + 256, int(end_h, 16))
                    dst_ini = int(dst_h, 16)
                    for offset in range(fin - ini + 1):
                        mapa[(ini + offset).to_bytes(ancho, "big")] = chr(dst_ini + offset)
                except Exception:
                    continue
    return mapa


def _decodificar_hex_pdf(hex_str: str, cmap: dict[bytes, str]) -> str:
    limpio = re.sub(r"\s+", "", hex_str or "")
    if not limpio:
        return ""
    if len(limpio) % 2 == 1:
        limpio += "0"
    try:
        raw_b = bytes.fromhex(limpio)
    except Exception:
        return ""
    if cmap:
        pasos = 2 if any(len(k) == 2 for k in cmap) else 1
        if pasos == 2 and len(raw_b) % 2 == 0:
            chars = []
            encontrados = 0
            for i in range(0, len(raw_b), 2):
                par = raw_b[i : i + 2]
                if par in cmap:
                    chars.append(cmap[par])
                    encontrados += 1
                else:
                    chars.append(par.decode("latin-1", errors="ignore"))
            if encontrados > 0:
                return "".join(chars)
        chars_1 = []
        enc_1 = 0
        for b in raw_b:
            kb = bytes([b])
            if kb in cmap:
                chars_1.append(cmap[kb])
                enc_1 += 1
            else:
                chars_1.append(chr(b))
        if enc_1 > 0:
            return "".join(chars_1)
    if b"\x00" in raw_b and len(raw_b) % 2 == 0:
        return raw_b.decode("utf-16-be", errors="ignore")
    try:
        return raw_b.decode("utf-8")
    except UnicodeDecodeError:
        return raw_b.decode("latin-1", errors="ignore")


def _extraer_lineas_bt_pdf(contenido: str, cmap: dict[bytes, str]) -> List[str]:
    """Reconstruye líneas lógicas dentro de bloques `BT ... ET` respetando `Tj`, `TJ`, `Td`, `TD`, `T*` y `Tm`."""
    lineas: List[str] = []
    patron_tokens = re.compile(
        r"(\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>|\[(?:\\.|[^\[\]])*\]\s*TJ|-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s+T[dD]|T\*|\[(?:[^\]]+)\]\s*Tm|Tm|\bTj\b|\b'\b|\b\"\b)"
    )
    for bt in re.finditer(r"\bBT\b(.*?)\bET\b", contenido, re.DOTALL):
        cuerpo = bt.group(1)
        buf: List[str] = []
        for tok in patron_tokens.finditer(cuerpo):
            t = tok.group(0).strip()
            if t.endswith("TJ"):
                interior = t[1 : t.rfind("]")]
                for sub in re.finditer(r"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>|(-?\d+(?:\.\d+)?)", interior):
                    seg = sub.group(0)
                    if seg.startswith("("):
                        buf.append(_decodificar_literal_pdf(seg[1:-1].encode("latin-1", errors="ignore")))
                    elif seg.startswith("<"):
                        buf.append(_decodificar_hex_pdf(seg[1:-1], cmap))
                    else:
                        try:
                            if float(seg) <= -120:
                                buf.append(" ")
                        except ValueError:
                            pass
            elif t.startswith("("):
                buf.append(_decodificar_literal_pdf(t[1:-1].encode("latin-1", errors="ignore")))
            elif t.startswith("<"):
                buf.append(_decodificar_hex_pdf(t[1:-1], cmap))
            elif t.endswith(("Td", "TD", "T*", "Tm")):
                linea = re.sub(r"\s+", " ", "".join(buf)).strip()
                if linea:
                    lineas.append(linea)
                buf.clear()
        linea_fin = re.sub(r"\s+", " ", "".join(buf)).strip()
        if linea_fin:
            lineas.append(linea_fin)
    return lineas


def _leer_pdf_optimizado(archivo: Path) -> str:
    """
    Extrae texto de archivos PDF:
    1. Si `pypdf` está disponible en el entorno, lo utiliza para máxima cobertura (Unicode/CMap).
    2. Si no está disponible o falla, utiliza descompresión nativa `zlib`, decodificación
       `ToUnicode` CMap + bloques `BT ... ET` (`Tj` / `TJ`) y literales PDF sin descartar líneas matemáticas.
    """
    try:
        import pypdf  # type: ignore

        lector = pypdf.PdfReader(str(archivo))
        paginas = []
        for idx, pag in enumerate(lector.pages):
            if idx >= 40:
                break
            txt = (pag.extract_text() or "").strip()
            if txt:
                paginas.append(txt)
        if paginas:
            return "\n\n".join(paginas)
    except Exception:
        pass

    return _leer_pdf_fallback_nativo(archivo)


def _leer_pdf_fallback_nativo(archivo: Path) -> str:
    """Extractor PDF puro Python sin dependencias externas, preservando ejercicios numéricos puros."""
    raw = archivo.read_bytes()
    bloques_fuente: List[bytes] = [raw]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL):
        cuerpo = match.group(1)
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                bloques_fuente.append(zlib.decompress(cuerpo, wbits))
                break
            except Exception:
                continue

    cmap = _extraer_cmap_tounicode(bloques_fuente)
    lineas_extraidas: List[str] = []

    for bloque in bloques_fuente:
        texto_b = bloque.decode("latin-1", errors="ignore")
        if "BT" in texto_b and "ET" in texto_b:
            for ln in _extraer_lineas_bt_pdf(texto_b, cmap):
                if len(ln) >= 1 and any(c.isalnum() or c in "+-*/=×÷" for c in ln):
                    if not ln.startswith(("Identity-H", "Adobe", "WinAnsiEncoding", "MacRoman")):
                        lineas_extraidas.append(ln)

    if not lineas_extraidas:
        for bloque in bloques_fuente:
            for m in re.finditer(rb"\((?:\\.|[^\\()])+\)", bloque):
                interior = m.group(0)[1:-1]
                txt = _decodificar_literal_pdf(interior).strip()
                if len(txt) >= 1 and any(c.isalnum() or c in "+-*/=×÷" for c in txt):
                    if not txt.startswith(("Identity-H", "Adobe", "WinAnsiEncoding", "MacRoman")):
                        lineas_extraidas.append(txt)

    return "\n".join(lineas_extraidas)
