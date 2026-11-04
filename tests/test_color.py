import unittest
import numpy as np

from revelador.revelado import (
    srgb_a_lineal,
    lineal_a_srgb,
    _lum,
    _curva_tonal,
    limitar,
    neutros,
    aplicar_balance,
)


class TestColor(unittest.TestCase):

    def test_srgb_lineal_reversibilidad(self):
        """Comprueba que la conversión sRGB -> Lineal -> sRGB es simétrica y reversible."""
        x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
        lin = srgb_a_lineal(x)
        rec = lineal_a_srgb(lin)
        np.testing.assert_allclose(x, rec, atol=1e-3)

    def test_luminancia_ponderada(self):
        """Verifica los pesos estándar BT.709 para la luminancia (0.2126 R + 0.7152 G + 0.0722 B)."""
        blanco = np.ones((1, 1, 3), dtype=np.float32)
        self.assertAlmostEqual(float(_lum(blanco)[0, 0]), 1.0, places=4)
        negro = np.zeros((1, 1, 3), dtype=np.float32)
        self.assertAlmostEqual(float(_lum(negro)[0, 0]), 0.0, places=4)
        verde = np.array([[[0.0, 1.0, 0.0]]], dtype=np.float32)
        self.assertAlmostEqual(float(_lum(verde)[0, 0]), 0.7152, places=4)

    def test_curva_tonal_anclaje_negros(self):
        """La curva tonal debe anclar siempre el negro puro en cero absoluto para no lavar la noche."""
        aj = neutros()
        x, y = _curva_tonal(aj)
        self.assertEqual(float(y[0]), 0.0)
        self.assertAlmostEqual(float(y[-1]), 1.0, places=2)
        # Debe mantenerse dentro del rango [0, 1]
        self.assertTrue(np.all(y >= 0.0))
        self.assertTrue(np.all(y <= 1.0))

    def test_limitar_ajustes(self):
        """Verifica que los ajustes queden acotados dentro de sus límites seguros."""
        aj_locos = {
            "exposicion": 99.0,
            "temperatura": -500.0,
            "sombras": 200.0,
            "negros": -999.0,
        }
        lim = limitar(aj_locos)
        self.assertLessEqual(lim["exposicion"], 4.0)
        self.assertGreaterEqual(lim["temperatura"], -100.0)
        self.assertLessEqual(lim["sombras"], 100.0)
        self.assertGreaterEqual(lim["negros"], -100.0)

    def test_balance_de_blancos_neutro(self):
        """Con temperatura=0 y matiz=0 la imagen debe permanecer inalterada."""
        img = np.full((10, 10, 3), 0.5, dtype=np.float32)
        bal = aplicar_balance(img, 0.0, 0.0)
        np.testing.assert_allclose(img, bal, atol=1e-5)


if __name__ == "__main__":
    unittest.main()

