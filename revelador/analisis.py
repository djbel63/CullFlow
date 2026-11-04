"""Análisis de cada foto: huella para agrupar y puntuación de calidad."""
import os
import threading

import cv2
import numpy as np

_LOCAL = threading.local()


def _detector_yunet():
    """Detector neuronal de caras y landmarks YuNet (OpenCV DNN), seguro para multihilo."""
    if not hasattr(_LOCAL, "yunet"):
        ruta = os.path.join(os.path.dirname(__file__), "modelos", "face_detection_yunet_2023mar.onnx")
        if os.path.exists(ruta) and hasattr(cv2, "FaceDetectorYN"):
            try:
                _LOCAL.yunet = cv2.FaceDetectorYN.create(ruta, "", (320, 320), score_threshold=0.6, nms_threshold=0.3)
            except Exception:
                _LOCAL.yunet = False
        else:
            _LOCAL.yunet = False
    return _LOCAL.yunet


def _clasificadores():
    """Clasificadores de caras y ojos seguros para multihilo (fallback Haar Cascades)."""
    if not hasattr(_LOCAL, "caras"):
        if not hasattr(cv2, "CascadeClassifier"):
            _LOCAL.caras, _LOCAL.ojos = False, False
            return _LOCAL.caras, _LOCAL.ojos
        base = getattr(cv2, "data", None)
        base = base.haarcascades if base else ""
        caras = cv2.CascadeClassifier(os.path.join(base, "haarcascade_frontalface_alt2.xml"))
        ojos = cv2.CascadeClassifier(os.path.join(base, "haarcascade_eye.xml"))
        _LOCAL.caras = caras if not caras.empty() else False
        _LOCAL.ojos = ojos if not ojos.empty() else False
    return _LOCAL.caras, _LOCAL.ojos


