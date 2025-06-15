"""
The dependency injection module provides a framework for managing dependencies and lifecycle of objects in Python applications.
"""
from __future__ import annotations

import inspect
import logging

from abc import abstractmethod, ABC
from enum import Enum
import threading
from operator import truediv
from typing import Type, Dict, TypeVar, Generic, Optional, cast, Callable, TypedDict

from aspyx.di.util import StringBuilder
from aspyx.reflection import Decorators, TypeDescriptor, DecoratorDescriptor

T = TypeVar("T")

class Factory(ABC, Generic[T]):
    """
    Abstract base class for factories that create instances of type T.
    """

    __slots__ = []

    @abstractmethod
    def create(self) -> T:
        pass

class DIException(Exception):
    """
    Exception raised for errors in the injector.
    """
    def __init__(self, message: str):
        super().__init__(message)

class DIRegistrationException(DIException):
    """
    Exception raised during the registration of dependencies.
    """
    def __init__(self, message: str):
        super().__init__(message)

class ProviderCollisionException(DIRegistrationException):
    def __init__(self, message: str, *providers: AbstractInstanceProvider):
         super().__init__(message)

         self.providers = providers

    def __str__(self):
        return f"[{self.args[0]} {self.providers[1].location()} collides with {self.providers[0].location()}"

class DIRuntimeException(DIException):
    """
    Exception raised during the runtime.
    """
    def __init__(self, message: str):
        super().__init__(message)

class AbstractInstanceProvider(ABC, Generic[T]):
    """
    Interface for instance providers.
    """
    @abstractmethod
    def get_module(self) -> str:
        pass

    def get_host(self) -> Type[T]:
        return type(self)

    @abstractmethod
    def get_type(self) -> Type[T]:
        pass

    @abstractmethod
    def is_eager(self) -> bool:
        pass

    @abstractmethod
    def get_scope(self) -> str:
        pass

    def get_dependencies(self) -> (list[Type],int):
        return [],1

    @abstractmethod
    def create(self, environment: Environment, *args):
        pass

    def report(self) -> str:
        return str(self)

    def location(self) -> str:
        host = self.get_host()

        file = inspect.getfile(host)
        line = inspect.getsourcelines(host)[1]

        return f"{file}:{line}"

    def check_factories(self):
        pass


class InstanceProvider(AbstractInstanceProvider):
    """
    An InstanceProvider is able to create instances of type T.
    """
    __slots__ = [
        "host",
        "type",
        "eager",
        "scope"
    ]

    # constructor

    def __init__(self, host: Type, t: Type[T], eager: bool, scope: str):
        self.host = host
        self.type = t
        self.eager = eager
        self.scope = scope

    # implement AbstractInstanceProvider

    def get_host(self):
        return self.host

    def check_factories(self):
        pass

    def get_module(self) -> str:
        return self.host.__module__

    def get_type(self) -> Type[T]:
        return self.type

    def is_eager(self) -> bool:
        return self.eager

    def get_scope(self) -> str:
        return self.scope

    # public

    def module(self) -> str:
        return self.host.__module__

    @abstractmethod
    def create(self, environment: Environment, *args):
        pass

# we need this classes to bootstrap the system...
class SingletonScopeInstanceProvider(InstanceProvider):
    def __init__(self):
        super().__init__(SingletonScopeInstanceProvider, SingletonScope, False, "request")

    def create(self, environment: Environment, *args):
        return SingletonScope()

class RequestScopeInstanceProvider(InstanceProvider):
    def __init__(self):
        super().__init__(RequestScopeInstanceProvider, RequestScope, False, "singleton")

    def create(self, environment: Environment, *args):
        return RequestScope()


