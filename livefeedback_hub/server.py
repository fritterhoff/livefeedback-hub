import os
from urllib.parse import urlparse

import sqlalchemy.orm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.util.compat import contextmanager
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from traitlets import default, Unicode

from traitlets.config.application import Application
from tornado.web import Application as TornadoApplication

import logging

from jupyterhub.services.auth import HubOAuthCallbackHandler
from jupyterhub.utils import url_path_join

from livefeedback_hub.db import Base
from livefeedback_hub.handler import FeedbackHandler
import pathlib


class JupyterService(Application):

    url = Unicode()
    prefix = Unicode()
    db_url = Unicode()

    @default("db_url")
    def _default_db_url(self):
        return os.environ.get("SERVICE_DB_URL", f"sqlite:///{pathlib.Path(__file__).parent.resolve()}\\data.db")

    @default("prefix")
    def _default_prefix(self):
        return os.environ.get("JUPYTERHUB_SERVICE_PREFIX", f"/services/{self.name}/")

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
        super().__init__(**kwargs)
        logging.basicConfig(level=logging.INFO)
        self._init_db()
        self.log = logging.getLogger("tornado.application")
        self.app = TornadoApplication(
            [
                (self.prefix, FeedbackHandler, {"service": self}),
                (
                    url_path_join(self.prefix, "oauth_callback"),
                    HubOAuthCallbackHandler,
                ),
                (r".*", FeedbackHandler, {"service": self}),
            ],
            cookie_secret=os.urandom(32),
        )

    def start(self):
        http_server = HTTPServer(self.app)
        url = urlparse(self.url)
        http_server.bind(url.port)
        http_server.start(16)  # forks one process per cpu

        IOLoop.current().start()

def main():
    service = JupyterService()
    service.start()

if __name__ == "__main__":
    main()