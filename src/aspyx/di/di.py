from __future__ import annotations

import logging
import threading
from abc import abstractmethod, ABC
from enum import Enum, auto
from typing import Type, Dict, TypeVar, Generic, Optional

from aspyx.reflection import Decorators, TypeDescriptor, DecoratorDescriptor

T = TypeVar("T")

class Factory(ABC, Generic[T]):
    __slots__ = []

    @abstractmethod
    def create(self) -> T:
        pass

class InjectorError(Exception):
    pass

class InstanceProvider(ABC, Generic[T]):
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
        self.dependencies : Optional[list[InstanceProvider]] = None

    def module(self):
        return self.host.__module__

    def addDependency(self, provider: InstanceProvider):
        if any(issubclass(provider.type, dependency.type) for dependency in self.dependencies):
            return False

        self.dependencies.append(provider)

        return True

    def getArguments(self,  environment: Environment):
        return [provider.create(environment) for provider in self.dependencies]

    def resolve(self, context: Providers.Context)-> InstanceProvider:
        # add this to subclasses

        if self.dependencies is not None:
            return self

        return self

    @abstractmethod
    def create(self, environment: Environment):
        pass

class SingletonProvider(InstanceProvider):
    __slots__ = [
        "provider",
        "value",
        "_lock"
    ]

    # constructor

    def __init__(self, provider: InstanceProvider):
        super().__init__(provider.host, provider.type, provider.eager, provider.singleton)

        self.provider = provider
        self.value = None
        self._lock = threading.Lock()

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.provider.resolve(context)

            self.dependencies = self.provider.dependencies
        else:  # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def __str__(self):
        return f"SingletonProvider({self.provider})"

    def create(self, environment: Environment):
        if self.value is None:
            with self._lock:
                self.value = self.provider.create(environment)

        return self.value

class ClassInstanceProvider(InstanceProvider[T]):
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

            init = TypeDescriptor.forType(self.type).get_method("__init__")
            if init is None:
                raise InjectorError(f"{self.type.__name__} does not implement __init__")

            for param in init.paramTypes:
                provider = Providers.getProvider(param)
                self.params += 1
                if self.addDependency(provider):
                    provider.resolve(context)

            # check @inject

            for method in TypeDescriptor.forType(self.type).methods.values():
                if method.has_decorator(inject):
                    for param in method.paramTypes:
                        provider = Providers.getProvider(param)

                        if self.addDependency(provider):
                            provider.resolve(context)
        else: # check if the dependencies create a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment):
        Environment.logger.debug(f"create class {self.type.__qualname__}")

        args = self.getArguments(environment)[:self.params]
        return environment.created(self.type(*args))

    # object

    def __str__(self):
        return f"ClassInstanceProvider({self.type.__name__})"

class FunctionInstanceProvider(InstanceProvider[T]):
    __slots__ = [
        "method"
    ]

    # constructor

    def __init__(self, clazz : Type, method, return_type : Type[T], eager = True, singleton = True):
        super().__init__(clazz, return_type, eager, singleton)

        self.method = method

    # implement

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            provider = Providers.getProvider(self.host)
            if self.addDependency(provider):
                provider.resolve(context)
        else: # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment):
        Environment.logger.debug(f"create class {self.type.__qualname__}")

        configuration = self.getArguments(environment)[0]

        instance = self.method(configuration)

        return environment.created(instance)

    def __str__(self):
        return f"FunctionInstanceProvider({self.host.__name__}.{self.method.__name__} -> {self.type.__name__})"

class FactoryInstanceProvider(InstanceProvider):
    __slots__ = []

    # class method

    @classmethod
    def getFactoryType(cls, clazz):
        return TypeDescriptor.forType(clazz).get_local_method("create").returnType

    # constructor

    def __init__(self, factory: Type, eager: bool, singleton: bool):
        super().__init__(factory, FactoryInstanceProvider.getFactoryType(factory), eager, singleton)

    # implement

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            provider = Providers.getProvider(self.host)
            if self.addDependency(provider):
                provider.resolve(context)

        else: # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment):
        Environment.logger.debug(f"create class {self.type.__qualname__}")

        return environment.created(self.getArguments(environment)[0].create())

    def __str__(self):
        return f"FactoryInstanceProvider({self.host.__name__} -> {self.type.__name__})"


class Lifecycle(Enum):
    ON_CREATE = auto()
    ON_DESTROY = auto()

