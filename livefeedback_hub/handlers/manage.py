import shutil
import subprocess
import tempfile
import unittest.mock
import uuid
import zipfile
from concurrent.futures.thread import ThreadPoolExecutor
from io import BytesIO
from typing import Optional

import pkg_resources
from jupyterhub.services.auth import HubOAuthenticated
from otter.grade import utils
from python_on_whales import docker
from tornado import web
from tornado.httputil import HTTPFile

import livefeedback_hub.helper.misc
from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip, Result, State
from livefeedback_hub.helper.misc import teacher_only
from livefeedback_hub.server import JupyterService
from livefeedback_hub.helper.misc import calcuate_zip_hash, get_user_hash, delete_docker_image
manage_executor = ThreadPoolExecutor(max_workers=16)


def build(service: JupyterService, id: str, zip_file: HTTPFile, update: bool = False):
    """
    Builds a docker image from a zip file and optional deletes the old image if requested
    :param service: a service instance used for logging
    :param id: the id of live feedback task
    :param zip_file: the provided zip file
    :param update: flag indicating whether an update is executed (or a new image was added)
    """

    with service.session() as session:
        item: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=id).first()
        if item is None:
            return
        try:

            base = "ucbdsinfra/otter-grader"
            service.log.info(f"Building new docker image for {id}")
            image = utils.OTTER_DOCKER_IMAGE_TAG + ":" + calcuate_zip_hash(zip_file["body"])

            if update and docker.image.exists(image):
                service.log.info(f"Image for {id} exists ({image})")
                item.state = State.ready
                return
            dockerfile = pkg_resources.resource_filename("livefeedback_hub.handlers", "Dockerfile")

            if not docker.image.exists(image):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    with zipfile.ZipFile(BytesIO(zip_file["body"]), "r") as zip_ref:
                        zip_ref.extractall(tmp_dir)
                    shutil.copy(dockerfile, tmp_dir)
                    service.log.info(f"Building new image for {id} using {base} as base image")
                    run = livefeedback_hub.helper.misc.timeout_injector(subprocess.run)
                    with unittest.mock.patch("subprocess.run", run):
                        for line in docker.build(tmp_dir, build_args={"BASE_IMAGE": base}, tags=[image], file=dockerfile, load=True, stream_logs=True):
                            service.log.debug(line)
                    service.log.info(f"Building new docker image {image} for {id} completed")

        except Exception as e:
            service.log.error(f"Error while building docker image for {id}: {e}")
            item.state = State.error
            return

        if update and calcuate_zip_hash(zip_file["body"]) != calcuate_zip_hash(item.data):
            delete_docker_image(service, item)
        service.log.info(f"Marking {id} as ready")
        item.data = zip_file["body"]
        item.state = State.ready
        session.commit()


class FeedbackManagementHandler(HubOAuthenticated, core.CoreRequestHandler):
    @teacher_only
    async def get(self):
        user_hash = get_user_hash(self.get_current_user())
        with self.service.session() as session:
            tasks = session.query(AutograderZip).filter_by(owner=user_hash).all()
            self.log.info(f"Found {len(tasks)} tasks by {user_hash}")
            await self.render("overview.html", tasks=tasks, base=self.service.prefix)


class FeedbackZipAddHandler(HubOAuthenticated, core.CoreRequestHandler):
    @teacher_only
    async def get(self):
        task = AutograderZip()
        task.description = ""
        await self.render("edit.html", task=task, edit=False, base=self.service.prefix)

    @teacher_only
    async def post(self):
        user_hash = get_user_hash(self.get_current_user())
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
            item = AutograderZip(id=new_uuid, owner=user_hash, data=zip_file["body"], description=description,
                                 state=State.building)
            session.add(item)
            session.commit()
            manage_executor.submit(build, self.service, new_uuid, zip_file)


class FeedbackZipDeleteHandler(HubOAuthenticated, core.CoreRequestHandler):
    @teacher_only
    async def get(self, live_id: str):

        user_hash = get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:

                if task.state == State.building:
                    self.set_status(500)
                    await self.render("error.html", base=self.service.prefix)
                    return
                    # Delete task from database and delete docker image
                self.service.log.info(f"Deleting task {live_id}")
                delete_docker_image(self.service, task)
                session.delete(task)
            session.query(Result).filter_by(assignment=live_id).delete()
        self.redirect(self.service.prefix)


class FeedbackZipUpdateHandler(HubOAuthenticated, core.CoreRequestHandler):
    @teacher_only
    async def get(self, live_id: str):

        user_hash = get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:
                if task.state == State.building:
                    await self.render("error.html", base=self.service.prefix)
                else:
                    await self.render("edit.html", task=task, edit=True, base=self.service.prefix)

    @teacher_only
    async def post(self, live_id: str):

        user_hash = get_user_hash(self.get_current_user())
        with self.service.session() as session:
            task: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not task:
                raise web.HTTPError(403)
            else:
                if task.state == State.building:
                    await self.render("error.html", base=self.service.prefix)
                    return
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
            task.state = State.building
            session.commit()
            manage_executor.submit(build, self.service, live_id, zip_file, update=True)
