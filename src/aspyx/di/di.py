from __future__ import annotations

import inspect
import logging
import threading
from abc import abstractmethod, ABC
from enum import Enum, auto
from types import FunctionType
from typing import Type, Dict, TypeVar, Generic, Optional, cast, Callable

from aspyx.reflection import Decorators, TypeDescriptor, DecoratorDescriptor

T = TypeVar("T")

class Factory(ABC, Generic[T]):
    """
    Abstract base class for factories that create insatnces of type T.
    """

    __slots__ = []

    @abstractmethod
    def create(self) -> T:
        pass

class InjectorException(Exception):
    """
    Exception raised for errors in the injector."""
    pass

class AbstractInstanceProvider(ABC, Generic[T]):
    """
    Interface for instance providers.
    """
    @abstractmethod
    def get_module(self) -> str:
        pass

    @abstractmethod
    def get_type(self) -> Type[T]:
        pass

    @abstractmethod
    def is_eager(self) -> bool:
        pass

    @abstractmethod
    def is_singleton(self) -> bool:
        pass

    @abstractmethod
    def get_dependencies(self) -> list[AbstractInstanceProvider]:
        pass

    @abstractmethod
    def create(self, env: Environment, *args):
        pass

    @abstractmethod
    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        pass


class InstanceProvider(AbstractInstanceProvider):
    """
    An InstanceProvider is able to create instances of type T.
    """
    __slots__ = [
        "host",
        "type",
        "eager",
        "singleton",
        "dependencies"
    ]

    # constructor

    def __init__(self, host: Type, t: Type[T], eager: bool, singleton: bool):
        self.host = host
        self.type = t
        self.eager = eager
        self.singleton = singleton
        self.dependencies : Optional[list[AbstractInstanceProvider]] = None

    # implement AbstractInstanceProvider

    def get_module(self) -> str:
        return self.host.__module__

    def get_type(self) -> Type[T]:
        return self.type

    def is_eager(self) -> bool:
        return self.eager

    def is_singleton(self) -> bool:
        return self.singleton

    def get_dependencies(self) -> list[AbstractInstanceProvider]:
        return self.dependencies

    # public

    def module(self) -> str:
        return self.host.__module__

    def add_dependency(self, provider: AbstractInstanceProvider):
        if any(issubclass(provider.get_type(), dependency.get_type()) for dependency in self.dependencies):
            return False

        self.dependencies.append(provider)

        return True

    @abstractmethod
    def create(self, environment: Environment, *args):
        pass

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

    def is_singleton(self) -> bool:
        return False

    def get_dependencies(self) -> list[AbstractInstanceProvider]:
        return []

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        return self

    def create(self, environment: Environment, *args):
        raise InjectorException(f"multiple candidates for type {self.type}")

    def __str__(self):
        return f"AmbiguousProvider({self.type})"

####### TEST

class Scopes:
    # static data

    scopes : Dict[str, Type] = {}

    # class methods

    @classmethod
    def register(cls, scopeClass: Type, name: str):
        Scopes.scopes[name] = scopeClass

def scope(name: str):
    def decorator(cls):
        Scopes.register(cls, name)

        return cls

    return decorator

class Scope:
    # properties

    __slots__ = [
    ]

    # constructor

    def __init__(self):
        pass

    # public

    def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
        return provider.create(environment, *argProvider())

@scope("singleton")
class SingletonScope(Scope):
    # properties

    __slots__ = [
        "value"
    ]

    # constructor

    def __init__(self):
        super().__init__()

        self.value = None

    # override

    def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
        if self.value is None:
            self.value = provider.create(environment, *argProvider())

        return self.value

