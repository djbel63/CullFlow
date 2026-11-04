import unittest
import numpy as np

from revelador.config import Config
from revelador.ia import ClienteIA, extraer_json, _data_url


class TestIA(unittest.TestCase):

    def test_extraer_json(self):
        # JSON directo
        self.assertEqual(extraer_json('{"a": 1, "b": 2}'), {"a": 1, "b": 2})

        # JSON con bloques markdown
        txt_md = 'Aquí está el resultado:\n```json\n{"exposicion": 0.5, "nota": "ok"}\n```'
        self.assertEqual(extraer_json(txt_md), {"exposicion": 0.5, "nota": "ok"})

        # JSON con etiquetas de pensamiento <think>
        txt_think = '<think>Analizando la toma...</think>\n{"exposicion": -0.2, "sombras": 10}'
        self.assertEqual(extraer_json(txt_think), {"exposicion": -0.2, "sombras": 10})

        # Sin JSON válido
        self.assertIsNone(extraer_json("No hay ningún objeto aquí"))
        self.assertIsNone(extraer_json(""))

    def test_data_url_encoding(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        url = _data_url(img, lado=50)
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))
        self.assertGreater(len(url), 50)

    def test_ajustes_ia_mock(self):
        cfg = Config()
        cliente = ClienteIA(cfg)

        # Mockear chat para devolver JSON simulado con categoria y tags
        cliente.chat = lambda contenido, **kwargs: (
            '{"exposicion": 0.3, "sombras": 15, "nota": "Calidez adecuada", '
            '"categoria": "paisaje", "tags": ["montana", "atardecer", "cielo"]}'
        )
        
        auto = {"exposicion": 0.0, "sombras": 0, "altas": 0, "contraste": 0}
        preview = np.zeros((50, 50, 3), dtype=np.uint8)
        res = cliente.ajustes(preview, {}, auto, vision=False, nombre="test.nef")

        self.assertIsNotNone(res)
        self.assertEqual(res["ajustes"]["exposicion"], 0.3)
        self.assertEqual(res["ajustes"]["sombras"], 15)
        self.assertIn("Calidez", res["nota"])
        self.assertEqual(res["categoria"], "paisaje")
        self.assertEqual(res["tags"], ["montana", "atardecer", "cielo"])


if __name__ == "__main__":
    unittest.main()