class AmbiguousProvider(AbstractInstanceProvider):
    """
    An AmbiguousProvider covers all cases, where fetching a class would lead to an ambiguity exception.
    """

    __slots__ = [
        "type",
        "providers",
    ]

    # constructor

    def __init__(self, type: Type, *providers: AbstractInstanceProvider):
        super().__init__()

        self.type = type
        self.providers = list(providers)

    # public

    def add_provider(self, provider: AbstractInstanceProvider):
        self.providers.append(provider)

    # implement

    def get_module(self) -> str:
        return self.type.__module__

    def get_type(self) -> Type[T]:
        return self.type

    def is_eager(self) -> bool:
        return False

    def get_scope(self) -> str:
        return "singleton"

    def create(self, environment: Environment, *args):
        raise DIException(f"multiple candidates for type {self.type}")

    def report(self) -> str:
        return "ambiguous: " + ",".join([provider.report() for provider in self.providers])

    def __str__(self):
        return f"AmbiguousProvider({self.type})"

class Scopes:
    # static data

    scopes : Dict[str, Type] = {}

    # class methods

    @classmethod
    def get(cls, scope: str, environment: Environment):
        scope_type = Scopes.scopes.get(scope, None)
        if scope_type is None:
            raise DIRegistrationException(f"unknown scope type {scope}")

        return environment.get(scope_type)

    @classmethod
    def register(cls, scope_type: Type, name: str):
        Scopes.scopes[name] = scope_type

class Scope:
    # properties

    __slots__ = [
    ]

    # constructor

    def __init__(self):
        pass

    # public

    def get(self, provider: AbstractInstanceProvider, environment: Environment, arg_provider: Callable[[],list]):
        return provider.create(environment, *arg_provider())

class EnvironmentInstanceProvider(AbstractInstanceProvider):
    # properties

    __slots__ = [
        "environment",
        "scope_instance",
        "dependencies",
        "provider"
    ]

    # constructor

    def __init__(self, environment: Environment, provider: AbstractInstanceProvider):
        super().__init__()

        self.environment = environment
        self.provider = provider
        self.dependencies = []
        self.scope_instance = Scopes.get(provider.get_scope(), environment)

    # implement

    def resolve(self, context: Providers.ResolveContext):
        context.add(self)

        if not context.is_resolved(self):
            context.provider_dependencies[self] = [] #?

            type_and_params = self.provider.get_dependencies()
            params = type_and_params[1]
            for type in type_and_params[0]:
                if params > 0:
                    params -= 1
                    self.dependencies.append(context.get_provider(type))

                provider = context.add_provider_dependency(self, type)
                if provider is not None:
                    provider.resolve(context)

        else:
            context.add(*context.get_provider_dependencies(self))

    def get_module(self) -> str:
        return self.provider.get_module()

    def get_type(self) -> Type[T]:
        return self.provider.get_type()

    def is_eager(self) -> bool:
        return self.provider.is_eager()

    def get_scope(self) -> str:
        return self.provider.get_scope()

    def report(self) -> str:
        return self.provider.report()

    # own logic

    def create(self, environment: Environment, *args):
        return self.scope_instance.get(self.provider, self.environment, lambda: [provider.create(environment) for provider in self.dependencies]) # already scope property!

    def __str__(self):
        return f"EnvironmentInstanceProvider({self.provider})"

class ClassInstanceProvider(InstanceProvider):
    """
    A ClassInstanceProvider is able to create instances of type T by calling the class constructor.
    """

    __slots__ = [
        "params"
    ]

    # constructor

    def __init__(self, t: Type[T], eager: bool, scope = "singleton"):
        super().__init__(t, t, eager, scope)

        self.params = 0

    # implement

    def check_factories(self):
        register_factories(self.host)

    def get_dependencies(self) -> (list[Type],int):
        types : list[Type] = []

        # check constructor

        init = TypeDescriptor.for_type(self.type).get_method("__init__")
        if init is None:
            raise DIRegistrationException(f"{self.type.__name__} does not implement __init__")

        self.params = len(init.param_types)
        for param in init.param_types:
            types.append(param)

        # check @inject

        for method in TypeDescriptor.for_type(self.type).get_methods():
            if method.has_decorator(inject):
                for param in method.param_types:
                    types.append(param)

        return (types, self.params)

    def create(self, environment: Environment, *args):
        Environment.logger.debug("%s create class %s", self, self.type.__qualname__)

        return environment.created(self.type(*args[:self.params]))

    def report(self) -> str:
        return f"{self.host.__name__}.__init__"

    # object

    def __str__(self):
        return f"ClassInstanceProvider({self.type.__name__})"

