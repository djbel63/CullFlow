"""Modo vigilar: procesa automáticamente las fotos nuevas que aparecen en la carpeta."""
import os
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .archivos import EXT_JPG, EXT_RAW
from .proceso import Proyecto

EXT = EXT_RAW | EXT_JPG


class _Manejador(FileSystemEventHandler):
    def __init__(self, salida):
        self.ultimo = 0.0
        self.pendiente = False
        self.salida = os.path.normcase(os.path.abspath(salida))

    def _ev(self, ruta):
        if os.path.normcase(os.path.abspath(ruta)).startswith(self.salida):
            return
        if os.path.splitext(ruta)[1].lower() in EXT:
            self.ultimo = time.time()
            self.pendiente = True

    def on_created(self, e):
        if not e.is_directory:
            self._ev(e.src_path)

    def on_modified(self, e):
        if not e.is_directory:
            self._ev(e.src_path)

    def on_moved(self, e):
        if not e.is_directory:
            self._ev(e.dest_path)


def _tamanos_estables(carpeta, salida, espera=2.0):
    def foto(raiz, a):
        return os.path.splitext(a)[1].lower() in EXT and not os.path.abspath(raiz).startswith(os.path.abspath(salida))

    def medir():
        r = {}
        for raiz, _, archivos in os.walk(carpeta):
            for a in archivos:
                if foto(raiz, a):
                    try:
                        r[os.path.join(raiz, a)] = os.path.getsize(os.path.join(raiz, a))
                    except OSError:
                        pass
        return r
    a = medir()
    time.sleep(espera)
    return a == medir()


def vigilar(entrada, salida, cfg, parar: threading.Event = None, registro=print):
    os.makedirs(entrada, exist_ok=True)
    proyecto = Proyecto(entrada, salida, cfg, registro=registro)
    registro(f"Vigilando {entrada} (resultado en {salida}). Pulsa Ctrl+C para salir.")
    proyecto.ejecutar()  # procesa lo que ya hubiera
    man = _Manejador(salida)
    obs = Observer()
    obs.schedule(man, entrada, recursive=True)
    obs.start()
    parar = parar or threading.Event()
    try:
        while not parar.is_set():
            time.sleep(1)
            if man.pendiente and time.time() - man.ultimo >= cfg.espera_segundos:
                if not _tamanos_estables(entrada, salida):
                    man.ultimo = time.time()
                    continue
                man.pendiente = False
                registro("Fotos nuevas detectadas, procesando…")
                try:
                    proyecto.ejecutar()
                except Exception as e:  # noqa: BLE001
                    registro(f"⚠ Error durante el proceso: {e}")
    except KeyboardInterrupt:
        registro("Saliendo del modo vigilar.")
    finally:
        obs.stop()
        obs.join(5)
    return proyecto
