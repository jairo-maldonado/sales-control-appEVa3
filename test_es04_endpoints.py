import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from ventas.models import AnalisisIA, Producto


class ES04EndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="tester_es04",
            password="PasswordSeguro123!",
        )
        Producto.objects.create(
            codigo="TEST-001",
            nombre="Producto Prueba Stock Bajo",
            precio="1500.00",
            stock=2,
        )
        token_resp = self.client.post(
            "/api/token/",
            {"username": "tester_es04", "password": "PasswordSeguro123!"},
            format="json",
        )
        self.assertEqual(token_resp.status_code, 200)
        self.access_token = token_resp.data["access"]

    def _auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.access_token}"}

    def test_analytics_requires_auth(self):
        resp = self.client.get("/api/analytics/resumen/")
        self.assertEqual(resp.status_code, 401)

    def test_analytics_invalid_days_returns_400(self):
        resp = self.client.get(
            "/api/analytics/resumen/?dias=0", **self._auth_headers()
        )
        self.assertEqual(resp.status_code, 400)

    def test_analytics_success_returns_kpis_and_series(self):
        resp = self.client.get(
            "/api/analytics/resumen/?dias=30", **self._auth_headers()
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("kpis", resp.data)
        self.assertIn("ventas_por_fecha", resp.data)
        self.assertIn("stock_por_producto", resp.data)
        self.assertEqual(resp.data["kpis"]["total_productos"], 1)

    def test_ia_analisis_missing_api_key_returns_503_and_logs_error(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
            resp = self.client.post(
                "/api/ia/analisis/",
                {"enfoque": "general", "dias": 30},
                format="json",
                **self._auth_headers(),
            )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(
            AnalisisIA.objects.filter(estado=AnalisisIA.ESTADO_ERROR).count(), 1
        )

    @patch("ventas.services.groq_service.urllib.request.urlopen")
    def test_ia_analisis_success_persists_record(self, mock_urlopen):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    b'{"choices":[{"message":{"content":"{\\"resumen_ejecutivo\\":\\"Stock '
                    b'bajo detectado en producto de prueba.\\",\\"nivel_riesgo\\":\\"ALTO\\",'
                    b'\\"acciones_prioritarias\\":[\\"Reponer stock de inmediato.\\"],'
                    b'\\"productos_criticos\\":[\\"Producto Prueba Stock Bajo\\"]}"}}]}'
                )

        mock_urlopen.return_value = FakeResponse()
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_fake_key"}, clear=False):
            resp = self.client.post(
                "/api/ia/analisis/",
                {"enfoque": "reposicion", "dias": 30},
                format="json",
                **self._auth_headers(),
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["estado"], AnalisisIA.ESTADO_OK)
        self.assertEqual(resp.data["resultado"]["nivel_riesgo"], "ALTO")