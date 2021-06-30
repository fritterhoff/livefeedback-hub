import hashlib
import json
import os
import re
import shutil
import tempfile
from typing import Optional

from jupyterhub.services.auth import HubOAuthenticated
from otter import grade
from tornado.web import RequestHandler, authenticated

from livefeedback_hub.db import AutograderZip, Result


class FeedbackHandler(HubOAuthenticated, RequestHandler):
    @staticmethod
    def _create_pattern() -> re.Pattern:
        return re.compile("^#\s*LIVE:\s*([a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})\s*\r?\n?$", re.IGNORECASE)

    @staticmethod
    def _check_line(pattern, line) -> Optional[str]:
        match = pattern.match(line)
        if match:
            return match.group(1)
        return None

    def _get_autograding_zip(self, nb) -> Optional[bytes]:
        cells = [cell["source"] for cell in nb["cells"]]
        pattern = self._create_pattern()
        live_ids = [self._check_line(pattern, line) for item in cells for line in item.split("\n") if self._check_line(pattern, line)]

        if len(live_ids) == 0:
            self.log.info("No livefeedback id in notebook")
            return None, None

        live_id = live_ids[0]
        self.log.info("Searching for grading zip with id %s", live_id)
        with self.service.session() as session:
            entry: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id).first()
            if entry:
                self.log.info("Found grading zip for %s", live_id)
                return (live_id, entry.data)

        return None, None

    def get(self):
        self.log.info("Handing live grading get request")
        pass

    @authenticated
    def post(self):
        self.log.info("Handing live grading request")
        nb = json.loads(self.request.body.decode("utf-8"))

        id, autograderZip = self._get_autograding_zip(nb)

        if autograderZip == None:
            self.finish()
            return

        m = hashlib.sha256()

        user_model = self.get_current_user()
        name = user_model["name"].encode("utf-8")

        m.update(name)
        user_hash = m.hexdigest()

        dir = tempfile.mkdtemp()
        fd, path = tempfile.mkstemp(suffix=".ipynb", dir=dir)
        fdZip, pathZip = tempfile.mkstemp(suffix=".zip", dir=dir)
        cwd = os.getcwd()
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(self.request.body)
                tmp.flush()
            with os.fdopen(fdZip, "wb") as tmp:
                tmp.write(autograderZip)
                tmp.flush()

            os.chdir(dir)
            results = grade.launch_grade(os.path.basename(pathZip), notebooks_dir=dir)
            user_result = results[0]
            self.add_or_update_results(user_hash, id, user_result)
        finally:
            os.chdir(cwd)
            shutil.rmtree(dir)
        self.finish()

    def initialize(self, service):
        self.service = service
        self.log = service.log

    def add_or_update_results(self, user_hash, assignment_id, user_result):
        with self.service.session() as session:
            existing: Optional[Result] = session.query(Result).filter_by(assignment=assignment_id, user=user_hash).first()
            if existing:
                session.delete(existing)
                session.commit()
            result = Result(user=user_hash, assignment=assignment_id, data=user_result.to_csv(index=False))
            session.add(result)
        return