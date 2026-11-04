"""Búsqueda de fotos, lectura EXIF, emparejado RAW+JPEG y vistas previas."""
import os
import datetime as dt
from dataclasses import dataclass, field, asdict

import cv2
import numpy as np

try:
    import exifread
except ImportError:  # pragma: no cover
    exifread = None

EXT_RAW = {
    ".nef", ".nrw",                # Nikon
    ".arw", ".srf", ".sr2",        # Sony
    ".cr2", ".cr3", ".crw",        # Canon
    ".raf",                        # Fujifilm
    ".orf", ".ori",                # Olympus / OM System
    ".rw2",                        # Panasonic Lumix
    ".pef", ".ptx",                # Pentax
    ".dng",                        # Universal RAW / Leica / DJI / Apple ProRAW
    ".3fr", ".fff",                # Hasselblad
    ".iiq",                        # Phase One
    ".rwl",                        # Leica
}
EXT_JPG = {".jpg", ".jpeg"}
CARPETAS_IGNORADAS = {"revelado", ".revelador", "cullflow", ".cullflow"}


# ---------------------------------------------------------------- E/S segura
def leer_imagen(ruta, flags=cv2.IMREAD_COLOR):
    """cv2.imread no admite rutas con acentos en Windows: usamos imdecode."""
    datos = np.fromfile(ruta, dtype=np.uint8)
    return cv2.imdecode(datos, flags)


def escribir_imagen(ruta, img, params=None):
    ext = os.path.splitext(ruta)[1]
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok:
        raise IOError(f"No se pudo codificar {ruta}")
    tmp = ruta + ".tmp"
    buf.tofile(tmp)
    os.replace(tmp, ruta)


def aplicar_orientacion(img, orient):
    """Orientación EXIF (1..8) -> imagen derecha."""
    if orient == 3:
        return cv2.rotate(img, cv2.ROTATE_180)
    if orient == 6:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if orient == 8:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if orient == 2:
        return cv2.flip(img, 1)
    if orient == 4:
        return cv2.flip(img, 0)
    if orient == 5:
        return cv2.flip(cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE), 1)
    if orient == 7:
        return cv2.flip(cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE), 1)
    return img


# ---------------------------------------------------------------- EXIF
def _ratio(v):
    try:
        x = v.values[0]
        return float(x.num) / float(x.den) if hasattr(x, "num") else float(x)
    except Exception:
        try:
            return float(str(v))
        except Exception:
            return None


def _parse_picture_control(val):
    if not val:
        return ""
    try:
        raw = getattr(val, "values", val)
        if isinstance(raw, (bytes, bytearray, list)):
            b = bytes(raw)
        elif isinstance(raw, str):
            b = raw.encode("latin-1", errors="ignore")
        else:
            return str(val).strip()
        if len(b) >= 24 and (b.startswith(b"0100") or b.startswith(b"0200")):
            name = b[4:24].split(b"\x00")[0].decode("ascii", errors="ignore").strip()
            if name:
                return name.capitalize()
        s = str(val).strip()
        return s if len(s) < 30 else ""
    except Exception:
        return ""


def leer_exif(ruta):
    info = {"modelo": "", "marca": "", "fecha": None, "iso": None, "exposicion": None,
            "apertura": None, "focal": None, "orientacion": 1, "exposicion_txt": "",
            "picture_control": ""}
    if exifread is None:
        return info
    try:
        with open(ruta, "rb") as fh:
            t = exifread.process_file(fh, details=False)
    except Exception:
        return info
    info["modelo"] = str(t.get("Image Model", "")).strip()
    info["marca"] = str(t.get("Image Make", "")).strip()
    # MakerNotes de perfiles de color según fabricante:
    # Nikon: PictureControl
    # Canon: PictureStyle / CanonPictureStyle
    # Sony: CreativeStyle / PictureProfile
    # Fujifilm: FilmMode / FilmSimulation
    # Olympus / Panasonic: PictureMode / PhotoStyle
    pc = (
        t.get("MakerNote PictureControl")
        or t.get("MakerNote PictureControlData")
        or t.get("MakerNote PictureControlName")
        or t.get("MakerNote PictureStyle")
        or t.get("MakerNote CanonPictureStyle")
        or t.get("MakerNote CreativeStyle")
        or t.get("MakerNote FilmMode")
        or t.get("MakerNote FilmSimulation")
        or t.get("MakerNote PhotoStyle")
        or t.get("MakerNote PictureMode")
    )
    info["picture_control"] = _parse_picture_control(pc)
    fecha = t.get("EXIF DateTimeOriginal") or t.get("Image DateTime")
    sub = str(t.get("EXIF SubSecTimeOriginal", "") or "").strip()
    if fecha:
        try:
            d = dt.datetime.strptime(str(fecha).strip(), "%Y:%m:%d %H:%M:%S")
            ts = d.timestamp()
            if sub.isdigit():
                ts += int(sub) / (10 ** len(sub))
            info["fecha"] = ts
        except ValueError:
            pass
    iso = t.get("EXIF ISOSpeedRatings") or t.get("EXIF PhotographicSensitivity")
    try:
        info["iso"] = int(str(iso).split(",")[0].strip("[] ")) if iso else None
    except ValueError:
        pass
    if t.get("EXIF ExposureTime"):
        info["exposicion"] = _ratio(t["EXIF ExposureTime"])
        info["exposicion_txt"] = str(t["EXIF ExposureTime"])
    if t.get("EXIF FNumber"):
        info["apertura"] = _ratio(t["EXIF FNumber"])
    if t.get("EXIF FocalLength"):
        info["focal"] = _ratio(t["EXIF FocalLength"])
    o = t.get("Image Orientation")
    try:
        info["orientacion"] = int(o.values[0]) if o else 1
    except Exception:
        info["orientacion"] = 1
    return info


