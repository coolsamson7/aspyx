from __future__ import annotations

import unittest

from aspyx.reflection import TypeDescriptor

class Base:
    def __init__(self):
        pass

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
    def test(self):
        derivedDescriptor = TypeDescriptor.for_type(Derived)

        self.assertIsNotNone(derivedDescriptor.get_method("derived").returnType, str)


        print(derivedDescriptor)


if __name__ == '__main__':
    unittest.main()