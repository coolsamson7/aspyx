from __future__ import annotations

from abc import abstractmethod, ABC
from enum import Enum, auto
from typing import Type, Dict, TypeVar, Generic, Optional

from aspyx.reflection import Decorators, TypeDescriptor, DecoratorDescriptor

T = TypeVar("T")

class Factory(ABC, Generic[T]):
    @abstractmethod
    def create(self) -> T:
        pass

class InjectorError(Exception):
    pass

class InstanceProvider(ABC, Generic[T]):
    # constructor

    def __init__(self, t: Type[T], eager: bool, singleton: bool):
        self.type = t
        self.eager = eager
        self.singleton = singleton
        self.dependencies : Optional[list[InstanceProvider]] = None

    def addDependency(self, provider: InstanceProvider):
        self.dependencies.append(provider)

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
    # constructor

    def __init__(self, provider: InstanceProvider):
        super().__init__(provider.type, provider.eager, provider.singleton)

        self.provider = provider
        self.value = None

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
            self.value = self.provider.create(environment)

        return self.value

class ClassInstanceProvider(InstanceProvider[T]):
    # constructor

    def __init__(self, t: Type[T], eager: bool, singleton: bool):
        super().__init__(t, eager, singleton)

        self.params = 0

    # implement

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            # check constructor

            init = TypeDescriptor.forType(self.type).getLocalMethod("__init__")
            if init is None:
                print("kk")

            for param in TypeDescriptor.forType(self.type).getLocalMethod("__init__").paramTypes:
                provider = Providers.getProvider(param)
                self.params += 1
                self.addDependency(provider)
                provider.resolve(context)

            # check @inject

            for method in TypeDescriptor.forType(self.type).methods.values():
                if method.hasDecorator(inject):
                    # todo error handling
                    provider = Providers.getProvider(method.paramTypes[0])

                    self.addDependency(provider)
                    provider.resolve(context)
                    pass
        else: # check if the dependencies create a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment):
        args = self.getArguments(environment)[:self.params]
        return environment.created(self.type(*args))

    # object

    def __str__(self):
        return f"ClassInstanceProvider({self.type.__name__})"

class FunctionInstanceProvider(InstanceProvider[T]):
    # constructor

    def __init__(self, clazz : Type, method, return_type : Type[T], eager = True, singleton = True):
        super().__init__(return_type, eager, singleton)

        self.clazz = clazz
        self.method = method

    # implement

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            provider = Providers.getProvider(self.clazz)
            self.addDependency(provider)
            provider.resolve(context)
        else: # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment):
        configuration = self.getArguments(environment)[0]

        instance = self.method(configuration)

        return environment.created(instance)

    def __str__(self):
        return f"FunctionInstanceProvider({self.clazz.__name__}.{self.method.__name__} -> {self.type.__name__})"

class FactoryInstanceProvider(InstanceProvider):
    # class method

    @classmethod
    def getFactoryType(cls, clazz):
        return TypeDescriptor.forType(clazz).getLocalMethod("create").returnType

    # constructor

    def __init__(self, factory: Type, eager: bool, singleton: bool):
        super().__init__(FactoryInstanceProvider.getFactoryType(factory), eager, singleton)

        self.factory = factory

    # implement

    def resolve(self, context: Providers.Context) -> InstanceProvider:
        if self.dependencies is None:
            self.dependencies = []

            context.add(self)

            provider = Providers.getProvider(self.factory)
            self.addDependency(provider)
            provider.resolve(context)
        else: # check if the dependencies crate a cycle
            context.add(*self.dependencies)

        return self

    def create(self, environment: Environment):
        return environment.created(self.getArguments(environment)[0].create())

    def __str__(self):
        return f"FactoryInstanceProvider({self.factory.__name__} -> {self.type.__name__})"


class Lifecycle(Enum):
    ON_CREATE = auto()
    ON_DESTROY = auto()

class LifecycleProcessor(ABC):
    # constructor

    def __init__(self):
        pass

    # methods

    @abstractmethod
    def processLifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        pass

class PostProcessor(LifecycleProcessor):
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
                    cacheProviderForType(provider, superClass)

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

    @classmethod
    def getProvider(cls, type: Type) -> InstanceProvider:
        provider = Providers.cache.get(type)
        if provider is None:
            raise InjectorError(f"{type} not registered")

        return provider

def injectable(eager=True, singleton=True):
    def decorator(cls):
        Decorators.add(cls, injectable)

        Providers.register(ClassInstanceProvider(cls, eager, singleton))

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

def configuration():
    def decorator(cls):
        Decorators.add(cls, configuration)
        #Decorators.add(cls, component)

        descriptor = TypeDescriptor.forType(cls)

        for method in descriptor.methods.values():
            if method.hasDecorator(create):
                create_decorator = method.getDecorator(create)
                Providers.register(FunctionInstanceProvider(cls, method.method, method.returnType, create_decorator.args[0], create_decorator.args[1]))

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
        def __init__(self, instance):
            self.instance = instance

        def __str__(self):
            return f"Instance({self.instance.__class__})"

    instance : 'Environment' = None

    # constructor

    def __init__(self):
        self.lifecycleProcessors: list[LifecycleProcessor] = []
        self.instances: list[Environment.Instance] = []

        Environment.instance = self

        # resolve

        Providers.resolve()

        # construct eager objects

        for provider in Providers.providers.values():
            if provider.eager:
                Providers.getProvider(provider.type).create(self) # here we need the singletons...

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
        return Providers.getProvider(type).create(self)

class Callable:
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
    def __init__(self, processor: CallableProcessor):
        super().__init__(on_init, processor, Lifecycle.ON_CREATE)

@injectable()
class OnDestroyCallable(Callable):
    def __init__(self, processor: CallableProcessor):
        super().__init__(on_destroy, processor, Lifecycle.ON_DESTROY)

@injectable()
class EnvironmentAwareCallable(Callable):
    def __init__(self, processor: CallableProcessor):
        super().__init__(inject_environment, processor, Lifecycle.ON_CREATE)

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment]

@injectable()
class InjectCallable(Callable):
    def __init__(self, processor: CallableProcessor):
        super().__init__(inject, processor, Lifecycle.ON_CREATE)

    # override

    def args(self, decorator: DecoratorDescriptor,  method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [environment.get(method.paramTypes[0])]


# TODO

# configuration & component?
