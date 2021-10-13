import os
import functools
import hashlib
from typing import Awaitable, Callable, Optional

from otter.grade import utils
from python_on_whales import docker
from python_on_whales.exceptions import NoSuchImage
from tornado.web import HTTPError, RequestHandler, authenticated

from livefeedback_hub.db import AutograderZip
from livefeedback_hub.server import JupyterService


def teachers():
    with open(os.getenv("FEEDBACK_TEACHERS"), 'r') as f:
        return [line.strip() for line in f.readlines()]


def teacher_only(method: Callable[..., Optional[Awaitable[None]]]) -> Callable[..., Optional[Awaitable[None]]]:
    @functools.wraps(method)
    def wrapper(self: RequestHandler, *args, **kwargs) -> Optional[Awaitable[None]]:
        if self.current_user['name'] not in teachers():
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