class EnvironmentInstanceProvider(AbstractInstanceProvider):
    # properties

    __slots__ = [
        "environment",
        "scope",
        "provider",
        "dependencies",
    ]

    # constructor

    def __init__(self, environment: Environment, provider: AbstractInstanceProvider):
        super().__init__()

        self.environment = environment
        self.provider = provider
        self.dependencies : list[AbstractInstanceProvider] = []

        # compute scope TODO -> registry

        if provider.is_singleton():
            self.scope = SingletonScope()
        else:
            self.scope = Scope()

    # implement

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        pass # noop

    def get_module(self) -> str:
        return self.provider.get_module()

    def get_type(self) -> Type[T]:
        return self.provider.get_type()

    def is_eager(self) -> bool:
        return self.provider.is_eager()

    def is_singleton(self) -> bool:
        return self.provider.is_singleton()

    # custom logic

    def tweakDependencies(self, providers: dict[Type, AbstractInstanceProvider]):
        for dependency in self.provider.get_dependencies():
            instanceProvider = providers.get(dependency.get_type(), None)
            if instanceProvider is None:
                raise InjectorException(f"missing import for {dependency.get_type()} ")

            self.dependencies.append(instanceProvider)
            pass
        pass

    def get_dependencies(self) -> list[AbstractInstanceProvider]:
        return self.provider.get_dependencies()

    def create(self, env: Environment, *args):
        return self.scope.get(self.provider, self.environment, lambda: [provider.create(env) for provider in self.dependencies] ) # already scope property!

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

    def __init__(self, t: Type[T], eager: bool, singleton: bool):
        super().__init__(t, t, eager, singleton)

        self.params = 0

    # implement

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            # check constructor

            init = TypeDescriptor.for_type(self.type).get_method("__init__")
            if init is None:
                raise InjectorException(f"{self.type.__name__} does not implement __init__")

            for param in init.paramTypes:
                provider = Providers.getProvider(param)
                self.params += 1
                if self.add_dependency(provider):
                    provider.resolve(context)

            # check @inject

            for method in TypeDescriptor.for_type(self.type).methods.values():
                if method.has_decorator(inject):
                    for param in method.paramTypes:
                        provider = Providers.getProvider(param)

                        if self.add_dependency(provider):
                            provider.resolve(context)
        else: # check if the dependencies create a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment, *args):
        Environment.logger.debug(f"{self} create class {self.type.__qualname__}")

        return environment.created(self.type(*args[:self.params]))

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

    def __init__(self, clazz : Type, method, return_type : Type[T], eager = True, singleton = True):
        super().__init__(clazz, return_type, eager, singleton)

        self.method = method

    # implement

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            provider = Providers.getProvider(self.host)
            if self.add_dependency(provider):
                provider.resolve(context)
        else: # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment, *args):
        Environment.logger.debug(f"{self} create class {self.type.__qualname__}")

        instance = self.method(*args)

        return environment.created(instance)

    def __str__(self):
        return f"FunctionInstanceProvider({self.host.__name__}.{self.method.__name__} -> {self.type.__name__})"

class FactoryInstanceProvider(InstanceProvider):
    """
    A FactoryInstanceProvider is able to create instances of type T by calling registered Factory instances.
    """

    __slots__ = []

    # class method

    @classmethod
    def getFactoryType(cls, clazz):
        return TypeDescriptor.for_type(clazz).get_local_method("create").returnType

    # constructor

    def __init__(self, factory: Type, eager: bool, singleton: bool):
        super().__init__(factory, FactoryInstanceProvider.getFactoryType(factory), eager, singleton)

    # implement

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            provider = Providers.getProvider(self.host)
            if self.add_dependency(provider):
                provider.resolve(context)

        else: # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment, *args):
        Environment.logger.debug(f"{self} create class {self.type.__qualname__}")

        return environment.created(args[0].create())

    def __str__(self):
        return f"FactoryInstanceProvider({self.host.__name__} -> {self.type.__name__})"


class Lifecycle(Enum):
    """
    This enum defines the lifecycle events that can be processed by lifecycle processors.
    """

    __slots__ = []

    ON_INIT = auto()
    ON_DESTROY = auto()

class LifecycleProcessor(ABC):
    """
    A LifecycleProcessor is used to perform any side effects on managed objects during their lifecycle.
    """
    __slots__ = []

    # constructor

    def __init__(self):
        pass

    # methods

    @abstractmethod
    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        pass

class PostProcessor(LifecycleProcessor):
    """
    Base class for custom post processors that are executed after object creation.
    """
    __slots__ = []

    # constructor

    def __init__(self):
        super().__init__()

    def process(self, instance: object):
        pass

    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle == Lifecycle.ON_INIT:
            self.process(instance)