class FunctionInstanceProvider(InstanceProvider):
    """
    A FunctionInstanceProvider is able to create instances of type T by calling specific methods annotated with 'create".
    """

    __slots__ = [
        "method"
    ]

    # constructor

    def __init__(self, clazz : Type, method, return_type : Type[T], eager = True, scope = "singleton"):
        super().__init__(clazz, return_type, eager, scope)

        self.method = method

    # implement

    def get_dependencies(self) -> (list[Type],int):
        return [self.host], 1

    def create(self, environment: Environment, *args):
        Environment.logger.debug("%s create class %s", self, self.type.__qualname__)

        instance = self.method(*args) # args[0]=self

        return environment.created(instance)

    def report(self) -> str:
        return f"{self.host.__name__}.{self.method.__name__}"

    def __str__(self):
        return f"FunctionInstanceProvider({self.host.__name__}.{self.method.__name__} -> {self.type.__name__})"

class FactoryInstanceProvider(InstanceProvider):
    """
    A FactoryInstanceProvider is able to create instances of type T by calling registered Factory instances.
    """

    __slots__ = []

    # class method

    @classmethod
    def get_factory_type(cls, clazz):
        return TypeDescriptor.for_type(clazz).get_method("create", local=True).return_type

    # constructor

    def __init__(self, factory: Type, eager: bool, scope: str):
        super().__init__(factory, FactoryInstanceProvider.get_factory_type(factory), eager, scope)

    # implement

    def get_dependencies(self) -> (list[Type],int):
        return [self.host],1

    def create(self, environment: Environment, *args):
        Environment.logger.debug("%s create class %s", self, self.type.__qualname__)

        return environment.created(args[0].create())

    def report(self) -> str:
        return f"{self.host.__name__}.create"

    def __str__(self):
        return f"FactoryInstanceProvider({self.host.__name__} -> {self.type.__name__})"


class Lifecycle(Enum):
    """
    This enum defines the lifecycle phases that can be processed by lifecycle processors.
    """

    __slots__ = []

    ON_INJECT  = 0
    ON_INIT    = 1
    ON_RUNNING = 2
    ON_DESTROY = 3

class LifecycleProcessor(ABC):
    """
    A LifecycleProcessor is used to perform any side effects on managed objects during different lifecycle phases.
    """
    __slots__ = [
        "order"
    ]

    # constructor

    def __init__(self):
        self.order = 0
        if TypeDescriptor.for_type(type(self)).has_decorator(order):
            self.order =  TypeDescriptor.for_type(type(self)).get_decorator(order).args[0]

    # methods

    @abstractmethod
    def process_lifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        pass

class PostProcessor(LifecycleProcessor):
    """
    Base class for custom post processors that are executed after object creation.
    """
    __slots__ = []


    def process(self, instance: object, environment: Environment):
        pass

    def process_lifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle == Lifecycle.ON_INIT:
            self.process(instance, environment)


