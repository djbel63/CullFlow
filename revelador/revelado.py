"""Revelado automático: balance de blancos, exposición, tonos, color, ruido y enfoque."""
import gc
import os

import cv2
import numpy as np

from .archivos import leer_imagen, escribir_imagen, aplicar_orientacion

try:
    import rawpy
    _DEMOSAIC_MAP = {
        "aahd": rawpy.DemosaicAlgorithm.AAHD,
        "ahd": rawpy.DemosaicAlgorithm.AHD,
        "dcb": rawpy.DemosaicAlgorithm.DCB,
        "dht": rawpy.DemosaicAlgorithm.DHT,
        "vng": rawpy.DemosaicAlgorithm.VNG,
        "linear": rawpy.DemosaicAlgorithm.LINEAR,
    }
except ImportError:
    rawpy = None
    _DEMOSAIC_MAP = {}

# clave, etiqueta, mínimo, máximo, paso
AJUSTES = [
    ("exposicion", "Exposición (EV)", -3.0, 3.0, 0.05),
    ("temperatura", "Temperatura", -100, 100, 1),
    ("matiz", "Matiz", -100, 100, 1),
    ("contraste", "Contraste", -100, 100, 1),
    ("altas_luces", "Altas luces", -100, 100, 1),
    ("sombras", "Sombras", -100, 100, 1),
    ("blancos", "Blancos", -100, 100, 1),
    ("negros", "Negros", -100, 100, 1),
    ("claridad", "Claridad", -100, 100, 1),
    ("intensidad", "Intensidad (vibrance)", -100, 100, 1),
    ("saturacion", "Saturación", -100, 100, 1),
    ("vineteo", "Viñeteo", -100, 100, 1),
    ("reduccion_ruido", "Reducción de ruido", 0, 100, 1),
    ("enfoque", "Enfoque", 0, 150, 1),
]
RANGOS = {k: (lo, hi) for k, _, lo, hi, _ in AJUSTES}


def neutros():
    return {k: 0.0 for k in RANGOS}


def limitar(aj):
    out = neutros()
    for k, (lo, hi) in RANGOS.items():
        try:
            v = float(aj.get(k, 0.0))
        except (TypeError, ValueError):
            v = 0.0
        if not np.isfinite(v):
            v = 0.0
        out[k] = round(float(min(hi, max(lo, v))), 2)
    return out


# ------------------------------------------------------------- conversión de color
def srgb_a_lineal(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lineal_a_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def _lum(rgb):
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32)


