"""Motor principal: analizar -> agrupar -> elegir -> revelar -> informe."""
import concurrent.futures
import csv
import gc
import hashlib
import json
import os
import queue
import threading
import time
from collections import OrderedDict

import cv2
import numpy as np

from . import analisis, archivos, revelado, xmp
from .ia import ClienteIA

VERSION_ESTADO = 1
_CERROJO = threading.Lock()


def nombre_seguro(clave):
    return clave.replace("/", "__").replace("\\", "__").replace(":", "_")


class Proyecto:
    """Una carpeta de entrada con su carpeta de salida y su estado guardado."""

    def __init__(self, entrada, salida, cfg, registro=None):
        self.entrada = os.path.abspath(entrada)
        self.salida = os.path.abspath(salida)
        self.cfg = cfg
        self.dir_int = os.path.join(self.salida, ".revelador")
        self.dir_min = os.path.join(self.dir_int, "miniaturas")
        self.ruta_estado = os.path.join(self.dir_int, "estado.json")
        self._log_ext = registro
        self.progreso = {"fase": "inactivo", "hecho": 0, "total": 0, "mensaje": "", "log": []}
        self.tomas = {}
        self._proxies = OrderedDict()
        self._lock_proxy = threading.Lock()
        self._lock_estado = threading.Lock()
        self._lock_log = threading.Lock()
        self.estado = self._cargar_estado()
        self.ia = ClienteIA(cfg, registro=self.log)

    # ------------------------------------------------------------ utilidades
    def log(self, msg):
        with self._lock_log:
            linea = time.strftime("%H:%M:%S ") + msg
            self.progreso["log"] = (self.progreso["log"] + [linea])[-300:]
            self.progreso["mensaje"] = msg
            if self._log_ext:
                self._log_ext(msg)

    def _fase(self, fase, total=0):
        self.progreso.update({"fase": fase, "hecho": 0, "total": total})

    def _cargar_estado(self):
        try:
            with open(self.ruta_estado, encoding="utf-8") as fh:
                e = json.load(fh)
            if e.get("version") == VERSION_ESTADO:
                return e
        except (OSError, ValueError):
            pass
        return {"version": VERSION_ESTADO, "entrada": self.entrada, "tomas": {}, "grupos": [],
                "elecciones_manuales": {}, "ajustes": {}, "revelados": {}, "ia": {}}

    def guardar_estado(self):
        with self._lock_estado:
            os.makedirs(self.dir_int, exist_ok=True)
            tmp = self.ruta_estado + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.estado, fh, ensure_ascii=False)
                os.replace(tmp, self.ruta_estado)
            except Exception:
                pass

    def miniatura(self, clave):
        return os.path.join(self.dir_min, nombre_seguro(clave) + ".jpg")

    def ruta_salida(self, clave, ext=".jpg"):
        return os.path.join(self.salida, clave.replace("/", os.sep) + ext)

    # ------------------------------------------------------------ 1. analizar
    def analizar(self):
        os.makedirs(self.dir_min, exist_ok=True)
        lista = archivos.buscar_tomas(self.entrada, excluir=[self.salida])
        cache = self.estado["tomas"]
        self._fase("analizando", len(lista))
        self.log(f"Encontradas {len(lista)} fotos en {self.entrada}")
        nuevas = 0
        pendientes = []

        for t in lista:
            archivos.completar_exif(t, cache)
            c = cache.get(t.clave)
            if not c or c.get("firma") != t.firma or "calidad" not in c or not os.path.exists(self.miniatura(t.clave)):
                pendientes.append(t)
            else:
                c.update({"raw": t.raw, "jpg": t.jpg, "tiempo": t.tiempo})
                self.tomas[t.clave] = t
                self.progreso["hecho"] += 1

        if pendientes:
            n_workers = self.cfg.trabajadores_analisis_efectivos()
            self.log(f"Analizando {len(pendientes)} fotos nuevas en paralelo ({n_workers} hilos)...")

            def _analizar_una(t):
                try:
                    cv2.setNumThreads(1)
                    img = archivos.vista_previa(t, 1600)
                    h, w = img.shape[:2]
                    s = 480 / max(h, w)
                    min_img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
                    archivos.escribir_imagen(self.miniatura(t.clave), min_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    c = {"firma": t.firma, "exif": t.exif, "huella": analisis.huella(img),
                         "calidad": analisis.calidad(img, self.cfg.detectar_caras),
                         "raw": t.raw, "jpg": t.jpg, "tiempo": t.tiempo}
                    return t, c, None
                except Exception as e:
                    return t, None, str(e)

            with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
                futures = {pool.submit(_analizar_una, t): t for t in pendientes}
                for f in concurrent.futures.as_completed(futures):
                    t, c, err = f.result()
                    if err:
                        self.log(f"  ⚠ No se pudo leer {t.nombre}: {err}")
                    else:
                        cache[t.clave] = c
                        self.tomas[t.clave] = t
                        nuevas += 1
                    self.progreso["hecho"] += 1

        # olvida lo que ya no está en la carpeta
        for k in list(cache):
            if k not in self.tomas:
                cache.pop(k)
        self.log(f"Analizadas {nuevas} fotos nuevas o cambiadas ({len(self.tomas)} en total)")
        return nuevas

    # ------------------------------------------------------------ 2. agrupar
    def agrupar(self):
        cache = self.estado["tomas"]
        orden = sorted(self.tomas.values(), key=lambda t: (t.tiempo, t.clave))
        grupos = []
        actual = []
        for t in orden:
            if actual:
                ult = actual[-1]
                mismo_modelo = (t.exif.get("modelo") or "") == (ult.exif.get("modelo") or "")
                cerca = abs(t.tiempo - ult.tiempo) <= self.cfg.segundos_max
                sim = 0.0
                if mismo_modelo and cerca:
                    sim = max(analisis.similitud(cache[t.clave]["huella"], cache[o.clave]["huella"])
                              for o in actual[-3:])
                if mismo_modelo and cerca and sim >= self.cfg.umbral_similitud:
                    actual.append(t)
                    continue
                grupos.append(actual)
            actual = [t]
        if actual:
            grupos.append(actual)

        anteriores = {g["id"]: g for g in self.estado.get("grupos", [])}
        manual = self.estado["elecciones_manuales"]
        resultado = []
        for miembros in grupos:
            claves = [t.clave for t in miembros]
            gid = claves[0]
            met = [cache[k]["calidad"] for k in claves]
            punt = analisis.puntuar_grupo(met, self.cfg, [cache[k]["exif"].get("iso") for k in claves])
            elegida = claves[int(np.argmax(punt))]
            origen = "auto"
            prev = anteriores.get(gid)
            if manual.get(gid) in claves:
                elegida, origen = manual[gid], "manual"
            elif prev and prev.get("origen") == "ia" and prev.get("miembros") == claves:
                elegida, origen = prev["elegida"], "ia"
            resultado.append({"id": gid, "miembros": claves, "puntuaciones": punt,
                              "elegida": elegida, "origen": origen})
        self.estado["grupos"] = resultado
        n_dup = sum(len(g["miembros"]) - 1 for g in resultado)
        self.log(f"{len(resultado)} grupos; {sum(len(g['miembros']) > 1 for g in resultado)} con fotos repetidas "
                 f"({n_dup} descartadas, nunca se borran)")
        return resultado

    # ------------------------------------------------------------ IA
    def estado_ia(self):
        if not self.cfg.ia_activado:
            r = {"disponible": False, "vision": False, "detalle": "IA desactivada"}
        else:
            r = {k: v for k, v in self.ia.comprobar().items() if not k.startswith("_")}
        self.estado["ia"] = r
        return r

    def elegir_con_ia(self):
        ia = self.estado_ia()
        if not (ia["disponible"] and ia["vision"] and self.cfg.ia_elegir_mejor):
            return
        candidatos = [g for g in self.estado["grupos"]
                      if len(g["miembros"]) >= 2 and g["origen"] not in ("manual", "ia")]
        if not candidatos:
            return

        def _evaluar_grupo(g):
            prevs = [archivos.leer_imagen(self.miniatura(k)) for k in g["miembros"][:6]]
            if any(p is None for p in prevs):
                return
            i = self.ia.elegir(prevs, g["puntuaciones"][:6])
            if i is None:
                return
            # Red de seguridad: no se acepta una foto técnicamente mucho peor (p. ej. movida).
            mejor = max(g["puntuaciones"])
            if g["puntuaciones"][i] < mejor - self.cfg.ia_margen_eleccion:
                self.log(f"   IA eligió {os.path.basename(g['miembros'][i])}, pero su puntuación técnica "
                         f"({g['puntuaciones'][i]:.2f}) es muy inferior a la mejor ({mejor:.2f}): se mantiene la automática")
                return
            g["elegida"], g["origen"] = g["miembros"][i], "ia"

        max_w = min(len(candidatos), max(1, self.cfg.ia_concurrencia))
        if max_w > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_w) as pool:
                list(pool.map(_evaluar_grupo, candidatos))
        else:
            for g in candidatos:
                _evaluar_grupo(g)

    # ------------------------------------------------------------ 3. ajustes
    def proxy(self, clave):
        with self._lock_proxy:
            if clave in self._proxies:
                self._proxies.move_to_end(clave)
                return self._proxies[clave]
        t = self.tomas[clave]
        p = revelado.cargar_proxy(t, 1400, preferir_jpg=self.cfg.preferir_jpg_camara)
        with self._lock_proxy:
            self._proxies[clave] = p
            while len(self._proxies) > 8:
                self._proxies.popitem(last=False)
        return p

    def _ev_base(self, clave, proxy):
        """Cuánto aclara la cámara su JPEG respecto al RAW lineal (para el XMP)."""
        t = self.tomas[clave]
        if not t.raw or self.cfg.preferir_jpg_camara:
            return 0.0
        return getattr(t, "ev_base", 0.0)

    def calcular_ajustes(self, clave, usar_ia=True):
        usar_ia = usar_ia and self.cfg.ia_activado and self.estado_ia().get("disponible", False)
        reg = self.estado["ajustes"].get(clave, {})
        firma = self.estado["tomas"][clave]["firma"]
        if reg.get("firma") == firma and reg.get("calibrado") and reg.get("origen") == "manual":
            return reg
        if reg.get("firma") == firma and reg.get("calibrado") and reg.get("auto") and (reg.get("origen") == "ia" or not usar_ia):
            return reg
        t = self.tomas[clave]
        proxy, escala = self.proxy(clave)
        auto = revelado.auto_ajustes(proxy, t.exif, t.es_raw, self.cfg.intensidad_auto)
        reg = {"firma": firma, "auto": auto, "final": auto, "origen": "auto", "nota": "",
               "categoria": "", "tags": [],
               "ev_base": self._ev_base(clave, proxy), "calibrado": True}
        if usar_ia:
            ia = self.estado_ia()
            if ia["disponible"]:
                prev = revelado.a_uint8_bgr(revelado.aplicar(proxy, auto, escala))
                c = self.estado["tomas"][clave]["calidad"]
                est = {"iso": t.exif.get("iso"), "exposicion_s": t.exif.get("exposicion"),
                       "apertura": t.exif.get("apertura"), "focal_mm": t.exif.get("focal"),
                       "camara": t.exif.get("modelo"), "es_raw": t.es_raw,
                       "pixeles_quemados": c["quemadas"], "pixeles_negros": c["empastadas"],
                       "brillo_medio_camara": c["brillo_medio"], "caras": len(c["caras"])}
                gris = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
                est["percentiles_luminancia_propuesta"] = {str(p): int(np.percentile(gris, p)) for p in (1, 5, 25, 50, 75, 95, 99)}
                est["media_rgb_propuesta"] = [round(float(x), 1) for x in prev.reshape(-1, 3)[:, ::-1].mean(0)]
                r = self.ia.ajustes(prev, est, auto, ia["vision"], nombre=t.nombre)
                if r:
                    reg.update({
                        "final": r["ajustes"],
                        "origen": "ia",
                        "nota": r["nota"],
                        "categoria": r.get("categoria", ""),
                        "tags": r.get("tags", []),
                    })
        self.estado["ajustes"][clave] = reg
        return reg

    def fijar_ajustes(self, clave, ajustes):
        reg = self.estado["ajustes"].get(clave) or self.calcular_ajustes(clave, usar_ia=False)
        reg = dict(reg)
        reg.update({"final": revelado.limitar(ajustes), "origen": "manual"})
        self.estado["ajustes"][clave] = reg
        self.guardar_estado()
        return reg

    def restablecer_ajustes(self, clave):
        self.estado["ajustes"].pop(clave, None)
        reg = self.calcular_ajustes(clave, usar_ia=False)
        self.guardar_estado()
        return reg

    def vista_revelada(self, clave, ajustes, lado=1200, recorte_alertas=False):
        proxy, escala = self.proxy(clave)
        rgb = revelado.aplicar(proxy, ajustes, escala, recorte_alertas=recorte_alertas)
        bgr = revelado.a_uint8_bgr(rgb)
        h, w = bgr.shape[:2]
        s = lado / max(h, w)
        if s < 1:
            bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return buf.tobytes()

    def recorte_1a1(self, clave, x_rel, y_rel, tam=550, ajustes=None):
        """Extrae un recorte 1:1 a resolución completa alrededor de (x_rel, y_rel)."""
        t = self.tomas[clave]
        img_full = None
        orient = t.exif.get("orientacion", 1) or 1
        proxy, _ = self.proxy(clave)
        hp, wp = proxy.shape[:2]

        if t.jpg and os.path.exists(t.jpg):
            img_full = archivos.leer_imagen(t.jpg, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            img_full = archivos.aplicar_orientacion(img_full, orient)
        elif t.raw and os.path.exists(t.raw):
            import rawpy
            try:
                with rawpy.imread(t.raw) as r:
                    th = r.extract_thumb()
                    if th.format == rawpy.ThumbFormat.JPEG:
                        img_full = cv2.imdecode(np.frombuffer(th.data, np.uint8),
                                               cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
                        img_full = archivos.aplicar_orientacion(img_full, orient)
            except Exception:
                pass

        if img_full is None:
            img_full = revelado.a_uint8_bgr(proxy)
        else:
            # Asegurar alineación absoluta de aspecto/orientación con la vista del proxy
            hf, wf = img_full.shape[:2]
            if (wf > hf) != (wp > hp):
                img_full = cv2.rotate(img_full, cv2.ROTATE_90_CLOCKWISE)

        h, w = img_full.shape[:2]
        tam = min(tam, min(h, w))
        cx = int(round(np.clip(x_rel, 0.0, 1.0) * w))
        cy = int(round(np.clip(y_rel, 0.0, 1.0) * h))

        half = tam // 2
        x1 = max(0, min(w - tam, cx - half))
        y1 = max(0, min(h - tam, cy - half))
        x2 = min(w, x1 + tam)
        y2 = min(h, y1 + tam)
        crop = img_full[y1:y2, x1:x2].copy()

        if ajustes:
            try:
                crop_lin = revelado.srgb_a_lineal(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
                crop_aj = revelado.aplicar(crop_lin, ajustes, escala=1.0)
                crop = revelado.a_uint8_bgr(crop_aj)
            except Exception:
                pass

        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return buf.tobytes()

    # ------------------------------------------------------------ 4. revelar
    def _firma_revelado(self, clave, aj):
        datos = json.dumps(["v2", aj, self.cfg.calidad_jpeg, self.cfg.formato_salida, self.cfg.calidad_webp,
                            self.cfg.guardar_tiff16, self.cfg.max_lado,
                            self.cfg.preferir_jpg_camara, self.estado["tomas"][clave]["firma"]], sort_keys=True)
        return hashlib.sha1(datos.encode()).hexdigest()[:16]

    def revelar_una(self, clave, forzar=False):
        t = self.tomas[clave]
        reg = self.calcular_ajustes(clave)
        aj = reg["final"]
        firma = self._firma_revelado(clave, aj)
        ext_principal = ".webp" if self.cfg.formato_salida == "webp" else ".jpg"
        destino = self.ruta_salida(clave, ext_principal)
        hecho = self.estado["revelados"].get(clave)
        if not forzar and hecho and hecho.get("firma") == firma and os.path.exists(destino):
            return False
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        t0 = time.time()
        rgb = revelado.revelar_completo(t, aj, self.cfg.max_lado,
                                        demosaic=self.cfg.demosaic,
                                        corregir_aberraciones=self.cfg.corregir_aberraciones,
                                        preferir_jpg=self.cfg.preferir_jpg_camara)
        rutas = []
        fmt = self.cfg.formato_salida
        if fmt in ("jpeg", "ambos"):
            dest_jpg = self.ruta_salida(clave, ".jpg")
            revelado.guardar_jpeg(rgb, dest_jpg, self.cfg.calidad_jpeg, t.exif,
                                  incrustar_icc=self.cfg.incrustar_icc)
            rutas.append(dest_jpg)
        if fmt in ("webp", "ambos"):
            dest_webp = self.ruta_salida(clave, ".webp")
            revelado.guardar_webp(rgb, dest_webp, self.cfg.calidad_webp, t.exif,
                                  incrustar_icc=self.cfg.incrustar_icc)
            rutas.append(dest_webp)
        if self.cfg.guardar_tiff16:
            rt = self.ruta_salida(clave, ".tif")
            revelado.guardar_tiff16(rgb, rt)
            rutas.append(rt)
        del rgb
        gc.collect()
        self.estado["revelados"][clave] = {"firma": firma, "rutas": rutas, "fecha": time.time(),
                                           "segundos": round(time.time() - t0, 1)}
        self.log(f"  ✓ {t.nombre} revelada en {time.time() - t0:.1f}s ({reg['origen']})")
        return True

    def escribir_xmp(self):
        dir_xmp = os.path.join(self.salida, "xmp")
        elegidas = {g["elegida"] for g in self.estado["grupos"]}
        for g in self.estado["grupos"]:
            for k, p in zip(g["miembros"], g["puntuaciones"]):
                t = self.tomas.get(k)
                if not t:
                    continue
                reg = self.estado["ajustes"].get(k, {})
                es = k in elegidas or self.cfg.revelar == "todas"
                texto = xmp.generar(t, reg.get("final"), elegida=es, puntuacion=p,
                                    ev_base=reg.get("ev_base", 0.0), grupo=g["id"],
                                    categoria=reg.get("categoria", ""),
                                    tags=reg.get("tags", []))
                try:
                    xmp.guardar(t, texto, dir_xmp, self.cfg.xmp_junto_al_original)
                except OSError as e:
                    self.log(f"  ⚠ XMP de {t.nombre}: {e}")

    def informe(self):
        os.makedirs(self.salida, exist_ok=True)
        ruta = os.path.join(self.salida, "informe.csv")
        cache = self.estado["tomas"]
        with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["grupo", "archivo", "elegida", "origen_eleccion", "puntuacion", "nitidez",
                        "ruido", "quemadas_%", "caras", "ojos_detectados", "iso", "picture_control",
                        "categoria", "etiquetas_tags", "fecha", "origen_ajustes", "revelada"])
            for g in self.estado["grupos"]:
                for k, p in zip(g["miembros"], g["puntuaciones"]):
                    c = cache.get(k, {})
                    q = c.get("calidad", {})
                    ex = c.get("exif", {})
                    aj_reg = self.estado["ajustes"].get(k, {})
                    w.writerow([g["id"], os.path.basename(c.get("raw") or c.get("jpg") or k),
                                "sí" if k == g["elegida"] else "no", g["origen"] if k == g["elegida"] else "",
                                f"{p:.3f}".replace(".", ","), q.get("nitidez"), q.get("ruido"),
                                f"{100 * q.get('quemadas', 0):.2f}".replace(".", ","), len(q.get("caras", [])),
                                sum(cf["ojos"] for cf in q.get("caras", [])), ex.get("iso"),
                                ex.get("picture_control", ""),
                                aj_reg.get("categoria", ""),
                                ", ".join(aj_reg.get("tags", [])),
                                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(c.get("tiempo", 0))),
                                aj_reg.get("origen", ""),
                                self.estado["revelados"].get(k, {}).get("rutas", [""])[0]])
        with open(os.path.join(self.salida, "descartadas.txt"), "w", encoding="utf-8") as fh:
            fh.write("Fotos repetidas que NO se han revelado (siguen intactas en la carpeta original).\n")
            fh.write("Formato: descartada  ->  elegida en su lugar\n\n")
            for g in self.estado["grupos"]:
                for k in g["miembros"]:
                    if k != g["elegida"]:
                        fh.write(f"{k}  ->  {g['elegida']}\n")
        return ruta

    # ------------------------------------------------------------ todo junto
    def ejecutar(self, revelar=True, forzar=False):
        with _CERROJO:
            t0 = time.time()
            try:
                self.analizar()
                self.agrupar()
                self.guardar_estado()
                ia = self.estado_ia() if self.cfg.ia_activado else {"disponible": False}
                if self.cfg.ia_activado:
                    if ia.get("disponible"):
                        self.log(f"IA conectada ({'con' if ia.get('vision') else 'sin'} visión)")
                    else:
                        self.log(f"IA no disponible: {ia.get('detalle', '').strip()} -> modo automático")
                    self.elegir_con_ia()
                if revelar:
                    if self.cfg.revelar == "todas":
                        objetivo = [k for g in self.estado["grupos"] for k in g["miembros"]]
                    else:
                        objetivo = [g["elegida"] for g in self.estado["grupos"]]
                    self._fase("revelando", len(objetivo))
                    n_workers = self.cfg.trabajadores_revelado_efectivos()
                    n = 0
                    lock_sync = threading.Lock()

                    usar_pipeline_ia = bool(
                        self.cfg.ia_activado
                        and ia.get("disponible")
                        and self.cfg.ia_concurrencia > 0
                        and len(objetivo) > 1
                    )

                    if usar_pipeline_ia:
                        n_ia = min(len(objetivo), max(1, self.cfg.ia_concurrencia))
                        self.log(f"Revelando en pipeline continuo ({n_workers} hilos CPU + {n_ia} hilos IA)...")

                        cola_ia = queue.Queue()
                        for k in objetivo:
                            cola_ia.put(k)

                        # Búfer intermedio para mantener la GPU alimentada sin sobrecargar RAM
                        cola_revelar = queue.Queue(maxsize=max(8, n_workers * 2))

                        def _ia_worker():
                            while True:
                                try:
                                    k = cola_ia.get_nowait()
                                except queue.Empty:
                                    break
                                try:
                                    self.calcular_ajustes(k, usar_ia=True)
                                except Exception as e:
                                    self.log(f"  ⚠ Error al calcular ajustes de {k}: {e}")
                                cola_revelar.put(k)
                                cola_ia.task_done()

                        def _cpu_worker():
                            nonlocal n
                            while True:
                                k = cola_revelar.get()
                                if k is None:
                                    cola_revelar.task_done()
                                    break
                                try:
                                    if self.revelar_una(k, forzar):
                                        with lock_sync:
                                            n += 1
                                except MemoryError:
                                    with lock_sync:
                                        self.log(f"  ⚠ Sin memoria al revelar {k}. Prueba con max_lado en config.ini")
                                except Exception as e:
                                    with lock_sync:
                                        self.log(f"  ⚠ Error al revelar {k}: {e}")
                                finally:
                                    with lock_sync:
                                        self.progreso["hecho"] += 1
                                        self.guardar_estado()
                                    cola_revelar.task_done()

                        # Iniciar hilos IA (productores continuos)
                        hilos_ia = [threading.Thread(target=_ia_worker, daemon=True) for _ in range(n_ia)]
                        for h in hilos_ia:
                            h.start()

                        # Iniciar hilos CPU (consumidores de revelado a resolución completa)
                        hilos_cpu = [threading.Thread(target=_cpu_worker, daemon=True) for _ in range(n_workers)]
                        for h in hilos_cpu:
                            h.start()

                        # Esperar a que la IA procese la cola continua
                        for h in hilos_ia:
                            h.join()

                        # Enviar señal de fin a los consumidores CPU
                        for _ in range(n_workers):
                            cola_revelar.put(None)

                        # Esperar a que todos los revelados terminen
                        for h in hilos_cpu:
                            h.join()

                    elif n_workers > 1 and len(objetivo) > 1:
                        self.log(f"Revelando en paralelo ({n_workers} hilos de exportación)...")

                        def _tarea_revelar(k):
                            nonlocal n
                            try:
                                if self.revelar_una(k, forzar):
                                    with lock_sync:
                                        n += 1
                            except MemoryError:
                                with lock_sync:
                                    self.log(f"  ⚠ Sin memoria al revelar {k}. Prueba con max_lado en config.ini")
                            except Exception as e:
                                with lock_sync:
                                    self.log(f"  ⚠ Error al revelar {k}: {e}")
                            with lock_sync:
                                self.progreso["hecho"] += 1
                                self.guardar_estado()

                        with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
                            list(pool.map(_tarea_revelar, objetivo))
                    else:
                        for k in objetivo:
                            try:
                                if self.revelar_una(k, forzar):
                                    n += 1
                            except MemoryError:
                                self.log(f"  ⚠ Sin memoria al revelar {k}. Prueba con max_lado en config.ini")
                            except Exception as e:  # noqa: BLE001
                                self.log(f"  ⚠ Error al revelar {k}: {e}")
                            self.progreso["hecho"] += 1
                            self.guardar_estado()
                    self.log(f"Reveladas {n} fotos nuevas o cambiadas")
                self.escribir_xmp()
                self.informe()
                self.guardar_estado()
                self.log(f"Terminado en {time.time() - t0:.0f}s. Resultado en {self.salida}")
            finally:
                self._fase("terminado")
        return self.estado
