"""
Configuration handling module.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import Optional, Type, TypeVar
from dotenv import load_dotenv

from aspyx.di import injectable, Environment, CallableProcessor, LifecycleCallable, Lifecycle
from aspyx.di.di import order, inject
from aspyx.reflection import Decorators, DecoratorDescriptor, TypeDescriptor

T = TypeVar("T")

class ConfigurationException(Exception):
    """
    Exception raised for errors in the configuration logic.
    """

@injectable()
class ConfigurationManager:
    """
    ConfigurationManager is responsible for managing different configuration sources by merging the different values
    and offering a uniform api.
    """

    __slots__ = ["sources", "_data", "coercions"]

    # constructor

    def __init__(self):
        self.sources = []
        self._data = {}
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
        self.load_source(source)

    # public

    def load_source(self,  source: ConfigurationSource):
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

        self._data = merge_dicts(self._data, source.load())

    def get(self, path: str, type: Type[T], default : Optional[T]=None) -> T:
        """
        Get a configuration value by path and type, with optional coercion.
        Arguments:
            path (str): The path to the configuration value, e.g. "database.host".
            type (Type[T]): The expected type.
            default (Optional[T]): The default value to return if the path is not found.
        Returns:
            T: The configuration value coerced to the specified type, or the default value if not found.
        """
        def resolve_value(path: str, default=None) -> T:
            keys = path.split(".")
            current = self._data
            for key in keys:
                if not isinstance(current, dict) or key not in current:
                    return default
                current = current[key]

            return current

        v = resolve_value(path, default)

        if isinstance(v, type):
            return v

        if type in self.coercions:
            try:
                return self.coercions[type](v)
            except Exception as e:
                raise ConfigurationException(f"error during coercion to {type}") from e
        else:
            raise ConfigurationException(f"unknown coercion to {type}")


class ConfigurationSource(ABC):
    """
    A configuration source is a provider of configuration data.
    """

    __slots__ = []

    def __init__(self):
        pass

    @inject()
    def set_manager(self, manager: ConfigurationManager):
        manager._register(self)

    @abstractmethod
    def load(self) -> dict:
        """
        return the configuration values of this source as a dictionary.
        """

@injectable()
class EnvConfigurationSource(ConfigurationSource):
    """
    EnvConfigurationSource loads all environment variables.
    """

    __slots__ = []

    # constructor

    def __init__(self):
        super().__init__()

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
    """
    Decorator to inject a configuration value into a method.

    Arguments:
        key (str): The configuration key to inject.
        default: The default value to use if the key is not found.

    """
    def decorator(func):
        Decorators.add(func, value, key, default)

        return func

    return decorator

@injectable()
@order(9)
class ConfigurationLifecycleCallable(LifecycleCallable):
    def __init__(self, processor: CallableProcessor,  manager: ConfigurationManager):
        super().__init__(value, processor, Lifecycle.ON_INIT)

        self.manager = manager

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [self.manager.get(decorator.args[0], method.param_types[0], decorator.args[1])]