# ------------------------------------------------------------- carga de imágenes
def calcular_ev_base(toma, r, rgb_half=None):
    """Calcula la ganancia base fotográfica para alinear el RAW lineal con la luminancia de cámara."""
    import rawpy
    try:
        t = r.extract_thumb()
        if t.format == rawpy.ThumbFormat.JPEG:
            thumb = cv2.imdecode(np.frombuffer(t.data, np.uint8), cv2.IMREAD_COLOR)
            if thumb is not None:
                # La miniatura integrada de Nikon y r.postprocess comparten exactamente la misma orientación
                th_s = cv2.resize(thumb, (240, int(round(240.0 * thumb.shape[0] / thumb.shape[1]))))
                if rgb_half is None:
                    rw = r.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16, gamma=(1, 1), half_size=True)
                else:
                    rw = rgb_half
                rw_s = cv2.resize(rw.astype(np.float32) / 65535.0, (th_s.shape[1], th_s.shape[0]))
                th_lin = srgb_a_lineal(cv2.cvtColor(th_s, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
                th_lum = _lum(th_lin)
                rw_lum = _lum(rw_s)
                mask = (th_lum > 0.02) & (th_lum < 0.80) & (rw_lum > 1e-4)
                if mask.sum() > 50:
                    med_ratio = float(np.median(th_lum[mask] / rw_lum[mask]))
                    return float(np.clip(np.log2(med_ratio), 0.5, 3.5))
    except Exception:
        pass

    return 2.2  # Calibración base estándar para sensores Nikon de 14 bits


def cargar_lineal(toma, medio=False, max_lado=0, demosaic="aahd", ev_base=None, preferir_jpg=False):
    """Imagen RGB float32 lineal (sRGB primarios) calibrada fotográficamente."""
    if preferir_jpg and toma.jpg:
        bgr = leer_imagen(toma.jpg, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if bgr is None:
            raise IOError(f"No se pudo leer {toma.jpg}")
        bgr = aplicar_orientacion(bgr, toma.exif.get("orientacion", 1) or 1)
        if medio:
            bgr = cv2.resize(bgr, (bgr.shape[1] // 2, bgr.shape[0] // 2), interpolation=cv2.INTER_AREA)
        img = srgb_a_lineal(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
    elif toma.raw:
        import rawpy
        algo = _DEMOSAIC_MAP.get((demosaic or "aahd").lower(), rawpy.DemosaicAlgorithm.AAHD)
        kw = {
            "use_camera_wb": True,
            "no_auto_bright": True,
            "output_bps": 16,
            "gamma": (1, 1),
            "half_size": medio,
            "highlight_mode": rawpy.HighlightMode.Blend,
            "output_color": rawpy.ColorSpace.sRGB,
        }
        if not medio:
            kw["demosaic_algorithm"] = algo
            if algo == rawpy.DemosaicAlgorithm.DCB:
                kw["dcb_iterations"] = 2
                kw["dcb_enhance"] = True
            kw["median_filter_passes"] = 1  # Limpia moiré y falsos colores tras interpolar
        with rawpy.imread(toma.raw) as r:
            rgb = r.postprocess(**kw)
            if ev_base is None:
                ev_base = getattr(toma, "ev_base", 0.0)
                if not ev_base or ev_base <= 0.0:
                    ev_base = calcular_ev_base(toma, r, rgb if medio else None)
                    toma.ev_base = ev_base
        img = rgb.astype(np.float32) * (1.0 / 65535.0)
        if ev_base:
            img *= np.float32(2.0 ** ev_base)
    else:
        bgr = leer_imagen(toma.jpg, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if bgr is None:
            raise IOError(f"No se pudo leer {toma.jpg}")
        bgr = aplicar_orientacion(bgr, toma.exif.get("orientacion", 1) or 1)
        if medio:
            bgr = cv2.resize(bgr, (bgr.shape[1] // 2, bgr.shape[0] // 2), interpolation=cv2.INTER_AREA)
        img = srgb_a_lineal(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
    if max_lado and max(img.shape[:2]) > max_lado:
        s = max_lado / max(img.shape[:2])
        img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return img


def cargar_proxy(toma, lado=1400, preferir_jpg=False):
    """Versión pequeña lineal + escala respecto a la resolución completa."""
    completo = 0
    if toma.raw and not preferir_jpg:
        try:
            import rawpy
            with rawpy.imread(toma.raw) as r:
                completo = max(r.sizes.width, r.sizes.height)
        except Exception:
            completo = 0
    img = cargar_lineal(toma, medio=True, max_lado=lado, preferir_jpg=preferir_jpg)
    if not completo:
        completo = max(img.shape[:2]) * 2
    return img, max(img.shape[:2]) / float(completo)


# ------------------------------------------------------------- ajustes automáticos
_ISO_RUIDO = [(100, 0), (200, 3), (400, 10), (800, 20), (1600, 32), (3200, 45), (6400, 58), (12800, 70)]


def auto_ajustes(proxy, exif=None, es_raw=True, intensidad=100.0):
    """Calcula los ajustes automáticos con sensibilidad fotográfica para cada tipo de escena."""
    exif = exif or {}
    img = np.ascontiguousarray(proxy, dtype=np.float32)
    aj = neutros()
    eps = 1e-6
    h, w = img.shape[:2]

    # 1) Balance de blancos:
    # Respetar el balance de cámara (use_camera_wb=True) calculado por el sensor de escena
    aj["temperatura"] = 0.0
    aj["matiz"] = 0.0

    # 2) Detección de tipo de escena sobre el proxy ya calibrado a luminancia real:
    lum = _lum(img)
    p05 = float(np.percentile(lum, 5))
    p50 = float(np.percentile(lum, 50))
    p95 = float(np.percentile(lum, 95))
    p995 = float(np.percentile(lum, 99.5))

    # Escena nocturna o de alto rango dinámico (sombras dominantes con luces puntuales)
    es_nocturna = (p50 < 0.06) or (p05 < 0.015 and p995 > 0.6)

    if es_nocturna:
        # En fotos nocturnas, la exposición de cámara ya es intencionada (fondo oscuro, luces brillantes).
        # ev en 0.0 conserva fielmente la noche natural (cero ruido en sombras).
        aj["exposicion"] = 0.0
        aj["altas_luces"] = 0.0   # Permitir que las luces del árbol/bombillas brillen limpias
        aj["sombras"] = 0.0       # Cero levantamiento de sombras para no generar ruido
        aj["negros"] = -5.0       # Anclar negros profundos y limpios
        aj["contraste"] = 10.0    # Firmeza fotográfica
        aj["claridad"] = 8.0
        aj["intensidad"] = 10.0
    else:
        # Escenas diurnas o equilibradas: ajuste fino centrado hacia el gris medio
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        peso = np.exp(-(((xx - w / 2) / (0.45 * w)) ** 2 + ((yy - h / 2) / (0.45 * h)) ** 2))
        valido = lum > 1e-4
        logmed = float(np.exp((np.log(lum[valido] + 1e-4) * peso[valido]).sum() / (peso[valido].sum() + eps)))
        objetivo = 0.18
        ev = float(np.log2(objetivo / max(logmed, 1e-4)))
        # Límites suaves porque la base ya está alineada con la cámara
        ev = float(np.clip(ev * 0.7, -0.4, 0.4) if es_raw else np.clip(ev * 0.5, -0.3, 0.3))
        aj["exposicion"] = ev
        lum_e = lum * (2 ** ev)

        # Altas luces solo si hay recorte real en áreas extensas
        p995e = float(np.percentile(lum_e, 99.5))
        frac_quemada = float((lum_e > 0.98).mean())
        if p995e > 0.95 and frac_quemada > 0.015:
            aj["altas_luces"] = -float(np.clip((p995e - 0.90) * 80 + frac_quemada * 250, 0, 30))
        else:
            aj["altas_luces"] = 0.0

        y = _lum(aplicar(proxy, {**aj, "sombras": 0, "contraste": 0, "claridad": 0,
                                 "intensidad": 0, "saturacion": 0}, escala=0))
        frac_oscura = float((y < 0.10).mean())
        aj["sombras"] = float(np.clip(frac_oscura * 25, 0, 15))
        p005d = float(np.percentile(y, 0.5))
        if p005d > 0.03:
            aj["negros"] = -float(np.clip((p005d - 0.02) * 150, 0, 12))
        desv = float(y.std())
        aj["contraste"] = float(np.clip((0.21 - desv) * 100, 0, 12))
        aj["claridad"] = 10.0
        aj["intensidad"] = 10.0

    aj["saturacion"] = 0.0

    # Ruido y enfoque según ISO
    iso = exif.get("iso") or 100
    xs, ys = zip(*_ISO_RUIDO)
    rr = float(np.interp(np.log2(max(iso, 50)), np.log2(xs), ys))
    if iso >= 1600:
        rr = min(100.0, rr * 1.25)
    aj["reduccion_ruido"] = rr if es_raw else rr * 0.5
    aj["enfoque"] = float(np.clip(30 - rr * 0.25, 15, 30)) if es_raw else 15.0

    f = max(0.0, intensidad) / 100.0
    for k in aj:
        aj[k] *= f
    return limitar(aj)


# ------------------------------------------------------------- aplicación
def aplicar_balance(img, temperatura, matiz):
    k = 0.4 / 100.0
    g = np.array([2 ** (k * (temperatura + matiz)) * 1.0,
                  2 ** (-k * matiz) * 1.0,
                  2 ** (k * (-temperatura + matiz))], np.float32)
    g /= (0.2126 * g[0] + 0.7152 * g[1] + 0.0722 * g[2])  # conserva el brillo
    return img * g


def _curva_tonal(aj):
    """LUT 1D (en espacio gamma) con respuesta fotográfica estilo Picture Control de Nikon.

    Proporciona negros profundos y limpios (anclados en 0.0), contraste armónico en
    medios tonos y conservación natural de altas luces.
    """
    x = np.linspace(0, 1, 4096, dtype=np.float32)
    # Curva base estilo Nikon: añade fuerza y contraste natural a la linealidad plana
    y = (x * x * (3.0 - 2.0 * x)) * 0.45 + x * 0.55

    # Negros y blancos: el negro nunca levanta el cero absoluto
    negros = aj["negros"] / 100.0
    blancos = aj["blancos"] / 100.0
    bp = -negros * 0.06 if negros < 0 else -negros * 0.04
    wp = 1.0 - blancos * 0.15
    y = np.clip((y - bp) / max(wp - bp, 0.05), 0.0, 1.2)

    # Sombras: caída suave hacia el cero absoluto para jamás lavar la noche ni crear ruido
    s = aj["sombras"] / 100.0
    if s != 0:
        yc = np.clip(y, 0.0, 1.0)
        toe = (yc ** 1.8) * ((1.0 - yc) ** 2) * 10.5
        y = y + s * 0.25 * toe

    # Altas luces: roll-off elegante para conservar destellos y bombillas brillantes
    hl = aj["altas_luces"] / 100.0
    if hl != 0:
        yc = np.clip(y, 0.0, 1.0)
        shoulder = (yc ** 2.2) * (1.0 - yc) * 3.5
        y = y + hl * 0.22 * shoulder

    # Contraste de usuario
    c = aj["contraste"] / 100.0
    if c != 0:
        yc = np.clip(y, 0.0, 1.0)
        y = yc + c * 0.9 * (yc * yc * (3.0 - 2.0 * yc) - yc)

    # El punto negro absoluto siempre es puro 0.0
    y[0] = 0.0
    return x, np.clip(y, 0.0, 1.0).astype(np.float32)


def corregir_aberraciones_cromaticas(rgb, escala=1.0):
    """Atenúa halos púrpuras y aberraciones cromáticas en bordes de alto contraste."""
    try:
        hsv = cv2.cvtColor((np.clip(rgb, 0, 1) * 255.0).astype(np.uint8), cv2.COLOR_RGB2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        # Púrpura / magenta saturado en altas luces o ramas a contraluz
        halo_purpura = (h >= 125) & (h <= 170) & (s > 35) & (v > 50)
        halo_cian = (h >= 75) & (h <= 100) & (s > 45) & (v > 70)
        fringe_mask = halo_purpura | halo_cian
        if not np.any(fringe_mask):
            return rgb
        gray = cv2.cvtColor((rgb * 255.0).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        bordes = cv2.Canny(gray, 50, 150)
        rad = max(2, int(round(3 * max(0.5, escala))))
        bordes_dil = cv2.dilate(bordes, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (rad, rad)))
        afectados = fringe_mask & (bordes_dil > 0)
        if np.any(afectados):
            hsv[..., 1] = np.where(afectados, (s * 0.20).astype(np.uint8), s)
            rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).astype(np.float32) / 255.0
    except Exception:
        pass
    return rgb


def aplicar(lineal, aj, escala=1.0, corregir_aberraciones=True, recorte_alertas=False):
    """Revela una imagen lineal con los ajustes dados. Devuelve RGB sRGB float32 0..1.

    escala: tamaño relativo a la resolución completa (para que ruido y enfoque
    se comporten igual en la vista previa). 0 = sin ruido ni enfoque.
    recorte_alertas: resalta en rojo píxeles quemados (>0.985) y en azul los empastados (<0.015).
    """
    aj = limitar(aj)
    img = aplicar_balance(lineal, aj["temperatura"], aj["matiz"])
    img *= np.float32(2 ** aj["exposicion"])

    # recuperación de altas luces en lineal (solo en luces extremas > 0.88 cuando se pide)
    rec = max(0.0, -aj["altas_luces"]) / 100.0
    if rec > 0.02:
        kn = 0.88  # Solo en la cúspide de las luces; jamás aplastar medios tonos
        blanco = 1.0 + 2.0 * rec
        L = _lum(img)
        z = np.maximum(L - kn, 0) / (1 - kn + 1e-6)
        wz = (blanco - kn) / (1 - kn + 1e-6)
        comp = kn + (1 - kn) * z * (1 + z / (wz * wz)) / (1 + z)
        nuevo = np.where(L > kn, comp, L)
        ratio = nuevo / np.maximum(L, 1e-6)
        img *= ratio[..., None]
    img = lineal_a_srgb(img)

    # corrección automática de aberraciones cromáticas (halos púrpuras en bordes)
    if corregir_aberraciones and escala > 0:
        img = corregir_aberraciones_cromaticas(img, escala=escala)

    # reducción de ruido (antes de subir contraste y claridad)
    rr = aj["reduccion_ruido"] / 100.0
    if rr > 0 and escala > 0:
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2Lab)
        # Reducción de ruido de crominancia más efectiva (canales a y b en Lab)
        sig_c = max(0.8, 4.0 * rr * escala)
        lab[..., 1] = cv2.GaussianBlur(lab[..., 1], (0, 0), sig_c)
        lab[..., 2] = cv2.GaussianBlur(lab[..., 2], (0, 0), sig_c)
        if rr * escala > 0.05:
            L = lab[..., 0]
            d = int(np.clip(round(5 * escala), 3, 9))
            lab[..., 0] = cv2.bilateralFilter(L, d, 3.0 + 10.0 * rr, 2.0 + 3.0 * rr * escala)
        img = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB)

    # curva tonal sobre la luminancia
    x, lut = _curva_tonal(aj)
    Y = np.clip(_lum(img), 0, 1)
    Yn = np.interp(Y, x, lut).astype(np.float32)
    ratio = np.clip(Yn / np.maximum(Y, 1e-4), 0, 4)
    img = np.clip(img * ratio[..., None], 0, 1)

    lab = cv2.cvtColor(img, cv2.COLOR_RGB2Lab)
    # claridad: CLAHE sobre la luminancia (SOLO en medios tonos, protegiendo sombras y luces)
    cl = aj["claridad"] / 100.0
    if abs(cl) > 0.01:
        h, w = lab.shape[:2]
        tx = max(4, min(64, int(round(w / 160.0))))
        ty = max(4, min(64, int(round(h / 160.0))))
        L16 = np.clip(lab[..., 0] / 100.0 * 65535, 0, 65535).astype(np.uint16)
        clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(tx, ty))
        Lc = clahe.apply(L16).astype(np.float32) / 65535.0 * 100.0
        # Máscara de medios tonos: 0 en negros (L<15), 1 en medios (L~50), 0 en luces puras (L>95)
        L_norm = np.clip(lab[..., 0] / 100.0, 0, 1)
        mascara_medios = np.maximum(0.0, np.sin(L_norm * np.pi)) ** 1.5
        lab[..., 0] = lab[..., 0] + cl * (Lc - lab[..., 0]) * mascara_medios

    # intensidad (sube más los colores apagados) y saturación (protegiendo sombras del ruido)
    a, b = lab[..., 1], lab[..., 2]
    croma = np.sqrt(a * a + b * b)
    vib = aj["intensidad"] / 100.0
    sat = aj["saturacion"] / 100.0
    mascara_luz = np.clip((lab[..., 0] - 12.0) / 25.0, 0, 1)
    factor = (1.0 + sat) * (1.0 + vib * 0.5 * np.clip(1.0 - croma / 60.0, 0, 1) * mascara_luz)
    lab[..., 1] = a * factor
    lab[..., 2] = b * factor

    # enfoque: máscara de enfoque sobre la luminancia (protegiendo sombras del grano)
    en = aj["enfoque"] / 100.0
    if en > 0 and escala > 0:
        L = lab[..., 0]
        rad = max(0.5, 1.0 * escala)
        desen = cv2.GaussianBlur(L, (0, 0), rad)
        detalle = L - desen
        umbral = 1.0
        detalle = np.where(np.abs(detalle) > umbral, detalle, detalle * 0.1)
        mascara_enfoque = np.clip((L - 15.0) / 25.0, 0, 1)
        lab[..., 0] = L + en * 0.8 * detalle * mascara_enfoque
    img = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB)

    # viñeteo: compensación periférica (>0 aclara esquinas de objetivos, <0 oscurecimiento artístico)
    vin = aj.get("vineteo", 0.0) / 100.0
    if abs(vin) > 0.01:
        h, w = img.shape[:2]
        y_grid = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
        x_grid = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        r2 = (x_grid * x_grid + y_grid * y_grid) * 0.5
        factor = 1.0 + (vin * 0.65) * r2
        img = np.clip(img * factor[..., None], 0, 1)

    img = np.clip(img, 0, 1)
    if recorte_alertas:
        # Píxeles quemados (R,G,B > 0.985): rojo brillante
        quem = (img[..., 0] > 0.985) & (img[..., 1] > 0.985) & (img[..., 2] > 0.985)
        # Píxeles empastados (R,G,B < 0.015): azul cobalto
        emp = (img[..., 0] < 0.015) & (img[..., 1] < 0.015) & (img[..., 2] < 0.015)
        img[quem] = [1.0, 0.0, 0.0]
        img[emp] = [0.0, 0.35, 1.0]
    return img


# ------------------------------------------------------------- exportación
def a_uint8_bgr(rgb):
    return cv2.cvtColor((rgb * 255.0 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR)


_SRGB_ICC = None


def _obtener_perfil_srgb():
    global _SRGB_ICC
    if _SRGB_ICC is None:
        try:
            from PIL import ImageCms
            _SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        except Exception:
            _SRGB_ICC = b""
    return _SRGB_ICC


def _exif_pil(exif):
    try:
        from PIL import Image
        from PIL.TiffImagePlugin import IFDRational
        e = Image.Exif()
        if exif.get("marca"):
            e[0x010F] = exif["marca"]
        if exif.get("modelo"):
            e[0x0110] = exif["modelo"]
        e[0x0131] = "CullFlow Studio"
        e[0x0112] = 1
        sub = {}
        import datetime as dt
        if exif.get("fecha"):
            sub[0x9003] = dt.datetime.fromtimestamp(exif["fecha"]).strftime("%Y:%m:%d %H:%M:%S")
        if exif.get("iso"):
            sub[0x8827] = int(exif["iso"])
        if exif.get("exposicion"):
            from fractions import Fraction
            fr = Fraction(exif["exposicion"]).limit_denominator(100000)
            sub[0x829A] = IFDRational(fr.numerator, fr.denominator)
        if exif.get("apertura"):
            sub[0x829D] = IFDRational(int(round(exif["apertura"] * 10)), 10)
        if exif.get("focal"):
            sub[0x920A] = IFDRational(int(round(exif["focal"] * 10)), 10)
        if sub:
            e.get_ifd(0x8769).update(sub)
        return e
    except Exception:
        return None


def guardar_jpeg(rgb, ruta, calidad=95, exif=None, incrustar_icc=True):
    try:
        from PIL import Image
        im = Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB")
        kw = {"quality": int(calidad), "subsampling": 0 if calidad >= 90 else 2, "optimize": True}
        e = _exif_pil(exif or {})
        if e is not None:
            kw["exif"] = e
        if incrustar_icc:
            icc = _obtener_perfil_srgb()
            if icc:
                kw["icc_profile"] = icc
        tmp = ruta + ".tmp"
        im.save(tmp, "JPEG", **kw)
        os.replace(tmp, ruta)
    except ImportError:
        escribir_imagen(ruta, a_uint8_bgr(rgb), [cv2.IMWRITE_JPEG_QUALITY, int(calidad)])


def guardar_webp(rgb, ruta, calidad=90, exif=None, incrustar_icc=True):
    try:
        from PIL import Image
        im = Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB")
        kw = {"quality": int(calidad), "method": 4}
        e = _exif_pil(exif or {})
        if e is not None:
            kw["exif"] = e
        if incrustar_icc:
            icc = _obtener_perfil_srgb()
            if icc:
                kw["icc_profile"] = icc
        tmp = ruta + ".tmp"
        im.save(tmp, "WEBP", **kw)
        os.replace(tmp, ruta)
    except Exception as exc:
        raise IOError(f"No se pudo guardar WebP {ruta}: {exc}")


def guardar_tiff16(rgb, ruta):
    bgr = cv2.cvtColor((rgb * 65535.0 + 0.5).astype(np.uint16), cv2.COLOR_RGB2BGR)
    # Compresión LZW sin pérdidas para ahorrar espacio (~50% menos que TIFF sin comprimir)
    params = [cv2.IMWRITE_TIFF_COMPRESSION, cv2.IMWRITE_TIFF_COMPRESSION_LZW]
    escribir_imagen(ruta, bgr, params=params)


def revelar_completo(toma, aj, max_lado=0, demosaic="aahd", corregir_aberraciones=True, preferir_jpg=False):
    """Revela a resolución completa (y reduce al final si se pide max_lado)."""
    lin = cargar_lineal(toma, medio=False, demosaic=demosaic, preferir_jpg=preferir_jpg)
    rgb = aplicar(lin, aj, escala=1.0, corregir_aberraciones=corregir_aberraciones)
    del lin
    gc.collect()
    if max_lado and max(rgb.shape[:2]) > max_lado:
        s = max_lado / max(rgb.shape[:2])
        rgb = cv2.resize(rgb, (int(rgb.shape[1] * s), int(rgb.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return rgb
