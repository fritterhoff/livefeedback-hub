import json
import logging
import os
import re
import shutil
import tempfile
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Optional

import pandas as pd
from jupyterhub.services.auth import HubOAuthenticated
from otter.grade import containers, utils
from livefeedback_hub.server import JupyterService
from tornado.web import RequestHandler, authenticated

from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip, Result, GUID_REGEX
import otter


class FeedbackSubmissionHandler(HubOAuthenticated, RequestHandler):
    executor = ThreadPoolExecutor(max_workers=16)

    @staticmethod
    def _create_pattern() -> re.Pattern:
        return re.compile(f"^#\s*LIVE:\s*({GUID_REGEX})\s*\r?\n?$", re.IGNORECASE)

    @staticmethod
    def _check_line(pattern, line) -> Optional[str]:
        match = pattern.match(line)
        if match:
            return match.group(1)
        return None

    def _get_autograding_zip(self, nb) -> (Optional[str], Optional[bytes]):
        cells = [cell["source"] for cell in nb["cells"]]
        pattern = self._create_pattern()
        live_ids = [self._check_line(pattern, line) for item in cells for line in item.split("\n") if
                    self._check_line(pattern, line)]

        if len(live_ids) == 0:
            self.log.info("No live feedback id in notebook")
            return None, None

        live_id = live_ids[0]
        self.log.info("Searching for grading zip with id %s", live_id)
        with self.service.session() as session:
            entry: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id).first()
            if entry:
                self.log.info("Found grading zip for %s", live_id)
                return (live_id, entry.data)

        return None, None

    @authenticated
    async def post(self):
        self.log.info("Handing live feedback request")
        nb = json.loads(self.request.body.decode("utf-8"))

        id, autograder_zip = self._get_autograding_zip(nb)

        if autograder_zip is None:
            await self.finish()
            return

        user_hash = core.get_user_hash(self.get_current_user())

        self.executor.submit(self.process_notebook,
                             autograder_zip=autograder_zip,
                             notebook=self.request.body,
                             id=id,
                             user_hash=user_hash)
        await self.finish()

    def process_notebook(self, autograder_zip: bytes, notebook: bytes, id: str, user_hash: str):
        dir = tempfile.mkdtemp()
        fd, path = tempfile.mkstemp(suffix=".ipynb", dir=dir)
        fdZip, pathZip = tempfile.mkstemp(suffix=".zip", dir=dir)
        cwd = os.getcwd()
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(notebook)
                tmp.flush()
            with os.fdopen(fdZip, "wb") as tmp:
                tmp.write(autograder_zip)
                tmp.flush()

            os.chdir(dir)
            self.log.info(f"Launching otter-grader for {user_hash} and {id}")
            image = utils.OTTER_DOCKER_IMAGE_TAG + ":" + containers.generate_hash(os.path.basename(pathZip))
            user_result = containers.grade_assignments(path, image, debug=True, verbose=True)
            self.add_or_update_results(user_hash, id, user_result)
        finally:
            os.chdir(cwd)
            shutil.rmtree(dir)

    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    def add_or_update_results(self, user_hash, assignment_id, user_result: pd.DataFrame):
        with self.service.session() as session:
            existing: Optional[Result] = session.query(Result).filter_by(assignment=assignment_id,
                                                                         user=user_hash).first()
            if existing:
                existing.data = user_result.to_csv(index=False)
            else:
                result = Result(user=user_hash,
                                assignment=assignment_id,
                                data=user_result.to_csv(index=False))
                session.add(result)
