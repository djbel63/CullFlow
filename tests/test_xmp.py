import unittest
from revelador.xmp import generar


class MockToma:
    def __init__(self, raw=True):
        self.raw = raw
        self.nombre = "DSC_0001.NEF"
        self.clave = "DSC_0001.NEF"
        self.principal = "d:/fotos/DSC_0001.NEF"


class TestXMP(unittest.TestCase):

    def test_generar_xmp_basico(self):
        toma = MockToma(raw=True)
        aj = {
            "exposicion": 0.5,
            "contraste": 10,
            "altas_luces": -20,
            "sombras": 15,
            "blancos": 0,
            "negros": -5,
            "claridad": 10,
            "intensidad": 8,
            "saturacion": 5,
            "enfoque": 25,
            "reduccion_ruido": 15,
            "temperatura": 5,
            "matiz": 0,
            "vineteo": -15,
        }
        xmp_str = generar(
            toma,
            aj,
            elegida=True,
            puntuacion=0.88,
            categoria="retrato",
            tags=["navidad", "luces", "noche"],
        )

        self.assertIn('<x:xmpmeta', xmp_str)
        self.assertIn('crs:Exposure2012="+0.50"', xmp_str)
        self.assertIn('crs:PostCropVignetteAmount="-15"', xmp_str)
        self.assertIn('rev:Categoria="retrato"', xmp_str)
        self.assertIn('<dc:subject>', xmp_str)
        self.assertIn('<rdf:li>retrato</rdf:li>', xmp_str)
        self.assertIn('<rdf:li>navidad</rdf:li>', xmp_str)
        self.assertIn('<rdf:li>luces</rdf:li>', xmp_str)
        self.assertIn('<lr:hierarchicalSubject>', xmp_str)
        self.assertIn('</rdf:Description>', xmp_str)


if __name__ == "__main__":
    unittest.main()