# ---------------------------------------------------------------- Tomas
@dataclass
class Toma:
    """Una foto: un RAW, un JPEG o una pareja RAW+JPEG con el mismo nombre."""
    clave: str                 # ruta relativa sin extensión (identificador estable)
    raw: str = ""
    jpg: str = ""
    exif: dict = field(default_factory=dict)
    tiempo: float = 0.0
    firma: str = ""            # tamaño+mtime para detectar cambios
    ev_base: float = 0.0       # ganancia fotográfica de cámara calculada para alinear RAW a luminancia real

    @property
    def principal(self):
        return self.raw or self.jpg

    @property
    def nombre(self):
        return os.path.basename(self.principal)

    @property
    def es_raw(self):
        return bool(self.raw)

    def a_dict(self):
        return asdict(self)


def _firma(ruta):
    st = os.stat(ruta)
    return f"{st.st_size}-{int(st.st_mtime)}"


def buscar_tomas(carpeta, excluir=None):
    """Recorre la carpeta (y subcarpetas) y devuelve las tomas ordenadas por hora."""
    excluir = {os.path.normcase(os.path.abspath(e)) for e in (excluir or []) if e}
    grupos = {}
    for raiz, dirs, archivos in os.walk(carpeta):
        dirs[:] = [d for d in dirs
                   if d.lower() not in CARPETAS_IGNORADAS and not d.startswith(".")
                   and os.path.normcase(os.path.abspath(os.path.join(raiz, d))) not in excluir]
        for a in archivos:
            base, ext = os.path.splitext(a)
            ext = ext.lower()
            if ext not in EXT_RAW and ext not in EXT_JPG:
                continue
            if a.startswith("._"):  # basura de macOS
                continue
            ruta = os.path.join(raiz, a)
            rel = os.path.relpath(os.path.join(raiz, base), carpeta).replace("\\", "/")
            t = grupos.setdefault(rel.lower(), Toma(clave=rel))
            if ext in EXT_RAW:
                t.raw = ruta
            elif not t.jpg:
                t.jpg = ruta
    tomas = []
    for t in grupos.values():
        try:
            t.firma = _firma(t.principal)
        except OSError:
            continue
        tomas.append(t)
    return tomas


def completar_exif(t: Toma, cache=None):
    if cache and t.clave in cache and cache[t.clave].get("firma") == t.firma:
        t.exif = cache[t.clave]["exif"]
    else:
        t.exif = leer_exif(t.principal)
        if not t.exif.get("modelo") and t.jpg and t.raw:
            t.exif = leer_exif(t.jpg)
    t.tiempo = t.exif.get("fecha") or os.path.getmtime(t.principal)
    return t


# ---------------------------------------------------------------- Vista previa
def vista_previa(t: Toma, lado=1600):
    """Imagen BGR uint8 pequeña para analizar (rápida: usa la miniatura del RAW)."""
    img = None
    orient = t.exif.get("orientacion", 1) or 1
    if t.jpg:
        img = leer_imagen(t.jpg, cv2.IMREAD_REDUCED_COLOR_2 | cv2.IMREAD_IGNORE_ORIENTATION)
    if img is None and t.raw:
        import rawpy
        try:
            with rawpy.imread(t.raw) as r:
                th = r.extract_thumb()
                if th.format == rawpy.ThumbFormat.JPEG:
                    img = cv2.imdecode(np.frombuffer(th.data, np.uint8),
                                       cv2.IMREAD_REDUCED_COLOR_2 | cv2.IMREAD_IGNORE_ORIENTATION)
                elif th.format == rawpy.ThumbFormat.BITMAP:
                    img = cv2.cvtColor(th.data, cv2.COLOR_RGB2BGR)
        except Exception:
            img = None
        if img is not None and min(img.shape[:2]) < 400:
            img = None  # miniatura demasiado pequeña: mejor decodificar el RAW
        if img is None:
            with rawpy.imread(t.raw) as r:
                rgb = r.postprocess(half_size=True, use_camera_wb=True, output_bps=8)
            img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            orient = 1  # rawpy ya gira la imagen
    if img is None:
        raise IOError(f"No se pudo leer {t.principal}")
    img = aplicar_orientacion(img, orient)
    h, w = img.shape[:2]
    s = lado / max(h, w)
    if s < 1:
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return img
