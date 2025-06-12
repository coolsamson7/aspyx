"""
This module provides a TypeDescriptor class that allows introspection of Python classes,
including their methods, decorators, and type hints. It supports caching for performance
"""
from __future__ import annotations

import inspect
from inspect import signature, getmembers
from typing import Callable, get_type_hints, Type, Dict, Optional
from weakref import WeakKeyDictionary


class DecoratorDescriptor:
    __slots__ = [
        "decorator",
        "args"
    ]

    def __init__(self, decorator, *args):
        self.decorator = decorator
        self.args = args

    def __str__(self):
        return f"@{self.decorator.__name__}({','.join(self.args)})"

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
        return getattr(func, '__decorators__', [])

class TypeDescriptor:
    # inner class

    class MethodDescriptor:
        def __init__(self, cls, method: Callable):
            self.clazz = cls
            self.method = method
            self.decorators: list[DecoratorDescriptor] = Decorators.get(method)
            self.param_types : list[Type] = []

            type_hints = get_type_hints(method)
            sig = signature(method)

            for name, _ in sig.parameters.items():
                if name != 'self':
                    self.param_types.append(type_hints.get(name, object))

            self.return_type = type_hints.get('return', None)

        def get_decorator(self, decorator) -> Optional[DecoratorDescriptor]:
            for dec in self.decorators:
                if dec.decorator is decorator:
                    return dec

            return None

        def has_decorator(self, decorator) -> bool:
            for dec in self.decorators:
                if dec.decorator is decorator:
                    return True

            return False

        def __str__(self):
            return f"Method({self.method.__name__})"

    # class properties

    _cache = WeakKeyDictionary()

    # class methods

    @classmethod
    def for_type(cls, clazz: Type) -> TypeDescriptor:
        descriptor = cls._cache.get(clazz)
        if descriptor is None:
            descriptor = TypeDescriptor(clazz)
            cls._cache[clazz] = descriptor

        return descriptor

    # constructor

    def __init__(self, cls):
        self.cls = cls
        self.decorators = Decorators.get(cls)
        self.methods: Dict[str, TypeDescriptor.MethodDescriptor] = {}
        self.local_methods: Dict[str, TypeDescriptor.MethodDescriptor] = {}

        # check superclasses

        self.super_types = [TypeDescriptor.for_type(x) for x in cls.__bases__ if not x is object]

        for super_type in self.super_types:
            self.methods = self.methods | super_type.methods

        # methods

        for name, member in self._get_local_members(cls):
            method = TypeDescriptor.MethodDescriptor(cls, member)
            self.local_methods[name] = method
            self.methods[name] = method

    # internal

    def _get_local_members(self, cls):
        return [
            (name, value)
            for name, value in getmembers(cls, predicate=inspect.isfunction)
            if name in cls.__dict__
        ]

    # public

    def get_decorator(self, decorator) -> Optional[DecoratorDescriptor]:
        for dec in self.decorators:
            if dec.decorator is decorator:
                return dec

        return None

    def has_decorator(self, decorator) -> bool:
        for dec in self.decorators:
            if dec.decorator is decorator:
                return True

        return False

    def get_methods(self, local = False) ->  list[TypeDescriptor.MethodDescriptor]:
        if local:
            return list(self.local_methods.values())
        else:
            return list(self.methods.values())

    def get_method(self, name: str, local = False) -> Optional[TypeDescriptor.MethodDescriptor]:
        if local:
            return self.local_methods.get(name, None)
        else:
            return self.methods.get(name, None)
