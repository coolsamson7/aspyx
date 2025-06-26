"""
Configuration handling module.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar

from aspyx.di import injectable, Environment, LifecycleCallable, Lifecycle
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
        Retrieve a configuration value by path and type, with optional coercion.

        Args:
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

# decorator

def inject_value(key: str, default=None):
    """
    Decorator to inject a configuration value into a method.

    Args:
        key (str): The configuration key to inject.
        default: The default value to use if the key is not found.

    """
    def decorator(func):
        Decorators.add(func, inject_value, key, default)

        return func

    return decorator

@injectable()
@order(9)
class ConfigurationLifecycleCallable(LifecycleCallable):
    def __init__(self,  manager: ConfigurationManager):
        super().__init__(inject_value, Lifecycle.ON_INJECT)

        self.manager = manager

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [self.manager.get(decorator.args[0], method.param_types[0], decorator.args[1])]