class Providers:
    """
    The Providers class is a static class that manages the registration and resolution of InstanceProviders.
    """
    # local class

    class ResolveContext:
        __slots__ = [
            "dependencies",
            "providers",
            "provider_dependencies"
        ]

        # constructor

        def __init__(self, providers: Dict[Type, EnvironmentInstanceProvider]):
            self.dependencies : list[EnvironmentInstanceProvider] = []
            self.providers = providers
            self.provider_dependencies : dict[EnvironmentInstanceProvider, list[EnvironmentInstanceProvider]] = {}

        # public

        def is_resolved(self, provider: EnvironmentInstanceProvider) -> bool:
            return self.provider_dependencies.get(provider, None) is not None

        def get_provider_dependencies(self, provider: EnvironmentInstanceProvider) -> list[EnvironmentInstanceProvider]:
            return self.provider_dependencies[provider]

        def add_provider_dependency(self, provider: EnvironmentInstanceProvider, type: Type) -> Optional[EnvironmentInstanceProvider]:
            provider_dependencies = self.provider_dependencies.get(provider, None)
            if provider_dependencies is None:
                provider_dependencies = []
                self.provider_dependencies[provider] = provider_dependencies

            provider = self.get_provider(type)

            if any(issubclass(provider.get_type(), dependency.get_type()) for dependency in provider_dependencies):
                return None

            provider_dependencies.append(provider)

            return provider

        def next(self):
            self.dependencies.clear()

        def get_provider(self, type: Type) -> EnvironmentInstanceProvider:
            provider = self.providers.get(type, None)
            if provider is None:
                raise DIRegistrationException(f"Provider for {type} is not defined")

            return provider

        def add(self, *providers: EnvironmentInstanceProvider):
            for provider in providers:
                if next((p for p in self.dependencies if p.get_type() is provider.get_type()), None) is not None:
                    raise DIRegistrationException(self.cycle_report(provider))

                self.dependencies.append(provider)

        def cycle_report(self, provider: AbstractInstanceProvider):
            cycle = ""

            first = True
            for p in self.dependencies:
                if not first:
                    cycle += " -> "

                first = False

                cycle += f"{p.report()}"

            cycle += f" <> {provider.report()}"

            return cycle


    # class properties

    check : list[AbstractInstanceProvider] = []
    providers : Dict[Type,list[AbstractInstanceProvider]] = {}

    resolved = False

    @classmethod
    def register(cls, provider: AbstractInstanceProvider):
        Environment.logger.debug("register provider %s(%s)", provider.get_type().__qualname__, provider.get_type().__name__)

        Providers.check.append(provider)
        candidates = Providers.providers.get(provider.get_type(), None)
        if candidates is None:
            Providers.providers[provider.get_type()] = [provider]
        else:
            candidates.append(provider)

    # add factories lazily

    @classmethod
    def check_factories(cls):
        for check in Providers.check:
            check.check_factories()

        Providers.check.clear()

    @classmethod
    def filter(cls, environment: Environment) -> Dict[Type,AbstractInstanceProvider]:
        cache: Dict[Type,AbstractInstanceProvider] = {}

        context: ConditionContext = {
            "requires_feature": lambda feature : environment.has_feature(feature),
            "requires_class": lambda clazz : cache.get(clazz, None) is not None # ? only works if the class is in the cache already?
        }

        Providers.check_factories() # check for additional factories

        # local methods

        def filter_type(clazz: Type) -> Optional[AbstractInstanceProvider]:
            result = None
            for provider in Providers.providers[clazz]:
                if provider_applies(provider):
                    if result is not None:
                        raise ProviderCollisionException(f"type {clazz.__name__} already registered", result, provider)

                    else:
                        result = provider

            return result

        def provider_applies(provider: AbstractInstanceProvider) -> bool:
            descriptor = TypeDescriptor.for_type(provider.get_host())
            if descriptor.has_decorator(conditional):
                conditions: list[Condition] = [*descriptor.get_decorator(conditional).args]
                for condition in conditions:
                    if not condition.apply(context):
                        return False

                return True

            return True

        def is_injectable(type: Type) -> bool:
            if type is object:
                return False

            if inspect.isabstract(type):
                return False

            return True

        def cache_provider_for_type(provider: AbstractInstanceProvider, type: Type):
            existing_provider = cache.get(type)
            if existing_provider is None:
                cache[type] = provider

            else:
                if type is provider.get_type():
                    raise ProviderCollisionException(f"type {type.__name__} already registered", existing_provider, provider)

                if isinstance(existing_provider, AmbiguousProvider):
                    cast(AmbiguousProvider, existing_provider).add_provider(provider)
                else:
                    cache[type] = AmbiguousProvider(type, existing_provider, provider)

            # recursion

            for super_class in type.__bases__:
                if is_injectable(super_class):
                    cache_provider_for_type(provider, super_class)

        # filter conditional providers and fill base classes as well

        for provider_type, providers in Providers.providers.items():
            matching_provider = filter_type(provider_type)
            if matching_provider is not None:
                cache_provider_for_type(matching_provider, provider_type)

        # replace by EnvironmentInstanceProvider

        mapped = {}
        result = {}
        for provider_type, provider in cache.items():
            environment_provider = mapped.get(provider, None)
            if environment_provider is None:
                environment_provider = EnvironmentInstanceProvider(environment,  provider)
                mapped[provider] = environment_provider

            result[provider_type] = environment_provider

        # and resolve

        provider_context = Providers.ResolveContext(result)
        for provider in mapped.values():
            provider.resolve(provider_context)
            provider_context.next() # clear dependencies

        # done

        return result

