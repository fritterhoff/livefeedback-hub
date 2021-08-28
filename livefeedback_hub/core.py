import functools
import hashlib
from typing import Optional, Awaitable, Callable

from tornado.web import authenticated, HTTPError, RequestHandler


def teacher_only(method: Callable[..., Optional[Awaitable[None]]]) -> Callable[..., Optional[Awaitable[None]]]:
    @functools.wraps(method)
    def wrapper(self: RequestHandler, *args, **kwargs) -> Optional[Awaitable[None]]:
        if 'teacher' not in self.current_user['groups']:
            raise HTTPError(403)
        return method(self, *args, **kwargs)

    return authenticated(wrapper)


def get_user_hash(user_model) -> str:
    m = hashlib.sha256()
    name = user_model["name"].encode("utf-8")
    m.update(name)
    return m.hexdigest()
