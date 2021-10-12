from queue import Queue

from livefeedback_hub.helper.ordered_set import OrderedSet


class SetQueue(Queue):

    def _init(self, maxsize):
        self.maxsize = maxsize
        self.queue = OrderedSet()

    def _put(self, item):
        self.queue.add(item)

    def _get(self):
        return self.queue.pop()

    def find(self, fn):
        with self.mutex:
            for item in self.queue:
                if fn(item):
                    return item
            return None

    def find_and_remove(self, fn):
        with self.mutex:
            for item in self.queue:
                if fn(item):
                    self.queue.remove(item)
