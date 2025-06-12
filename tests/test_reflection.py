from __future__ import annotations

import unittest

from aspyx.di import injectable
from aspyx.reflection import TypeDescriptor, Decorators


def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func #

    return decorator

@transactional()
class Base:
    def __init__(self):
        pass

    @transactional()
    def base(self, message: str) -> str:
        pass

    def noTypeHints(self, message):
        pass

class Derived(Base):
    def __init__(self):
        super().__init__()

    @classmethod
    def foo(cls):
        pass

    def derived(self, message: str) -> str:
        pass

class TestReflection(unittest.TestCase):
    def test_decorators(self):
        baseDescriptor = TypeDescriptor.for_type(Base)

        self.assertTrue(baseDescriptor.has_decorator(transactional))
        self.assertTrue( baseDescriptor.get_method("base").has_decorator(transactional))

    def test_methods(self):
        derivedDescriptor = TypeDescriptor.for_type(Derived)

        self.assertIsNotNone(derivedDescriptor.get_method("derived").return_type, str)


        print(derivedDescriptor)


if __name__ == '__main__':
    unittest.main()