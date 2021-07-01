import hashlib
import logging

from jupyterhub.services.auth import HubOAuthenticated
from tornado.web import RequestHandler, authenticated

from livefeedback_hub import core


class FeedbackManagementHandler(HubOAuthenticated, RequestHandler):
    def initialize(self, service):
        self.service = service
        self.log: logging.Logger = service.log

    @authenticated
    async def get(self):
        user_hash = core.get_user_hash(self.get_current_user())
        await self.render("overview.html")


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
    async def post(self, id: str):

        user_hash = core.get_user_hash(self.get_current_user())

        self.update_grader(user_hash, id)

        await self.finish()

    def update_grader(self, user_hash, id):
        # Query for old zip, update zip, rebuild docker image and delete old image
        pass
