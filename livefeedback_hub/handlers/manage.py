import hashlib
import logging
from typing import Optional

from jupyterhub.services.auth import HubOAuthenticated
from tornado import web
from tornado.web import RequestHandler, authenticated

from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip


class FeedbackManagementHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self):
        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            tasks = session.query(AutograderZip).filter_by( owner=user_hash).all()
            self.log.info(f"Found {len(tasks)} tasks by {user_hash}")
            await self.render("overview.html",tasks=tasks,base=self.service.prefix)


class FeedbackZipAddHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self):
        user_hash = core.get_user_hash(self.get_current_user())
        await self.render("add.html")

    @authenticated
    async def post(self):

        user_hash = core.get_user_hash(self.get_current_user())

        self.insert_new_grader(user_hash)
        await self.finish()

    def insert_new_grader(self, user_hash):
        # Insert zip and rebuild image
        pass


class FeedbackZipUpdateHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self, id: str):
        user_hash = core.get_user_hash(self.get_current_user())
        await self.render("edit.html")

    @authenticated
    async def post(self, live_id: str):

        user_hash = core.get_user_hash(self.get_current_user())
        with self.service.session() as session:
            entry: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not entry:
                raise web.HTTPError(403)
            else:
                self.update_grader(user_hash, live_id)

        await self.finish()

    def update_grader(self, user_hash, live_id):
        # Query for old zip, update zip, rebuild docker image and delete old image
        pass
