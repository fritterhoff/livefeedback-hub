import uuid
from unittest.mock import MagicMock, patch

from tornado.testing import AsyncHTTPTestCase

import livefeedback_hub.helper.misc
from livefeedback_hub.db import AutograderZip, Result, State
from livefeedback_hub.server import JupyterService


class TestResultHandler(AsyncHTTPTestCase):
    service = JupyterService(xsrf_cookies=False)

    def get_app(self):
        return self.service.app

    def tearDown(self):
        with self.service.session() as session:
            session.query(AutograderZip).delete()
            session.query(Result).delete()

        super().tearDown()

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_load_logged_in(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "admin", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", state=State.building, data=bytes("Old", "utf-8"),
                                owner=livefeedback_hub.helper.misc.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)
        response = self.fetch(f"/results/{id}")
        assert response.code == 200
        response = self.fetch(f"/api/results/{id}")
        assert response.code == 204

        with self.service.session() as session:
            result = Result(assignment=id, data="q1,q2,q3,file\n1.0,1.0,1.0,tmp7_tbcley.ipynb", user="test")
            session.add(result)
        response = self.fetch(f"/api/results/{id}")
        assert response.code == 200
        assert response.body == b'{"index":{"0.0":1.0,"1.0":null},"q1":{"0.0":null,"1.0":1.0},"q2":{"0.0":null,"1.0":1.0},"q3":{"0.0":null,"1.0":1.0}}'

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_load_wrong_user(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "admin", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", state=State.building, data=bytes("Old", "utf-8"),
                                owner=livefeedback_hub.helper.misc.get_user_hash({"name": "user"}))
            session.add(zip)
        response = self.fetch(f"/results/{id}")
        assert response.code == 403
        response = self.fetch(f"/api/results/{id}")
        assert response.code == 403
