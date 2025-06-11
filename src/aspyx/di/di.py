from __future__ import annotations

import inspect
import logging

from abc import abstractmethod, ABC
from enum import Enum, auto
import threading
from typing import Type, Dict, TypeVar, Generic, Optional, cast, Callable

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
    def get_scope(self) -> str:
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
        "scope",
        "dependencies"
    ]

    # constructor

    def __init__(self, host: Type, t: Type[T], eager: bool, scope: str):
        self.host = host
        self.type = t
        self.eager = eager
        self.scope = scope
        self.dependencies : Optional[list[AbstractInstanceProvider]] = None

    # implement AbstractInstanceProvider

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        return self

    def get_module(self) -> str:
        return self.host.__module__

    def get_type(self) -> Type[T]:
        return self.type

    def is_eager(self) -> bool:
        return self.eager

    def get_scope(self) -> str:
        return self.scope

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

    def get_dependencies(self) -> list[AbstractInstanceProvider]:
        return []

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        return self

    def create(self, environment: Environment, *args):
        raise InjectorException(f"multiple candidates for type {self.type}")

    def __str__(self):
        return f"AmbiguousProvider({self.type})"

class Scopes:
    # static data

    scopes : Dict[str, Type] = {}

    # class methods

    @classmethod
    def get(cls, scope: str, environment: Environment):
        scopeType = Scopes.scopes.get(scope, None)
        if scopeType is None:
            raise InjectorException(f"unknown scope type {scope}")

        return environment.get(scopeType)

    @classmethod
    def register(cls, scopeClass: Type, name: str):
        Scopes.scopes[name] = scopeClass

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

class EnvironmentInstanceProvider(AbstractInstanceProvider):
    # properties

    __slots__ = [
        "environment",
        "scopeInstance",
        "provider",
        "dependencies",
    ]

    # constructor

    def __init__(self, environment: Environment, provider: AbstractInstanceProvider):
        super().__init__()

        self.environment = environment
        self.provider = provider
        self.dependencies : list[AbstractInstanceProvider] = []

        self.scopeInstance = Scopes.get(provider.get_scope(), environment)
        print()

    # implement

    def resolve(self, context: Providers.Context) -> AbstractInstanceProvider:
        pass # noop

    def get_module(self) -> str:
        return self.provider.get_module()

    def get_type(self) -> Type[T]:
        return self.provider.get_type()

    def is_eager(self) -> bool:
        return self.provider.is_eager()

    def get_scope(self) -> str:
        return self.provider.get_scope()

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
        return self.scopeInstance.get(self.provider, self.environment, lambda: [provider.create(env) for provider in self.dependencies] ) # already scope property!

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

    def __init__(self, clazz : Type, method, return_type : Type[T], eager = True, scope = "singleton"):
        super().__init__(clazz, return_type, eager, scope)

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

    def __init__(self, factory: Type, eager: bool, scope: str):
        super().__init__(factory, FactoryInstanceProvider.getFactoryType(factory), eager, scope)

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

    def process(self, instance: object, environment: Environment):
        pass

    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle == Lifecycle.ON_INIT:
            self.process(instance, environment)


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

    check: list[AbstractInstanceProvider] = list()

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

        Providers.check.append(provider)

        Providers.providers[provider.get_type()] = provider

        # cache providers

        cacheProviderForType(provider, provider.get_type())

    @classmethod
    def resolve(cls):
        for provider in Providers.check:
            provider.resolve(Providers.Context())

        Providers.check.clear()

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

        #TODO registerFactories(cls)

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
        "type",
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

        self.type = env
        self.parent = parent
        if self.parent is None and env is not BootEnvironment:
            self.parent = BootEnvironment.get_instance() # inherit environment including its manged instances!

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

        # bootstrapping hack, they will be overwritten by the "real" providers

        if env is BootEnvironment:
            add_provider(SingletonScope, SingletonScopeInstanceProvider())
            add_provider(RequestScope, RequestScopeInstanceProvider())

        def load_environment(env: Type):
            if env not in loaded:
                Environment.logger.debug(f"load environment {env.__qualname__}")

                loaded.add(env)

                # sanity check

                decorator = TypeDescriptor.for_type(env).get_decorator(environment)
                if decorator is None:
                    raise InjectorException(f"{env.__name__} is not an environment class")

                scan = env.__module__
                if "." in scan:
                    scan = scan.rsplit('.', 1)[0]

                # recursion

                for import_environment in decorator.args[0] or []:
                    load_environment(import_environment)

                # load providers

                localProviders = {type: provider for type, provider in Providers.cache.items() if provider.get_module().startswith(scan)}

                # register providers

                # make sure, that for every type ony a single EnvironmentInstanceProvider is created!
                # otherwise inheritance will fuck it up

                environmentProviders : dict[AbstractInstanceProvider, EnvironmentInstanceProvider] = {}

                for type, provider in localProviders.items():
                    environmentProvider = environmentProviders.get(provider, None)
                    if environmentProvider is None:
                        environmentProvider =  EnvironmentInstanceProvider(self, provider)
                        environmentProviders[provider] = environmentProvider

                    add_provider(type, environmentProvider)

                # tweak dependencies

                for type, provider in localProviders.items():
                    cast(EnvironmentInstanceProvider, self.providers[type]).tweakDependencies(self.providers)

                # return local providers

                return environmentProviders.values()
            else:
                return []

        # construct eager objects for local providers

        for provider in load_environment(env):
            if provider.is_eager():
                provider.create(self)
    # internal

    def executeProcessors(self, lifecycle: Lifecycle, instance: T) -> T:
        for processor in self.lifecycleProcessors:
            processor.processLifecycle(lifecycle, instance, self)

        return instance

    def created(self, instance: T) -> T:
        def get_order(type: TypeDescriptor) -> int:
            if type.has_decorator(order):
                return type.get_decorator(order).args[0]
            else:
                return 10

        # remember lifecycle processors

        if isinstance(instance, LifecycleProcessor):
            self.lifecycleProcessors.append(instance)

            # sort immediately

            self.lifecycleProcessors.sort(key=lambda processor: processor.order)

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
        "lifecycle",
        "order"
    ]

    def __init__(self, decorator, processor: CallableProcessor, lifecycle: Lifecycle):
        self.decorator = decorator
        self.lifecycle = lifecycle
        self.order = 0

        if TypeDescriptor.for_type(type(self)).has_decorator(order):
            self.order =  TypeDescriptor.for_type(type(self)).get_decorator(order).args[0]

        processor.register(self)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return []

