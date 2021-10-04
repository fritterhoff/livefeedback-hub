import io
import uuid
import zipfile
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import tornado.web
from otter.grade import utils
from python_on_whales.exceptions import NoSuchImage
from tornado.httputil import HTTPFile
from tornado.testing import AsyncHTTPTestCase

from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip, Result, State
from livefeedback_hub.handlers import manage
from livefeedback_hub.server import JupyterService


def compareTasks(x: AutograderZip, y: AutograderZip):
    return x.id == y.id and x.state == y.state and x.owner == y.owner and x.description == y.description


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
        core.delete_docker_image(service, zip)
        mock.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b", force=True)

    @patch("python_on_whales.docker.image.remove")
    def test_delete_image_fails(self, remove: MagicMock, service):
        zip = AutograderZip()
        zip.data = bytes("Test", "utf-8")
        remove.side_effect = NoSuchImage([], 0)
        service.log.warning = MagicMock()
        core.delete_docker_image(service, zip)
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
            session.add(AutograderZip(id="1", state=State.building))
        manage.build(service, "1", zip_file=zip, update=True)
        exists.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b")
        with service.session() as session:
            assert session.query(AutograderZip).filter_by(id="1").first().state == State.ready

    @patch("python_on_whales.docker.image.exists")
    @patch("python_on_whales.docker.build")
    @patch("python_on_whales.docker.image.remove")
    def test_build_update(self, delete: MagicMock, build: MagicMock, exists: MagicMock, service):
        zip = HTTPFile()
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w") as zip_ref:
            zip_ref.writestr("content", "Hello")
        zip["body"] = zip_bytes.getvalue()
        exists.return_value = False
        with service.session() as session:
            session.add(AutograderZip(id="1", state=State.building, data=bytes("Old", "utf-8")))

        manage.build(service, "1", zip_file=zip, update=True)

        exists.assert_called_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:{core.calcuate_zip_hash(zip_bytes.getvalue())}")

        delete.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:c7268757fbabf48019f4984933539d8a", force=True)

        build.assert_called_once()
        args: call = build.call_args
        assert args.kwargs["load"] is True
        assert args.kwargs["tags"] == [f"{utils.OTTER_DOCKER_IMAGE_TAG}:{core.calcuate_zip_hash(zip_bytes.getvalue())}"]

        with service.session() as session:
            assert session.query(AutograderZip).filter_by(id="1").first().state == State.ready
            assert session.query(AutograderZip).filter_by(id="1").first().data == zip_bytes.getvalue()

    @patch("python_on_whales.docker.image.exists")
    @patch("python_on_whales.docker.build")
    @patch("python_on_whales.docker.image.remove")
    def test_build_update_fails(self, delete: MagicMock, build: MagicMock, exists: MagicMock, service):
        zip = HTTPFile()
        zip["body"] = bytes("Test", "utf-8")
        exists.return_value = False
        with service.session() as session:
            session.add(AutograderZip(id="1", state=State.building, data=bytes("Old", "utf-8")))
        build.side_effect = Exception()
        try:
            manage.build(service, "1", zip_file=zip, update=True)
        except Exception as e:
            assert e is not None

        exists.assert_called_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b")

        delete.assert_not_called()

        with service.session() as session:
            assert session.query(AutograderZip).filter_by(id="1").first().state == State.error
            assert session.query(AutograderZip).filter_by(id="1").first().data == bytes("Old", "utf-8")


