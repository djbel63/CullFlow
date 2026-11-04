import os
import tempfile
import unittest
import numpy as np

from revelador.revelado import (
    aplicar,
    auto_ajustes,
    neutros,
    guardar_jpeg,
    guardar_webp,
    guardar_tiff16,
)


class TestRevelado(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_aplicar_sin_nans_ni_infs(self):
        grad = np.linspace(0.0, 1.0, 100 * 100, dtype=np.float32).reshape(100, 100, 1)
        img = np.repeat(grad, 3, axis=2)
        aj = neutros()
        aj["exposicion"] = 0.5
        aj["contraste"] = 15.0
        aj["claridad"] = 10.0
        aj["sombras"] = 20.0
        aj["altas_luces"] = -20.0

        res = aplicar(img, aj, escala=0.5)
        self.assertFalse(np.isnan(res).any())
        self.assertFalse(np.isinf(res).any())
        self.assertTrue(np.all(res >= 0.0))
        self.assertTrue(np.all(res <= 1.0))

    def test_recorte_alertas_coloreo(self):
        """Comprueba que recorte_alertas colorea píxeles quemados de rojo y empastados de azul."""
        img = np.zeros((10, 10, 3), dtype=np.float32)
        img[0, 0] = [1.0, 1.0, 1.0]  # Quemado
        img[9, 9] = [0.0, 0.0, 0.0]  # Empastado

        res = aplicar(img, neutros(), escala=0.0, recorte_alertas=True)
        # Quemado debe tener R=1.0, G=0.0, B=0.0
        np.testing.assert_allclose(res[0, 0], [1.0, 0.0, 0.0], atol=1e-2)
        # Empastado debe tener R=0.0, B=1.0
        self.assertAlmostEqual(float(res[9, 9, 0]), 0.0, places=2)
        self.assertAlmostEqual(float(res[9, 9, 2]), 1.0, places=2)

    def test_vineteo(self):
        """Comprueba que el viñeteo negativo oscurece las esquinas y el positivo las aclara."""
        img = np.full((100, 100, 3), 0.5, dtype=np.float32)
        aj_osc = neutros()
        aj_osc["vineteo"] = -50.0  # Oscurecer esquinas
        res_osc = aplicar(img, aj_osc, escala=0.0)
        # El centro debe estar cerca de 0.5 y las esquinas más oscuras
        self.assertGreater(float(res_osc[50, 50, 0]), float(res_osc[0, 0, 0]))

        aj_acl = neutros()
        aj_acl["vineteo"] = 50.0   # Aclarar esquinas
        res_acl = aplicar(img, aj_acl, escala=0.0)
        # Las esquinas deben ser más brillantes que el centro
        self.assertGreater(float(res_acl[0, 0, 0]), float(res_acl[50, 50, 0]))

    def test_guardar_formatos(self):
        img = np.full((50, 50, 3), 0.5, dtype=np.float32)

        # JPEG
        p_jpg = os.path.join(self.tmpdir, "test.jpg")
        guardar_jpeg(img, p_jpg, calidad=90)
        self.assertTrue(os.path.exists(p_jpg))
        self.assertGreater(os.path.getsize(p_jpg), 100)

        # WebP
        p_webp = os.path.join(self.tmpdir, "test.webp")
        guardar_webp(img, p_webp, calidad=85)
        self.assertTrue(os.path.exists(p_webp))
        self.assertGreater(os.path.getsize(p_webp), 100)

        # TIFF 16-bit
        p_tif = os.path.join(self.tmpdir, "test.tif")
        guardar_tiff16(img, p_tif)
        self.assertTrue(os.path.exists(p_tif))
        self.assertGreater(os.path.getsize(p_tif), 100)


if __name__ == "__main__":
    unittest.main()