def register_factories(cls: Type):
    descriptor = TypeDescriptor.for_type(cls)

    for method in descriptor.get_methods():
        if method.has_decorator(create):
            create_decorator = method.get_decorator(create)
            return_type = method.return_type
            if return_type is None:
                raise DIRegistrationException(f"{cls.__name__}.{method.method.__name__} expected to have a return type")

            Providers.register(FunctionInstanceProvider(cls, method.method, return_type, create_decorator.args[0],
                                                        create_decorator.args[1]))
def order(prio = 0):
    def decorator(cls):
        Decorators.add(cls, order, prio)

        return cls

    return decorator

def injectable(eager=True, scope="singleton"):
    """
    Instances of classes that are annotated with @injectable can be created by an Environment.
    """
    def decorator(cls):
        Decorators.add(cls, injectable)

        Providers.register(ClassInstanceProvider(cls, eager, scope))

        return cls

    return decorator

def factory(eager=True, scope="singleton"):
    """
    Decorator that needs to be used on a class that implements the Factory interface.
    """
    def decorator(cls):
        Decorators.add(cls, factory)

        Providers.register(ClassInstanceProvider(cls, eager, scope))
        Providers.register(FactoryInstanceProvider(cls, eager, scope))

        return cls

    return decorator

def create(eager=True, scope="singleton"):
    """
    Any method annotated with @create will be registered as a factory method.
    """
    def decorator(func):
        Decorators.add(func, create, eager, scope)
        return func

    return decorator

def on_init():
    """
    Methods annotated with @on_init will be called when the instance is created."""
    def decorator(func):
        Decorators.add(func, on_init)
        return func

    return decorator

def on_running():
    """
    Methods annotated with @on_running will be called when the container up and running."""
    def decorator(func):
        Decorators.add(func, on_running)
        return func

    return decorator

def on_destroy():
    """
    Methods annotated with @on_destroy will be called when the instance is destroyed.
    """
    def decorator(func):
        Decorators.add(func, on_destroy)
        return func

    return decorator

def environment(imports: Optional[list[Type]] = None):
    """
    This annotation is used to mark classes that control the set of injectables that will be managed based on their location
    relative to the module of the class. All @injectable s and @factory s that are located in the same or any sub-module will
    be registered and managed accordingly.
    Arguments:
        imports (Optional[list[Type]]): Optional list of imported environment types
    """
    def decorator(cls):
        Providers.register(ClassInstanceProvider(cls, True))

        Decorators.add(cls, environment, imports)
        Decorators.add(cls, injectable) # do we need that?

        return cls

    return decorator

def inject():
    """
    Methods annotated with @inject will be called with the required dependencies injected.
    """
    def decorator(func):
        Decorators.add(func, inject)
        return func

    return decorator

def inject_environment():
    """
    Methods annotated with @inject_environment will be called with the Environment instance injected.
    """
    def decorator(func):
        Decorators.add(func, inject_environment)
        return func

    return decorator

# conditional stuff

class ConditionContext(TypedDict):
    requires_feature: Callable[[str], bool]
    requires_class: Callable[[Type], bool]

class Condition(ABC):
    @abstractmethod
    def apply(self, context: ConditionContext) -> bool:
        pass

class FeatureCondition(Condition):
    def __init__(self, feature: str):
        super().__init__()

        self.feature = feature

    def apply(self, context: ConditionContext) -> bool:
        return context["requires_feature"](self.feature)

