from __future__ import annotations

from abc import ABC, abstractmethod
import inspect
import re
import types
from dataclasses import dataclass
from enum import auto, Enum
from typing import Optional, Dict, Type, Callable

from sympy.solvers.diophantine.diophantine import descent

from aspyx.reflection import Decorators, TypeDescriptor
from aspyx.di import injectable, environment, Providers, ClassInstanceProvider, Environment, PostProcessor


class AOPException(Exception):
    """
    Exception raised for errors in the aop logic."""
    pass

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

        "_clazz",
        "_instance",
        "names",
        "patterns",
        "types",
        "decorators",
    ]

    # constructor

    def __init__(self):
        self._clazz = None
        self._instance = None

        self.patterns = []
        self.names = []
        self.types = []
        self.decorators = []

        pass

    # abstract

    @abstractmethod
    def _matches(self, clazz : Type, func):
        pass

     # fluent

    def function(self, func):
        self._function = func
        return self

    def type(self, type: AspectType):
        self._type = type

        return self
    
    def ofType(self, type: Type):
        self.types.append(type)
        return self

    def decoratedWith(self, decorator):
        self.decorators.append(decorator)
        return self
    
    def matches(self, pattern: str):
        """
        Matches the target against a pattern.
        """
        self.patterns.append(re.compile(pattern))
        return self

    def named(self, name: str):
        self.names.append(name)
        return self

class ClassAspectTarget(AspectTarget):
    # properties

    __slots__ = [
    ]

    # constructor

    def __init__(self):
        super().__init__()

        pass

    # public

    def _matches(self, clazz : Type, func):
        descriptor = TypeDescriptor.for_type(clazz)

        # type

        if len(self.types) > 0:
            if next((type for type in self.types if issubclass(clazz, type)), None) is None:
                return False

        # decorators

        if len(self.decorators) > 0:
            if next((decorator for decorator in self.decorators if descriptor.has_decorator(decorator)), None) is None:
                return False

        # names

        if len(self.names) > 0:
            if next((name for name in self.names if name == clazz.__name__), None) is None:
                return False
            
        # patterns

        if len(self.patterns) > 0:
            if next((pattern for pattern in self.patterns if re.fullmatch(pattern, clazz.__name__) is not None), None) is None:
                return False
   
        # yipee

        return True
    
    # fluent


    
class MethodAspectTarget(AspectTarget):
    # properties

    __slots__ = [
        "_clazz",
        "_instance",
        "_type",
        "_function",
        "names",
        "patterns",
        "types",
        "decorators",
    ]

    # constructor

    def __init__(self):
       super().__init__()

    # public

    def _matches(self, clazz : Type, func):
        descriptor = TypeDescriptor.for_type(clazz)

        methodDescriptor = descriptor.get_method(func.__name__)

        # type

        if len(self.types) > 0:
            if next((type for type in self.types if issubclass(clazz, type)), None) is None:
                return False

        # decorators

        if len(self.decorators) > 0:
            if next((decorator for decorator in self.decorators if methodDescriptor.has_decorator(decorator)), None) is None:
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

def methods():
    """
    Create a new AspectTarget instance to define method aspect targets.
    """
    return MethodAspectTarget()

def classes():
    """
    Create a new AspectTarget instance to define class aspect targets.
    """
    return ClassAspectTarget()


class JoinPoint:
    __slots__ = [
        "next",
    ]

    # constructor

    def __init__(self, next: 'JoinPoint'):
        self.next = next

    # public

    def call(self, invocation: 'Invocation'):
        pass

class FunctionJoinPoint(JoinPoint):
    __slots__ = [
        "instance",
        "func",
    ]

    def __init__(self, instance, func, next: Optional['JoinPoint']):
        super().__init__(next)

        self.instance = instance
        self.func = func

    def call(self, invocation: 'Invocation'):
        invocation.currentJoinPoint = self

        return self.func(self.instance, invocation)

class MethodJoinPoint(FunctionJoinPoint):
    __slots__ = []

    def __init__(self, instance, func):
        super().__init__(instance, func, None)

    def call(self, invocation: 'Invocation'):
        invocation.currentJoinPoint = self

        return self.func(*invocation.args, **invocation.kwargs)

@dataclass
class JoinPoints:
    before: list[JoinPoint]
    around: list[JoinPoint]
    error: list[JoinPoint]
    after: list[JoinPoint]

class Invocation:
    """
    Invocation stores the relevant data of a single method invocation.
    It holds the arguments, keyword arguments, result, error, and the join points that define the aspect behavior.
    """
    # properties

    __slots__ = [
        "func",
        "args",
        "kwargs",
        "result",
        "error",
        "joinPoints",
        "currentJoinPoint",
    ]

    # constructor

    def __init__(self,  func, joinPoints: JoinPoints):
        self.func = func
        self.args = None
        self.kwargs = None
        self.result = None
        self.error = None
        self.joinPoints = joinPoints
        self.currentJoinPoint = None

    def call(self, *args, **kwargs):
        # remember args

        self.args = args
        self.kwargs = kwargs

        # run all before

        for joinPoint in self.joinPoints.before:
            joinPoint.call(self)

        # run around's with the method being the last aspect!

        try:
            self.result = self.joinPoints.around[0].call(self) # will follow the proceed chain

        except Exception as e:
            self.error = e
            for joinPoint in self.joinPoints.error:
                joinPoint.call(self)

        # run all before

        for joinPoint in self.joinPoints.after:
            joinPoint.call(self)

        if self.error is not None:
            raise self.error # rethrow the error
        else:
            return self.result

    def proceed(self, *args, **kwargs):
        """
        Proceed to the next join point in the around chain up to the original method.
        """
        if len(args) > 0 or len(kwargs) > 0:  # as soon as we have args, we replace the current ones
            self.args = args
            self.kwargs = kwargs

        # next one please...

        return self.currentJoinPoint.next.call(self)