class Providers:
    """
    The Providers class is a static class that manages the registration and resolution of InstanceProviders.
    """
    # local class

    class Context:
        __slots__ = ["dependencies"]

        def __init__(self):
            self.dependencies : list[AbstractInstanceProvider] = []

        def add(self, *providers: AbstractInstanceProvider):
            for provider in providers:
                if next((p for p in self.dependencies if p.get_type() is provider.get_type()), None) is not None:
                    raise InjectorException(self.cycleReport(provider))

                self.dependencies.append(provider)

        def cycleReport(self, provider: AbstractInstanceProvider):
            cycle = ""

            first = True
            for p in self.dependencies:
                if not first:
                    cycle += " -> "

                first = False

                cycle += f"{p.get_type().__name__}"

            cycle += f" -> {provider.get_type().__name__}"

            return cycle


    # class properties

    providers : Dict[Type,AbstractInstanceProvider] = dict()
    cache: Dict[Type, AbstractInstanceProvider] = dict()

    resolved = False

    @classmethod
    def register(cls, provider: AbstractInstanceProvider):
        Environment.logger.debug(f"register provider {provider.get_type().__qualname__}({provider.get_type().__name__})")

        # local functions

        def is_injectable(type: Type) -> bool:
            if type is object:
                return False

            if inspect.isabstract(type):
                return False

            #for decorator in Decorators.get(type):
            #    if decorator.decorator is injectable:
            #        return True

            # darn

            return True

        def cacheProviderForType(provider: AbstractInstanceProvider, type: Type):
            existing_provider = Providers.cache.get(type)
            if existing_provider is None:
                Providers.cache[type] = provider

            else:
                if type is provider.get_type():
                    raise InjectorException(f"{type} already registered")

                if isinstance(existing_provider, AmbiguousProvider):
                    cast(AmbiguousProvider, existing_provider).add_provider(provider)
                else:
                    Providers.cache[type] = AmbiguousProvider(type, existing_provider, provider)

            # recursion

            for superClass in type.__bases__:
                if is_injectable(superClass):
                    cacheProviderForType(provider, superClass)

        # go

        Providers.providers[provider.get_type()] = provider

        # cache providers

        cacheProviderForType(provider, provider.get_type())

    @classmethod
    def resolve(cls):
        if not Providers.resolved:
            Providers.resolved = True

            for provider in Providers.providers.values():
                provider.resolve(Providers.Context())

        #Providers.report()

    @classmethod
    def report(cls):
        for provider in Providers.cache.values():
            print(f"provider {provider.get_type().__qualname__}")

    @classmethod
    def getProvider(cls, type: Type) -> AbstractInstanceProvider:
        provider = Providers.cache.get(type, None)
        if provider is None:
            raise InjectorException(f"{type.__name__} not registered as injectable")

        return provider

def registerFactories(cls: Type):
    descriptor = TypeDescriptor.for_type(cls)

    for method in descriptor.methods.values():
        if method.has_decorator(create):
            create_decorator = method.get_decorator(create)
            Providers.register(FunctionInstanceProvider(cls, method.method, method.returnType, create_decorator.args[0],
                                                        create_decorator.args[1]))

def injectable(eager=True, singleton=True):
    """
    Instances of classes that are annotated with @injectable can be created by an Environment.
    """
    def decorator(cls):
        Decorators.add(cls, injectable)

        Providers.register(ClassInstanceProvider(cls, eager, singleton))

        #TODO registerFactories(cls)

        return cls

    return decorator

def factory(eager=True, singleton=True):
    """
    Decorator that needs to be used on a class that implements the Factory interface.
    """
    def decorator(cls):
        Decorators.add(cls, factory)

        Providers.register(ClassInstanceProvider(cls, eager, singleton))
        Providers.register(FactoryInstanceProvider(cls, eager, singleton))

        return cls

    return decorator

def create(eager=True, singleton=True):
    """
    Any method annotated with @create will be registered as a factory method.
    """
    def decorator(func):
        Decorators.add(func, create, eager, singleton)
        return func

    return decorator

def on_init():
    """
    Methods annotated with @on_init will be called when the instance is created."""
    def decorator(func):
        Decorators.add(func, on_init)
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
        Providers.register(ClassInstanceProvider(cls, True, True))

        Decorators.add(cls, environment, imports)
        Decorators.add(cls, injectable) # do we need that?

        registerFactories(cls)

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

