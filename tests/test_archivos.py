import unittest
import numpy as np

from revelador.archivos import aplicar_orientacion, _parse_picture_control, Toma


class TestArchivos(unittest.TestCase):

    def test_aplicar_orientacion_rotaciones(self):
        # Matriz 10x20
        img = np.zeros((10, 20, 3), dtype=np.uint8)
        img[0, 0] = [255, 0, 0]  # Píxel de prueba

        # Orientación 1 (sin cambios)
        self.assertEqual(aplicar_orientacion(img, 1).shape, (10, 20, 3))
        # Orientación 3 (180 grados)
        self.assertEqual(aplicar_orientacion(img, 3).shape, (10, 20, 3))
        # Orientación 6 (90 CW)
        self.assertEqual(aplicar_orientacion(img, 6).shape, (20, 10, 3))
        # Orientación 8 (90 CCW)
        self.assertEqual(aplicar_orientacion(img, 8).shape, (20, 10, 3))

    def test_parse_picture_control(self):
        raw_val = b"0100STANDARD" + b"\x00" * 20
        self.assertEqual(_parse_picture_control(raw_val), "Standard")
        self.assertEqual(_parse_picture_control("VIVID"), "VIVID")
        self.assertEqual(_parse_picture_control(None), "")

    def test_toma_dataclass(self):
        t = Toma(clave="test_01", raw="foto.nef", jpg="foto.jpg")
        self.assertEqual(t.principal, "foto.nef")
        self.assertTrue(t.es_raw)
        self.assertEqual(t.nombre, "foto.nef")

    def test_universal_raw_formats(self):
        from revelador.archivos import EXT_RAW
        formatos_esperados = [".nef", ".nrw", ".arw", ".cr2", ".cr3", ".raf", ".orf", ".rw2", ".pef", ".dng"]
        for ext in formatos_esperados:
            self.assertIn(ext, EXT_RAW, f"Extensión {ext} debe estar soportada")
        # Verificar que una toma Sony ARW o Canon CR3 es reconocida como RAW
        t_sony = Toma(clave="sony_01", raw="DSC001.ARW")
        self.assertTrue(t_sony.es_raw)
        t_canon = Toma(clave="canon_01", raw="IMG_001.CR3")
        self.assertTrue(t_canon.es_raw)


if __name__ == "__main__":
    unittest.main()