class LifecycleProcessor(ABC):
    __slots__ = []

    # constructor

    def __init__(self):
        pass

    # methods

    @abstractmethod
    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        pass

class PostProcessor(LifecycleProcessor):
    __slots__ = []

    # constructor

    def __init__(self):
        super().__init__()

    def process(self, instance: object):
        pass

    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle == Lifecycle.ON_CREATE:
            self.process(instance)


class Providers:
    # local class

    class Context:
        __slots__ = ["dependencies"]

        def __init__(self):
            self.dependencies : list[InstanceProvider] = []

        def add(self, *providers: InstanceProvider):
            for provider in providers:
                if next((p for p in self.dependencies if p.type is provider.type), None) is not None:
                    raise InjectorError(self.cycleReport(provider))

                self.dependencies.append(provider)

        def cycleReport(self, provider: InstanceProvider):
            cycle = ""

            first = True
            for p in self.dependencies:
                if not first:
                    cycle += " -> "

                first = False

                cycle += f"{p.type.__name__}"

            cycle += f" -> {provider.type.__name__}"

            return cycle


    # class properties

    providers : Dict[Type,InstanceProvider] = dict()
    cache: Dict[Type, InstanceProvider] = dict()

    resolved = False

    @classmethod
    def register(cls, provider: InstanceProvider):
        Environment.logger.debug(f"register {provider.type.__qualname__}")

        # local functions

        def isInjectable(type: Type) -> bool:
            if type is object:
                return False

            for decorator in Decorators.get(type):
                if decorator.decorator is injectable:
                    return True

            return False

        def cacheProviderForType(provider: InstanceProvider, type: Type):
            if Providers.cache.get(type) is None:
                Providers.cache[type] = provider

            else:
                raise InjectorError(f"{type} already registered")

            # recursion

            for superClass in type.__bases__:
                if isInjectable(superClass):
                    cacheProviderForType(provider, superClass) # TODO ?????

        # go

        Providers.providers[provider.type] = provider

        # singleton handling

        if provider.singleton:
            provider = SingletonProvider(provider)

        # cache providers

        cacheProviderForType(provider, provider.type)

    @classmethod
    def resolve(cls):
        if not Providers.resolved:
            Providers.resolved = True

            for provider in Providers.providers.values():
                provider.resolve(Providers.Context())

        #Providers.report()

    @classmethod
    def report(cls):
        for provider in Providers.providers.values():
            print(f"provider {provider.type.__qualname__}")

    @classmethod
    def getProvider(cls, type: Type) -> InstanceProvider:
        provider = Providers.cache.get(type, None)
        if provider is None:
            raise InjectorError(f"{type.__name__} not registered as injectable")

        return provider

def registerFactories(cls: Type):
    descriptor = TypeDescriptor.forType(cls)

    for method in descriptor.methods.values():
        if method.has_decorator(create):
            create_decorator = method.get_decorator(create)
            Providers.register(FunctionInstanceProvider(cls, method.method, method.returnType, create_decorator.args[0],
                                                        create_decorator.args[1]))

def injectable(eager=True, singleton=True):
    def decorator(cls):
        Decorators.add(cls, injectable)

        Providers.register(ClassInstanceProvider(cls, eager, singleton))

        #TODOregisterFactories(cls)

        return cls

    return decorator

def factory(eager=True, singleton=True):
    def decorator(cls):
        Decorators.add(cls, factory)

        Providers.register(ClassInstanceProvider(cls, eager, singleton))
        Providers.register(FactoryInstanceProvider(cls, eager, singleton))

        return cls

    return decorator

def create(eager=True, singleton=True):
    def decorator(func):
        Decorators.add(func, create, eager, singleton)
        return func

    return decorator

def on_init():
    def decorator(func):
        Decorators.add(func, on_init)
        return func

    return decorator

def on_destroy():
    def decorator(func):
        Decorators.add(func, on_destroy)
        return func

    return decorator

def configuration(imports: Optional[list[Type]] = None):
    def decorator(cls):
        Providers.register(ClassInstanceProvider(cls, True, True))

        Decorators.add(cls, configuration, imports)
        Decorators.add(cls, injectable) # do we need that?

        registerFactories(cls)

        return cls

    return decorator

def inject():
    def decorator(func):
        Decorators.add(func, inject)
        return func

    return decorator

def inject_environment():
    def decorator(func):
        Decorators.add(func, inject_environment)
        return func

    return decorator