class Environment:
    """
    Central class that manages the lifecycle of instances and their dependencies.
    """

    # static data

    logger = logging.getLogger(__name__)  # __name__ = module name

    instance : 'Environment' = None

    __slots__ = [
        "providers",
        "lifecycleProcessors",
        "parent",
        "instances"
    ]

    # constructor
    def __init__(self, env: Type, parent : Optional[Environment] = None):
        """
        Creates a new Environment instance.

        Args:
            env (Type): The environment class that controls the scanning of managed objects.
            parent (Optional[Environment]): Optional parent environment, whose objects are inherited.
        """
        # initialize

        self.parent = parent
        self.providers: Dict[Type, AbstractInstanceProvider] = dict()
        self.lifecycleProcessors: list[LifecycleProcessor] = []

        if self.parent is not None:
            self.providers |= self.parent.providers
            self.lifecycleProcessors += self.parent.lifecycleProcessors

        self.instances = []

        Environment.instance = self

        # resolve providers on a static basis. This is only executed once!

        Providers.resolve()

        loaded = set()

        def add_provider(type: Type, provider: AbstractInstanceProvider):
            Environment.logger.debug(f"\tadd provider {provider} for {type})")

            self.providers[type] = provider

        def load_environment(env: Type):
            if env not in loaded:
                Environment.logger.debug(f"load environment {env.__qualname__}")

                loaded.add(env)

                # sanity check

                decorator = TypeDescriptor.for_type(env).get_decorator(environment)
                if decorator is None:
                    raise InjectorException(f"{env.__name__} is not an environment class")

                scan = env.__module__  # maybe add parameters as well

                # recursion

                for import_environment in decorator.args[0] or []:
                    load_environment(import_environment)

                # load providers

                #{k: v for k, v in my_dict.items() if v % 2 == 0}

                localProviders = {type: provider for type, provider in Providers.cache.items() if provider.get_module().startswith(scan)}

                # register providers

                for type, provider in localProviders.items():
                    self.providers[type] = EnvironmentInstanceProvider(self, provider)

                # tweak dependencies

                for type, provider in localProviders.items():
                    cast(EnvironmentInstanceProvider, self.providers[type]).tweakDependencies(self.providers)

        # load environments

        if parent is None:
            load_environment(DIEnvironment) # internal stuff

        load_environment(env)

        # construct eager objects

        for provider in self.providers.values():
            if provider.is_eager():
                provider.create(self)
    # internal

    def executeProcessors(self, lifecycle: Lifecycle, instance: T) -> T:
        for processor in self.lifecycleProcessors:
            processor.processLifecycle(lifecycle, instance, self)

        return instance

    def created(self, instance: T) -> T:
        # remember lifecycle processors

        if isinstance(instance, LifecycleProcessor):
            self.lifecycleProcessors.append(instance)

        # remember instance

        self.instances.append(instance)

        # execute processors

        return self.executeProcessors(Lifecycle.ON_INIT, instance)

    # public

    def destroy(self):
        """
        destroy all managed instances by calling the appropriate lifecycle methods
        """
        for instance in self.instances:
            self.executeProcessors(Lifecycle.ON_DESTROY, instance)

        self.instances.clear() # make the cy happy

    def get(self, type: Type[T]) -> T:
        """
        Return and possibly create a new instance of the given type.

        Arguments:
            type (Type): The desired type

        Returns: The requested instance
        """
        provider = self.providers.get(type, None)
        if provider is None:
            Environment.logger.error(f"{type} is not supported")
            raise InjectorException(f"{type} is not supported")

        return provider.create(self)

class LifecycleCallable:
    __slots__ = [
        "decorator",
        "lifecycle"
    ]

    def __init__(self, decorator, processor: CallableProcessor, lifecycle: Lifecycle):
        self.decorator = decorator
        self.lifecycle = lifecycle

        processor.register(self)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return []

@injectable()
class CallableProcessor(LifecycleProcessor):
    # local classes

    class MethodCall:
        __slots__ = [
            "decorator",
            "method",
            "lifecycleCallable"
        ]

        # constructor

        def __init__(self, method: TypeDescriptor.MethodDescriptor, decorator: DecoratorDescriptor, lifecycleCallable: LifecycleCallable):
            self.decorator = decorator
            self.method = method
            self.lifecycleCallable = lifecycleCallable

        def execute(self, instance, environment: Environment):
            self.method.method(instance, *self.lifecycleCallable.args(self.decorator, self.method, environment))

        def __str__(self):
            return f"MethodCall({self.method.method.__name__})"

    # constructor

    def __init__(self):
        super().__init__()

        self.callables : Dict[object,LifecycleCallable] = dict()
        self.cache : Dict[Type,list[CallableProcessor.MethodCall]]  = dict()

    def computeCallables(self, type: Type) -> list[CallableProcessor.MethodCall] :
        descriptor = TypeDescriptor.for_type(type)

        result = []

        for method in descriptor.methods.values():
            for decorator in method.decorators:
                if self.callables.get(decorator.decorator) is not None:
                    result.append(CallableProcessor.MethodCall(method, decorator, self.callables[decorator.decorator]))

        return result

    def callablesFor(self, type: Type)-> list[CallableProcessor.MethodCall]:
        callables = self.cache.get(type, None)
        if callables is None:
            callables = self.computeCallables(type)
            self.cache[type] = callables

        return callables

    def register(self, callable: LifecycleCallable):
        self.callables[callable.decorator] = callable

    # implement

    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        callables = self.callablesFor(type(instance))
        for callable in callables:
            if callable.lifecycleCallable.lifecycle is lifecycle:
                callable.execute(instance, environment)

@injectable()
class OnInitLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(on_init, processor, Lifecycle.ON_INIT)

@injectable()
class OnDestroyLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(on_destroy, processor, Lifecycle.ON_DESTROY)

@injectable()
class EnvironmentAwareLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(inject_environment, processor, Lifecycle.ON_INIT)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment]

@injectable()
class InjectLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(inject, processor, Lifecycle.ON_INIT)

    # override

    def args(self, decorator: DecoratorDescriptor,  method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment.get(type) for type in method.paramTypes]

##

# internal class that is required to import technical instance providers

@environment()
class DIEnvironment:
    __slots__ = []

    def __init__(self):
        pass