import unittest
import numpy as np
import cv2

from revelador.analisis import calidad, _detector_yunet


class TestAnalisis(unittest.TestCase):

    def test_detector_yunet_carga(self):
        """Verifica que el modelo YuNet ONNX de OpenCV Zoo se inicializa correctamente."""
        yn = _detector_yunet()
        self.assertIsNotNone(yn)
        self.assertNotEqual(yn, False)

    def test_calidad_metadatos_basicos(self):
        """Verifica que calidad() devuelve las claves esperadas sin error."""
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        # Dibujar un círculo para nitidez mínima
        cv2.circle(img, (320, 240), 50, (255, 255, 255), -1)

        res = calidad(img, detectar_caras=True)
        self.assertIn("nitidez", res)
        self.assertIn("ruido", res)
        self.assertIn("quemadas", res)
        self.assertIn("empastadas", res)
        self.assertIn("caras", res)
        self.assertIsInstance(res["caras"], list)


if __name__ == "__main__":
    unittest.main()

