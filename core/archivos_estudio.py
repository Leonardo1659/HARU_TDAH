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
MAX_CARACTERES_CONTEXTO = 16000


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
    """Lee párrafos y tablas de un archivo Word (.docx) sin dependencias externas."""
    with zipfile.ZipFile(archivo, "r") as zf:
        xml_bytes = zf.read("word/document.xml")
    raiz = ElementTree.fromstring(xml_bytes)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    parrafos: List[str] = []
    for p in raiz.iter(f"{ns}p"):
        fragmentos = [t.text for t in p.iter(f"{ns}t") if t.text]
        linea = "".join(fragmentos).strip()
        if linea:
            parrafos.append(linea)
    return "\n".join(parrafos)


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


def _leer_pdf_optimizado(archivo: Path) -> str:
    """
    Extrae texto de archivos PDF:
    1. Si `pypdf` está disponible en el entorno, lo utiliza para máxima cobertura.
    2. Si no está disponible, utiliza descompresión nativa de flujos `stream` (`zlib`)
       y decodificación de operadores `Tj` / `TJ` en Python estándar.
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

    lineas_extraidas: List[str] = []
    for bloque in bloques_fuente:
        # Extraer literales entre paréntesis precedidos/seguidos de operadores PDF de texto
        for m in re.finditer(rb"\((?:\\.|[^\\()])+\)", bloque):
            interior = m.group(0)[1:-1]
            txt = _decodificar_literal_pdf(interior).strip()
            if len(txt) >= 2 and any(c.isalpha() for c in txt):
                # Filtrar metadatos internos de fuentes PDF
                if not txt.startswith(("Identity-H", "Adobe", "WinAnsiEncoding", "MacRoman")):
                    lineas_extraidas.append(txt)

    return "\n".join(lineas_extraidas)