@injectable()
class Advice:
    # static data

    targets: list[AspectTarget] = []

    __slots__ = [
        "cache",
    ]

    # constructor

    def __init__(self):
        self.cache : Dict[Type, Dict[Callable,JoinPoints]] = dict()
        self.resolve()

    # methods

    def resolve(self):
        for target in Advice.targets:
            target._instance = Environment.instance.get(target._clazz) # TODO

    def collect(self, clazz, member, type: AspectType):
        aspects = [FunctionJoinPoint(target._instance, target._function, None) for target in Advice.targets if target._type == type and target._matches(clazz, member)]

        # link

        for i in range(0, len(aspects) - 1):
            aspects[i].next = aspects[i + 1]

        # done

        return aspects

    # TODO thread-safe
    def joinPoints4(self, instance) -> Dict[Callable,JoinPoints]:
        clazz = type(instance)

        result = self.cache.get(clazz, None)
        if result is None:
            result = dict()

            for name, member in inspect.getmembers(clazz, predicate=inspect.isfunction):
                joinPoints = self.computeJoinPoints(clazz, member)
                if joinPoints is not None:
                    result[member] = joinPoints

            self.cache[clazz] = result

        # add around methods

        value = dict()

        for key, cjp in result.items():
            jp = JoinPoints(
                before=cjp.before,
                around=cjp.around,
                error=cjp.error,
                after=cjp.after)

            # add method to around

            jp.around.append(MethodJoinPoint(instance, key))
            if len(jp.around) > 1:
                jp.around[len(jp.around) - 2].next = jp.around[len(jp.around) - 1]

            value[key] = jp

        # done

        return value

    def computeJoinPoints(self, clazz, member) -> Optional[JoinPoints]:
        befores = self.collect(clazz, member, AspectType.BEFORE)
        arounds = self.collect(clazz, member, AspectType.AROUND)
        afters = self.collect(clazz, member, AspectType.AFTER)
        errors = self.collect(clazz, member, AspectType.ERROR)

        if len(befores) > 0 or len(arounds) > 0 or len(afters) > 0  or len(errors) > 0:
            return JoinPoints(
                before=befores,
                around=arounds,
                error=errors,
                after=afters
            )
        else:
            return None

def sanityCheck(clazz: Type, name: str):
    m = TypeDescriptor.for_type(clazz).get_method(name)
    if len(m.paramTypes) != 1 or m.paramTypes[0] != Invocation:
        raise AOPException(f"Method {clazz.__name__}.{name} expected to have one parameter of type Invocation")

# decorators

def advice(cls):
    """
    Classes decorated with @advice are treated as aspect classes.
    They can contain methods decorated with @before, @after, @around, or @error to define aspects.
    """
    Providers.register(ClassInstanceProvider(cls, True, True))

    Decorators.add(cls, advice)

    for name, member in TypeDescriptor.for_type(cls).methods.items():
        decorator = next((decorator for decorator in member.decorators if decorator.decorator in [before, after, around, error]), None)
        if decorator is not None:
            target = decorator.args[0]
            target._clazz = cls
            sanityCheck(cls, name)
            Advice.targets.append(target)

    return cls


# decorators

def _register(decorator, target: AspectTarget, func, aspectType: AspectType):
    target.function(func).type(aspectType)

    Decorators.add(func, decorator, target)

def before(target: AspectTarget):
    """
    Methods decorated with @before will be executed before the target method is invoked.
    """
    def decorator(func):
        _register(before, target, func, AspectType.BEFORE)

        return func

    return decorator

def error(target: AspectTarget):
    """
    Methods decorated with @error will be executed if the target method raises an exception."""
    def decorator(func):
        _register(error, target, func, AspectType.ERROR)

        return func

    return decorator

def after(target: AspectTarget):
    """
    Methods decorated with @after will be executed after the target method is invoked.
    """
    def decorator(func):
        _register(after, target, func, AspectType.AFTER)

        return func

    return decorator

def around(target: AspectTarget):
    """
    Methods decorated with @around will be executed around the target method.
    Every around method must accept a single parameter of type Invocation and needs to call proceed
    on this parameter to proceed to the next around method.
    """
    def decorator(func):
        _register(around, target, func, AspectType.AROUND)

        return func

    return decorator

@injectable()
class AdviceProcessor(PostProcessor):
    # properties

    __slots__ = [
        "advice",
    ]

    # constructor

    def __init__(self, advice: Advice):
        super().__init__()

        self.advice = advice

    # implement

    def process(self, instance: object):
        joinPointDict = self.advice.joinPoints4(instance)

        for member, joinPoints in joinPointDict.items():
            Environment.logger.debug(f"add aspects for {type(instance)}:{member.__name__}")

            def wrap(jp):
                return lambda *args, **kwargs: Invocation(member, jp).call(*args, **kwargs)

            setattr(instance, member.__name__, types.MethodType(wrap(joinPoints), instance))

@environment()
class AOPEnvironment:
    def __init__(self):
        pass