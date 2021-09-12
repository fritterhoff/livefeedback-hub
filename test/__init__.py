import unittest


class TestCase(unittest.TestCase):
    """
    Base class for unit and integration tests
    """

    def setUp(self):
        print("\n" + ("-" * 70) + f"\nRunning {self.id()}\n" + ("-" * 70))
        return super().setUp()
