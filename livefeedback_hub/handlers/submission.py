import json
import os
import re
import shutil
import tempfile
from io import BytesIO
from typing import Optional, Tuple

import pandas as pd
import stdio_proxy
from jupyterhub.services.auth import HubOAuthenticated
from otter.grade import containers, utils
from tornado.web import authenticated

from livefeedback_hub import core
from livefeedback_hub.core import UniqueActionThreadPoolExecutor
from livefeedback_hub.db import AutograderZip, GUID_REGEX, Result
from livefeedback_hub.server import JupyterService

submission_executor = UniqueActionThreadPoolExecutor(max_workers=16)


def process_notebook(service: JupyterService, autograder_zip: bytes, notebook: bytes, id: str, user_hash: str):
    tmp_dir = tempfile.mkdtemp()
    fd, path = tempfile.mkstemp(suffix=".ipynb", dir=tmp_dir)
    cwd = os.getcwd()
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(notebook)
            tmp.flush()

        os.chdir(tmp_dir)
        service.log.info(f"Launching otter-grader for {user_hash} and {id}")
        image = utils.OTTER_DOCKER_IMAGE_TAG + ":" + core.calcuate_zip_hash(autograder_zip)
        stdout = BytesIO()
        stderr = BytesIO()
        with stdio_proxy.redirect_stdout(stdout), stdio_proxy.redirect_stderr(stderr):
            user_result = containers.grade_assignments(path, image, debug=True, verbose=True)
        add_or_update_results(service, user_hash, id, user_result)
        service.log.info(f"Grading complete for {user_hash} and {id}")
    except Exception as e:
        service.log.exception(e)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp_dir)


def add_or_update_results(service, user_hash, assignment_id, user_result: pd.DataFrame):
    with service.session() as session:
        existing: Optional[Result] = session.query(Result).filter_by(assignment=assignment_id, user=user_hash).first()
        if existing:
            existing.data = user_result.to_csv(index=False)
        else:
            result = Result(user=user_hash, assignment=assignment_id, data=user_result.to_csv(index=False))
            session.add(result)


class FeedbackSubmissionHandler(HubOAuthenticated, core.CustomRequestHandler):

    @staticmethod
    def _create_pattern() -> re.Pattern:
        return re.compile(r"^#\s*LIVE:\s*(%s)\s*\r?\n?$" % GUID_REGEX, re.IGNORECASE)

    @staticmethod
    def _check_line(pattern, line) -> Optional[str]:
        match = pattern.match(line)
        if match:
            return match.group(1)
        return None

    def _get_autograding_zip(self, nb) -> Tuple[Optional[str], Optional[bytes]]:
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
        self.log.info("Handing live feedback submission")
        try:
            nb = json.loads(self.request.body.decode("utf-8"))
        except Exception:
            self.set_status(400)
            return
        id, autograder_zip = self._get_autograding_zip(nb)

        if autograder_zip is None:
            await self.finish()
            return

        user_hash = core.get_user_hash(self.get_current_user())

        def search(args):
            if args.kwargs["user_hash"] == user_hash and args.kwargs["id"] == id:
                return True
            else:
                return False
        submission_executor.find_and_remove(search)
        submission_executor.submit(process_notebook, service=self.service, autograder_zip=autograder_zip,
                                   notebook=self.request.body, id=id, user_hash=user_hash)
        await self.finish()
