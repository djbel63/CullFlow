import unittest
from revelador.config import Config
from revelador.web import app, ESTADO


class TestWebAPI(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.cfg = Config()
        ESTADO["cfg"] = self.cfg
        ESTADO["proyecto"] = None

    def test_get_config(self):
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("config", data)
        self.assertIn("ajustes", data)
        self.assertEqual(data["config"]["revelado"]["calidad_jpeg"], 95)

    def test_post_config(self):
        nuevos = {
            "revelado": {
                "calidad_jpeg": 89,
                "formato_salida": "webp"
            },
            "ia": {
                "concurrencia": 3
            }
        }
        res = self.client.post("/api/config", json=nuevos)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(self.cfg.calidad_jpeg, 89)
        self.assertEqual(self.cfg.formato_salida, "webp")
        self.assertEqual(self.cfg.ia_concurrencia, 3)


if __name__ == "__main__":
    unittest.main()

