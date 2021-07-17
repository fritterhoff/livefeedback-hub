import logging
import os
import pathlib


from urllib.parse import urlparse

import sqlalchemy.orm
from jupyterhub.services.auth import HubAuthenticated, HubOAuthCallbackHandler
from jupyterhub.utils import url_path_join
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.util.compat import contextmanager
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application as TornadoApplication
from traitlets import default, Unicode
from traitlets.config.application import Application

from livefeedback_hub.db import Base, GUID_REGEX


class JupyterService(Application):
    url = Unicode()
    prefix = Unicode()
    db_url = Unicode()

    @default("db_url")
    def _default_db_url(self):
        return os.environ.get("SERVICE_DB_URL", f"sqlite:///{pathlib.Path(__file__).parent.resolve()}\\data.db")

    @default("prefix")
    def _default_prefix(self):
        return os.environ.get("JUPYTERHUB_SERVICE_PREFIX", f"/")

    @default("url")
    def _default_url(self):
        return os.environ.get("JUPYTERHUB_SERVICE_URL", "http://[::]:5000")

    def _init_db(self):
        engine = create_engine(url=self.db_url)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)

    @contextmanager
    def session(self) -> sqlalchemy.orm.Session:
        session = self.db()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    def __init__(self, **kwargs):
        from livefeedback_hub.handlers.manage import FeedbackManagementHandler, FeedbackZipAddHandler, FeedbackZipUpdateHandler
        from livefeedback_hub.handlers.results import FeedbackResultsApiHandler, FeedbackResultsHandler
        from livefeedback_hub.handlers.submission import FeedbackSubmissionHandler

        super().__init__(**kwargs)
        logging.basicConfig(level=logging.INFO)
        self._init_db()
        self.log: logging.Logger = logging.getLogger("tornado.application")
        self.app = TornadoApplication(
            [
                (self.prefix, FeedbackManagementHandler, {"service": self}),
                (url_path_join(self.prefix, "submit"), FeedbackSubmissionHandler, {"service": self}),
                (url_path_join(self.prefix, f"manage/add"), FeedbackZipAddHandler, {"service": self}),
                (url_path_join(self.prefix, f"manage/({GUID_REGEX})"), FeedbackZipUpdateHandler, {"service": self}),
                (url_path_join(self.prefix, f"results/({GUID_REGEX})"), FeedbackResultsHandler, {"service": self}),
                (url_path_join(self.prefix, f"api/results/({GUID_REGEX})"), FeedbackResultsApiHandler, {"service": self}),
                (
                    url_path_join(self.prefix, "oauth_callback"),
                    HubOAuthCallbackHandler,
                ),
            ],
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            cookie_secret=os.urandom(32),
            xsrf_cookies=True,
        )

    def start(self):
        http_server = HTTPServer(self.app)
        url = urlparse(self.url)
        http_server.listen(url.port, url.hostname)

        IOLoop.current().start()


def main():
    service = JupyterService()
    service.start()


from unittest.mock import patch, MagicMock


@patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
def development(mock: MagicMock):
    mock.return_value = {"name": "admin"}
    main()
    pass


if __name__ == "__main__":
    if os.getenv("JUPYTERHUB_SERVICE_URL") == None:
        development()
    else:
        main()
