import os
import tempfile
import unittest
from revelador.config import Config, _bool, cargar, to_dict, actualizar_desde_dict, guardar_en_ini


class TestConfig(unittest.TestCase):

    def test_bool_parsing(self):
        self.assertTrue(_bool("si"))
        self.assertTrue(_bool("SÍ"))
        self.assertTrue(_bool("true"))
        self.assertTrue(_bool("1"))
        self.assertTrue(_bool("yes"))
        self.assertFalse(_bool("no"))
        self.assertFalse(_bool("false"))
        self.assertFalse(_bool("0"))
        self.assertFalse(_bool(""))
        self.assertTrue(_bool("", defecto=True))

    def test_trabajadores_efectivos_limites(self):
        c = Config()
        c.trabajadores = 0
        w = c.trabajadores_revelado_efectivos()
        self.assertGreaterEqual(w, 1)
        self.assertLessEqual(w, 4)

        c.trabajadores = 2
        self.assertEqual(c.trabajadores_revelado_efectivos(), 2)

    def test_config_defecto_formato_salida(self):
        c = Config()
        self.assertEqual(c.formato_salida, "jpeg")
        self.assertEqual(c.calidad_webp, 90)
        self.assertFalse(c.preferir_jpg_camara)
        self.assertTrue(c.corregir_aberraciones)
        self.assertTrue(c.incrustar_icc)
        self.assertEqual(c.ia_concurrencia, 2)

    def test_to_dict_y_actualizar(self):
        c = Config()
        d = to_dict(c)
        self.assertIn("ia", d)
        self.assertIn("revelado", d)
        self.assertEqual(d["revelado"]["calidad_jpeg"], 95)

        # Actualización con diccionario anidado
        actualizar_desde_dict(c, {"revelado": {"calidad_jpeg": 85}, "ia": {"concurrencia": 3}})
        self.assertEqual(c.calidad_jpeg, 85)
        self.assertEqual(c.ia_concurrencia, 3)

    def test_guardar_en_ini(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ini", encoding="utf-8") as f:
            f.write("; Comentario inicial\n[revelado]\ncalidad_jpeg = 95\n")
            ruta = f.name
        try:
            c = Config(ruta=ruta)
            c.calidad_jpeg = 88
            guardar_en_ini(c, ruta)
            
            c2 = cargar(ruta)
            self.assertEqual(c2.calidad_jpeg, 88)
            with open(ruta, "r", encoding="utf-8") as fh:
                txt = fh.read()
                self.assertIn("; Comentario inicial", txt)
        finally:
            if os.path.exists(ruta):
                os.remove(ruta)


if __name__ == "__main__":
    unittest.main()

