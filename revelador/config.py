"""Lectura de config.ini con valores por defecto seguros."""
import configparser
import os
from dataclasses import dataclass, field

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_POR_DEFECTO = os.path.join(RAIZ, "config.ini")

_SI = {"si", "sí", "s", "true", "1", "yes", "y", "on"}


def _bool(v, defecto=False):
    if v is None or str(v).strip() == "":
        return defecto
    return str(v).strip().lower() in _SI


@dataclass
class Config:
    entrada: str = ""
    salida: str = ""
    segundos_max: float = 30.0
    umbral_similitud: float = 0.80
    peso_nitidez: float = 0.55
    peso_exposicion: float = 0.20
    peso_ruido: float = 0.10
    peso_ojos: float = 0.15
    detectar_caras: bool = True
    revelar: str = "mejores"
    formato_salida: str = "jpeg"
    calidad_jpeg: int = 95
    calidad_webp: int = 90
    guardar_tiff16: bool = False
    intensidad_auto: float = 100.0
    max_lado: int = 0
    xmp_junto_al_original: bool = False
    demosaic: str = "aahd"
    corregir_aberraciones: bool = True
    incrustar_icc: bool = True
    preferir_jpg_camara: bool = False
    trabajadores: int = 0
    trabajadores_analisis: int = 0
    espera_segundos: float = 10.0
    ia_activado: bool = True
    ia_api_base: str = "http://127.0.0.1:11434/v1"
    ia_modelo: str = "qwen2.5-vl:7b"
    ia_api_key: str = ""
    ia_usar_imagen: str = "auto"
    ia_elegir_mejor: bool = True
    ia_margen_eleccion: float = 0.15
    ia_lado_preview: int = 768
    ia_timeout: float = 90.0
    ia_sin_razonamiento: bool = True
    ia_concurrencia: int = 2
    ruta: str = field(default=CONFIG_POR_DEFECTO)

    def carpeta_salida(self, entrada=None):
        entrada = entrada or self.entrada
        if self.salida:
            return self.salida
        return os.path.join(entrada, "Revelado")

    def trabajadores_revelado_efectivos(self) -> int:
        if self.trabajadores > 0:
            return self.trabajadores
        cpus = os.cpu_count() or 4
        # Seguro contra saturación de RAM: min 1, máx 4
        return max(1, min(4, cpus // 2))

    def trabajadores_analisis_efectivos(self) -> int:
        if self.trabajadores_analisis > 0:
            return self.trabajadores_analisis
        cpus = os.cpu_count() or 4
        return max(1, min(8, cpus))


def cargar(ruta=None) -> Config:
    ruta = ruta or CONFIG_POR_DEFECTO
    c = Config(ruta=ruta)
    if not os.path.exists(ruta):
        return c
    p = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    p.read(ruta, encoding="utf-8-sig")

    def g(sec, key, defecto=""):
        try:
            return p.get(sec, key).strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return defecto

    def num(sec, key, defecto, tipo=float):
        v = g(sec, key, "")
        try:
            return tipo(v.replace(",", ".")) if v else defecto
        except ValueError:
            return defecto

    c.entrada = g("carpetas", "entrada")
    c.salida = g("carpetas", "salida")
    c.segundos_max = num("agrupacion", "segundos_max_entre_fotos", c.segundos_max)
    c.umbral_similitud = num("agrupacion", "umbral_similitud", c.umbral_similitud)
    c.peso_nitidez = num("seleccion", "peso_nitidez", c.peso_nitidez)
    c.peso_exposicion = num("seleccion", "peso_exposicion", c.peso_exposicion)
    c.peso_ruido = num("seleccion", "peso_ruido", c.peso_ruido)
    c.peso_ojos = num("seleccion", "peso_ojos", c.peso_ojos)
    c.detectar_caras = _bool(g("seleccion", "detectar_caras"), True)
    c.revelar = (g("revelado", "revelar") or "mejores").lower()
    c.formato_salida = (g("revelado", "formato_salida") or "jpeg").lower()
    c.calidad_jpeg = int(num("revelado", "calidad_jpeg", 95))
    c.calidad_webp = int(num("revelado", "calidad_webp", 90))
    c.guardar_tiff16 = _bool(g("revelado", "guardar_tiff16"), False)
    c.intensidad_auto = num("revelado", "intensidad_auto", 100.0)
    c.max_lado = int(num("revelado", "max_lado", 0))
    c.xmp_junto_al_original = _bool(g("revelado", "xmp_junto_al_original"), False)
    c.demosaic = (g("revelado", "demosaic") or "aahd").lower()
    c.corregir_aberraciones = _bool(g("revelado", "corregir_aberraciones"), True)
    c.incrustar_icc = _bool(g("revelado", "incrustar_icc"), True)
    c.preferir_jpg_camara = _bool(g("revelado", "preferir_jpg_camara"), False)
    c.trabajadores = int(num("rendimiento", "trabajadores", 0))
    c.trabajadores_analisis = int(num("rendimiento", "trabajadores_analisis", 0))
    c.espera_segundos = num("vigilar", "espera_segundos", 10.0)
    c.ia_activado = _bool(g("ia", "activado"), True)
    c.ia_api_base = g("ia", "api_base", c.ia_api_base) or ""
    c.ia_modelo = g("ia", "modelo", c.ia_modelo) or ""
    c.ia_api_key = g("ia", "api_key")
    c.ia_usar_imagen = (g("ia", "usar_imagen") or "auto").lower()
    c.ia_elegir_mejor = _bool(g("ia", "elegir_mejor"), True)
    c.ia_margen_eleccion = num("ia", "margen_eleccion", 0.15)
    c.ia_lado_preview = int(num("ia", "lado_preview", 768))
    c.ia_timeout = num("ia", "timeout_segundos", 90.0)
    c.ia_sin_razonamiento = _bool(g("ia", "desactivar_razonamiento"), True)
    c.ia_concurrencia = max(1, int(num("ia", "concurrencia", 2)))
    return c


def to_dict(c: Config) -> dict:
    """Convierte la configuración a diccionario estructurado para la API web."""
    return {
        "carpetas": {
            "entrada": c.entrada,
            "salida": c.salida,
        },
        "agrupacion": {
            "segundos_max_entre_fotos": c.segundos_max,
            "umbral_similitud": c.umbral_similitud,
        },
        "seleccion": {
            "peso_nitidez": c.peso_nitidez,
            "peso_exposicion": c.peso_exposicion,
            "peso_ruido": c.peso_ruido,
            "peso_ojos": c.peso_ojos,
            "detectar_caras": c.detectar_caras,
        },
        "revelado": {
            "revelar": c.revelar,
            "formato_salida": c.formato_salida,
            "calidad_jpeg": c.calidad_jpeg,
            "calidad_webp": c.calidad_webp,
            "guardar_tiff16": c.guardar_tiff16,
            "intensidad_auto": c.intensidad_auto,
            "max_lado": c.max_lado,
            "xmp_junto_al_original": c.xmp_junto_al_original,
            "demosaic": c.demosaic,
            "corregir_aberraciones": c.corregir_aberraciones,
            "incrustar_icc": c.incrustar_icc,
            "preferir_jpg_camara": c.preferir_jpg_camara,
        },
        "rendimiento": {
            "trabajadores": c.trabajadores,
            "trabajadores_analisis": c.trabajadores_analisis,
            "trabajadores_revelado_efectivos": c.trabajadores_revelado_efectivos(),
            "trabajadores_analisis_efectivos": c.trabajadores_analisis_efectivos(),
        },
        "ia": {
            "activado": c.ia_activado,
            "api_base": c.ia_api_base,
            "modelo": c.ia_modelo,
            "api_key": c.ia_api_key,
            "usar_imagen": c.ia_usar_imagen,
            "elegir_mejor": c.ia_elegir_mejor,
            "margen_eleccion": c.ia_margen_eleccion,
            "lado_preview": c.ia_lado_preview,
            "timeout_segundos": c.ia_timeout,
            "desactivar_razonamiento": c.ia_sin_razonamiento,
            "concurrencia": c.ia_concurrencia,
        },
    }


def actualizar_desde_dict(c: Config, d: dict) -> None:
    """Actualiza la instancia Config a partir de un dict (claves anidadas o planas)."""
    def get_val(sec, key, defecto):
        if sec in d and isinstance(d[sec], dict) and key in d[sec]:
            return d[sec][key]
        if key in d:
            return d[key]
        return defecto

    if "carpetas" in d or "entrada" in d:
        c.entrada = str(get_val("carpetas", "entrada", c.entrada) or "")
        c.salida = str(get_val("carpetas", "salida", c.salida) or "")
    if "agrupacion" in d or "segundos_max_entre_fotos" in d or "umbral_similitud" in d:
        c.segundos_max = float(get_val("agrupacion", "segundos_max_entre_fotos", c.segundos_max))
        c.umbral_similitud = float(get_val("agrupacion", "umbral_similitud", c.umbral_similitud))
    if "seleccion" in d or "peso_nitidez" in d or "detectar_caras" in d:
        c.peso_nitidez = float(get_val("seleccion", "peso_nitidez", c.peso_nitidez))
        c.peso_exposicion = float(get_val("seleccion", "peso_exposicion", c.peso_exposicion))
        c.peso_ruido = float(get_val("seleccion", "peso_ruido", c.peso_ruido))
        c.peso_ojos = float(get_val("seleccion", "peso_ojos", c.peso_ojos))
        c.detectar_caras = _bool(get_val("seleccion", "detectar_caras", c.detectar_caras))
    if "revelado" in d or "calidad_jpeg" in d or "formato_salida" in d:
        c.revelar = str(get_val("revelado", "revelar", c.revelar)).lower()
        c.formato_salida = str(get_val("revelado", "formato_salida", c.formato_salida)).lower()
        c.calidad_jpeg = int(get_val("revelado", "calidad_jpeg", c.calidad_jpeg))
        c.calidad_webp = int(get_val("revelado", "calidad_webp", c.calidad_webp))
        c.guardar_tiff16 = _bool(get_val("revelado", "guardar_tiff16", c.guardar_tiff16))
        c.intensidad_auto = float(get_val("revelado", "intensidad_auto", c.intensidad_auto))
        c.max_lado = int(get_val("revelado", "max_lado", c.max_lado))
        c.xmp_junto_al_original = _bool(get_val("revelado", "xmp_junto_al_original", c.xmp_junto_al_original))
        c.demosaic = str(get_val("revelado", "demosaic", c.demosaic)).lower()
        c.corregir_aberraciones = _bool(get_val("revelado", "corregir_aberraciones", c.corregir_aberraciones))
        c.incrustar_icc = _bool(get_val("revelado", "incrustar_icc", c.incrustar_icc))
        c.preferir_jpg_camara = _bool(get_val("revelado", "preferir_jpg_camara", c.preferir_jpg_camara))
    if "rendimiento" in d or "trabajadores" in d:
        c.trabajadores = int(get_val("rendimiento", "trabajadores", c.trabajadores))
        c.trabajadores_analisis = int(get_val("rendimiento", "trabajadores_analisis", c.trabajadores_analisis))
    if "ia" in d or "ia_activado" in d or "api_base" in d:
        c.ia_activado = _bool(get_val("ia", "activado", c.ia_activado))
        c.ia_api_base = str(get_val("ia", "api_base", c.ia_api_base) or "")
        c.ia_modelo = str(get_val("ia", "modelo", c.ia_modelo) or "")
        c.ia_api_key = str(get_val("ia", "api_key", c.ia_api_key) or "")
        c.ia_usar_imagen = str(get_val("ia", "usar_imagen", c.ia_usar_imagen)).lower()
        c.ia_elegir_mejor = _bool(get_val("ia", "elegir_mejor", c.ia_elegir_mejor))
        c.ia_margen_eleccion = float(get_val("ia", "margen_eleccion", c.ia_margen_eleccion))
        c.ia_lado_preview = int(get_val("ia", "lado_preview", c.ia_lado_preview))
        c.ia_timeout = float(get_val("ia", "timeout_segundos", c.ia_timeout))
        c.ia_sin_razonamiento = _bool(get_val("ia", "desactivar_razonamiento", c.ia_sin_razonamiento))
        c.ia_concurrencia = max(1, int(get_val("ia", "concurrencia", c.ia_concurrencia)))


def guardar_en_ini(c: Config, ruta=None) -> None:
    """Guarda la configuración en config.ini preservando todos los comentarios existentes."""
    ruta = ruta or c.ruta or CONFIG_POR_DEFECTO
    lineas = []
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8-sig") as fh:
            lineas = fh.readlines()

    valores = {
        "carpetas": {
            "entrada": c.entrada,
            "salida": c.salida,
        },
        "agrupacion": {
            "segundos_max_entre_fotos": str(c.segundos_max),
            "umbral_similitud": str(c.umbral_similitud),
        },
        "seleccion": {
            "peso_nitidez": str(c.peso_nitidez),
            "peso_exposicion": str(c.peso_exposicion),
            "peso_ruido": str(c.peso_ruido),
            "peso_ojos": str(c.peso_ojos),
            "detectar_caras": "si" if c.detectar_caras else "no",
        },
        "revelado": {
            "revelar": c.revelar,
            "formato_salida": c.formato_salida,
            "calidad_jpeg": str(c.calidad_jpeg),
            "calidad_webp": str(c.calidad_webp),
            "guardar_tiff16": "si" if c.guardar_tiff16 else "no",
            "intensidad_auto": str(c.intensidad_auto),
            "max_lado": str(c.max_lado),
            "xmp_junto_al_original": "si" if c.xmp_junto_al_original else "no",
            "demosaic": c.demosaic,
            "corregir_aberraciones": "si" if c.corregir_aberraciones else "no",
            "incrustar_icc": "si" if c.incrustar_icc else "no",
            "preferir_jpg_camara": "si" if c.preferir_jpg_camara else "no",
        },
        "rendimiento": {
            "trabajadores": str(c.trabajadores),
            "trabajadores_analisis": str(c.trabajadores_analisis),
        },
        "vigilar": {
            "espera_segundos": str(c.espera_segundos),
        },
        "ia": {
            "activado": "si" if c.ia_activado else "no",
            "api_base": c.ia_api_base,
            "modelo": c.ia_modelo,
            "api_key": c.ia_api_key,
            "usar_imagen": c.ia_usar_imagen,
            "elegir_mejor": "si" if c.ia_elegir_mejor else "no",
            "margen_eleccion": str(c.ia_margen_eleccion),
            "lado_preview": str(c.ia_lado_preview),
            "timeout_segundos": str(c.ia_timeout),
            "desactivar_razonamiento": "si" if c.ia_sin_razonamiento else "no",
            "concurrencia": str(c.ia_concurrencia),
        },
    }

    seccion_actual = ""
    claves_vistas = {sec: set() for sec in valores}
    nuevas_lineas = []

    for linea in lineas:
        limpia = linea.strip()
        if limpia.startswith("[") and limpia.endswith("]"):
            if seccion_actual in valores:
                faltantes = set(valores[seccion_actual]) - claves_vistas[seccion_actual]
                for k in sorted(faltantes):
                    nuevas_lineas.append(f"{k} = {valores[seccion_actual][k]}\n")
            seccion_actual = limpia[1:-1].strip().lower()
            nuevas_lineas.append(linea)
            continue

        if seccion_actual in valores and "=" in linea and not limpia.startswith((";", "#")):
            partes = linea.split("=", 1)
            clave = partes[0].strip().lower()
            if clave in valores[seccion_actual]:
                val = valores[seccion_actual][clave]
                claves_vistas[seccion_actual].add(clave)
                comentario = ""
                resto = partes[1]
                for pref in (";", "#"):
                    if pref in resto:
                        idx = resto.index(pref)
                        comentario = "  " + resto[idx:].rstrip()
                        break
                nuevas_lineas.append(f"{partes[0].rstrip()} = {val}{comentario}\n")
                continue

        nuevas_lineas.append(linea)

    if seccion_actual in valores:
        faltantes = set(valores[seccion_actual]) - claves_vistas[seccion_actual]
        for k in sorted(faltantes):
            nuevas_lineas.append(f"{k} = {valores[seccion_actual][k]}\n")

    for sec, items in valores.items():
        if sec not in claves_vistas or not claves_vistas[sec]:
            nuevas_lineas.append(f"\n[{sec}]\n")
            for k, v in items.items():
                nuevas_lineas.append(f"{k} = {v}\n")

    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(nuevas_lineas)
    os.replace(tmp, ruta)
