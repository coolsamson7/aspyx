from __future__ import annotations

import inspect
from inspect import signature, getmembers
from typing import Callable, get_type_hints, Type, Dict


class DecoratorDescriptor:
    def __init__(self, decorator, *args):
        self.decorator = decorator
        self.args = args


    def __str__(self):
        return f"@({self.decorator.__name__})" # args?

class Decorators:
    @classmethod
    def add(cls, func, decorator, *args):
        decorators = getattr(func, '__decorators__', None)
        if decorators is None:
            setattr(func, '__decorators__', [DecoratorDescriptor(decorator, *args)])
        else:
            decorators.append(DecoratorDescriptor(decorator, *args))

    @classmethod
    def get(cls, func) -> list[DecoratorDescriptor]:
        return  getattr(func, '__decorators__', [])

class TypeDescriptor:
    # inner class

    class MethodDescriptor:  # TODO static methods
        def __init__(self, cls, method: Callable):
            self.clazz = cls
            self.method = method
            self.decorators: list[DecoratorDescriptor] = Decorators.get(method)
            self.paramTypes = []

            type_hints = get_type_hints(method)
            sig = signature(method)

            for name, param in sig.parameters.items():
                if name != 'self':
                    self.paramTypes.append(type_hints.get(name, object))

            self.returnType = type_hints.get('return', None)

        def getDecorator(self, decorator):
            for dec in self.decorators:
                if dec.decorator == decorator:
                    return dec

            return None

        def hasDecorator(self, decorator):
            for dec in self.decorators:
                if dec.decorator == decorator:
                    return True

            return False

        def __str__(self):
            return f"Method({self.method.__name__})"

    # class methods

    @classmethod
    def forType(cls, clazz: Type) -> TypeDescriptor:
        descriptor = getattr(clazz, '_descriptor', None)

        if descriptor is None:
            descriptor = TypeDescriptor(clazz)
            clazz._descriptor = descriptor

        return descriptor

    # constructor

    def __init__(self, cls):
        self.cls = cls
        self.decorators = Decorators.get(cls)
        self.methods: Dict[str, TypeDescriptor.MethodDescriptor] = dict()
        for name, member in getmembers(cls, predicate=inspect.isfunction):
            self.methods[name] = TypeDescriptor.MethodDescriptor(cls, member)

    def get_local_members(cls):  # TODO
        return [
            (name, value)
            for name, value in inspect.getmembers(cls)
            if name in cls.__dict__
        ]

    # public

    def hasDecorator(self, decorator):
        for dec in self.decorators:
            if dec.decorator == decorator:
                return True

        return False

    def get(self, name) -> MethodDescriptor:
        return self.methods[name]
