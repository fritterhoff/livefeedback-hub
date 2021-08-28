import logging
import os
import shutil
import tempfile
import uuid
from concurrent.futures.thread import ThreadPoolExecutor
from hashlib import md5
from typing import Optional

import docker
from jupyterhub.services.auth import HubOAuthenticated
from otter.grade import utils, containers
from tornado import web
from tornado.httputil import HTTPFile
from tornado.web import RequestHandler

from livefeedback_hub import core
from livefeedback_hub.core import teacher_only
from livefeedback_hub.db import AutograderZip, Result
from livefeedback_hub.server import JupyterService

executor = ThreadPoolExecutor(max_workers=16)


def delete_docker_image(service: JupyterService, task: AutograderZip):
    """
    Trys to delete the docker image belonging to the provided task
    :param service: a service instance used for logging
    :param task: the task to delete
    """
    m = md5()
    m.update(task.data)
    image = f"{utils.OTTER_DOCKER_IMAGE_TAG}:{m.hexdigest()}"
    service.log.info(f"Deleting docker image {image}")
    client = docker.from_env()
    try:
        client.images.remove(image=image, force=True)
    except docker.errors.ImageNotFound as e:
        service.log.warning(f"Image not found: {e}")


def build(service: JupyterService, id: str, zip_file: HTTPFile, update: bool = False):
    """
    Builds a docker image from a zip file and optional deletes the old image if requested
    :param service: a service instance used for logging
    :param id: the id of live feedback task
    :param zip_file: the provided zip file
    :param update: flag indicating whether an update is executed (or a new image was added)
    """
    tmp_dir = tempfile.mkdtemp()
    fd_zip, path_zip = tempfile.mkstemp(suffix=".zip", dir=tmp_dir)
    cwd = os.getcwd()
    try:
        with os.fdopen(fd_zip, "wb") as tmp:
            tmp.write(zip_file["body"])
            tmp.flush()

        os.chdir(tmp_dir)
        base = "ucbdsinfra/otter-grader"
        service.log.info(f"Building new docker image for {id}")
        image = containers.build_image(os.path.basename(path_zip), base, containers.generate_hash(os.path.basename(path_zip)))
        service.log.info(f"Building new docker image {image} for {id} completed")
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp_dir)

    with service.session() as session:
        if update:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=id).first()
            delete_docker_image(service, task)
        service.log.info(f"Marking task {id} as ready")
        item: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=id).first()
        item.ready = True
        item.data = zip_file["body"]



class FeedbackManagementHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    @teacher_only
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

    @teacher_only
    async def get(self):
        task = AutograderZip()
        await self.render("edit.html", task=task, edit=False, base=self.service.prefix)

    @teacher_only
    async def post(self):
        user_hash = core.get_user_hash(self.get_current_user())
        description = self.get_body_argument("description")
        if "zip" in self.request.files:
            if self.request.files["zip"][0]:
                zip_file = self.request.files["zip"][0]
                self.insert_new_grader(user_hash, zip_file, description)
        self.redirect(self.service.prefix)

    def insert_new_grader(self, user_hash, zip_file, description):
        # Insert zip file into database and build docker image
        self.log.info(f"Got zip file {zip_file['filename']}")
        with self.service.session() as session:
            # get new uuid
            new_uuid = str(uuid.uuid4())
            item = AutograderZip(id=new_uuid, owner=user_hash, data=zip_file["body"], description=description, ready=False)
            session.add(item)
            session.commit()
            executor.submit(build, self.service, new_uuid, zip_file)


class FeedbackZipDeleteHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    @teacher_only
    async def get(self, live_id: str):

        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:
                # Delete task from database and delete docker image
                self.service.log.info(f"Deleting task {live_id}")
                delete_docker_image(self.service, task)
                session.delete(task)
            session.query(Result).filter_by(assignment=live_id).delete()
        self.redirect(self.service.prefix)


class FeedbackZipUpdateHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    @teacher_only
    async def get(self, live_id: str):

        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:
                await self.render("edit.html", task=task, edit=True, base=self.service.prefix)

    @teacher_only
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
                        zip_file = self.request.files["zip"][0]
                        self.update_grader(user_hash, live_id, zip_file)

        self.redirect(self.service.prefix)

    def update_grader(self, user_hash, live_id, zip_file):
        self.log.info(f"Got zip file {zip_file['filename']}")

        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            # Mark as not ready, rebuild image and mark as ready afterwards
            task.ready = False
            session.commit()
            executor.submit(build, self.service, live_id, zip_file, update=True)