@injectable()
@order(1)
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

        # sort according to order

        result.sort(key=lambda call: call.lifecycleCallable.order)

        # done

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
@order(1000)
class OnInitLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(on_init, processor, Lifecycle.ON_INIT)

@injectable()
@order(1001)
class OnDestroyLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(on_destroy, processor, Lifecycle.ON_DESTROY)

@injectable()
@order(9)
class EnvironmentAwareLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(inject_environment, processor, Lifecycle.ON_INIT)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment]

@injectable()
@order(10)
class InjectLifecycleCallable(LifecycleCallable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(inject, processor, Lifecycle.ON_INIT)

    # override

    def args(self, decorator: DecoratorDescriptor,  method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment.get(type) for type in method.paramTypes]

def scope(name: str):
    def decorator(cls):
        Scopes.register(cls, name)

        Decorators.add(cls, scope)
        # Decorators.add(cls, injectable)

        Providers.register(ClassInstanceProvider(cls, eager=True, scope="request"))

        return cls

    return decorator

@scope("request")
class RequestScope(Scope):
    # properties

    __slots__ = [
    ]

    # constructor

    def __init__(self):
        super().__init__()

    # public

    def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
        return provider.create(environment, *argProvider())

@scope("singleton")
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
        self.lock = threading.Lock()

    # override

    def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
        if self.value is None:
            with self.lock:
                if self.value is None: 
                    self.value = provider.create(environment, *argProvider())

        return self.value

# internal class that is required to import technical instance providers

@environment()
class BootEnvironment:
    # class

    environment = None

    @classmethod
    def get_instance(cls):
        if BootEnvironment.environment is None:
            BootEnvironment.environment = Environment(BootEnvironment)

        return BootEnvironment.environment

    # properties

    __slots__ = []

    # constructor

    def __init__(self):
        pass