class Environment:
    # local class

    class Instance:
        __slots__ = ["instance"]

        def __init__(self, instance):
            self.instance = instance

        def __str__(self):
            return f"Instance({self.instance.__class__})"

    # static data

    logger = logging.getLogger(__name__)  # __name__ = module name

    instance : 'Environment' = None

    __slots__ = [
        "providers",
        "lifecycleProcessors",
        "instances"
    ]

    # constructor

    def __init__(self, conf: Type, parent : Optional[Environment] = None):
        # initialize

        self.providers: Dict[Type, InstanceProvider] = dict()
        self.lifecycleProcessors: list[LifecycleProcessor] = []
        self.instances: list[Environment.Instance] = []

        Environment.instance = self

        # resolve providers on a static basis. This is only executed once!

        Providers.resolve()

        loaded = set()

        def addProvider(provider: InstanceProvider):
            Environment.logger.debug(f"\tadd provider {provider.host.__qualname__}")

            self.providers[provider.type] = Providers.getProvider(provider.type)

        def loadConfiguration(conf: Type):
            if conf not in loaded:
                Environment.logger.debug(f"load configuration {conf.__qualname__}")

                loaded.add(conf)

                # sanity check

                decorator = TypeDescriptor.forType(conf).get_decorator(configuration)
                if decorator is None:
                    raise InjectorError(f"{conf.__name__} is not a configuration class")

                scan = conf.__module__  # maybe add parameters as well

                # recursion

                for importConfiguration in decorator.args[0] or []:
                    loadConfiguration(importConfiguration)

                # load providers

                for provider in Providers.providers.values():
                    if provider.module().startswith(scan):
                        addProvider(provider)

        # load configurations

        loadConfiguration(DIConfiguration) # internal stuff
        loadConfiguration(conf)

        # construct eager objects

        for provider in self.providers.values():
            if provider.eager:
                provider.create(self)

        #for provider in Providers.providers.values():
        #    if provider.eager:
        #        Providers.getProvider(provider.type).create(self) # here we need the singletons...

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

        self.instances.append(Environment.Instance(instance))

        # execute processors

        return self.executeProcessors(Lifecycle.ON_CREATE, instance)

    # public

    def shutdown(self):
        for instance in self.instances:
            self.executeProcessors(Lifecycle.ON_DESTROY, instance.instance)

    def get(self, type: Type[T]) -> T:
        return self.providers[type].create(self) # TODO cache, etc.

class Callable:
    __slots__ = ["decorator", "lifecycle"]

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
        __slots__ = ["decorator", "method", "callable"]

        # constructor

        def __init__(self, method: TypeDescriptor.MethodDescriptor, decorator: DecoratorDescriptor, callable: Callable):
            self.decorator = decorator
            self.method = method
            self.callable = callable

        def execute(self, instance, environment: Environment):
            self.method.method(instance, *self.callable.args(self.decorator, self.method, environment))

        def __str__(self):
            return f"MethodCall({self.method.method.__name__})"

    # constructor

    def __init__(self):
        super().__init__()

        self.callables : Dict[object,Callable] = dict()
        self.cache : Dict[Type,list[CallableProcessor.MethodCall]]  = dict()

    def computeCallables(self, type: Type) -> list[CallableProcessor.MethodCall] :
        descriptor = TypeDescriptor.forType(type)

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

    def register(self, callable: Callable):
        self.callables[callable.decorator] = callable

    # implement

    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        callables = self.callablesFor(type(instance))
        for callable in callables:
            if callable.callable.lifecycle is lifecycle:
                callable.execute(instance, environment)

@injectable()
class OnInitCallable(Callable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(on_init, processor, Lifecycle.ON_CREATE)

@injectable()
class OnDestroyCallable(Callable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(on_destroy, processor, Lifecycle.ON_DESTROY)

@injectable()
class EnvironmentAwareCallable(Callable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(inject_environment, processor, Lifecycle.ON_CREATE)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment]

@injectable()
class InjectCallable(Callable):
    __slots__ = []

    def __init__(self, processor: CallableProcessor):
        super().__init__(inject, processor, Lifecycle.ON_CREATE)

    # override

    def args(self, decorator: DecoratorDescriptor,  method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment.get(type) for type in method.paramTypes]

# internal class that is required to import technical instance providers

@configuration()
class DIConfiguration:
    __slots__ = []

    def __init__(self):
        pass