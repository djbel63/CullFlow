"""Archivo XMP (Lightroom / Camera Raw; darktable lo lee en parte) con los ajustes."""
import os
from xml.sax.saxutils import quoteattr


def _f(v, dec=0, signo=True):
    s = f"{v:+.{dec}f}" if signo else f"{v:.{dec}f}"
    return s


def generar(toma, aj, elegida=True, puntuacion=None, ev_base=0.0, grupo="", categoria="", tags=None):
    """Devuelve el texto XMP.

    En RAW, la exposición se corrige con ev_base (lo que la cámara ya aclara su
    propio JPEG) porque Lightroom parte de un revelado ya aclarado, no del RAW lineal.
    """
    attrs = {
        "xmp:Rating": "3" if elegida else "-1",
        "xmp:Label": "Green" if elegida else "",
        "xmp:CreatorTool": "CullFlow Studio",
        "rev:Grupo": grupo,
        "rev:Elegida": "True" if elegida else "False",
    }
    if puntuacion is not None:
        attrs["rev:Puntuacion"] = f"{puntuacion:.4f}"
    if categoria:
        attrs["rev:Categoria"] = categoria
    if elegida and aj:
        exp = aj["exposicion"] - (ev_base if toma.raw else 0.0)
        attrs.update({
            "crs:Version": "15.0",
            "crs:ProcessVersion": "11.0",
            "crs:HasSettings": "True",
            "crs:Exposure2012": _f(max(-5, min(5, exp)), 2),
            "crs:Contrast2012": _f(aj["contraste"]),
            "crs:Highlights2012": _f(aj["altas_luces"]),
            "crs:Shadows2012": _f(aj["sombras"]),
            "crs:Whites2012": _f(aj["blancos"]),
            "crs:Blacks2012": _f(aj["negros"]),
            "crs:Clarity2012": _f(aj["claridad"]),
            "crs:Vibrance": _f(aj["intensidad"]),
            "crs:Saturation": _f(aj["saturacion"]),
            "crs:Sharpness": _f(aj["enfoque"], signo=False),
            "crs:LuminanceSmoothing": _f(aj["reduccion_ruido"], signo=False),
            "crs:ColorNoiseReduction": _f(max(25, aj["reduccion_ruido"]), signo=False),
            # valores originales del revelador (por si los quieres consultar)
            "rev:Temperatura": _f(aj["temperatura"], 1),
            "rev:Matiz": _f(aj["matiz"], 1),
            "rev:ExposicionLineal": _f(aj["exposicion"], 2),
        })
        if aj.get("vineteo", 0) != 0:
            attrs["crs:PostCropVignetteAmount"] = _f(aj["vineteo"])
            attrs["rev:Vineteo"] = _f(aj["vineteo"])
        if toma.raw:
            # en RAW Lightroom usa Kelvin absolutos: dejamos "Como se tomó"
            attrs["crs:WhiteBalance"] = "As Shot"
        else:
            attrs["crs:WhiteBalance"] = "Custom"
            attrs["crs:Temperature"] = _f(aj["temperatura"])
            attrs["crs:Tint"] = _f(aj["matiz"])
    cuerpo = "\n   ".join(f"{k}={quoteattr(str(v))}" for k, v in attrs.items() if v != "")

    dc_bloque = ""
    todas_tags = []
    if categoria:
        todas_tags.append(categoria)
    if tags:
        for tg in tags:
            t_limpio = str(tg).strip()
            if t_limpio and t_limpio not in todas_tags:
                todas_tags.append(t_limpio)
    if todas_tags:
        lis = "\n     ".join(f"<rdf:li>{quoteattr(tg)[1:-1]}</rdf:li>" for tg in todas_tags)
        dc_bloque = f"""
   <dc:subject>
    <rdf:Bag>
     {lis}
    </rdf:Bag>
   </dc:subject>
   <lr:hierarchicalSubject>
    <rdf:Bag>
     {lis}
    </rdf:Bag>
   </lr:hierarchicalSubject>"""

    cierre_desc = f">{dc_bloque}\n  </rdf:Description>" if dc_bloque else "/>"

    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="CullFlow">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:xmp="http://ns.adobe.com/xap/1.0/"
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   xmlns:rev="https://github.com/djbel63/CullFlow/ns/1.0/"
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
   {cuerpo}{cierre_desc}
 </rdf:RDF>
</x:xmpmeta>
"""


def guardar(toma, texto, carpeta_xmp, junto_al_original=False):
    rutas = []
    os.makedirs(carpeta_xmp, exist_ok=True)
    base = os.path.splitext(os.path.basename(toma.principal))[0]
    sub = os.path.dirname(toma.clave)
    destino = os.path.join(carpeta_xmp, sub) if sub else carpeta_xmp
    os.makedirs(destino, exist_ok=True)
    r = os.path.join(destino, base + ".xmp")
    with open(r, "w", encoding="utf-8") as fh:
        fh.write(texto)
    rutas.append(r)
    if junto_al_original:
        r2 = os.path.splitext(toma.principal)[0] + ".xmp"
        if not os.path.exists(r2):  # nunca sobrescribe un XMP tuyo
            with open(r2, "w", encoding="utf-8") as fh:
                fh.write(texto)
            rutas.append(r2)
    return rutas
