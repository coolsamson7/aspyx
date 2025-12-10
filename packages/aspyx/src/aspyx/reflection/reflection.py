"""
This module provides a TypeDescriptor class that allows introspection of Python classes,
including their methods, decorators, and type hints. It supports caching for performance
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import inspect
from inspect import signature
import threading
from types import FunctionType

from typing import Callable, get_type_hints, Type, Dict, Any, get_origin, List, get_args, Annotated
from weakref import WeakKeyDictionary

from aspyx.validation import AbstractType, IntType
from aspyx.validation.validation import DoubleType, StringType, BoolType, ListType

import dataclasses
from dataclasses import MISSING, is_dataclass, fields
from typing import Any, Optional, Type
from pydantic import BaseModel, Field


try:
    from pydantic import Field
except ImportError:
    Field = None

def is_pydantic_model(cls: type) -> bool:
    return hasattr(cls, "__fields__")

def is_sqlalchemy_entity(cls: type) -> bool:
    # All mapped SQLAlchemy classes have a __mapper__ attribute
    return hasattr(cls, "__mapper__")

def is_dataclass(cls: type) -> bool:
    return hasattr(cls, "__dataclass_fields__")

def get_safe_type_hints(obj) -> Dict[str, Any]:
    """
    Safe wrapper around typing.get_type_hints that never raises.
    Returns either the resolved hints or a best-effort fallback (raw __annotations__).
    """
    try:
        # If obj is a function/method, use its globals so forward refs that are resolvable succeed
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            return get_type_hints(obj, globalns=obj.__globals__, localns={})
        # classes / other objects
        return get_type_hints(obj)
    except Exception:
        # fallback: return raw annotations (may contain strings / TypeVar names)
        anns = getattr(obj, "__annotations__", {})
        # make a safe copy; don't attempt to eval strings
        return dict(anns)

def make_setter(cls: Type, field_name: str) -> Callable[[Any, Any], None]:
    attr = getattr(cls, field_name, None)

    # If it's a property with a fset, call that directly
    if isinstance(attr, property) and attr.fset:
        fset = attr.fset
        def setter(instance: Any, value: Any):
            fset(instance, value)
        return setter

    # Default: setattr
    def setter(instance: Any, value: Any):
        setattr(instance, field_name, value)

    return setter

def get_method_class(method):
    """
    return the class of the specified method
    Args:
        method: the method

    Returns:
        the class of the specified method

    """
    if inspect.ismethod(method) or inspect.isfunction(method):
        qualname = method.__qualname__
        module = inspect.getmodule(method)
        if module:
            cls_name = qualname.split('.<locals>', 1)[0].rsplit('.', 1)[0]
            cls = getattr(module, cls_name, None)
            if inspect.isclass(cls):
                return cls

    return None

def is_list_type(typ) -> bool:
    """
    Returns True if the given type hint represents a list-like container.
    Handles typing.List, list, and parameterized generics like list[int].
    """
    if typ is None:
        return False

    origin = get_origin(typ) or typ
    return origin in (list, List)

def get_list_element_type(typ) -> Any:
    """
    Returns the element type if `typ` is a list-like type.
    Examples:
        list[int]        -> int
        List[str]        -> str
        list[Any]        -> Any
        list             -> Any
        not a list       -> None
    """
    origin = get_origin(typ)
    if origin in (list, List):
        args = get_args(typ)
        return args[0] if args else Any
    return None

class DecoratorDescriptor:
    """
    A DecoratorDescriptor covers the decorator - a callable - and the passed arguments
    """
    __slots__ = [
        "decorator",
        "args",
        "kwargs"
    ]

    def __init__(self, decorator: Callable, *args, **kwargs):
        self.decorator = decorator
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        parts = [*map(str, self.args)]
        parts += [f"{k}={v}" for k, v in self.kwargs.items()]

        return f"@{self.decorator.__name__}({', '.join(parts)})"

class Decorators:
    """
    Utility class that caches decorators ( Python does not have a feature for this )
    """
    @classmethod
    def add(cls, func_or_class, decorator: Callable, *args, **kwargs):
        """
        Remember the decorator
        Args:
            func_or_class: a function or class
            decorator: the decorator
            *args: positional arguments supplied to the decorator
            **kwargs: keyword arguments supplied to the decorator
        """
        current = func_or_class.__dict__.get('__decorators__')
        desc = DecoratorDescriptor(decorator, *args, **kwargs)
        if current is None:
            setattr(func_or_class, '__decorators__', [desc])
        else:
            if '__decorators__' not in func_or_class.__dict__:
                current = list(current)
                setattr(func_or_class, '__decorators__', current)
            current.append(desc)

    @classmethod
    def has_decorator(cls, func_or_class, callable: Callable) -> bool:
        """
        Return True, if the function or class is decorated with the decorator
        Args:
            func_or_class: a function or class
            callable: the decorator

        Returns:
            bool: the result
        """
        return any(decorator.decorator is callable for decorator in Decorators.get(func_or_class))

    @classmethod
    def get_decorator(cls, func_or_class, callable: Callable) -> DecoratorDescriptor:
        return next((decorator for decorator in Decorators.get_all(func_or_class) if decorator.decorator is callable), None)

    @classmethod
    def get_all(cls, func_or_class) -> list[DecoratorDescriptor]:
        return getattr(func_or_class, '__decorators__', [])

    @classmethod
    def get(cls, func_or_class) -> list[DecoratorDescriptor]:
        """
        return the list of decorators associated with the given function or class
        Args:
            func_or_class: the function or class

        Returns:
            list[DecoratorDescriptor]: the list
        """
        if inspect.ismethod(func_or_class):
            func_or_class = func_or_class.__func__  # unwrap bound method

        #return getattr(func_or_class, '__decorators__', []) #will return inherited as well
        return func_or_class.__dict__.get('__decorators__', [])


def attribute(*, primary_key: bool = False, type_property: Optional[Any] = None,
              default=MISSING, **extra):
    metadata = {"primary_key": primary_key, "type_property": type_property}
    metadata.update(extra)
    return dataclasses.field(default=default, metadata=metadata)

class PropertyExtractor(ABC):
    """Base interface for all property extraction strategies."""

    @abstractmethod
    def extract(self, cls: Type) -> Optional[Dict[str, "TypeDescriptor.PropertyDescriptor"]]:
        """
        Attempt to extract property descriptors for the given class.
        Return a dict if successful, or None if not applicable.
        """
        pass

class PydanticPropertyExtractor(PropertyExtractor):
    def extract(self, cls: Type):
        if not issubclass(cls, BaseModel):
            return None

        props = {}
        for name, field in cls.model_fields.items():
            typ = field.annotation
            default = field.default if field.default is not None else None

            # Pydantic metadata support
            extra = field.json_schema_extra or {}
            p = TypeDescriptor.PropertyDescriptor(cls, name, typ, default)
            p.primary_key = extra.get("primary_key", False)
            p.type_property = extra.get("type_property", None)
            props[name] = p

        return props
class DataclassPropertyExtractor(PropertyExtractor):
    def extract(self, cls: Type):
        if not is_dataclass(cls):
            return None

        type_hints = get_type_hints(cls)
        props = {}
        for f in fields(cls):
            meta = getattr(f, "metadata", {})
            typ = type_hints.get(f.name, f.type)  # <-- resolve "str" -> str

            default = None
            if f.default is not f.default_factory and f.default is not dataclasses.MISSING:
                default = f.default

            prop = TypeDescriptor.PropertyDescriptor(cls, f.name, typ, default)
            prop.primary_key = meta.get("primary_key", False)
            prop.type_property = meta.get("type_property", None)
            props[f.name] = prop

        return props

class DefaultPropertyExtractor(PropertyExtractor):
    def extract(self, cls: Type):
        try:
            hints = get_type_hints(cls)
        except Exception:
            hints = {}
        try:
            sig = inspect.signature(cls.__init__)
        except Exception:
            return None

        props = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            props[name] = TypeDescriptor.PropertyDescriptor(
                cls,
                name,
                hints.get(name, object),
                None if param.default is inspect.Parameter.empty else param.default
            )
        return props


class TypeDescriptor:
    """
    This class provides a way to introspect Python classes, their methods, decorators, and type hints.
    """

    # static

    _extractors: list[PropertyExtractor] = [
        PydanticPropertyExtractor(),
        DataclassPropertyExtractor(),
        DefaultPropertyExtractor()
    ]

    @classmethod
    def register_extractor(cls, extractor: PropertyExtractor):
        TypeDescriptor._extractors.insert(0, extractor)

    @classmethod
    def extract_properties(cls, type: Type) -> Optional[Dict[str, "TypeDescriptor.PropertyDescriptor"]]:
        for extractor in TypeDescriptor._extractors:
            properties = extractor.extract(type)
            if properties is not None:
                return properties

        raise Exception("no properties")

    # inner classes

    class ParameterDescriptor:
        def __init__(self, name: str, type: Type):
            self.name = name
            self.type = type

    class AnnotatedParam:
        """
        Describes a parameter with its type and annotation metadata.
        Used for analyzing Annotated[Type, metadata...] parameters.
        """
        __slots__ = ['name', 'type', 'metadata', 'has_default', 'default']

        def __init__(self, name: str, type: Type, metadata: tuple, has_default: bool, default: Any = inspect.Parameter.empty):
            self.name = name
            self.type = type  # The actual type (from Annotated[str, ...])
            self.metadata = metadata  # Tuple of metadata items
            self.has_default = has_default
            self.default = default

        def __str__(self):
            meta_str = f", metadata={self.metadata}" if self.metadata else ""
            default_str = f", default={self.default}" if self.has_default else ""
            return f"AnnotatedParam({self.name}: {getattr(self.type, '__name__', self.type)}{meta_str}{default_str})"

    class PropertyDescriptor:
        """
        Describes a class property (field) — can be read and written via reflection.
        """
        def __init__(self, cls: Type, name: str, typ: Optional[Type] = None, default: Any = None, type_property: Optional[AbstractType] = None):
            self.clazz = cls
            self.name = name
            self.type = typ or object
            self.default = default
            self.type_property = type_property
            if self.type_property is None:
                self.type_property = self._infer_type_property(self.type)

        def _infer_type_property(self, typ: Any):
            """
            Try to infer an AbstractType from Python type hints.
            This provides automatic mapping when no explicit type_property is set.
            """
            origin = get_origin(typ)

            if typ is int:
                return IntType()
            elif typ is float:
                return DoubleType()
            elif typ is str:
                return StringType()
            elif typ is bool:
                return BoolType()
            elif origin in (list, List):
                args = get_args(typ)
                elem_type = args[0] if args else Any
                element_spec = self._infer_type_property(elem_type)
                return ListType(element_spec)
            #TODO elif inspect.isclass(typ):
                # For complex/nested objects
            #    return ObjectType(typ)
            return None

        def get(self, instance):
            return getattr(instance, self.name, self.default)

        def set(self, instance, value):
            setattr(instance, self.name, value)

        def __str__(self):
            return f"Property({self.name}: {getattr(self.type, '__name__', self.type)})"

    class MethodDescriptor:
        """
        This class represents a method of a class, including its decorators, parameter types, and return type.
        """
        # constructor

        def __init__(self, cls, method: Callable):
            self.clazz = cls
            self.method = method
            self.decorators: list[DecoratorDescriptor] = Decorators.get(method)
            self.param_types : list[Type] = []
            self.params: list[TypeDescriptor.ParameterDescriptor] = []

            type_hints = get_safe_type_hints(method)
            sig = signature(method)

            for name, _ in sig.parameters.items():
                if name != 'self':
                    self.params.append(TypeDescriptor.ParameterDescriptor(name, type_hints.get(name)))
                    self.param_types.append(type_hints.get(name, object))

            self.return_type = type_hints.get('return', None)

        # public

        def get_name(self) -> str:
            """
            return the method name

            Returns:
                str: the method name
            """
            return self.method.__name__

        def get_doc(self, default = "") -> str:
            """
            return the method docstring

            Args:
                default: the default if no docstring is found

            Returns:
                str: the docstring
            """
            return self.method.__doc__ or default

        def is_async(self) -> bool:
            """
            return true if the method is asynchronous

            Returns:
                bool: async flag
            """
            return inspect.iscoroutinefunction(self.method)

        def get_decorators(self) -> list[DecoratorDescriptor]:
            return self.decorators

        def get_decorator(self, decorator: Callable) -> Optional[DecoratorDescriptor]:
            """
            return the DecoratorDescriptor - if any - associated with the passed Callable

            Args:
                decorator: the decorator

            Returns:
                Optional[DecoratorDescriptor]: the DecoratorDescriptor or None
            """
            for dec in self.decorators:
                if dec.decorator is decorator:
                    return dec

            return None

        def has_decorator(self, decorator: Callable) -> bool:
            """
            return True if the method is decorated with the decorator

            Args:
                decorator: the decorator callable

            Returns:
                bool: True if the method is decorated with the decorator
            """
            for dec in self.decorators:
                if dec.decorator is decorator:
                    return True

            return False

        def get_annotated_params(self) -> list['TypeDescriptor.AnnotatedParam']:
            """
            Extract annotated parameters with their metadata.
            Returns a list of AnnotatedParam objects containing parameter name, type, and metadata.

            Returns:
                list[AnnotatedParam]: List of annotated parameters
            """
            params = []
            sig = inspect.signature(self.method)

            # Use get_type_hints with include_extras=True to preserve Annotated metadata
            try:
                type_hints = get_type_hints(self.method, globalns=self.method.__globals__, include_extras=True)
            except Exception:
                # Fallback to annotations
                type_hints = getattr(self.method, '__annotations__', {})

            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue

                annotation = type_hints.get(param_name, param.annotation)
                if annotation == inspect.Parameter.empty:
                    annotation = object

                # Check if it's Annotated
                if get_origin(annotation) is Annotated:
                    actual_type, *metadata = get_args(annotation)
                    params.append(TypeDescriptor.AnnotatedParam(
                        name=param_name,
                        type=actual_type,
                        metadata=tuple(metadata),
                        has_default=param.default != inspect.Parameter.empty,
                        default=param.default
                    ))
                else:
                    # Regular parameter (no metadata)
                    params.append(TypeDescriptor.AnnotatedParam(
                        name=param_name,
                        type=annotation,
                        metadata=(),
                        has_default=param.default != inspect.Parameter.empty,
                        default=param.default
                    ))

            return params

        def __str__(self):
            return f"Method({self.method.__name__})"

    # class properties

    _cache = WeakKeyDictionary()
    _lock = threading.RLock()

    # class methods

    @classmethod
    def for_type(cls, clazz: Type) -> TypeDescriptor:
        """
        Returns a TypeDescriptor for the given class, using a cache to avoid redundant introspection.
        """
        descriptor = cls._cache.get(clazz)
        if descriptor is None:
            with cls._lock:
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
        self.properties: Dict[str, TypeDescriptor.PropertyDescriptor] = {}

        # check superclasses

        self.super_types = [TypeDescriptor.for_type(x) for x in cls.__bases__ if not self._is_framework_class(x)]

        for super_type in self.super_types:
            self.methods = self.methods | super_type.methods

        # methods

        for name, member in self._get_local_members(cls):
            method = TypeDescriptor.MethodDescriptor(cls, member)
            self.local_methods[name] = method
            self.methods[name] = method

        # properties

        self.properties = TypeDescriptor.extract_properties(cls)

        # constructor

        self.constructor = self._create_constructor()

    # internal

    def _is_framework_class(self, cls):
        if cls is object:
            return True

        module = getattr(cls, "__module__", "")

        return module.startswith("pydantic.") or module.startswith("sqlalchemy.")

    def _create_constructor(self) -> Callable[..., object]:
        cls = self.cls

        def make(**kwargs: Any) -> object:
            return cls(**kwargs)

        def new():
                return cls.__new__(cls)

        #if is_dataclass(cls):# or is_sqlalchemy_entity(cls):
        #    return new

        return make

    def _get_local_members(self, cls):
        #return [
        #    (name, value)
        #    for name, value in getmembers(cls, predicate=inspect.isfunction)
        #    if name in cls.__dict__
        #]

        return [
            (name, attr)
            for name, attr in cls.__dict__.items()
            if isinstance(attr, FunctionType)
        ]

    # public new

    def constructor_parameters(self):
        return self.local_methods["__init__"].params

    def is_immutable(self) -> bool:
        return False

    def has_default_constructor(self) -> bool:
        #if is_sqlalchemy_entity(self.cls):
        #    return True

        #if is_dataclass(self.cls):
        #    return True

        return False

    # public

    def get_properties(self) -> list[TypeDescriptor.PropertyDescriptor]:
        return list(self.properties.values())

    def get_property_names(self) -> list[str]:
        return [prop.name for prop in self.properties.values()]

    def get_property(self, name: str) -> Optional[TypeDescriptor.PropertyDescriptor]:
        return self.properties.get(name)

    def has_property(self, name: str) -> bool:
        return self.properties.get(name) is not None

    def get_decorator(self, decorator: Callable) -> Optional[DecoratorDescriptor]:
        """
        Returns the first decorator of the given type, or None if not found.
        """
        for dec in self.decorators:
            if dec.decorator is decorator:
                return dec

        return None

    def has_decorator(self, decorator: Callable) -> bool:
        """
        Checks if the class has a decorator of the given type."""
        for dec in self.decorators:
            if dec.decorator is decorator:
                return True

        return False

    def get_methods(self, local = False) ->  list[TypeDescriptor.MethodDescriptor]:
        """
        Returns a list of MethodDescriptor objects for the class.
        If local is True, only returns methods defined in the class itself, otherwise includes inherited methods.
        """
        if local:
            return list(self.local_methods.values())
        else:
            return list(self.methods.values())

    def get_method(self, name: str, local = False) -> Optional[TypeDescriptor.MethodDescriptor]:
        """
        Returns a MethodDescriptor for the method with the given name.
        If local is True, only searches for methods defined in the class itself, otherwise includes inherited methods.
        """
        if local:
            return self.local_methods.get(name, None)
        else:
            return self.methods.get(name, None)
