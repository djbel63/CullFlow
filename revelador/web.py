"""Interfaz web local (solo accesible desde tu PC: http://127.0.0.1:8765)."""
import logging
import os
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, Response, abort, jsonify, request, send_file

from . import config as cfgmod
from . import revelado
from .ia import ClienteIA
from .proceso import Proyecto, _CERROJO

app = Flask(__name__)
ESTADO = {"cfg": None, "proyecto": None, "hilo": None}
_LOCK_VISTA = threading.Lock()


def _p():
    p = ESTADO["proyecto"]
    if p is None:
        abort(400, "Primero elige una carpeta")
    return p


def _ocupado():
    h = ESTADO["hilo"]
    return h is not None and h.is_alive()


def _en_segundo_plano(fn):
    if _ocupado():
        return False
    h = threading.Thread(target=fn, daemon=True)
    ESTADO["hilo"] = h
    h.start()
    return True


@app.get("/")
def inicio():
    with open(os.path.join(os.path.dirname(__file__), "plantillas", "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    return Response(html, mimetype="text/html")


@app.get("/api/config")
def api_config():
    c = ESTADO["cfg"]
    p = ESTADO["proyecto"]
    return jsonify({
        "entrada": p.entrada if p else c.entrada,
        "salida": p.salida if p else c.salida,
        "config": cfgmod.to_dict(c),
        "ia": {"activado": c.ia_activado, "api_base": c.ia_api_base, "modelo": c.ia_modelo,
               "concurrencia": c.ia_concurrencia},
        "rendimiento": {"trabajadores": c.trabajadores_revelado_efectivos(),
                        "trabajadores_analisis": c.trabajadores_analisis_efectivos()},
        "revelado": {"demosaic": c.demosaic, "corregir_aberraciones": c.corregir_aberraciones,
                     "incrustar_icc": c.incrustar_icc},
        "ajustes": [{"clave": k, "etiqueta": e, "min": lo, "max": hi, "paso": st}
                    for k, e, lo, hi, st in revelado.AJUSTES]
    })


@app.post("/api/config")
def api_guardar_config():
    d = request.get_json(force=True) or {}
    c = ESTADO["cfg"]
    cfgmod.actualizar_desde_dict(c, d)
    cfgmod.guardar_en_ini(c)
    p = ESTADO["proyecto"]
    if p:
        p.cfg = c
        if hasattr(p, "ia"):
            p.ia = ClienteIA(c, registro=p.log)
    return jsonify({"ok": True, "config": cfgmod.to_dict(c)})


@app.post("/api/probar_ia")
def api_probar_ia():
    d = request.get_json(silent=True) or {}
    c = ESTADO["cfg"]
    if d:
        temp_c = cfgmod.cargar(c.ruta)
        cfgmod.actualizar_desde_dict(temp_c, d)
        cliente = ClienteIA(temp_c)
    else:
        cliente = ClienteIA(c)
    res = cliente.comprobar()
    return jsonify({k: v for k, v in res.items() if not k.startswith("_")})


@app.post("/api/carpeta")
def api_carpeta():
    """Abre el selector de carpetas de Windows (en un proceso aparte)."""
    codigo = ("import tkinter as tk; from tkinter import filedialog; r=tk.Tk(); r.withdraw(); "
              "r.attributes('-topmost', True); print(filedialog.askdirectory(title='Elige la carpeta de fotos') or '')")
    try:
        out = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=600)
        return jsonify({"ruta": out.stdout.strip().replace("/", os.sep)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ruta": "", "error": str(e)})


@app.post("/api/abrir")
def api_abrir():
    d = request.get_json(force=True)
    entrada = (d.get("entrada") or "").strip().strip('"')
    if not entrada or not os.path.isdir(entrada):
        return jsonify({"error": f"No existe la carpeta: {entrada}"}), 400
    salida = (d.get("salida") or "").strip().strip('"') or ESTADO["cfg"].carpeta_salida(entrada)
    c = ESTADO["cfg"]
    c.ia_activado = bool(d.get("ia", c.ia_activado))
    ESTADO["proyecto"] = Proyecto(entrada, salida, c, registro=print)
    return jsonify({"ok": True, "entrada": entrada, "salida": salida})


@app.post("/api/procesar")
def api_procesar():
    p = _p()
    forzar = bool((request.get_json(silent=True) or {}).get("forzar"))
    if not _en_segundo_plano(lambda: p.ejecutar(forzar=forzar)):
        return jsonify({"error": "Ya hay un proceso en marcha"}), 409
    return jsonify({"ok": True})


@app.get("/api/progreso")
def api_progreso():
    p = ESTADO["proyecto"]
    if not p:
        return jsonify({"fase": "sin carpeta", "log": []})
    pr = dict(p.progreso)
    pr["ocupado"] = _ocupado()
    pr["ia"] = p.estado.get("ia", {})
    return jsonify(pr)


@app.get("/api/grupos")
def api_grupos():
    p = _p()
    salida = []
    grupos = p.estado.get("grupos", [])
    if grupos:
        for g in grupos:
            miembros = []
            for k, s in zip(g["miembros"], g["puntuaciones"]):
                t = p.estado["tomas"].get(k, {})
                q = t.get("calidad", {})
                ex = t.get("exif", {})
                aj_reg = p.estado["ajustes"].get(k, {})
                miembros.append({"clave": k, "nombre": os.path.basename(t.get("raw") or t.get("jpg") or k),
                                 "puntuacion": s, "nitidez": q.get("nitidez"), "caras": len(q.get("caras", [])),
                                 "revelada": k in p.estado["revelados"],
                                 "iso": ex.get("iso"),
                                 "picture_control": ex.get("picture_control", ""),
                                 "origen_ajustes": aj_reg.get("origen", ""),
                                 "categoria": aj_reg.get("categoria", ""),
                                 "tags": aj_reg.get("tags", []),
                                 "pareja": bool(t.get("raw") and t.get("jpg"))})
            salida.append({"id": g["id"], "elegida": g["elegida"], "origen": g["origen"], "miembros": miembros})
    elif p.estado.get("tomas"):
        # Emisión progresiva: fotos que ya han sido analizadas antes de terminar el agrupado
        for k, t in p.estado["tomas"].items():
            q = t.get("calidad", {})
            ex = t.get("exif", {})
            aj_reg = p.estado["ajustes"].get(k, {})
            m = {"clave": k, "nombre": os.path.basename(t.get("raw") or t.get("jpg") or k),
                 "puntuacion": 1.0, "nitidez": q.get("nitidez", 0), "caras": len(q.get("caras", [])),
                 "revelada": k in p.estado["revelados"],
                 "iso": ex.get("iso"),
                 "picture_control": ex.get("picture_control", ""),
                 "origen_ajustes": aj_reg.get("origen", ""),
                 "categoria": aj_reg.get("categoria", ""),
                 "tags": aj_reg.get("tags", []),
                 "pareja": bool(t.get("raw") and t.get("jpg"))}
            salida.append({"id": k, "elegida": k, "origen": "auto", "miembros": [m]})
    return jsonify(salida)


@app.get("/mini/<path:clave>")
def mini(clave):
    p = _p()
    r = p.miniatura(clave)
    if not os.path.exists(r):
        abort(404)
    return send_file(r, mimetype="image/jpeg", max_age=0)


@app.get("/revelada/<path:clave>")
def revelada(clave):
    p = _p()
    info = p.estado["revelados"].get(clave)
    if not info or not os.path.exists(info["rutas"][0]):
        abort(404)
    return send_file(info["rutas"][0], mimetype="image/jpeg", max_age=0)


@app.post("/api/elegir")
def api_elegir():
    p = _p()
    _asegurar_tomas(p)
    d = request.get_json(force=True)
    gid, clave = d.get("grupo"), d.get("clave")
    for g in p.estado["grupos"]:
        if g["id"] == gid and clave in g["miembros"]:
            g["elegida"], g["origen"] = clave, "manual"
            p.estado["elecciones_manuales"][gid] = clave
            p.guardar_estado()
            if p.tomas and clave in p.tomas:
                def tarea():
                    with _CERROJO:
                        p.revelar_una(clave)
                        p.escribir_xmp()
                        p.informe()
                        p.guardar_estado()
                _en_segundo_plano(tarea)
            return jsonify({"ok": True})
    return jsonify({"error": "Grupo o foto no encontrados"}), 404


def _asegurar_tomas(p):
    if not p.tomas:
        with _CERROJO:
            p.analizar()
            p._fase("inactivo")


@app.get("/api/ajustes/<path:clave>")
def api_ajustes(clave):
    p = _p()
    _asegurar_tomas(p)
    if clave not in p.tomas:
        abort(404)
    with _LOCK_VISTA:
        reg = p.estado["ajustes"].get(clave) or p.calcular_ajustes(clave, usar_ia=False)
    return jsonify({
        "auto": reg["auto"],
        "final": reg["final"],
        "origen": reg["origen"],
        "nota": reg.get("nota", ""),
        "categoria": reg.get("categoria", ""),
        "tags": reg.get("tags", []),
    })


@app.post("/api/vista")
def api_vista():
    p = _p()
    _asegurar_tomas(p)
    d = request.get_json(force=True)
    clave = d.get("clave")
    if clave not in p.tomas:
        abort(404)
    clipping = bool(d.get("clipping", False))
    with _LOCK_VISTA:
        datos = p.vista_revelada(clave, d.get("ajustes") or {}, lado=int(d.get("lado", 1200)), recorte_alertas=clipping)
    return Response(datos, mimetype="image/jpeg")


@app.post("/api/recorte")
def api_recorte():
    p = _p()
    _asegurar_tomas(p)
    d = request.get_json(force=True)
    clave = d.get("clave")
    if clave not in p.tomas:
        abort(404)
    x = float(d.get("x", 0.5))
    y = float(d.get("y", 0.5))
    tam = int(d.get("tam", 500))
    ajustes = d.get("ajustes") or {}
    with _LOCK_VISTA:
        datos = p.recorte_1a1(clave, x, y, tam=tam, ajustes=ajustes)
    return Response(datos, mimetype="image/jpeg")


@app.post("/api/ajustes/lote")
def api_ajustes_lote():
    p = _p()
    _asegurar_tomas(p)
    d = request.get_json(force=True)
    claves = d.get("claves") or []
    ajustes = d.get("ajustes") or {}
    afectadas = 0
    with _LOCK_VISTA:
        for c in claves:
            if c in p.tomas:
                p.fijar_ajustes(c, ajustes)
                afectadas += 1
    return jsonify({"ok": True, "afectadas": afectadas})


@app.post("/api/exportar")
def api_exportar():
    p = _p()
    _asegurar_tomas(p)
    d = request.get_json(force=True)
    clave = d.get("clave")
    if clave not in p.tomas:
        abort(404)
    p.fijar_ajustes(clave, d.get("ajustes") or {})

    def tarea():
        with _CERROJO:
            p._fase("revelando", 1)
            try:
                p.revelar_una(clave, forzar=True)
                p.escribir_xmp()
                p.informe()
                p.guardar_estado()
            except Exception as e:  # noqa: BLE001
                p.log(f"⚠ Error al exportar: {e}")
            finally:
                p._fase("terminado")
    if not _en_segundo_plano(tarea):
        return jsonify({"error": "Espera a que termine el proceso en marcha"}), 409
    return jsonify({"ok": True})


@app.post("/api/restablecer")
def api_restablecer():
    p = _p()
    _asegurar_tomas(p)
    clave = request.get_json(force=True).get("clave")
    with _LOCK_VISTA:
        reg = p.restablecer_ajustes(clave)
    return jsonify({"final": reg["final"]})


@app.post("/api/abrir_salida")
def api_abrir_salida():
    p = _p()
    try:
        if os.name == "nt":
            os.startfile(p.salida)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p.salida])
        else:
            subprocess.Popen(["xdg-open", p.salida])
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)})
    return jsonify({"ok": True})


def arrancar(cfg, puerto=8765, abrir=True):
    ESTADO["cfg"] = cfg
    if cfg.entrada and os.path.isdir(cfg.entrada):
        ESTADO["proyecto"] = Proyecto(cfg.entrada, cfg.carpeta_salida(), cfg, registro=print)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # sin una línea por petición
    url = f"http://127.0.0.1:{puerto}/"
    print(f"Interfaz web en {url}  (cierra esta ventana para salir)")
    if abrir:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=puerto, debug=False, threaded=True)
