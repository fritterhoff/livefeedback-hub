from concurrent.futures.thread import ThreadPoolExecutor

from livefeedback_hub.helper.set_queue import SetQueue


class UniqueActionThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers=None, thread_name_prefix='', initializer=None, initargs=()):
        super().__init__(max_workers, thread_name_prefix, initializer, initargs)
        self._work_queue = SetQueue()

    def find_and_remove(self, fn):
        self._work_queue.find_and_remove(fn)

    def find(self, fn):
        self._work_queue.find(fn)