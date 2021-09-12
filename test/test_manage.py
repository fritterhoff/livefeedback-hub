from unittest.mock import MagicMock, patch

from otter.grade import utils
from python_on_whales.exceptions import NoSuchImage

from livefeedback_hub.db import AutograderZip
from livefeedback_hub.handlers import manage
from livefeedback_hub.server import JupyterService


class TestManage:

    @patch("python_on_whales.docker.image.remove")
    def test_delete_image(self, mock: MagicMock):
        service = JupyterService()
        zip = AutograderZip()
        zip.data = bytes("Test", "utf-8")
        mock.return_value = None
        manage.delete_docker_image(service, zip)
        mock.assert_called_once_with(f"{utils.OTTER_DOCKER_IMAGE_TAG}:0cbc6611f5540bd0809a388dc95a615b", force=True)

    @patch("python_on_whales.docker.image.remove")
    def test_delete_image_fails(self, remove: MagicMock):
        service = JupyterService()
        zip = AutograderZip()
        zip.data = bytes("Test", "utf-8")
        remove.side_effect = NoSuchImage([], 0)
        service.log.warning = MagicMock()
        manage.delete_docker_image(service, zip)
        service.log.warning.assert_called_once()
