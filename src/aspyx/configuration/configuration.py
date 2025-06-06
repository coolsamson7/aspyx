from __future__ import annotations

import os
from typing import Type, TypeVar
from dotenv import load_dotenv

from aspyx.di import component, Environment, CallableProcessor, Callable, Lifecycle
from aspyx.reflection import Decorators, DecoratorDescriptor, TypeDescriptor


T = TypeVar("T")

@component()
class ConfigurationManager:
    # constructor

    def __init__(self):
        self.sources = []
        self._data = dict()
        self.coercions = {
            int: int,
            float: float,
            bool: lambda v: str(v).lower() in ("1", "true", "yes", "on"),
            str: str,
            # Add more types as needed
        }

    # internal

    def _register(self, source: ConfigurationSource):
        self.sources.append(source)
        pass

    # public

    def load(self):
        def merge_dicts(a: dict, b: dict) -> dict:
            result = a.copy()
            for key, b_val in b.items():
                if key in result:
                    a_val = result[key]
                    if isinstance(a_val, dict) and isinstance(b_val, dict):
                        result[key] = merge_dicts(a_val, b_val)  # Recurse
                    else:
                        result[key] = b_val  # Overwrite
                else:
                    result[key] = b_val
            return result

        for source in self.sources:
            self._data = merge_dicts(self._data, source.load())

    def get(self, path: str, type: Type[T], default=None) -> T:
        def value(path: str, default=None) -> T:
            keys = path.split(".")
            current = self._data
            for key in keys:
                if not isinstance(current, dict) or key not in current:
                    return default
                current = current[key]

            return current
        
        v = value(path, default)

        if isinstance(v, type):
            return v
            
        if type in self.coercions:
            try:
                return self.coercions[type](v)
            except Exception:
                raise Exception(f"unknown coercion to {type}")


class ConfigurationSource:
    def __init__(self, manager: ConfigurationManager):
        manager._register(self)
        pass

    def load(self) -> dict:
        pass

@component()
class EnvConfigurationSource(ConfigurationSource):
    # constructor

    def __init__(self, manager: ConfigurationManager):
        super().__init__(manager)

        load_dotenv()

    # implement

    def load(self) -> dict:
        def merge_dicts(a, b):
            """Recursively merges b into a"""
            for key, value in b.items():
                if isinstance(value, dict) and key in a and isinstance(a[key], dict):
                    merge_dicts(a[key], value)
                else:
                    a[key] = value
            return a

        def explode_key(key, value):
            """Explodes keys with '.' or '/' into nested dictionaries"""
            parts = key.replace('/', '.').split('.')
            d = current = {}
            for part in parts[:-1]:
                current[part] = {}
                current = current[part]
            current[parts[-1]] = value
            return d

        exploded = {}

        for key, value in os.environ.items():
            if '.' in key or '/' in key:
                partial = explode_key(key, value)
                merge_dicts(exploded, partial)
            else:
                exploded[key] = value

        return exploded

# decorator

def value(key: str, default=None):
    def decorator(func):
        Decorators.add(func, value, key, default)

        return func

    return decorator

@component()
class ConfigurationCallable(Callable):
    def __init__(self, processor: CallableProcessor,  manager: ConfigurationManager):
        super().__init__(value, processor, Lifecycle.ON_CREATE)

        self.manager = manager

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [self.manager.get(decorator.args[0], method.paramTypes[0])]