"""
This module provides aspect-oriented programming (AOP) capabilities for Python applications.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import inspect
import re
import threading
import types
from dataclasses import dataclass
from enum import auto, Enum
from typing import Optional, Dict, Type, Callable

from aspyx.reflection import Decorators, TypeDescriptor
from aspyx.di import injectable, order, Providers, ClassInstanceProvider, Environment, PostProcessor

class AOPException(Exception):
    """
    Exception raised for errors in the aop logic.
    """

class AspectType(Enum):
    """
    AspectType defines the types of aspect-oriented advice that can be applied to methods.

    The available types are:

    - BEFORE: Advice to be executed before the method invocation.
    - AROUND: Advice that intercepts the method invocation.
    - AFTER: Advice to be executed after the method invocation, regardless of its outcome.
    - ERROR: Advice to be executed if the method invocation raises an exception.

    These types are used to categorize and apply aspect logic at different points in a method's execution lifecycle.
    """
    BEFORE = auto()
    AROUND = auto()
    AFTER = auto()
    ERROR = auto()

class AspectTarget(ABC):
    """
    AspectTarget defines the target for an aspect. It can be used to specify the class, method, and conditions under which the aspect should be applied.
    It supports matching by class type, method name, patterns, decorators, and more.
    """

    # properties

    __slots__ = [
        "_function",
        "_type",
        "_async",
        "_clazz",
        "_instance",
        "names",
        "patterns",
        "types",
        "other",
        "decorators",
    ]

    # constructor

    def __init__(self):
        self._clazz = None
        self._instance = None
        self._async = False
        self._function = None
        self._type = None

        self.patterns = []
        self.names = []
        self.types = []
        self.decorators = []

        self.other : list[AspectTarget] = []

    # abstract

    def _matches(self, clazz : Type, func):
        if not self._matches_self(clazz, func):
            for target in self.other:
                if target._matches(clazz, func):
                    return True

            return False

        return True

    @abstractmethod
    def _matches_self(self, clazz: Type, func):
        pass

    # protected

    def _add(self, target: AspectTarget):
        self.other.append(target)
        return self

     # fluent

    def function(self, func) -> AspectTarget:
        self._function = func
        return self

    def type(self, type: AspectType):
        self._type = type

        return self

    def that_are_async(self) -> AspectTarget:
        """
        matches methods that are async

        Returns:
            AspectTarget: self
        """
        self._async = True
        return self

    def of_type(self, type: Type) -> AspectTarget:
        """
        matches methods belonging to a class or classes that are subclasses of the specified type

        Args:
            type (Type): the type to match against

        Returns:
            AspectTarget: self
        """
        self.types.append(type)
        return self

    def decorated_with(self, decorator: Callable) -> AspectTarget:
        """
        matches methods or classes that are decorated with the specified decorator

        Args:
            decorator (Callable): the decorator callable

        Returns:
            AspectTarget: self
        """
        self.decorators.append(decorator)
        return self

    def matches(self, pattern: str) -> AspectTarget:
        """
        Matches the target against a pattern.

        Args:
            pattern (str): the pattern

        Returns:
            AspectTarget: self
        """
        self.patterns.append(re.compile(pattern))
        return self

    def named(self, name: str) -> AspectTarget:
        """
        Matches the target against a name.

        Args:
            name (str): the name

        Returns:
            AspectTarget: self
        """
        self.names.append(name)
        return self

class ClassAspectTarget(AspectTarget):
    """
    An AspectTarget matching classes
    """
    # properties

    __slots__ = [
    ]

    # public

    def _matches_self(self, clazz : Type, func):
        class_descriptor = TypeDescriptor.for_type(clazz)
        #descriptor = TypeDescriptor.for_type(func)
        # type

        if len(self.types) > 0:
            if next((type for type in self.types if issubclass(clazz, type)), None) is None:
                return False

        # decorators

        if len(self.decorators) > 0:
            if next((decorator for decorator in self.decorators if class_descriptor.has_decorator(decorator)), None) is None:
                return False

        # names

        if len(self.names) > 0:
            if next((name for name in self.names if name == clazz.__name__), None) is None:
                return False

        # patterns

        if len(self.patterns) > 0:
            if next((pattern for pattern in self.patterns if re.fullmatch(pattern, clazz.__name__) is not None), None) is None:
                return False

        return True

    # fluent

class MethodAspectTarget(AspectTarget):
    """
       An AspectTarget matching methods
       """

    # properties

    __slots__ = [ ]

    # public

    def _matches_self(self, clazz : Type, func):
        descriptor = TypeDescriptor.for_type(clazz)

        method_descriptor = descriptor.get_method(func.__name__)

        # async

        if self._async is not method_descriptor.is_async():
            return False

        # type

        if len(self.types) > 0:
            if next((type for type in self.types if issubclass(clazz, type)), None) is None:
                return False

        # decorators

        if len(self.decorators) > 0:
            if next((decorator for decorator in self.decorators if method_descriptor.has_decorator(decorator)), None) is None:
                return False

        # names

        if len(self.names) > 0:
            if next((name for name in self.names if name == func.__name__), None) is None:
                return False

        # patterns

        if len(self.patterns) > 0:
            if next((pattern for pattern in self.patterns if re.fullmatch(pattern, func.__name__) is not None), None) is None:
                return False

        # yipee

        return True

def methods() -> AspectTarget:
    """
    Create a new AspectTarget instance to define method aspect targets.

    Returns:
         AspectTarget: the method target
    """
    return MethodAspectTarget()

def classes() -> AspectTarget:
    """
    Create a new AspectTarget instance to define class aspect targets.

    Returns:
        AspectTarget: the method target
    """
    return ClassAspectTarget()


class Aspect:
    __slots__ = [
        "next",
    ]

    # constructor

    def __init__(self, next: 'Aspect'):
        self.next = next

    # public

    def call(self, invocation: 'Invocation'):
        pass

    async def call_async(self, invocation: 'Invocation'):
        pass

class FunctionAspect(Aspect):
    __slots__ = [
        "instance",
        "func",
        "order",
    ]

    def __init__(self, instance, func, next_aspect: Optional['Aspect']):
        super().__init__(next_aspect)

        self.instance = instance
        self.func = func

        self.order = next((decorator.args[0] for decorator in Decorators.get(func) if decorator.decorator is order), 0)

    def call(self, invocation: 'Invocation'):
        invocation.current_aspect = self

        return self.func(self.instance, invocation)

    async def call_async(self, invocation: 'Invocation'):
        invocation.current_aspect = self

        return await self.func(self.instance, invocation)

class MethodAspect(FunctionAspect):
    __slots__ = []

    def __init__(self, instance, func):
        super().__init__(instance, func, None)

    def call(self, invocation: 'Invocation'):
        invocation.current_aspect = self

        return self.func(*invocation.args, **invocation.kwargs)

    async def call_async(self, invocation: 'Invocation'):
        invocation.current_aspect = self

        return await self.func(*invocation.args, **invocation.kwargs)

@dataclass
class Aspects:
    before: list[Aspect]
    around: list[Aspect]
    error: list[Aspect]
    after: list[Aspect]

class Invocation:
    """
    Invocation stores the relevant data of a single method invocation.
    It holds the arguments, keyword arguments, result, error, and the aspects that define the aspect behavior.
    """
    # properties

    __slots__ = [
        "func",
        "args",
        "kwargs",
        "result",
        "exception",
        "aspects",
        "current_aspect",
    ]

    # constructor

    def __init__(self, func, aspects: Aspects):
        self.func = func
        self.args : list[object] = []
        self.kwargs = None
        self.result = None
        self.exception = None
        self.aspects = aspects
        self.current_aspect = None

    def call(self, *args, **kwargs):
        # remember args

        self.args = args
        self.kwargs = kwargs

        # run all before

        for aspect in self.aspects.before:
            aspect.call(self)

        # run around's with the method being the last aspect!

        try:
            self.result = self.aspects.around[0].call(self) # will follow the proceed chain

        except Exception as e:
            self.exception = e
            for aspect in self.aspects.error:
                aspect.call(self)

        # run all before

        for aspect in self.aspects.after:
            aspect.call(self)

        if self.exception is not None:
            raise self.exception # rethrow the error

        return self.result

    async def call_async(self, *args, **kwargs):
        # remember args

        self.args = args
        self.kwargs = kwargs

        # run all before

        for aspect in self.aspects.before:
            aspect.call(self)

        # run around's with the method being the last aspect!

        try:
            self.result = await self.aspects.around[0].call_async(self) # will follow the proceed chain

        except Exception as e:
            self.exception = e
            for aspect in self.aspects.error:
                aspect.call(self)

        # run all before

        for aspect in self.aspects.after:
            aspect.call(self)

        if self.exception is not None:
            raise self.exception # rethrow the error

        return self.result

    def proceed(self, *args, **kwargs):
        """
        Proceed to the next aspect in the around chain up to the original method.
        """
        if len(args) > 0 or len(kwargs) > 0:  # as soon as we have args, we replace the current ones
            self.args = args
            self.kwargs = kwargs

        # next one please...

        return self.current_aspect.next.call(self)

    async def proceed_async(self, *args, **kwargs):
        """
        Proceed to the next aspect in the around chain up to the original method.
        """
        if len(args) > 0 or len(kwargs) > 0:  # as soon as we have args, we replace the current ones
            self.args = args
            self.kwargs = kwargs

        # next one please...

        return await self.current_aspect.next.call_async(self)

class Advices:
    """
    Internal utility class that collects all advice s
    """
    # static data

    targets: list[AspectTarget] = []

    __slots__ = []

    # constructor

    def __init__(self):
        pass

    # methods

    @classmethod
    def collect(cls, clazz, member, type: AspectType, environment: Environment):
        aspects = [
            FunctionAspect(environment.get(target._clazz), target._function, None) for target in Advices.targets
            if target._type == type
               and target._clazz is not clazz
               and environment.providers.get(target._clazz) is not None
               and target._matches(clazz, member)
        ]

        # sort according to order

        aspects = sorted(aspects, key=lambda aspect: aspect.order)

        # link

        for i in range(0, len(aspects) - 1):
            aspects[i].next = aspects[i + 1]

        # done

        return aspects

    @classmethod
    def aspects_for(cls, instance, environment: Environment) -> Dict[Callable,Aspects]:
        clazz = type(instance)

        result = {}

        for _, member in inspect.getmembers(clazz, predicate=inspect.isfunction):
            aspects = cls.compute_aspects(clazz, member, environment)
            if aspects is not None:
                result[member] = aspects

        # add around methods

        value = {}

        for key, cjp in result.items():
            jp = Aspects(
                before=cjp.before,
                around=cjp.around,
                error=cjp.error,
                after=cjp.after)

            # add method to around

            jp.around.append(MethodAspect(instance, key))
            if len(jp.around) > 1:
                jp.around[len(jp.around) - 2].next = jp.around[len(jp.around) - 1]

            value[key] = jp

        # done

        return value

    @classmethod
    def compute_aspects(cls, clazz, member, environment: Environment) -> Optional[Aspects]:
        befores = cls.collect(clazz, member, AspectType.BEFORE, environment)
        arounds = cls.collect(clazz, member, AspectType.AROUND, environment)
        afters = cls.collect(clazz, member, AspectType.AFTER, environment)
        errors = cls.collect(clazz, member, AspectType.ERROR, environment)

        if len(befores) > 0 or len(arounds) > 0 or len(afters) > 0  or len(errors) > 0:
            return Aspects(
                before=befores,
                around=arounds,
                error=errors,
                after=afters
            )
        else:
            return None

def sanity_check(clazz: Type, name: str):
    m = TypeDescriptor.for_type(clazz).get_method(name)
    if len(m.param_types) != 1 or m.param_types[0] != Invocation:
        raise AOPException(f"Method {clazz.__name__}.{name} expected to have one parameter of type Invocation")

# decorators

def advice(cls):
    """
    Classes decorated with `@advice` are treated as advice classes.
    They can contain methods decorated with `@before`, `@after`, `@around`, or `@error` to define aspects.
    """
    Providers.register(ClassInstanceProvider(cls, True))

    Decorators.add(cls, advice)

    for name, member in TypeDescriptor.for_type(cls).methods.items():
        decorator = next((decorator for decorator in member.decorators if decorator.decorator in [before, after, around, error]), None)
        if decorator is not None:
            target = decorator.args[0] # multiple targets are already merged in a single! check _register
            target._clazz = cls
            sanity_check(cls, name)
            Advices.targets.append(target) #??

    return cls


# decorators

def _register(decorator, targets: list[AspectTarget], func, aspect_type: AspectType):
    target = targets[0]

    for i in range(1, len(targets)):
        target._add(targets[i])

    target.function(func).type(aspect_type)

    Decorators.add(func, decorator, target)

def before(*targets: AspectTarget):
    """
    Methods decorated with `@before` will be executed before the target method is invoked.
    """
    def decorator(func):
        _register(before, targets, func, AspectType.BEFORE)

        return func

    return decorator

def error(*targets: AspectTarget):
    """
    Methods decorated with `@error` will be executed if the target method raises an exception."""
    def decorator(func):
        _register(error, targets, func, AspectType.ERROR)

        return func

    return decorator

def after(*targets: AspectTarget):
    """
    Methods decorated with `@after` will be executed after the target method is invoked.
    """
    def decorator(func):
        _register(after, targets, func, AspectType.AFTER)

        return func

    return decorator

def around(*targets: AspectTarget):
    """
    Methods decorated with `@around` will be executed around the target method.
    Every around method must accept a single parameter of type Invocation and needs to call proceed
    on this parameter to proceed to the next around method.
    """
    def decorator(func):
        _register(around, targets, func, AspectType.AROUND)

        return func

    return decorator

@injectable(scope="environment")
@order(0)
class AdviceProcessor(PostProcessor):
    # properties

    __slots__ = [
        "lock",
        "cache"
    ]

    # constructor

    def __init__(self):
        super().__init__()

        self.cache : Dict[Type, Dict[Callable,Aspects]] = {}
        self.lock = threading.RLock()

    # local

    def aspects_for(self, instance, environment: Environment) -> Dict[Callable,Aspects]:
        clazz = type(instance)
        result = self.cache.get(clazz, None)
        if result is None:
            with self.lock:
                result = Advices.aspects_for(instance, environment)
                self.cache[clazz] = result # TOID der cache ist zu dick?????

        return result

    # implement

    def process(self, instance: object, environment: Environment):
        aspect_dict = self.aspects_for(instance, environment)

        for member, aspects in aspect_dict.items():
            Environment.logger.debug("add aspects for %s:%s", type(instance), member.__name__)

            def wrap(jp):
                def sync_wrapper(*args, **kwargs):
                    return Invocation(member, jp).call(*args, **kwargs)

                return sync_wrapper

            def wrap_async(jp):
                async def async_wrapper(*args, **kwargs):
                    return await Invocation(member, jp).call_async(*args, **kwargs)

                return async_wrapper

            if inspect.iscoroutinefunction(member):
                setattr(instance, member.__name__, types.MethodType(wrap_async(aspects), instance))
            else:
                setattr(instance, member.__name__, types.MethodType(wrap(aspects), instance))