class ClassCondition(Condition):
    def __init__(self, clazz: Type):
        super().__init__()

        self.clazz = clazz

    def apply(self, context: ConditionContext) -> bool:
        return context["requires_class"](self.clazz)

def requires_feature(feature: str):
    return FeatureCondition(feature)

def requires_class(clazz: Type):
    return ClassCondition(clazz)

def conditional(*conditions: Condition):
    def decorator(cls):
        Decorators.add(cls, conditional, *conditions)

        return cls

    return decorator

class Environment:
    """
    Central class that manages the lifecycle of instances and their dependencies.
    """

    # static data

    logger = logging.getLogger(__name__)  # __name__ = module name

    instance : 'Environment' = None

    __slots__ = [
        "type",
        "providers",
        "lifecycle_processors",
        "parent",
        "features",
        "instances"
    ]

    # constructor

    def __init__(self, env: Type, features: list[str] = [], parent : Optional[Environment] = None):
        """
        Creates a new Environment instance.

        Args:
            env (Type): The environment class that controls the scanning of managed objects.
            parent (Optional[Environment]): Optional parent environment, whose objects are inherited.
        """

        Environment.logger.debug("create environment for class %s", env.__qualname__)

        # initialize

        self.type = env
        self.parent = parent
        if self.parent is None and env is not Boot:
            self.parent = Boot.get_environment() # inherit environment including its manged instances!

        self.features = features
        self.providers: Dict[Type, AbstractInstanceProvider] = {}
        self.lifecycle_processors: list[LifecycleProcessor] = []

        if self.parent is not None:
            self.providers |= self.parent.providers
            self.lifecycle_processors += self.parent.lifecycle_processors
        else: #if self.type is Boot:
            self.providers[SingletonScope] = SingletonScopeInstanceProvider()
            self.providers[RequestScope]   = RequestScopeInstanceProvider()

        self.instances = []

        Environment.instance = self

        # filter conditional providers

        overall_providers = Providers.filter(self)

        loaded = set()

        def add_provider(type: Type, provider: AbstractInstanceProvider):
            Environment.logger.debug("\tadd provider %s for %s", provider, type)

            self.providers[type] = provider

        def load_environment(env: Type):
            if env not in loaded:
                Environment.logger.debug("load environment %s", env.__qualname__)

                loaded.add(env)

                # sanity check

                decorator = TypeDescriptor.for_type(env).get_decorator(environment)
                if decorator is None:
                    raise DIRegistrationException(f"{env.__name__} is not an environment class")

                scan = env.__module__
                if "." in scan:
                    scan = scan.rsplit('.', 1)[0]

                # recursion

                for import_environment in decorator.args[0] or []:
                    load_environment(import_environment)

                # filter and load providers according to their module

                for type, provider in overall_providers.items():
                    if provider.get_module().startswith(scan):
                        add_provider(type, provider)
        # go

        load_environment(env)

        # construct eager objects for local providers

        for provider in set(self.providers.values()):
            if provider.is_eager():
                provider.create(self)

        # running callback

        for instance in self.instances:
            self.execute_processors(Lifecycle.ON_RUNNING, instance)

    # internal

    def has_feature(self, feature: str) -> bool:
        return feature in self.features

    def execute_processors(self, lifecycle: Lifecycle, instance: T) -> T:
        for processor in self.lifecycle_processors:
            processor.process_lifecycle(lifecycle, instance, self)

        return instance

    def created(self, instance: T) -> T:
        # remember lifecycle processors

        if isinstance(instance, LifecycleProcessor):
            self.lifecycle_processors.append(instance)

            # sort immediately

            self.lifecycle_processors.sort(key=lambda processor: processor.order)

        # remember instance

        self.instances.append(instance)

        # execute processors

        self.execute_processors(Lifecycle.ON_INJECT, instance)
        self.execute_processors(Lifecycle.ON_INIT, instance)

        return instance

    # public

    def report(self):
        builder = StringBuilder()

        builder.append(f"Environment {self.type.__name__}")

        if self.parent is not None:
            builder.append(f" parent {self.parent.type.__name__}")

        builder.append("\n")

        # post processors

        builder.append("Processors \n")
        for processor in self.lifecycle_processors:
            builder.append(f"- {processor.__class__.__name__}\n")

        # providers

        builder.append("Providers \n")
        for result_type, provider in self.providers.items():
            if isinstance(provider, EnvironmentInstanceProvider):
                if cast(EnvironmentInstanceProvider, provider).environment is self:
                    builder.append(f"- {result_type.__name__}: {provider.report()}\n")

        # instances

        builder.append("Instances \n")

        result = {}
        for obj in self.instances:
            cls = type(obj)
            result[cls] = result.get(cls, 0) + 1

        for cls, count in result.items():
            builder.append(f"- {cls.__name__}: {count} \n")

        # done

        result = str(builder)

        return result

    def destroy(self):
        """
        destroy all managed instances by calling the appropriate lifecycle methods
        """
        for instance in self.instances:
            self.execute_processors(Lifecycle.ON_DESTROY, instance)

        self.instances.clear() # make the cy happy

    def get(self, type: Type[T]) -> T:
        """
        Create or return a cached instance for the given type.

        Arguments:
            type (Type): The desired type

        Returns: The requested instance
        """
        provider = self.providers.get(type, None)
        if provider is None:
            Environment.logger.error("%s is not supported", type)
            raise DIRuntimeException(f"{type} is not supported")

        return provider.create(self)

    def __str__(self):
        return f"Environment({self.type.__name__})"

