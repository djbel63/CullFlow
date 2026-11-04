#!/usr/bin/env python3
"""CullFlow — The Private, AI-Powered RAW Culling & Development Studio.

Uso:
  py revelar.py procesar  "C:\\Fotos\\SD"  [-o "C:\\Fotos\\Revelado"] [--sin-ia] [--todas] [--tiff] [--forzar]
  py revelar.py vigilar   "C:\\Fotos\\SD"  [-o ...]
  py revelar.py web       [--puerto 8765] [--no-abrir]
  py revelar.py probar-ia
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

from revelador import config as cfgmod  # noqa: E402


def _cfg(args):
    c = cfgmod.cargar(args.config)
    if getattr(args, "sin_ia", False):
        c.ia_activado = False
    if getattr(args, "todas", False):
        c.revelar = "todas"
    if getattr(args, "tiff", False):
        c.guardar_tiff16 = True
    if getattr(args, "trabajadores", None) is not None:
        c.trabajadores = args.trabajadores
    if getattr(args, "ia_concurrencia", None) is not None:
        c.ia_concurrencia = max(1, args.ia_concurrencia)
    return c


def _carpetas(args, c):
    entrada = args.entrada or c.entrada
    if not entrada:
        sys.exit("Indica la carpeta de entrada (o rellénala en config.ini, sección [carpetas]).")
    entrada = os.path.abspath(entrada.strip('"'))
    if not os.path.isdir(entrada):
        sys.exit(f"No existe la carpeta: {entrada}")
    salida = os.path.abspath(args.salida) if args.salida else c.carpeta_salida(entrada)
    return entrada, salida


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="cullflow",
        description="CullFlow: Selección inteligente y revelado RAW universal (Sony, Canon, Nikon, Fuji, Leica, DNG)"
    )
    p.add_argument("--config", help="ruta a config.ini (por defecto, la del programa)")
    sub = p.add_subparsers(dest="orden", required=True)

    a = sub.add_parser("procesar", help="procesa una carpeta una vez")
    a.add_argument("entrada", nargs="?")
    a.add_argument("-o", "--salida")
    a.add_argument("--sin-ia", action="store_true", help="no usar el modelo local")
    a.add_argument("--todas", action="store_true", help="revelar todas, no solo la mejor de cada grupo")
    a.add_argument("--tiff", action="store_true", help="guardar también TIFF de 16 bits")
    a.add_argument("--forzar", action="store_true", help="volver a revelar aunque ya exista")
    a.add_argument("-j", "--trabajadores", type=int, help="número de fotos en paralelo (0 = auto)")
    a.add_argument("--ia-concurrencia", type=int, help="número de peticiones simultáneas a la IA (por defecto 2)")

    v = sub.add_parser("vigilar", help="vigila una carpeta y procesa lo nuevo automáticamente")
    v.add_argument("entrada", nargs="?")
    v.add_argument("-o", "--salida")
    v.add_argument("--sin-ia", action="store_true")
    v.add_argument("--todas", action="store_true")
    v.add_argument("--tiff", action="store_true")

    w = sub.add_parser("web", help="abre la interfaz web local")
    w.add_argument("--puerto", type=int, default=8765)
    w.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")

    sub.add_parser("probar-ia", help="comprueba la conexión con el modelo local")

    args = p.parse_args(argv)
    c = _cfg(args)

    if args.orden == "procesar":
        from revelador.proceso import Proyecto
        entrada, salida = _carpetas(args, c)
        Proyecto(entrada, salida, c, registro=print).ejecutar(forzar=args.forzar)
    elif args.orden == "vigilar":
        from revelador.vigilar import vigilar
        entrada, salida = _carpetas(args, c)
        vigilar(entrada, salida, c)
    elif args.orden == "web":
        from revelador.web import arrancar
        arrancar(c, args.puerto, abrir=not args.no_abrir)
    elif args.orden == "probar-ia":
        from revelador.ia import ClienteIA
        print(f"Servidor: {c.ia_api_base}\nModelo:   {c.ia_modelo}")
        r = ClienteIA(c).comprobar()
        print(f"Disponible: {'sí' if r['disponible'] else 'no'}")
        print(f"Ve imágenes: {'sí' if r['vision'] else 'no'}")
        if r.get("detalle"):
            print("Detalle:", r["detalle"].strip())


if __name__ == "__main__":
    main()
