from concurrent.futures.thread import ThreadPoolExecutor
import functools
import hashlib
from livefeedback_hub.set import OrderedSet
import logging
from queue import Queue
from typing import Any, Awaitable, Callable, Optional

from otter.grade import utils
from tornado.web import HTTPError, RequestHandler, authenticated

from livefeedback_hub.db import AutograderZip
from livefeedback_hub.server import JupyterService

from python_on_whales import docker
from python_on_whales.exceptions import NoSuchImage


class SetQueue(Queue):

    def _init(self, maxsize):
        self.maxsize = maxsize
        self.queue = OrderedSet()

    def _put(self, item):
        self.queue.add(item)

    def _get(self):
        return self.queue.pop()

    def find_and_remove(self, fn):
        with self.mutex:
            for item in self.queue:
                if fn(item):
                    self.queue.remove(item)


class UniqueActionThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers=None, thread_name_prefix='', initializer=None, initargs=()):
        super().__init__(max_workers, thread_name_prefix, initializer, initargs)
        self._work_queue = SetQueue()

    def find_and_remove(self, fn):
        self._work_queue.find_and_remove(fn)


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


def calcuate_zip_hash(data: bytes):
    zip_hash = ""
    m = hashlib.md5()
    m.update(data)
    zip_hash = m.hexdigest()
    return zip_hash


def delete_docker_image(service: JupyterService, task: AutograderZip):
    """
    Trys to delete the docker image belonging to the provided task
    :param service: a service instance used for logging
    :param task: the task to delete
    """
    m = hashlib.md5()
    m.update(task.data)
    image = f"{utils.OTTER_DOCKER_IMAGE_TAG}:{m.hexdigest()}"
    service.log.info(f"Deleting docker image {image}")
    try:
        docker.image.remove(image, force=True)
    except NoSuchImage as e:
        service.log.warning(f"Image not found: {e}")


def timeout_injector(method_to_decorate):
    """
    Inject a timeout parameter into the arguments of the passed call.
    :param method_to_decorate: The method to decorate
    :return: a wrapper containing the real method
    """

    def wrapper(self, *args, **kwargs):
        kwargs['timeout'] = 600
        return method_to_decorate(self, *args, **kwargs)

    return wrapper


class CustomRequestHandler(RequestHandler):
    """
    To allow some (fancy) custom error pages we overwrite the (Default) RequestHandler's method write_error
    """

    def initialize(self, service: JupyterService):
        self.service = service
        self.log: logging.Logger = service.log

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        self.set_status(status_code)
        if status_code == 403:
            msg = "Zugriff verweigert!"
        else:
            msg = "Interner Serverfehler!"
        self.render("error.html", base=self.service.prefix, msg=msg)