class LifecycleCallable:
    __slots__ = [
        "decorator",
        "lifecycle",
        "order"
    ]

    def __init__(self, decorator, lifecycle: Lifecycle):
        self.decorator = decorator
        self.lifecycle = lifecycle
        self.order = 0

        if TypeDescriptor.for_type(type(self)).has_decorator(order):
            self.order = TypeDescriptor.for_type(type(self)).get_decorator(order).args[0]

        AbstractCallableProcessor.register(self)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return []


class AbstractCallableProcessor(LifecycleProcessor):
    # local classes

    class MethodCall:
        __slots__ = [
            "decorator",
            "method",
            "lifecycle_callable"
        ]

        # constructor

        def __init__(self, method: TypeDescriptor.MethodDescriptor, decorator: DecoratorDescriptor, lifecycle_callable: LifecycleCallable):
            self.decorator = decorator
            self.method = method
            self.lifecycle_callable = lifecycle_callable

        def execute(self, instance, environment: Environment):
            self.method.method(instance, *self.lifecycle_callable.args(self.decorator, self.method, environment))

        def __str__(self):
            return f"MethodCall({self.method.method.__name__})"

    # static data

    lock = threading.RLock()
    callables : Dict[object, LifecycleCallable] = {}
    cache : Dict[Type, list[list[AbstractCallableProcessor.MethodCall]]] = {}

    # static methods

    @classmethod
    def register(cls, callable: LifecycleCallable):
        AbstractCallableProcessor.callables[callable.decorator] = callable

    @classmethod
    def compute_callables(cls, type: Type) -> list[list[AbstractCallableProcessor.MethodCall]]:
        descriptor = TypeDescriptor.for_type(type)

        result = [[], [], [], []]  # per lifecycle

        for method in descriptor.get_methods():
            for decorator in method.decorators:
                callable = AbstractCallableProcessor.callables.get(decorator.decorator)
                if callable is not None:  # any callable for this decorator?
                    result[callable.lifecycle.value].append(
                        AbstractCallableProcessor.MethodCall(method, decorator, callable))

        # sort according to order

        result[0].sort(key=lambda call: call.lifecycle_callable.order)
        result[1].sort(key=lambda call: call.lifecycle_callable.order)
        result[2].sort(key=lambda call: call.lifecycle_callable.order)
        result[3].sort(key=lambda call: call.lifecycle_callable.order)

        # done

        return result

    @classmethod
    def callables_for(cls, type: Type) -> list[list[AbstractCallableProcessor.MethodCall]]:
        callables = AbstractCallableProcessor.cache.get(type, None)
        if callables is None:
            with AbstractCallableProcessor.lock:
                callables = AbstractCallableProcessor.cache.get(type, None)
                if callables is None:
                    callables = AbstractCallableProcessor.compute_callables(type)
                    AbstractCallableProcessor.cache[type] = callables

        return callables

    # constructor

    def __init__(self, lifecycle: Lifecycle):
        super().__init__()

        self.lifecycle = lifecycle

    # implement

    def process_lifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle is self.lifecycle:
            callables = self.callables_for(type(instance))

            for callable in callables[lifecycle.value]:
                callable.execute(instance, environment)

