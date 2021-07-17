import hashlib
import logging
from typing import Optional

from jupyterhub.services.auth import HubOAuthenticated
from tornado import web
from tornado.web import RequestHandler, authenticated

from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip
import sqlalchemy
from livefeedback_hub.server import JupyterService
import uuid
from otter.grade import containers
import os
import tempfile
import shutil
from hashlib import md5
import docker
import otter


def build(service, zip):
    dir = tempfile.mkdtemp()
    fdZip, pathZip = tempfile.mkstemp(suffix=".zip", dir=dir)
    cwd = os.getcwd()
    try:
        with os.fdopen(fdZip, "wb") as tmp:
            tmp.write(zip["body"])
            tmp.flush()

        os.chdir(dir)
        base = "ucbdsinfra/otter-grader"
        image = containers.build_image(os.path.basename(pathZip), base, containers.generate_hash(os.path.basename(pathZip)))
    finally:
        os.chdir(cwd)
        shutil.rmtree(dir)


class FeedbackManagementHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self):
        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            tasks = session.query(AutograderZip).filter_by(owner=user_hash).all()
            self.log.info(f"Found {len(tasks)} tasks by {user_hash}")
            await self.render("overview.html", tasks=tasks, base=self.service.prefix)


class FeedbackZipAddHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self):
        user_hash = core.get_user_hash(self.get_current_user())
        await self.render("add.html")

    @authenticated
    async def post(self):

        user_hash = core.get_user_hash(self.get_current_user())
        description = self.get_body_argument("description")
        if "zip" in self.request.files:
            if self.request.files["zip"][0]:
                zip = self.request.files["zip"][0]
                self.insert_new_grader(user_hash, zip, description)
        await self.finish()

    def insert_new_grader(self, user_hash, zip, description):
        # Insert zip file into database and build docker image
        self.log.info(f"Got zip file {zip['filename']}")
        with self.service.session() as session:
            # get new uuid
            new_uuid = str(uuid.uuid4())
            item = AutograderZip(id=new_uuid, owner=user_hash, zip_file=zip["body"], description=description, ready=False)
            session.add(item)
            session.commit()
            build(self.service, zip)
            item.ready = True
            session.commit()


class FeedbackZipUpdateHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self, live_id: str):

        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:
                await self.render("edit.html", task=task, base=self.service.prefix)

    @authenticated
    async def post(self, live_id: str):

        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:
                task.description = self.get_body_argument("description")
                session.commit()

                if "zip" in self.request.files:
                    if self.request.files["zip"][0]:
                        zip = self.request.files["zip"][0]
                        self.update_grader(user_hash, live_id, zip)

        await self.finish()

    def update_grader(self, user_hash, live_id, zip):
        self.log.info(f"Got zip file {zip['filename']}")

        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()

            m = md5()
            m.update(task.data)
            oldImageHash = m.hexdigest()

            # Mark as not ready, rebuild image and mark as ready afterwards
            task.ready = False
            session.commit()
            build(self.service, zip)
            # Mark task as ready and update database entry
            task.ready = True
            task.data = zip["body"]
            session.commit()

            client = docker.from_env()
            client.images.remove(f"{otter.utils.OTTER_DOCKER_IMAGE_TAG}:{oldImageHash}")
