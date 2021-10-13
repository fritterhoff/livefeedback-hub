import logging
from typing import Any

from tornado.web import RequestHandler

from livefeedback_hub.server import JupyterService


class CoreRequestHandler(RequestHandler):
    """
    To allow some (fancy) custom error pages we overwrite the (Default) RequestHandler's method write_error
    """

    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        self.set_status(status_code)
        if status_code == 403:
            msg = "Zugriff verweigert!"
        else:
            msg = "Interner Serverfehler!"
        self.render("error.html", base=self.service.prefix, msg=msg)
