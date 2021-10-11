import logging
import os
import pathlib
from urllib.parse import urlparse

import sqlalchemy.orm
from jupyterhub.services.auth import HubOAuthCallbackHandler
from jupyterhub.utils import url_path_join
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.util.compat import contextmanager
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application as TornadoApplication
from traitlets import Unicode, default
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
        return os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")

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
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def __init__(self, **kwargs):
        from livefeedback_hub.handlers.manage import FeedbackManagementHandler, FeedbackZipAddHandler, \
            FeedbackZipUpdateHandler, FeedbackZipDeleteHandler
        from livefeedback_hub.handlers.results import FeedbackResultsApiHandler, FeedbackResultsHandler
        from livefeedback_hub.handlers.submission import FeedbackSubmissionHandler

        super().__init__(**kwargs)
        logging.basicConfig(level=logging.INFO)
        self._init_db()
        self.log: logging.Logger = logging.getLogger("tornado.application")
        xsrf_cookies = True
        if "xsrf_cookies" in kwargs:
            xsrf_cookies = kwargs["xsrf_cookies"]
        self.app = TornadoApplication(
            [
                (self.prefix, FeedbackManagementHandler, {"service": self}),
                (url_path_join(self.prefix, "submit"), FeedbackSubmissionHandler, {"service": self}),
                (url_path_join(self.prefix, "manage/add"), FeedbackZipAddHandler, {"service": self}),
                (
                url_path_join(self.prefix, f"manage/edit/({GUID_REGEX})"), FeedbackZipUpdateHandler, {"service": self}),
                (url_path_join(self.prefix, f"manage/delete/({GUID_REGEX})"), FeedbackZipDeleteHandler,
                 {"service": self}),
                (url_path_join(self.prefix, f"results/({GUID_REGEX})"), FeedbackResultsHandler, {"service": self}),
                (url_path_join(self.prefix, f"api/results/({GUID_REGEX})"), FeedbackResultsApiHandler,
                 {"service": self}),
                (
                    url_path_join(self.prefix, "oauth_callback"),
                    HubOAuthCallbackHandler,
                ),
            ],
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            static_url_prefix=url_path_join(self.prefix, "static/"),
            cookie_secret=os.urandom(32),
            xsrf_cookies=xsrf_cookies,
        )

    def start(self):
        self.log.info("Starting server")
        http_server = HTTPServer(self.app)
        url = urlparse(self.url)
        http_server.listen(url.port, url.hostname)
        self.log.info("Listening on %s", self.url)
        IOLoop.current().start()


def main(**kwargs):
    service = JupyterService(**kwargs)
    service.start()


if __name__ == "__main__":
    if os.getenv("JUPYTERHUB_SERVICE_URL") is None:
        from unittest.mock import patch, MagicMock


        @patch("jupyterhub.services.auth.HubAuthenticated.get_current_user")
        def development(get_current_user_mock: MagicMock):
            """
            Method for development! Mocks the user so running without
            :param get_current_user_mock: MagicMock object representing the get_current_user method. The return value gets set to a static defined user.
            """
            get_current_user_mock.return_value = {"name": "admin", "groups": ["teacher"]}

            main(xsrf_cookies=False)


        development()
    else:
        main()