def huella(img_bgr):
    """Datos compactos para comparar fotos entre sí."""
    gris = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    peq = cv2.resize(gris, (9, 8), interpolation=cv2.INTER_AREA)
    dhash = (peq[:, 1:] > peq[:, :-1]).flatten()
    mini = cv2.resize(gris, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
    hsv = cv2.cvtColor(cv2.resize(img_bgr, (64, 64), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-6)
    h, w = gris.shape
    return {"dhash": "".join("1" if b else "0" for b in dhash),
            "mini": mini.astype(np.uint8).tolist(),
            "hist": hist.round(5).tolist(),
            "horizontal": bool(w >= h)}


def similitud(a, b):
    """0..1: lo parecidas que son dos fotos (encuadre + tonos + color)."""
    if a["horizontal"] != b["horizontal"]:
        return 0.0
    ham = sum(x != y for x, y in zip(a["dhash"], b["dhash"])) / 64.0
    s_hash = 1.0 - ham
    ma = np.asarray(a["mini"], np.float32)
    mb = np.asarray(b["mini"], np.float32)
    # correlación de la estructura con pequeñas tolerancias de desplazamiento
    ma_b = cv2.GaussianBlur(ma, (0, 0), 1.5)
    mb_b = cv2.GaussianBlur(mb, (0, 0), 1.5)
    za = (ma_b - ma_b.mean()) / (ma_b.std() + 1e-6)
    best = -1.0
    for dy in (-2, 0, 2):
        for dx in (-2, 0, 2):
            m = np.roll(np.roll(mb_b, dy, 0), dx, 1)[4:-4, 4:-4]
            zb = (m - m.mean()) / (m.std() + 1e-6)
            best = max(best, float((za[4:-4, 4:-4] * zb).mean()))
    s_corr = max(0.0, best)
    ha = np.asarray(a["hist"])
    hb = np.asarray(b["hist"])
    s_hist = float(np.minimum(ha, hb).sum())
    return round(min(1.0, 0.30 * s_hash + 0.50 * s_corr + 0.20 * s_hist), 4)


def _ruido_sigma(gris):
    """Estimación rápida del ruido (método de Immerkær)."""
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    g = gris.astype(np.float32)
    conv = cv2.filter2D(g, -1, k)
    h, w = g.shape
    # solo zonas planas: ignora bordes fuertes
    bordes = cv2.Canny(gris, 50, 150)
    bordes = cv2.dilate(bordes, np.ones((5, 5), np.uint8))
    m = bordes == 0
    if m.sum() < 1000:
        m = np.ones_like(m)
    return float(np.sqrt(np.pi / 2) * np.abs(conv[m]).mean() / 6.0)


def calidad(img_bgr, detectar_caras=True):
    """Métricas de calidad de una vista previa (lado mayor ~1600 px)."""
    gris = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gris.shape
    lap = cv2.Laplacian(cv2.GaussianBlur(gris, (3, 3), 0), cv2.CV_32F)
    # nitidez por zonas: la zona más nítida suele ser el sujeto
    n = 6
    zonas = []
    for i in range(n):
        for j in range(n):
            z = lap[i * h // n:(i + 1) * h // n, j * w // n:(j + 1) * w // n]
            peso = 1.0 + 0.5 * (1 - (abs(i - (n - 1) / 2) + abs(j - (n - 1) / 2)) / (n - 1))
            zonas.append(float(z.var()) * peso)
    zonas.sort(reverse=True)
    nitidez = float(np.mean(zonas[:max(1, len(zonas) // 6)]))
    centro = lap[h // 4:3 * h // 4, w // 4:3 * w // 4]
    nitidez_centro = float(centro.var())

    quemadas = float((gris >= 250).mean())
    empastadas = float((gris <= 5).mean())
    media = float(gris.mean()) / 255.0
    exposicion = 1.0 - min(1.0, quemadas * 8 + empastadas * 4 + abs(media - 0.45) * 0.8)

    ruido = _ruido_sigma(gris)

    caras = []
    if detectar_caras:
        try:
            yn = _detector_yunet()
            if yn is not False and yn is not None:
                s_factor = 640.0 / max(h, w)
                peq_w = int(round(w * s_factor))
                peq_h = int(round(h * s_factor))
                img_peq = cv2.resize(img_bgr, (peq_w, peq_h), interpolation=cv2.INTER_AREA)
                yn.setInputSize((peq_w, peq_h))
                _, faces = yn.detect(img_peq)
                if faces is not None:
                    inv_s = 1.0 / s_factor
                    for f in faces:
                        fx = int(round(f[0] * inv_s))
                        fy = int(round(f[1] * inv_s))
                        fw = int(round(f[2] * inv_s))
                        fh = int(round(f[3] * inv_s))
                        score = float(f[14])
                        if score < 0.55:
                            continue
                        # Landmarks de ojos de YuNet (ojo der f[4:6], ojo izq f[6:8])
                        rx, ry = f[4] * inv_s, f[5] * inv_s
                        lx, ly = f[6] * inv_s, f[7] * inv_s
                        dist_ojos = np.hypot(rx - lx, ry - ly)
                        ojos = 1 if dist_ojos < fw * 0.12 else 2

                        y1 = max(0, min(h - 1, fy))
                        y2 = max(0, min(h, fy + fh))
                        x1 = max(0, min(w - 1, fx))
                        x2 = max(0, min(w, fx + fw))
                        zona = lap[y1:y2, x1:x2]
                        caras.append({"x": fx, "y": fy, "w": fw, "h": fh,
                                      "ojos": ojos, "nitidez": float(zona.var()) if zona.size else 0.0,
                                      "confianza": score})
            else:
                det_c, det_o = _clasificadores()
                if det_c is not False:
                    ms = max(30, int(min(h, w) * 0.06))
                    eq = cv2.equalizeHist(gris)
                    for (x, y, fw, fh) in det_c.detectMultiScale(eq, 1.1, 8, minSize=(ms, ms)):
                        ojos = 0
                        if det_o is not False:
                            roi = eq[y:y + fh // 2 + fh // 10, x:x + fw]
                            e = det_o.detectMultiScale(roi, 1.1, 5, minSize=(max(8, fw // 10),) * 2)
                            ojos = min(2, len(e))
                        zona = lap[y:y + fh, x:x + fw]
                        caras.append({"x": int(x), "y": int(y), "w": int(fw), "h": int(fh),
                                      "ojos": int(ojos), "nitidez": float(zona.var())})
        except Exception:
            caras = []
    return {"nitidez": round(nitidez, 2), "nitidez_centro": round(nitidez_centro, 2),
            "quemadas": round(quemadas, 5), "empastadas": round(empastadas, 5),
            "brillo_medio": round(media, 4), "exposicion": round(exposicion, 4),
            "ruido": round(ruido, 3), "caras": caras}


def puntuar_grupo(metricas, cfg, isos=None):
    """Devuelve una puntuación 0..1 para cada foto del grupo (relativa al grupo)."""
    if not metricas:
        return []
    nit = np.array([m["nitidez"] + 0.3 * m["nitidez_centro"] for m in metricas], float)
    # si hay caras, la nitidez de la cara manda
    if any(m["caras"] for m in metricas):
        nit_c = np.array([max([c["nitidez"] for c in m["caras"]] or [0]) for m in metricas], float)
        nit = 0.5 * nit / (nit.max() + 1e-9) + 0.5 * nit_c / (nit_c.max() + 1e-9)
    else:
        nit = nit / (nit.max() + 1e-9)
    nit = np.clip(nit, 0, 1) ** 0.75
    expo = np.array([m["exposicion"] for m in metricas], float)
    # Ruido: el ruido medido baja cuando la foto está movida, así que solo se
    # compara cuando cambia el ISO dentro del grupo (más ISO = más ruido).
    isos = [i or 0 for i in (isos or [])]
    if len(isos) == len(metricas) and all(isos) and max(isos) > min(isos):
        li = np.log2(np.array(isos, float))
        ru_s = 1.0 - (li - li.min()) / (li.max() - li.min())
    else:
        ru_s = np.ones(len(metricas))
    ojos = []
    for m in metricas:
        if m["caras"]:
            ojos.append(np.mean([c["ojos"] / 2.0 for c in m["caras"]]))
        else:
            ojos.append(np.nan)
    ojos = np.array(ojos, float)
    peso_ojos = cfg.peso_ojos if not np.all(np.isnan(ojos)) else 0.0
    ojos = np.nan_to_num(ojos, nan=0.0)
    total = cfg.peso_nitidez + cfg.peso_exposicion + cfg.peso_ruido + peso_ojos
    p = (cfg.peso_nitidez * nit + cfg.peso_exposicion * expo + cfg.peso_ruido * ru_s
         + peso_ojos * ojos) / max(total, 1e-9)
    return [round(float(x), 4) for x in p]
