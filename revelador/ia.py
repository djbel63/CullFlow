"""Conexión opcional con un modelo local compatible con la API de OpenAI.

Nada de aquí puede romper el proceso: ante cualquier error se devuelve None
y el programa sigue con el modo automático.
"""
import base64
import json
import re
import time
import urllib.error
import urllib.request

import cv2
import numpy as np

from .revelado import RANGOS, limitar

_ESTADO = {}  # caché por (api_base, modelo)

SISTEMA = ("Eres una reveladora fotográfica experta (estilo Lightroom). Respondes SOLO con "
           "un objeto JSON válido, sin texto adicional ni explicaciones.")


class ClienteIA:
    def __init__(self, cfg, registro=print):
        self.cfg = cfg
        self.log = registro
        self.base = (cfg.ia_api_base or "").rstrip("/")
        self.modelo = cfg.ia_modelo
        self.activo = bool(cfg.ia_activado and self.base and self.modelo)
        self._sin_kwargs = False

    # ------------------------------------------------------------ HTTP
    def _post(self, ruta, cuerpo, timeout=None):
        datos = json.dumps(cuerpo).encode("utf-8")
        req = urllib.request.Request(self.base + ruta, data=datos, method="POST",
                                     headers={"Content-Type": "application/json"})
        if self.cfg.ia_api_key:
            req.add_header("Authorization", "Bearer " + self.cfg.ia_api_key)
        with urllib.request.urlopen(req, timeout=timeout or self.cfg.ia_timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _get(self, ruta, timeout=8):
        req = urllib.request.Request(self.base + ruta)
        if self.cfg.ia_api_key:
            req.add_header("Authorization", "Bearer " + self.cfg.ia_api_key)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def chat(self, contenido, max_tokens=600, timeout=None):
        cuerpo = {"model": self.modelo, "temperature": 0.2, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": SISTEMA},
                               {"role": "user", "content": contenido}]}
        if self.cfg.ia_sin_razonamiento and not self._sin_kwargs:
            cuerpo["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            r = self._post("/chat/completions", cuerpo, timeout)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "chat_template_kwargs" in cuerpo:
                cuerpo.pop("chat_template_kwargs")
                r = self._post("/chat/completions", cuerpo, timeout)
                self._sin_kwargs = True  # el servidor no admite ese campo: no volver a enviarlo
            else:
                raise
        msg = r["choices"][0]["message"]
        return msg.get("content") or ""

    # ------------------------------------------------------------ capacidades
    def comprobar(self):
        """Devuelve {'disponible': bool, 'vision': bool, 'detalle': str}."""
        clave = (self.base, self.modelo)
        previo = _ESTADO.get(clave)
        # Si funcionó se recuerda 1 hora; si falló, se reintenta a los 5 minutos.
        if previo and time.time() - previo["_t"] < (3600 if previo["disponible"] else 300):
            return previo
        res = {"disponible": False, "vision": False, "detalle": "", "_t": time.time()}
        if not self.activo:
            res["detalle"] = "IA desactivada en config.ini"
            return res
        try:
            modelos = [m.get("id") for m in self._get("/models").get("data", [])]
            if modelos and self.modelo not in modelos:
                res["detalle"] = f"El servidor no anuncia '{self.modelo}' (tiene: {', '.join(modelos[:5])}). Se intenta igualmente."
        except Exception as e:  # noqa: BLE001
            res["detalle"] = f"No se puede conectar con {self.base}: {e}"
            _ESTADO[clave] = res
            return res
        try:
            txt = self.chat('Responde exactamente {"ok": true}', max_tokens=20, timeout=min(60, self.cfg.ia_timeout))
            res["disponible"] = "ok" in txt.lower()
            if not res["disponible"]:
                res["detalle"] += f" Respuesta inesperada: {txt[:80]!r}"
        except Exception as e:  # noqa: BLE001
            res["detalle"] += f" Error al hablar con el modelo: {e}"
        modo = self.cfg.ia_usar_imagen
        if res["disponible"] and modo in ("auto", "si", "sí", "true", "1"):
            if modo == "auto":
                res["vision"] = self._prueba_vision()
            else:
                res["vision"] = True
        _ESTADO[clave] = res
        return res

    def _prueba_vision(self):
        img = np.zeros((64, 64, 3), np.uint8)
        img[:] = (0, 0, 255)  # rojo en BGR
        try:
            txt = self.chat([
                {"type": "image_url", "image_url": {"url": _data_url(img)}},
                {"type": "text", "text": 'What is the dominant colour of this image? Answer as JSON {"colour": "..."}'},
            ], max_tokens=30, timeout=min(60, self.cfg.ia_timeout))
            return any(p in txt.lower() for p in ("red", "rojo"))
        except Exception:
            return False

    # ------------------------------------------------------------ tareas
    def ajustes(self, preview_bgr, estadisticas, auto, vision, nombre=""):
        """Pide al modelo ajustes JSON. Devuelve dict limitado o None."""
        rangos = {k: [lo, hi] for k, (lo, hi) in RANGOS.items()}
        texto = (
            "Ajusta el revelado fotográfico de esta toma con estilo profesional (Lightroom / Nikon Picture Control).\n"
            "Criterios esenciales:\n"
            "- En fotos nocturnas o fondos oscuros, conserva negros profundos y contraste; no levantes sombras en exceso para evitar ruido.\n"
            "- Deja que las luces puntuales (árboles iluminados, farolas, velas) brillen con calidez sin aplastarlas a gris.\n"
            "- Respeta los tonos de piel naturales y el color de la atmósfera original.\n"
            f"Rangos permitidos: {json.dumps(rangos)}\n"
            "Los valores son finales (la exposición en EV sobre el RAW lineal). Si la propuesta automática te parece adecuada, devuelve los mismos valores.\n"
            f"Estadísticas: {json.dumps(estadisticas)}\n"
            f"Propuesta automática: {json.dumps(auto)}\n"
            "Devuelve SOLO un JSON con las mismas claves que la propuesta automática y valores finales, "
            "más las siguientes claves adicionales:\n"
            "- 'nota': frase corta descriptiva en español.\n"
            "- 'categoria': clasifica la toma en una de ['retrato', 'paisaje', 'noche', 'evento', 'arquitectura', 'macro', 'fauna'].\n"
            "- 'tags': lista de 3 a 5 etiquetas en español descriptivas del contenido (ej: ['navidad', 'luces', 'noche'])."
        )
        contenido = texto
        if vision and preview_bgr is not None:
            contenido = [{"type": "image_url", "image_url": {"url": _data_url(preview_bgr, self.cfg.ia_lado_preview)}},
                         {"type": "text", "text": "La imagen es la vista previa con la propuesta automática ya aplicada.\n" + texto}]
        try:
            t0 = time.time()
            txt = self.chat(contenido, max_tokens=700)
            datos = extraer_json(txt)
            if not isinstance(datos, dict):
                self.log("   IA: respuesta sin JSON válido, uso el modo automático")
                return None
            nota = str(datos.get("nota", ""))[:200]
            cat = str(datos.get("categoria", "")).lower().strip()
            raw_tags = datos.get("tags", [])
            tags = [str(t).lower().strip() for t in raw_tags if isinstance(t, str) and len(str(t).strip()) > 1][:6]
            final = dict(auto)
            for k in RANGOS:
                if k in datos:
                    try:
                        final[k] = float(datos[k])
                    except (TypeError, ValueError):
                        pass
            # prudencia: la exposición no se aleja más de 1,5 EV de la automática
            final["exposicion"] = float(np.clip(final["exposicion"], auto["exposicion"] - 1.5, auto["exposicion"] + 1.5))
            final = limitar(final)
            sufijo = f" para {nombre}" if nombre else ""
            cat_info = f" [{cat}]" if cat else ""
            self.log(f"   IA: ajustes recibidos en {time.time() - t0:.1f}s{sufijo}{cat_info}. {nota}")
            return {"ajustes": final, "nota": nota, "categoria": cat, "tags": tags}
        except Exception as e:  # noqa: BLE001
            sufijo = f" ({nombre})" if nombre else ""
            self.log(f"   IA: error{sufijo} ({e}); uso el modo automático")
            return None

    def elegir(self, previews_bgr, puntuaciones):
        """Pide al modelo cuál es la mejor foto del grupo. Devuelve índice o None."""
        try:
            contenido = []
            for i, p in enumerate(previews_bgr[:6]):
                contenido.append({"type": "text", "text": f"Foto {i}:"})
                contenido.append({"type": "image_url", "image_url": {"url": _data_url(p, 512)}})
            contenido.append({"type": "text", "text": (
                "Son fotos casi iguales de una misma ráfaga. Elige la mejor (enfoque del sujeto, "
                "ojos abiertos, expresión, movimiento, encuadre). Puntuación técnica automática "
                f"(más alto = mejor): {json.dumps(puntuaciones[:6])}. "
                'Responde SOLO {"mejor": <número de foto>, "motivo": "<frase corta>"}')})
            txt = self.chat(contenido, max_tokens=120)
            d = extraer_json(txt)
            i = int(d.get("mejor"))
            if 0 <= i < min(6, len(previews_bgr)):
                self.log(f"   IA elige la foto {i}: {str(d.get('motivo', ''))[:120]}")
                return i
        except Exception as e:  # noqa: BLE001
            self.log(f"   IA: no pudo elegir ({e}); uso la puntuación automática")
        return None


def _data_url(bgr, lado=768):
    h, w = bgr.shape[:2]
    s = lado / max(h, w)
    if s < 1:
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def extraer_json(txt):
    """Saca el primer objeto JSON de una respuesta (ignora <think> y ```json)."""
    if not txt:
        return None
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    txt = txt.replace("```json", "```")
    ini = txt.find("{")
    while ini != -1:
        prof = 0
        for i in range(ini, len(txt)):
            if txt[i] == "{":
                prof += 1
            elif txt[i] == "}":
                prof -= 1
                if prof == 0:
                    try:
                        return json.loads(txt[ini:i + 1])
                    except json.JSONDecodeError:
                        break
        ini = txt.find("{", ini + 1)
    return None
