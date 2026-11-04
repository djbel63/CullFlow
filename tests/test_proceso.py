import os
import shutil
import tempfile
import unittest
import numpy as np
import cv2

from revelador.config import Config
from revelador.proceso import Proyecto


class TestProceso(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.entrada = os.path.join(self.temp_dir, "entrada")
        self.salida = os.path.join(self.temp_dir, "salida")
        os.makedirs(self.entrada, exist_ok=True)
        os.makedirs(self.salida, exist_ok=True)

        # Crear 3 imágenes de prueba JPEG sintéticas
        for i in range(3):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            img[:] = (i * 50, 100, 200)
            cv2.imwrite(os.path.join(self.entrada, f"DSC_{i:04d}.JPG"), img)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_sin_ia(self):
        cfg = Config()
        cfg.ia_activado = False
        p = Proyecto(self.entrada, self.salida, cfg)
        st = p.ejecutar(revelar=True)
        self.assertGreater(len(st["grupos"]), 0)
        self.assertTrue(os.path.exists(os.path.join(self.salida, "informe.csv")))

    def test_pipeline_con_ia_simulada(self):
        cfg = Config()
        cfg.ia_activado = True
        cfg.ia_concurrencia = 2
        p = Proyecto(self.entrada, self.salida, cfg)

        # Mockear IA para simular servidor activo
        p.ia.comprobar = lambda: {"disponible": True, "vision": False, "detalle": "OK mock"}
        p.ia.ajustes = lambda prev, est, auto, vision, nombre="": {
            "ajustes": dict(auto, exposicion=0.2),
            "nota": "Ajuste simulado"
        }

        st = p.ejecutar(revelar=True)
        self.assertGreater(len(st["grupos"]), 0)
        self.assertTrue(os.path.exists(os.path.join(self.salida, "informe.csv")))
        for g in st["grupos"]:
            k = g["elegida"]
            self.assertEqual(st["ajustes"][k]["origen"], "ia")


if __name__ == "__main__":
    unittest.main()

