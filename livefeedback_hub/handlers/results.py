import io
from typing import Optional

import pandas as pd
from jupyterhub.services.auth import HubOAuthenticated
from tornado import web
from tornado.web import authenticated

import livefeedback_hub.helper.misc
from livefeedback_hub import core
from livefeedback_hub.db import AutograderZip, Result


class FeedbackResultsHandler(HubOAuthenticated, core.CoreRequestHandler):

    @authenticated
    async def get(self, live_id):
        self.log.info("Handing live feedback results request")

        user_hash = livefeedback_hub.helper.misc.get_user_hash(self.get_current_user())

        with self.service.session() as session:
            entry: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not entry:
                raise web.HTTPError(403)
            else:
                await self.render("results.html", task=entry, base=self.service.prefix)


class FeedbackResultsApiHandler(HubOAuthenticated, core.CoreRequestHandler):

    @authenticated
    async def get(self, live_id):
        self.log.info("Handing live feedback results api request")

        user_hash = livefeedback_hub.helper.misc.get_user_hash(self.get_current_user())

        with self.service.session() as session:
            entry: Optional[AutograderZip] = session.query(AutograderZip).filter_by(id=live_id, owner=user_hash).first()
            if not entry:
                raise web.HTTPError(403)
            else:
                results = session.query(Result).filter_by(assignment=live_id)
                dataframes = [pd.read_table(io.StringIO(result.data), sep=",") for result in results]
                if len(dataframes) > 0:
                    data = pd.concat(dataframes)
                    data = data.drop(columns=["file"])
                    data = data.reset_index()
                    data = data.apply(pd.value_counts)
                    self.set_header("Content-Type", "application/json")
                    self.write(data.to_json())
                else:
                    self.set_status(204)
                await self.finish()
