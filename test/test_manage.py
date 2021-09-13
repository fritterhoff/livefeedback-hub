import os
import uuid
from unittest.mock import MagicMock, call, patch

import pytest
import tornado.web
from otter.grade import utils
from python_on_whales.exceptions import NoSuchImage
from tornado.httputil import HTTPFile
from tornado.testing import AsyncHTTPTestCase

from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip, Result
from livefeedback_hub.handlers import manage
from livefeedback_hub.server import JupyterService

os.environ["SERVICE_DB_URL"] = "sqlite:///:memory:"


def compareTasks(x: AutograderZip, y: AutograderZip):
    return x.id == y.id and x.ready == y.ready and x.owner == y.owner and x.description == y.description


class TestManage:
    @pytest.fixture()
    def service(self):
        service = JupyterService()
        return service

    @patch("python_on_whales.docker.image.remove")
    def test_delete_image(self, mock: MagicMock, service):
        zip = AutograderZip()
        zip.data = bytes("Test", "utf-8")
        mock.return_value = None
        manage.delete_docker_image(service, zip)
        mock.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b", force=True)

    @patch("python_on_whales.docker.image.remove")
    def test_delete_image_fails(self, remove: MagicMock, service):
        zip = AutograderZip()
        zip.data = bytes("Test", "utf-8")
        remove.side_effect = NoSuchImage([], 0)
        service.log.warning = MagicMock()
        manage.delete_docker_image(service, zip)
        service.log.warning.assert_called_once()

    @patch("python_on_whales.docker.image.exists")
    def test_build_update_non_existing(self, exists: MagicMock, service):
        zip = HTTPFile()
        zip["body"] = bytes("Test", "utf-8")
        exists.return_value = True
        manage.build(service, "1", zip_file=zip, update=True)
        exists.assert_not_called()

    @patch("python_on_whales.docker.image.exists")
    def test_build_update_same(self, exists: MagicMock, service):
        zip = HTTPFile()
        zip["body"] = bytes("Test", "utf-8")
        exists.return_value = True
        with service.session() as session:
            session.add(AutograderZip(id="1", ready=False))
        manage.build(service, "1", zip_file=zip, update=True)
        exists.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b")
        with service.session() as session:
            assert session.query(AutograderZip).filter_by(id="1").first().ready is True

    @patch("python_on_whales.docker.image.exists")
    @patch("python_on_whales.docker.build")
    @patch("python_on_whales.docker.image.remove")
    def test_build_update(self, delete: MagicMock, build: MagicMock, exists: MagicMock, service):
        zip = HTTPFile()
        zip["body"] = bytes("Test", "utf-8")
        exists.return_value = False
        with service.session() as session:
            session.add(AutograderZip(id="1", ready=False, data=bytes("Old", "utf-8")))

        manage.build(service, "1", zip_file=zip, update=True)

        exists.assert_called_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b")

        delete.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:c7268757fbabf48019f4984933539d8a", force=True)

        build.assert_called_once()
        args: call = build.call_args
        assert args.kwargs["load"] is True
        assert args.kwargs["tags"] == [f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b"]

        with service.session() as session:
            assert session.query(AutograderZip).filter_by(id="1").first().ready is True
            assert session.query(AutograderZip).filter_by(id="1").first().data == bytes("Test", "utf-8")


class TestManageHandler(AsyncHTTPTestCase):
    service = JupyterService()

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
        response = self.fetch("/")
        assert response.code == 200

        with patch.object(tornado.web.RequestHandler, "render") as mock:
            self.fetch("/")
            mock.assert_called_once_with("overview.html", tasks=[], base="/")

        zip = AutograderZip(id="1", description="Test 1", ready=False, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
        zip2 = AutograderZip(id="2", description="Test 2", ready=False, data=bytes("Old", "utf-8"), owner=core.get_user_hash({"name": "user"}))
        zip3 = AutograderZip(id="3", description="Test 3", ready=False, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))

        with self.service.session() as session:
            session.add(zip)
            session.add(zip2)
            session.add(zip3)

        response = self.fetch("/")
        assert response.code == 200

        with patch.object(tornado.web.RequestHandler, "render") as mock:
            self.fetch("/")
            mock.assert_called_once()
            args = mock.call_args
            assert len(args.kwargs["tasks"]) == 2
            with self.service.session() as session:
                x = session.merge(args.kwargs["tasks"][0])
                y = session.merge(zip)
                assert compareTasks(x, y) is True
                x = session.merge(args.kwargs["tasks"][1])
                y = session.merge(zip3)
                assert compareTasks(x, y) is True

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_load_no_teacher(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "admin", "groups": []}
        response = self.fetch("/")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_edit_no_teacher(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "admin", "groups": []}
        response = self.fetch(f"/manage/edit/{str(uuid.uuid4())}")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_edit_no_task(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "admin", "groups": ["teacher"]}
        response = self.fetch(f"/manage/edit/{str(uuid.uuid4())}")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_edit_wrong_user(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "admin", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", ready=False, data=bytes("Old", "utf-8"), owner=core.get_user_hash({"name": "user"}))
            session.add(zip)

        response = self.fetch(f"/manage/edit/{id}")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_edit_success(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", ready=False, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)

        response = self.fetch(f"/manage/edit/{id}")

        assert response.code == 200
