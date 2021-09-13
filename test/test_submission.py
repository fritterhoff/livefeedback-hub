from unittest.mock import MagicMock, patch

from tornado.testing import AsyncHTTPTestCase

from livefeedback_hub.db import AutograderZip, Result
from livefeedback_hub.server import JupyterService


class TestSubmissionHandler(AsyncHTTPTestCase):
    service = JupyterService(xsrf_cookies=False)

    def get_app(self):
        return self.service.app

    def tearDown(self):
        with self.service.session() as session:
            session.query(AutograderZip).delete()
            session.query(Result).delete()

        super().tearDown()

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_submit_empty(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "student"}
        response = self.fetch("/submit", method="POST", body="")
        assert response.code == 400

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_submit_invalid(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "student"}
        response = self.fetch("/submit", method="POST", body="Hello")
        assert response.code == 400