@injectable()
@order(1)
class OnInjectCallableProcessor(AbstractCallableProcessor):
    def __init__(self):
        super().__init__(Lifecycle.ON_INJECT)

@injectable()
@order(2)
class OnInitCallableProcessor(AbstractCallableProcessor):
    def __init__(self):
        super().__init__(Lifecycle.ON_INIT)

@injectable()
@order(3)
class OnRunningCallableProcessor(AbstractCallableProcessor):
    def __init__(self):
        super().__init__(Lifecycle.ON_RUNNING)

@injectable()
@order(4)
class OnDestroyCallableProcessor(AbstractCallableProcessor):
    def __init__(self):
        super().__init__(Lifecycle.ON_DESTROY)

# the callables

@injectable()
@order(1000)
class OnInitLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self):
        super().__init__(on_init, Lifecycle.ON_INIT)

@injectable()
@order(1001)
class OnDestroyLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self):
        super().__init__(on_destroy, Lifecycle.ON_DESTROY)

@injectable()
@order(1002)
class OnRunningLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self):
        super().__init__(on_running, Lifecycle.ON_RUNNING)

@injectable()
@order(9)
class EnvironmentAwareLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self):
        super().__init__(inject_environment, Lifecycle.ON_INJECT)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment]

@injectable()
@order(10)
class InjectLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self):
        super().__init__(inject, Lifecycle.ON_INJECT)

    # override

    def args(self, decorator: DecoratorDescriptor,  method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment.get(type) for type in method.param_types]

def scope(name: str, register=True):
    def decorator(cls):
        Scopes.register(cls, name)

        Decorators.add(cls, scope)

        if register:
            Providers.register(ClassInstanceProvider(cls, eager=True, scope="request"))

        return cls

    return decorator

@scope("request", register=False)
class RequestScope(Scope):
    # properties

    __slots__ = [
    ]

    # public

    def get(self, provider: AbstractInstanceProvider, environment: Environment, arg_provider: Callable[[],list]):
        return provider.create(environment, *arg_provider())

@scope("singleton", register=False)
class SingletonScope(Scope):
    # properties

    __slots__ = [
        "value",
        "lock"
    ]

    # constructor

    def __init__(self):
        super().__init__()

        self.value = None
        self.lock = threading.RLock()

    # override

    def get(self, provider: AbstractInstanceProvider, environment: Environment, arg_provider: Callable[[],list]):
        if self.value is None:
            with self.lock:
                if self.value is None:
                    self.value = provider.create(environment, *arg_provider())

        return self.value

@scope("thread")
class ThreadScope(Scope):
    __slots__ = [
        "_local"
    ]

    # constructor

    def __init__(self):
        super().__init__()
        self._local = threading.local()

    def get(self, provider: AbstractInstanceProvider, environment: Environment, arg_provider: Callable[[], list]):
        if not hasattr(self._local, "value"):
            self._local.value = provider.create(environment, *arg_provider())
        return self._local.value

# internal class that is required to import technical instance providers

@environment()
class Boot:
    # class

    environment = None

    @classmethod
    def get_environment(cls):
        if Boot.environment is None:
            Boot.environment = Environment(Boot)

        return Boot.environment

    # properties

    __slots__ = []

    # constructor

    def __init__(self):
        pass
