"""
Test cases for the TypeDescriptor and Decorators functionality in aspyx.reflection.
"""
from __future__ import annotations

import unittest

from aspyx.reflection import Decorators

def decorate_1(arg=""):
    def decorator(cls_or_func):
        Decorators.add(cls_or_func, decorate_1, arg)

        return cls_or_func #

    return decorator

def decorate_2(arg=""):
    def decorator(cls_or_func):
        Decorators.add(cls_or_func, decorate_2, arg)

        return cls_or_func #

    return decorator

@decorate_1("base")
class Base:
    def __init__(self):
        pass

    @decorate_1()
    def base(self, message: str) -> str:
        pass

    def no_type_hints(self, message):
        pass

@decorate_1("derived")
@decorate_2("derived")
class Derived(Base):
    @classmethod
    def foo(cls):
        pass

    def derived(self, message: str) -> str:
        pass

class OtherDerived(Base):
    pass

class TestReflection(unittest.TestCase):
    def test_decorators(self):
        base_decorators = Decorators.get(Base)
        derived_decorators = Decorators.get(Derived)
        other_derived_decorators = Decorators.get(OtherDerived)

        print()


if __name__ == '__main__':
    unittest.main()
