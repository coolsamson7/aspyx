"""
Test cases for the TypeDescriptor and Decorators functionality in aspyx.reflection.
"""
from __future__ import annotations

import unittest

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

    def no_type_hints(self, message):
        pass

class Derived(Base):
    @classmethod
    def foo(cls):
        pass

    def derived(self, message: str) -> str:
        pass

class TestReflection(unittest.TestCase):
    def test_decorators(self):
        base_descriptor = TypeDescriptor.for_type(Base)

        self.assertTrue(base_descriptor.has_decorator(transactional))
        self.assertTrue( base_descriptor.get_method("base").has_decorator(transactional))

    def test_methods(self):
        derived_descriptor = TypeDescriptor.for_type(Derived)

        self.assertIsNotNone(derived_descriptor.get_method("derived").return_type, str)


if __name__ == '__main__':
    unittest.main()
