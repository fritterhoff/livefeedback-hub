import os
import time
from unittest.mock import MagicMock, patch

from tornado.testing import AsyncHTTPTestCase

from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip, Result
from livefeedback_hub.server import JupyterService

os.environ["SERVICE_DB_URL"] = "sqlite:///:memory:"

notebook = '{ "cells": [ { "cell_type": "code", "metadata": {}, "source": "# LIVE: 333e2069-612e-4e0c-a4ac-e6ec1eaa44f0" } ], "metadata": { "kernelspec": { "display_name": "Python 3", "language": "python", "name": "python3" }, "language_info": { "codemirror_mode": { "name": "ipython", "version": 3 }, "file_extension": ".py", "mimetype": "text/x-python", "name": "python", "nbconvert_exporter": "python", "pygments_lexer": "ipython3", "version": "3.6.5" }, "varInspector": { "cols": { "lenName": 16, "lenType": 16, "lenVar": 40 }, "kernels_config": { "python": { "delete_cmd_postfix": "", "delete_cmd_prefix": "del ", "library": "var_list.py", "varRefreshCmd": "print(var_dic_list())" }, "r": { "delete_cmd_postfix": ") ", "delete_cmd_prefix": "rm(", "library": "var_list.r", "varRefreshCmd": "cat(var_dic_list()) " } }, "types_to_exclude": [ "module", "function", "builtin_function_or_method", "instance", "_Feature" ], "window_display": false } }, "nbformat": 4, "nbformat_minor": 4}'
notebook_without_id = '{ "cells": [ { "cell_type": "code", "metadata": {}, "source": "" } ], "metadata": { "kernelspec": { "display_name": "Python 3", "language": "python", "name": "python3" }, "language_info": { "codemirror_mode": { "name": "ipython", "version": 3 }, "file_extension": ".py", "mimetype": "text/x-python", "name": "python", "nbconvert_exporter": "python", "pygments_lexer": "ipython3", "version": "3.6.5" }, "varInspector": { "cols": { "lenName": 16, "lenType": 16, "lenVar": 40 }, "kernels_config": { "python": { "delete_cmd_postfix": "", "delete_cmd_prefix": "del ", "library": "var_list.py", "varRefreshCmd": "print(var_dic_list())" }, "r": { "delete_cmd_postfix": ") ", "delete_cmd_prefix": "rm(", "library": "var_list.r", "varRefreshCmd": "cat(var_dic_list()) " } }, "types_to_exclude": [ "module", "function", "builtin_function_or_method", "instance", "_Feature" ], "window_display": false } }, "nbformat": 4, "nbformat_minor": 4}'


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

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_submit_not_found(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "student"}
        response = self.fetch("/submit", method="POST", body=notebook)
        assert response.code == 200

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    def test_submitt_no_id(self, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "student"}
        response = self.fetch("/submit", method="POST", body=notebook_without_id)
        assert response.code == 200

    @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
    @patch("otter.grade.containers.grade_assignments")
    def test_submit(self, grade: MagicMock, get_current_user_mock: MagicMock):
        get_current_user_mock.return_value = {"name": "student"}
        with self.service.session() as session:
            zip = AutograderZip(id="333e2069-612e-4e0c-a4ac-e6ec1eaa44f0", description="Test", ready=True, data=bytes("Old", "utf-8"), owner=core.get_user_hash(get_current_user_mock.return_value))
            session.add(zip)
        response = self.fetch("/submit", method="POST", body=notebook)
        assert response.code == 200
        time.sleep(2)
        grade.assert_called_once()
        args = grade.call_args
        assert args.args[1] == "otter-grade:c7268757fbabf48019f4984933539d8a"
