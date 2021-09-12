import os
from unittest.mock import MagicMock, patch

import pytest
from otter.grade import utils
from python_on_whales.exceptions import NoSuchImage
from tornado.httputil import HTTPFile

from livefeedback_hub.db import AutograderZip, Base
from livefeedback_hub.handlers import manage
from livefeedback_hub.server import JupyterService

os.environ["SERVICE_DB_URL"] = "sqlite://"


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
            session.add(AutograderZip(id="1"))
        manage.build(service, "1", zip_file=zip, update=True)
        exists.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b")