class TestManageHandler(AsyncHTTPTestCase):
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
        response = self.fetch("/")
        assert response.code == 200

        with patch.object(tornado.web.RequestHandler, "render", new_callable=AsyncMock) as mock:
            self.fetch("/")
            mock.assert_called_once_with("overview.html", tasks=[], base="/")

        zip = AutograderZip(id="1", description="Test 1", state=State.building, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
        zip2 = AutograderZip(id="2", description="Test 2", state=State.building, data=bytes("Old", "utf-8"), owner=core.get_user_hash({"name": "user"}))
        zip3 = AutograderZip(id="3", description="Test 3", state=State.building, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))

        with self.service.session() as session:
            session.add(zip)
            session.add(zip2)
            session.add(zip3)

        response = self.fetch("/")
        assert response.code == 200

        with patch.object(tornado.web.RequestHandler, "render", new_callable=AsyncMock) as mock:
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
            zip = AutograderZip(id=id, description="Test", state=State.building, data=bytes("Old", "utf-8"), owner=core.get_user_hash({"name": "user"}))
            session.add(zip)

        response = self.fetch(f"/manage/edit/{id}")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_edit_success(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", state=State.building, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)

        response = self.fetch(f"/manage/edit/{id}")

        assert response.code == 200

    def generate_request(self, file, description):
        # create a boundary
        boundary = "SomeRandomBoundary"

        # set the Content-Type header
        headers = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}

        # create the body

        # opening boundary
        body = "--%s\r\n" % boundary

        # data for description
        body += 'Content-Disposition: form-data; name="description"\r\n'
        body += "\r\n"  # blank line
        body += f"{description}\r\n"

        # separator boundary
        body += "--%s\r\n" % boundary

        if file is not None:
            # data for zip
            body += 'Content-Disposition: form-data; name="zip"; filename="autograder.zip"\r\n'
            body += "\r\n"  # blank line
            body += "%s\r\n" % file
        else:
            # Simulate no file
            body += 'Content-Disposition: form-data; name="zip"; filename=""\r\nContent-Type: application/octet-stream\r\n'
        # the closing boundary
        body += "--%s--\r\n" % boundary
        return (headers, body)

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_update_grader_not_found(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        headers, body = self.generate_request(bytes("Test", "utf-8"), "Hello")
        response = self.fetch(f"/manage/edit/{id}", method="POST", headers=headers, body=body)
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_update_grader_no_teacher(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": [""]}
        id = str(uuid.uuid4())
        headers, body = self.generate_request(bytes("Test", "utf-8"), "Hello")
        response = self.fetch(f"/manage/edit/{id}", method="POST", headers=headers, body=body)
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    @patch("livefeedback_hub.handlers.manage.manage_executor.submit")
    def test_update_grader(self, submit: MagicMock, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", state=State.ready, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)
        headers, body = self.generate_request(bytes("Test", "utf-8"), "Hello")
        response = self.fetch(f"/manage/edit/{id}", method="POST", headers=headers, body=body, follow_redirects=False)
        assert response.code == 302
        submit.assert_called_once()
        with self.service.session() as session:
            assert session.query(AutograderZip).filter_by(id=id).first().state == State.building
            assert session.query(AutograderZip).filter_by(id=id).first().description == "Hello"

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    @patch("livefeedback_hub.handlers.manage.manage_executor.submit")
    def test_update_grader_no_zip(self, submit: MagicMock, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", state=State.ready, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)
        headers, body = self.generate_request(None, "Hello")
        response = self.fetch(f"/manage/edit/{id}", method="POST", headers=headers, body=body, follow_redirects=False)
        assert response.code == 302
        submit.assert_not_called()
        with self.service.session() as session:
            assert session.query(AutograderZip).filter_by(id=id).first().state == State.ready
            assert session.query(AutograderZip).filter_by(id=id).first().description == "Hello"

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_add_grader_no_teacher(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": [""]}
        response = self.fetch("/manage/add")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_add_grader(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        response = self.fetch("/manage/add")
        assert response.code == 200
        with patch.object(tornado.web.RequestHandler, "render", new_callable=AsyncMock) as mock:
            self.fetch("/manage/add")
            mock.assert_called_once()
            args = mock.call_args
            task = args.kwargs["task"]
            assert task.description == ""

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    @patch("livefeedback_hub.handlers.manage.manage_executor.submit")
    def test_add_grader_post(self, submit: MagicMock, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        headers, body = self.generate_request(bytes("Test", "utf-8"), "Hello")
        response = self.fetch("/manage/add", method="POST", headers=headers, body=body, follow_redirects=False)
        assert response.code == 302
        submit.assert_called_once()
        with self.service.session() as session:
            assert session.query(AutograderZip).first().state == State.building
            assert session.query(AutograderZip).first().description == "Hello"

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_delete_grader_no_teacher(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": [""]}
        id = str(uuid.uuid4())
        response = self.fetch(f"/manage/delete/{id}")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_delete_grader_no_task(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        response = self.fetch(f"/manage/delete/{id}")
        assert response.code == 403

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    @patch("livefeedback_hub.core.delete_docker_image")
    def test_delete(self, delete: MagicMock, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "teacher", "groups": ["teacher"]}
        id = str(uuid.uuid4())
        with self.service.session() as session:
            zip = AutograderZip(id=id, description="Test", state=State.ready, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)

        response = self.fetch(f"/manage/delete/{id}", follow_redirects=False)
        assert response.code == 302
        delete.assert_called_once()
