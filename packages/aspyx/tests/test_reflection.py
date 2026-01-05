"""
Test cases for the TypeDescriptor and Decorators functionality in aspyx.reflection.
"""
import unittest
from dataclasses import dataclass, fields

from pydantic import BaseModel

from aspyx.reflection import TypeDescriptor, Decorators


def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func #

    return decorator

def order(prio=0):
    def decorator(cls):
        Decorators.add(cls, order, prio=prio)
        return cls
    return decorator


@transactional()
@order(1)
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

class Normal:
    def __init__(self, id: str):
        self.id = id

@dataclass
class Dataclass:
    id: str

class Pydantic(BaseModel):
    id: str

class TestReflection(unittest.TestCase):
    def test_properties(self):
        #normal_descriptor = TypeDescriptor.for_type(Normal)
        dataclass_descriptor = TypeDescriptor.for_type(Dataclass)
        #pydantic_descriptor = TypeDescriptor.for_type(Pydantic)

        fs = fields(Dataclass)

        print(1)

    def test_decorator_kwargs(self):
        base_descriptor = TypeDescriptor.for_type(Base)

        decorator = base_descriptor.get_decorator(order)
        print(decorator.kwargs)

    def test_decorators(self):
        base_descriptor = TypeDescriptor.for_type(Base)

        self.assertTrue(base_descriptor.has_decorator(transactional))
        self.assertTrue( base_descriptor.get_method("base").has_decorator(transactional))

    def test_methods(self):
        derived_descriptor = TypeDescriptor.for_type(Derived)

        self.assertIsNotNone(derived_descriptor.get_method("derived").return_type, str)


if __name__ == '__main__':
    unittest.main()
