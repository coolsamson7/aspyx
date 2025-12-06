"""
Configuration handling module.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar, Any, Annotated

from aspyx.di.di import injectable, Environment, LifecycleCallable, Lifecycle, AnnotationResolver, AnnotationResolvers
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

    def has(self, path: str) -> bool:
        """
        Check if a configuration path exists (either as a value or an inner node).

        Args:
            path (str): The path to check, e.g. "database" or "database.host".

        Returns:
            bool: True if the path exists (as a value or dict node), False otherwise.
        """
        keys = path.split(".")
        current = self._data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        return True

    def get_raw(self, path: str, default=None):
        """
        Retrieve a raw configuration value without type coercion.

        Args:
            path (str): The path to the configuration value, e.g. "database.host".
            default: The default value to return if the path is not found.

        Returns:
            The raw configuration value, or the default value if not found.
        """
        keys = path.split(".")
        current = self._data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

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

# Annotation-based configuration injection

class ConfigValue:
    """
    Annotation metadata for configuration value injection.
    Usage: host: Annotated[str, config("server.host")]
    """
    __slots__ = ['key', 'default']

    def __init__(self, key: str, default: Any = None):
        self.key = key
        self.default = default

    def __str__(self):
        return f"config('{self.key}')"

    def __repr__(self):
        return f"ConfigValue(key='{self.key}', default={self.default})"

def config(typ: Type[T], key: str, default: T = None) -> T:
    """
    Shorthand for configuration value injection with type annotation.

    Usage:
        from aspyx.di.configuration import config

        @injectable()
        class MyService:
            def __init__(
                self,
                host: config(str, "server.host", "localhost"),
                port: config(int, "server.port", 8080),
                enabled: config(bool, "feature.enabled", False)
            ):
                self.host = host
                self.port = port
                self.enabled = enabled

    This is equivalent to:
        host: Annotated[str, ConfigValue("server.host", "localhost")]

    But much more concise!

    Args:
        typ: The type of the configuration value (str, int, bool, float, etc.)
        key: The configuration key path (e.g., "database.host")
        default: The default value if the key is not found

    Returns:
        An Annotated type that triggers configuration injection
    """
    return Annotated[typ, ConfigValue(key, default)]

class ConfigAnnotationResolver(AnnotationResolver):
    """Resolver for @config() annotations"""

    def __init__(self):
        super().__init__(ConfigValue)

    def dependencies(self) -> list[Type]:
        return [ConfigurationManager]

    def resolve(self, annotation_value: ConfigValue, param_type: Type, environment: Environment, *deps) -> Any:
        config_manager = deps[0]  # ConfigurationManager
        return config_manager.get(annotation_value.key, param_type, annotation_value.default)

# Register the resolver statically (not as a bean, just as a resolver)
AnnotationResolvers.register(ConfigAnnotationResolver())
