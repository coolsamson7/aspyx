"""
The dependency injection module provides a framework for managing dependencies and lifecycle of objects in Python applications.
"""
from __future__ import annotations

import inspect
import logging
import importlib
import pkgutil
import sys
import time

from abc import abstractmethod, ABC
from enum import Enum
import threading
from typing import Type, Dict, TypeVar, Generic, Optional, cast, Callable, TypedDict, Any

from aspyx.util import StringBuilder
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
    An AbstractInstanceProvider is responsible to create instances.
    """
    @abstractmethod
    def get_module(self) -> str:
        """
        return the module name of the provider

        Returns:
            str: the module name of the provider
        """

    def get_host(self) -> Type[T]:
        """
        return the class which is responsible for creation ( e.g. the injectable class )

        Returns:
            Type[T]: the class which is responsible for creation
        """
        return type(self)

    @abstractmethod
    def get_type(self) -> Type[T]:
        """
        return the type of the created instance
        
        Returns:
            Type[T: the type]
        """

    @abstractmethod
    def is_eager(self) -> bool:
        """
        return True, if the provider will eagerly construct instances

        Returns:
            bool: eager flag
        """

    @abstractmethod
    def get_scope(self) -> str:
        """
        return the scope name

        Returns:
            str: the scope name
        """


    def get_dependencies(self) -> (list[Type],int):
        """
        return the types that i depend on ( for constructor or setter injection  ).
        The second tuple element is the number of parameters that a construction injection will require

        Returns:
            (list[Type],int): the type array and the number of parameters
        """
        return [],1

    @abstractmethod
    def create(self, environment: Environment, *args) -> T:
        """
        Create a new instance.

        Args:
            environment: the Environment
            *args: the required arguments

        Returns:
            T: the instance
        """

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
        "scope",
        "param_providers",
        "_param_providers_initialized"
    ]

    # constructor

    def __init__(self, host: Type, t: Type[T], eager: bool, scope: str):
        self.host = host
        self.type = t
        self.eager = eager
        self.scope = scope
        self.param_providers: list[tuple[Optional[AnnotationInstanceProvider], Type]] = []
        self._param_providers_initialized = False

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

    # Shared parameter provider logic

    def _process_annotated_params(self, annotated_params) -> None:
        """
        Process annotated parameters and build param_providers list.
        Shared logic between ClassInstanceProvider and FunctionInstanceProvider.
        """
        for param in annotated_params:
            provider = None

            # Check for Environment type - special case for automatic injection
            if param.type is Environment:
                # Store special marker: ('environment', Environment) to indicate automatic environment injection
                provider = ('environment', Environment)
                self.param_providers.append(provider)
                continue

            # Check for annotation metadata
            for meta in param.metadata:
                resolver = AnnotationResolvers.get_resolver(type(meta))
                if resolver:
                    # Create annotation provider for this parameter
                    # Store tuple: (provider, param_type) so we can reconstruct dependencies
                    provider = (AnnotationInstanceProvider(resolver, meta, param.type), param.type)
                    break

            if provider is None:
                # Normal DI: store tuple (None, param_type)
                provider = (None, param.type)

            self.param_providers.append(provider)

    def _build_dependencies_from_params(self) -> list[Type]:
        """
        Build dependency list from param_providers.
        Shared logic between ClassInstanceProvider and FunctionInstanceProvider.
        """
        types: list[Type] = []

        for entry in self.param_providers:
            if entry:
                provider, param_type = entry
                if provider == 'environment':
                    # Environment type: no dependency needed, will inject current environment
                    continue
                elif provider is not None and provider != 'environment':
                    # Annotation-based: add resolver's dependencies
                    types.extend(provider.get_dependencies()[0])
                else:
                    # Normal DI: add parameter type directly
                    types.append(param_type)

        return types

    def _resolve_param_values(self, environment: Environment, args: tuple, start_index: int = 0) -> list:
        """
        Resolve parameter values from args using param_providers.
        Shared logic between ClassInstanceProvider and FunctionInstanceProvider.

        Args:
            environment: Current environment
            args: Dependency arguments
            start_index: Index in args to start from (0 for class, 1 for function)

        Returns:
            List of resolved parameter values
        """
        final_args = []
        dep_index = start_index

        for provider, param_type in self.param_providers:
            if provider == 'environment':
                # Environment type: inject current environment
                final_args.append(environment)
            elif provider is not None and provider != 'environment':
                # Annotation-based: call provider to resolve the value
                dep_count = len(provider.get_dependencies()[0])
                value = provider.create(environment, *args[dep_index:dep_index + dep_count])
                dep_index += dep_count
                final_args.append(value)
            else:
                # Normal DI: use the dependency directly
                final_args.append(args[dep_index])
                dep_index += 1

        return final_args

    @abstractmethod
    def create(self, environment: Environment, *args):
        pass

# we need this classes to bootstrap the system...
class SingletonScopeInstanceProvider(InstanceProvider):
    def __init__(self):
        super().__init__(SingletonScopeInstanceProvider, SingletonScope, False, "request")

    def create(self, environment: Environment, *args):
        return SingletonScope()

class EnvironmentScopeInstanceProvider(InstanceProvider):
    def __init__(self):
        super().__init__(SingletonScopeInstanceProvider, SingletonScope, False, "request")

    def create(self, environment: Environment, *args):
        return EnvironmentScope()

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
        self.dependencies : Optional[list[AbstractInstanceProvider]] = None # FOO
        self.scope_instance = Scopes.get(provider.get_scope(), environment)

    # public

    def print_tree(self, prefix=""):
        children = self.dependencies
        last_index = len(children) - 1
        print(prefix + "+- " + self.report())

        for i, child in enumerate(children):
            if i == last_index:
                # Last child
                child_prefix = prefix + "   "
            else:
                # Not last child
                child_prefix = prefix + "|  "


            cast(EnvironmentInstanceProvider, child).print_tree(child_prefix)

    # implement

    def resolve(self, context: Providers.ResolveContext):
        if self.dependencies is None:
            self.dependencies = []
            context.push(self)
            try:
                type_and_params = self.provider.get_dependencies()
                #params = type_and_params[1]
                for type in type_and_params[0]:
                    provider = context.require_provider(type)

                    self.dependencies.append(provider)

                    provider.resolve(context)
            finally:
                context.pop()

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

    def _init_param_providers(self):
        """Lazy initialization of parameter providers (called on first get_dependencies)"""
        if self._param_providers_initialized:
            return

        init = TypeDescriptor.for_type(self.type).get_method("__init__")
        if init is not None:
            annotated_params = init.get_annotated_params()
            self.params = len(annotated_params)
            self._process_annotated_params(annotated_params)

        self._param_providers_initialized = True

    # implement

    def check_factories(self):
        register_factories(self.host)

    def get_dependencies(self) -> (list[Type],int):
        # Lazy init: compute param_providers on first call
        self._init_param_providers()

        # Build dependency list using shared logic
        types = self._build_dependencies_from_params()

        # check @inject
        for method in TypeDescriptor.for_type(self.type).get_methods():
            if method.has_decorator(inject):
                # Check annotated params to handle annotation-based injection
                annotated_params = method.get_annotated_params()
                for param in annotated_params:
                    # Check if this parameter has an annotation resolver or is Environment type
                    has_resolver = False
                    for meta in param.metadata:
                        if AnnotationResolvers.get_resolver(type(meta)):
                            has_resolver = True
                            # Add the resolver's dependencies
                            resolver = AnnotationResolvers.get_resolver(type(meta))
                            provider = AnnotationInstanceProvider(resolver, meta, param.type)
                            types.extend(provider.get_dependencies()[0])
                            break

                    if not has_resolver:
                        # Environment type: no dependency needed
                        if param.type is Environment:
                            continue
                        # Normal DI: validate and add parameter type
                        if not Providers.is_registered(param.type):
                            raise DIRegistrationException(f"{self.type.__name__}.{method.method.__name__} declares an unknown parameter type {param.type.__name__}")
                        types.append(param.type)

        return types, self.params

    def create(self, environment: Environment, *args):
        Environment.logger.debug("%s create class %s", self, self.type.__qualname__)

        # If no param_providers, use old simple logic
        if not self.param_providers:
            return environment.created(self.type(*args[:self.params]))

        # Resolve parameter values using shared logic
        final_args = self._resolve_param_values(environment, args, start_index=0)

        return environment.created(self.type(*final_args))

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

    def __init__(self, clazz : Type, method: TypeDescriptor.MethodDescriptor, eager = True, scope = "singleton"):
        super().__init__(clazz, method.return_type, eager, scope)
        self.method : TypeDescriptor.MethodDescriptor = method

    def _init_param_providers(self):
        """Lazy initialization of parameter providers (called on first get_dependencies)"""
        if self._param_providers_initialized:
            return

        annotated_params = self.method.get_annotated_params()
        self._process_annotated_params(annotated_params)

        self._param_providers_initialized = True

    # implement

    def get_dependencies(self) -> (list[Type],int):
        # Lazy init: compute param_providers on first call
        self._init_param_providers()

        types = [self.host]  # First dependency is always the host class instance

        # Build dependency list using shared logic
        types.extend(self._build_dependencies_from_params())

        return types, 1 + len(self.param_providers)

    def create(self, environment: Environment, *args):
        Environment.logger.debug("%s create class %s", self, self.type.__qualname__)

        # If no param_providers (no parameters), use args directly
        if not self.param_providers:
            instance = self.method.method(*args) # args[0]=self
            return environment.created(instance)

        # args[0] is the host instance (self)
        host_instance = args[0]

        # Resolve parameter values using shared logic (start_index=1 to skip host instance)
        method_args = self._resolve_param_values(environment, args, start_index=1)

        instance = self.method.method(host_instance, *method_args)

        return environment.created(instance)

    def report(self) -> str:
        return f"{self.host.__name__}.{self.method.get_name()}({', '.join(t.__name__ for t in self.method.param_types)}) -> {self.type.__qualname__}"

    def __str__(self):
        return f"FunctionInstanceProvider({self.host.__name__}.{self.method.get_name()}({', '.join(t.__name__ for t in self.method.param_types)}) -> {self.type.__name__})"

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
        return f"{self.host.__name__}.create() -> {self.type.__name__} "

    def __str__(self):
        return f"FactoryInstanceProvider({self.host.__name__} -> {self.type.__name__})"


class Lifecycle(Enum):
    """
    This enum defines the lifecycle phases that can be processed by lifecycle processors.
    Phases are:

    - ON_INJECT
    - ON_INIT
    - ON_RUNNING
    - ON_DESTROY
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

    async def process_lifecycle_async(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        """Async version of process_lifecycle. Override in subclasses that need async processing."""
        # Default implementation calls the sync version
        return self.process_lifecycle(lifecycle, instance, environment)

class PostProcessor(LifecycleProcessor):
    """
    Base class for custom post processors that are executed after object creation.
    """
    __slots__ = []

    @abstractmethod
    def process(self, instance: object, environment: Environment):
        pass

    def process_lifecycle(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle == Lifecycle.ON_INIT:
            self.process(instance, environment)


class Providers:
    """
    The Providers class is a static class used in the context of the registration and resolution of InstanceProviders.
    """
    # local class

    class ResolveContext:
        __slots__ = [
            "providers",
            "path"
        ]

        # constructor

        def __init__(self, providers: Dict[Type, EnvironmentInstanceProvider]):
            self.providers = providers
            self.path = []

        # public

        def push(self, provider):
            self.path.append(provider)

        def pop(self):
            self.path.pop()

        def require_provider(self, type: Type) -> EnvironmentInstanceProvider:
            provider = self.providers.get(type, None)
            if provider is None:
                raise DIRegistrationException(f"Provider for {type} is not defined")

            if provider in self.path:
                raise DIRegistrationException(self.cycle_report(provider))

            return provider

        def cycle_report(self, provider: AbstractInstanceProvider):
            cycle = ""

            first = True
            for p in self.path:
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

    @classmethod
    def is_registered(cls,type: Type) -> bool:
        return Providers.providers.get(type, None) is not None

    # add factories lazily

    @classmethod
    def check_factories(cls):
        for check in Providers.check:
            check.check_factories()

        Providers.check.clear()

    @classmethod
    def filter(cls, environment: Environment, provider_filter: Callable) -> tuple[dict[Any, Any], list[Any]]:
        cache: Dict[Type,AbstractInstanceProvider] = {}

        Providers.check_factories() # check for additional factories

        # local methods

        def filter_type(clazz: Type, deferred_phase: bool = False) -> Optional[AbstractInstanceProvider]:
            result = None
            for provider in Providers.providers[clazz]:
                if provider_applies(provider, deferred_phase):
                    if result is not None:
                        raise ProviderCollisionException(f"type {clazz.__name__} already registered", result, provider)

                    result = provider

            return result

        def provider_applies(provider: AbstractInstanceProvider, deferred_phase: bool = False) -> bool:
            # is it in the right module?

            if not provider_filter(provider):
                return False

            # check conditionals

            descriptor = TypeDescriptor.for_type(provider.get_host())
            if descriptor.has_decorator(conditional):
                conditions: list[Condition] = [*descriptor.get_decorator(conditional).args]
                for condition in conditions:
                    # skip deferred checks , like the configuration logic
                    if condition.evaluate_on_scan() != (not deferred_phase):
                        continue

                    if not condition.apply(environment, cache):
                        return False

                return True

            return True

        def is_injectable(type: Type) -> bool:
            if type in [object, ABC]:
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

                if existing_provider.get_type() is not type:
                    # only overwrite if the existing provider is not specific

                    if isinstance(existing_provider, AmbiguousProvider):
                        cast(AmbiguousProvider, existing_provider).add_provider(provider)
                    else:
                        cache[type] = AmbiguousProvider(type, existing_provider, provider)

            # recursion

            for super_class in type.__bases__:
                if is_injectable(super_class):
                    cache_provider_for_type(provider, super_class)

        # filter conditional providers and fill base classes as well

        deferred_providers = []  # Track providers with deferred conditions
        for provider_type, _ in Providers.providers.items():
            matching_provider = filter_type(provider_type, deferred_phase=False)
            if matching_provider is not None:
                descriptor = TypeDescriptor.for_type(matching_provider.get_host())
                if descriptor.has_decorator(conditional):
                    conditions: list[Condition] = [*descriptor.get_decorator(conditional).args]
                    has_deferred = any(not c.evaluate_on_scan() for c in conditions)
                    if has_deferred:
                        deferred_providers.append((provider_type, matching_provider))
                        continue  # Don't cache yet

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

        providers = result
        if environment.parent is not None:
            providers = providers | environment.parent.providers # add parent providers

        provider_context = Providers.ResolveContext(providers)
        for provider in mapped.values():
            provider.resolve(provider_context)

        # done

        return result, deferred_providers

def register_factories(cls: Type):
    descriptor = TypeDescriptor.for_type(cls)

    for method in descriptor.get_methods():
        if method.has_decorator(create):
            create_decorator = method.get_decorator(create)
            return_type = method.return_type
            if return_type is None:
                raise DIRegistrationException(f"{cls.__name__}.{method.method.__name__} expected to have a return type")

            Providers.register(FunctionInstanceProvider(cls, method, create_decorator.args[0], create_decorator.args[1]))
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

    Args:
        eager (bool): If True, the corresponding object will be created eagerly when the environment is created.
        scope (str): The scope of the factory, e.g. "singleton", "request", "environment".
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

    Args:
        eager (bool): If True, the corresponding object will be created eagerly when the environment is created.
        scope (str): The scope of the factory, e.g. "singleton", "request", "environment".
    """
    def decorator(func):
        Decorators.add(func, create, eager, scope)
        return func

    return decorator

def on_init():
    """
    Methods annotated with `@on_init` will be called when the instance is created."""
    def decorator(func):
        Decorators.add(func, on_init)
        return func

    return decorator

def on_running():
    """
    Methods annotated with `@on_running` will be called when the container up and running."""
    def decorator(func):
        Decorators.add(func, on_running)
        return func

    return decorator

def on_destroy():
    """
    Methods annotated with `@on_destroy` will be called when the instance is destroyed.
    """
    def decorator(func):
        Decorators.add(func, on_destroy)
        return func

    return decorator

def module(imports: Optional[list[Type]] = None):
    """
    This annotation is used to mark classes that control the discovery process of injectables based on their location
    relative to the module of the class. All `@injectable`s and `@factory`s that are located in the same or any sub-module will
    be registered and managed accordingly.

    Args:
        imports (Optional[list[Type]]): Optional list of imported module types
    """
    def decorator(cls):
        Providers.register(ClassInstanceProvider(cls, True))

        Decorators.add(cls, module, imports)
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

# Annotation-based injection

class AnnotationResolver(ABC):
    """
    Base class for resolving annotated parameter values.
    Similar to PostProcessor, but for parameter injection.
    """

    __slots__ = ['annotation_type']

    def __init__(self, annotation_type: Type):
        self.annotation_type = annotation_type

    @abstractmethod
    def dependencies(self) -> list[Type]:
        """Return types this resolver depends on"""
        pass

    @abstractmethod
    def resolve(self, annotation_value: Any, param_type: Type, environment: Environment, *deps) -> Any:
        """
        Resolve the actual value to inject.

        Args:
            annotation_value: The annotation instance (e.g., ConfigValue("key"))
            param_type: The actual parameter type (e.g., str, int)
            environment: The DI environment
            *deps: Resolved dependencies from dependencies()

        Returns:
            The resolved value to inject
        """
        pass

class AnnotationResolvers:
    """Global registry for annotation resolvers"""

    resolvers: Dict[Type, AnnotationResolver] = {}

    @classmethod
    def register(cls, resolver: AnnotationResolver):
        """Register an annotation resolver"""
        cls.resolvers[resolver.annotation_type] = resolver

    @classmethod
    def get_resolver(cls, annotation_type: Type) -> Optional[AnnotationResolver]:
        """Get resolver for an annotation type"""
        return cls.resolvers.get(annotation_type)

class AnnotationInstanceProvider(AbstractInstanceProvider):
    """
    Provider that resolves a parameter value based on annotation metadata.
    Similar to how FactoryInstanceProvider wraps a Factory.
    """

    __slots__ = ['resolver', 'annotation_value', 'param_type', 'dependencies']

    def __init__(self, resolver: AnnotationResolver, annotation_value: Any, param_type: Type):
        self.resolver = resolver
        self.annotation_value = annotation_value
        self.param_type = param_type
        self.dependencies: list[Type] = []

    def get_module(self) -> str:
        return type(self.resolver).__module__

    def get_type(self) -> Type:
        return self.param_type

    def get_host(self) -> Type:
        return type(self.resolver)

    def is_eager(self) -> bool:
        return False  # Resolved on-demand

    def get_scope(self) -> str:
        return "request"  # Always resolve fresh

    def get_dependencies(self) -> (list[Type], int):
        deps = self.resolver.dependencies()
        return deps, len(deps)

    def resolve(self, context: 'Providers.ResolveContext'):
        """Resolve dependencies for this annotation provider"""
        self.dependencies = []
        for dep_type in self.resolver.dependencies():
            provider = context.require_provider(dep_type)
            self.dependencies.append(dep_type)

    def create(self, environment: Environment, *args) -> Any:
        # args are the resolver's dependencies
        return self.resolver.resolve(self.annotation_value, self.param_type, environment, *args)

    def report(self) -> str:
        return f"Annotation({self.annotation_value} -> {self.param_type.__name__})"

    def __str__(self):
        return f"AnnotationInstanceProvider({self.annotation_value} -> {self.param_type.__name__})"

# conditional stuff

class Condition(ABC):
    def dependencies(self) -> list[Type]:
        """Return list of types this condition depends on"""
        return []

    def evaluate_on_scan(self) -> bool:
        """Return True if condition can be evaluated during scan, False to defer until instantiation"""
        return True

    @abstractmethod
    def apply(self, environment: Environment, cache: Optional[Dict[Type, AbstractInstanceProvider]] = None) -> bool:
        """
        Apply the condition.

        Args:
            environment: The environment instance
            cache: Optional cache dict used during scanning phase (contains providers being filtered)
        """
        pass

class FeatureCondition(Condition):
    def __init__(self, feature: str):
        super().__init__()
        self.feature = feature

    def apply(self, environment: Environment, cache: Optional[Dict[Type, AbstractInstanceProvider]] = None) -> bool:
        return environment.has_feature(self.feature)

class ClassCondition(Condition):
    def __init__(self, clazz: Type):
        super().__init__()
        self.clazz = clazz

    def evaluate_on_scan(self) -> bool:
        """Defer evaluation until after all providers are registered"""
        return False

    def dependencies(self) -> list[Type]:
        """Declare dependency on the required class"""
        return [self.clazz]

    def apply(self, environment: Environment, cache: Optional[Dict[Type, AbstractInstanceProvider]] = None) -> bool:
        # Check the environment (called during deferred phase)
        return environment.is_registered_type(self.clazz)

class ConfigCondition(Condition):
    def __init__(self, key: str):
        super().__init__()
        self.key = key

    def evaluate_on_scan(self) -> bool:
        """Return True if condition can be evaluated during scan, False to defer until instantiation"""
        return False

    def dependencies(self) -> list[Type]:
        """Return list of types this condition depends on"""
        from aspyx.di.configuration import ConfigurationManager
        return [ConfigurationManager]

    def apply(self, environment: Environment, cache: Optional[Dict[Type, AbstractInstanceProvider]] = None) -> bool:
        from aspyx.di.configuration import ConfigurationManager
        config = environment.get(ConfigurationManager)
        return config.has(self.key)

class ConfigValueCondition(Condition):
    def __init__(self, key: str, value: Any = None):
        super().__init__()
        self.key = key
        self.value = value

    def evaluate_on_scan(self) -> bool:
        """Return True if condition can be evaluated during scan, False to defer until instantiation"""
        return False

    def dependencies(self) -> list[Type]:
        """Return list of types this condition depends on"""
        from aspyx.di.configuration import ConfigurationManager
        return [ConfigurationManager]

    def apply(self, environment: Environment, cache: Optional[Dict[Type, AbstractInstanceProvider]] = None) -> bool:
        from aspyx.di.configuration import ConfigurationManager
        config = environment.get(ConfigurationManager)
        return config.get_raw(self.key) == self.value

def requires_feature(feature: str):
    return FeatureCondition(feature)

def requires_class(clazz: Type):
    return ClassCondition(clazz)

def requires_configuration(key: str):
    return ConfigCondition(key)

def requires_configuration_value(key: str, value: Any = None):
    return ConfigValueCondition(key, value)

def conditional(*conditions: Condition):
    def decorator(cls):
        Decorators.add(cls, conditional, *conditions)

        return cls

    return decorator

class Environment:
    """
    Central class that manages the lifecycle of instances and their dependencies.

    Usage:

    ```python
    @injectable()
    class Foo:
        def __init__(self):

    @module()
    class Module:
        def __init__(self):
            pass

    environment = Environment(Module)

    foo = environment.get(Foo)  # will create an instance of Foo
    ```
    """

    # static data

    logger = logging.getLogger("aspyx.di")  # __name__ = module name

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

        def add_provider(type: Type, provider: AbstractInstanceProvider):
            Environment.logger.debug("\tadd provider %s for %s", provider, type)

            self.providers[type] = provider

        Environment.logger.debug("create environment for class %s", env.__qualname__)

        # initialize

        self.type = env
        self.parent = parent
        if self.parent is None and env is not Boot:
            self.parent = Boot.get_environment() # inherit environment including its manged instances!

        start = time.perf_counter()

        self.features = features
        self.providers: Dict[Type, AbstractInstanceProvider] = {}
        self.instances = []
        self.lifecycle_processors: list[LifecycleProcessor] = []

        if self.parent is not None:
            # inherit providers from parent

            for provider_type, inherited_provider in self.parent.providers.items():
                provider = inherited_provider
                if inherited_provider.get_scope() == "environment":
                    # replace with own environment instance provider
                    provider = EnvironmentInstanceProvider(self, cast(EnvironmentInstanceProvider, inherited_provider).provider)
                    provider.dependencies = [] # ??

                add_provider(provider_type, provider)

            # inherit processors as is unless they have an environment scope

            for processor in self.parent.lifecycle_processors:
                if self.providers[type(processor)].get_scope() != "environment":
                    self.lifecycle_processors.append(processor)
                else:
                    self.get(type(processor)) # will automatically be appended
        else:
            self.providers[SingletonScope] = SingletonScopeInstanceProvider()
            self.providers[RequestScope]   = RequestScopeInstanceProvider()
            self.providers[EnvironmentScope] = EnvironmentScopeInstanceProvider()

        Environment.instance = self

        prefix_list : list[str] = []

        loaded = set()

        def get_type_package(type: Type):
            module_name = type.__module__
            module = sys.modules.get(module_name)

            if not module:
                raise ImportError(f"Module {module_name} not found")

            # Try to get the package

            package = getattr(module, '__package__', None)

            # Fallback: if module is __main__, try to infer from the module name if possible

            if not package:
                if module_name == '__main__':
                    # Try to resolve real name via __file__
                    path = getattr(module, '__file__', None)
                    if path:
                        Environment.logger.warning(
                            "Module is __main__; consider running via -m to preserve package context")
                    return ''

                # Try to infer package name from module name

                parts = module_name.split('.')
                if len(parts) > 1:
                    return '.'.join(parts[:-1])

            return package or ''

        def import_package(name: str):
            """Import a package and all its submodules recursively."""
            package = importlib.import_module(name)
            results = {name: package}

            if hasattr(package, '__path__'):  # it's a package, not a single file
                for finder, name, ispkg in pkgutil.walk_packages(package.__path__, prefix=package.__name__ + "."):
                    try:
                        loaded = sys.modules

                        if loaded.get(name, None) is None:
                            Environment.logger.debug("import module %s", name)

                            submodule = importlib.import_module(name)
                            results[name] = submodule
                        else:
                            # skip import
                            results[name] = loaded[name]

                    except Exception as e:
                        Environment.logger.info("failed to import module %s due to %s", name, str(e))

            return results

        def load_environment(env: Type):
            if env not in loaded:
                Environment.logger.debug("load environment %s", env.__qualname__)

                loaded.add(env)

                # sanity check

                decorator = TypeDescriptor.for_type(env).get_decorator(module)
                if decorator is None:
                    raise DIRegistrationException(f"{env.__name__} is not an environment class")

                # package

                package_name = get_type_package(env)

                # recursion

                for import_environment in decorator.args[0] or []:
                    load_environment(import_environment)

                # import package

                if package_name is not None and len(package_name) > 0: # files outside of a package return None pr ""
                    import_package(package_name)

                # filter and load providers according to their module

                module_prefix = package_name
                if len(module_prefix) == 0:
                    module_prefix = env.__module__

                prefix_list.append(module_prefix)

        # go

        load_environment(env)

        # filter according to the prefix list

        def filter_provider(provider: AbstractInstanceProvider) -> bool:
            for prefix in prefix_list:
                if provider.get_host().__module__.startswith(prefix):
                    return True

            return False

        filtered_providers, deferred_providers = Providers.filter(self, filter_provider)
        self.providers.update(filtered_providers)

        # Phase 1: Create module instances and their @create() products to ensure config sources are loaded
        for provider in set(self.providers.values()):
            if provider.is_eager():
                # Get the actual provider (unwrap EnvironmentInstanceProvider)
                actual_provider = cast(EnvironmentInstanceProvider, provider).provider if isinstance(provider, EnvironmentInstanceProvider) else provider
                descriptor = TypeDescriptor.for_type(actual_provider.get_host())
                if descriptor.has_decorator(module):
                    provider.create(self)

        # Phase 2: Collect dependencies from deferred conditions
        deferred_dependencies = set()
        for provider_type, provider in deferred_providers:
            descriptor = TypeDescriptor.for_type(provider.get_host())
            if descriptor.has_decorator(conditional):
                conditions: list[Condition] = [*descriptor.get_decorator(conditional).args]
                for condition in conditions:
                    if not condition.evaluate_on_scan():
                        deferred_dependencies.update(condition.dependencies())

        # Phase 3: Create dependency instances (e.g., ConfigurationManager)
        for provider in set(self.providers.values()):
            if provider.is_eager() and provider.get_type() in deferred_dependencies:
                provider.create(self)

        # Phase 4: Evaluate deferred providers (dependencies now available)
        for provider_type, provider in deferred_providers:
            descriptor = TypeDescriptor.for_type(provider.get_host())
            if descriptor.has_decorator(conditional):
                conditions: list[Condition] = [*descriptor.get_decorator(conditional).args]
                all_pass = True
                for condition in conditions:
                    if not condition.evaluate_on_scan():
                        # Now dependencies are available, evaluate the condition
                        if not condition.apply(self):
                            all_pass = False
                            break

                if all_pass:
                    # Wrap and add to providers
                    env_provider = EnvironmentInstanceProvider(self, provider)

                    # Include parent providers in resolve context
                    providers = self.providers
                    if self.parent is not None:
                        providers = providers | self.parent.providers

                    env_provider.resolve(Providers.ResolveContext(providers))
                    self.providers[provider_type] = env_provider

                    # Add base classes
                    for super_class in provider_type.__bases__:
                        if super_class not in [object, ABC] and not inspect.isabstract(super_class):
                            if super_class not in self.providers:
                                self.providers[super_class] = env_provider

        # Phase 5: Create remaining eager singletons (module instances already created in Phase 1)
        for provider in set(self.providers.values()):
            if provider.is_eager():
                # Skip if already created (module instances and deferred dependencies)
                descriptor = TypeDescriptor.for_type(provider.get_host())
                if not descriptor.has_decorator(module) and provider.get_type() not in deferred_dependencies:
                    provider.create(self)

        # Phase 6: Execute ON_RUNNING for all instances (sync only - async methods will raise error)
        for instance in self.instances:
            self.execute_processors(Lifecycle.ON_RUNNING, instance)

        # NOTE: Async @on_running methods will raise an error during __init__
        # Call await environment.start() after creating the environment for async @on_running

        # done

        end = time.perf_counter()

        Environment.logger.info("created environment for class %s in %s ms, created %s instances", env.__qualname__, 1000 * (end - start),  len(self.instances))


    def is_registered_type(self, type: Type) -> bool:
        provider = self.providers.get(type, None)
        return provider is not None and not isinstance(provider, AmbiguousProvider)

    def registered_types(self,  predicate: Callable[[Type], bool]) -> list[Type]:
        return [provider.get_type() for provider in self.providers.values()
                if predicate(provider.get_type())]

    # internal

    def has_feature(self, feature: str) -> bool:
        return feature in self.features

    def execute_processors(self, lifecycle: Lifecycle, instance: T) -> T:
        for processor in self.lifecycle_processors:
            processor.process_lifecycle(lifecycle, instance, self)

        return instance

    async def execute_processors_async(self, lifecycle: Lifecycle, instance: T) -> T:
        """Execute lifecycle processors asynchronously, properly awaiting async methods."""
        for processor in self.lifecycle_processors:
            await processor.process_lifecycle_async(lifecycle, instance, self)

        return instance

    def created(self, instance: T) -> T:
        # remember lifecycle processors

        if isinstance(instance, LifecycleProcessor):
            self.lifecycle_processors.append(instance)

            # sort immediately

            self.lifecycle_processors.sort(key=lambda processor: processor.order)

        # remember instance

        self.instances.append(instance)

        # execute processors (ON_INJECT and ON_INIT during creation)
        # ON_INIT must be synchronous only (no async allowed)
        # ON_RUNNING will be executed in start() method and can be async

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
                    cast(EnvironmentInstanceProvider, provider).print_tree()
                    #builder.append(f"- {result_type.__name__}: {provider.report()}\n")

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

    async def start(self):
        """
        Start the environment by executing ON_RUNNING lifecycle phase.
        This method properly handles async @on_running methods.

        Call this after creating the environment if you have async @on_running methods.

        Note: @on_init methods are called during get() and must be synchronous.
              Use @on_running for async initialization (DB connections, etc.)

        Example:
            environment = Environment(MyModule)
            await environment.start()
        """
        Environment.logger.info("starting environment %s", self.type.__qualname__)

        # Execute ON_RUNNING phase for all instances (can be async)
        for instance in self.instances:
            await self.execute_processors_async(Lifecycle.ON_RUNNING, instance)

        Environment.logger.info("environment %s started successfully", self.type.__qualname__)

    async def stop(self):
        """
        Stop the environment by executing ON_DESTROY lifecycle phase.
        This method properly handles async lifecycle methods.

        Call this before discarding the environment to ensure proper cleanup.

        Example:
            await environment.stop()
        """
        Environment.logger.info("stopping environment %s", self.type.__qualname__)

        # Execute ON_DESTROY phase for all instances (in reverse order)
        for instance in reversed(self.instances):
            await self.execute_processors_async(Lifecycle.ON_DESTROY, instance)

        self.instances.clear()

        Environment.logger.info("environment %s stopped successfully", self.type.__qualname__)

    def destroy(self):
        """
        Destroy all managed instances by calling the appropriate lifecycle methods (synchronous version).

        IMPORTANT: If you have async lifecycle methods, use 'await environment.stop()' instead.
        This method will raise an error if called from within an async context.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError(
                "Cannot call destroy() from async context. Use 'await environment.stop()' instead."
            )
        except RuntimeError as e:
            if "Cannot call destroy()" in str(e):
                raise
            # No running loop - safe to run synchronously
            asyncio.run(self.stop())

    def get(self, type: Type[T]) -> T:
        """
        Create or return a cached instance for the given type.

        Args:
            type (Type): The desired type

        Returns:
            T: The requested instance
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

        def is_async(self):
            """Check if this method is async."""
            return inspect.iscoroutinefunction(self.method.method)

        def execute(self, instance, environment: Environment):
            """Execute lifecycle method synchronously (only for sync methods)."""
            # Check if method is async before calling
            if self.is_async():
                phase = self.lifecycle_callable.lifecycle.name
                if phase == "ON_INIT":
                    raise RuntimeError(
                        f"Async @on_init method '{self.method.method.__name__}' is not allowed. "
                        f"@on_init must be synchronous (called during get()). "
                        f"Use @on_running for async initialization instead."
                    )
                else:
                    # For ON_RUNNING and ON_DESTROY, skip during sync execution
                    # These will be called later via await start() or await stop()
                    return None

            # Execute sync method
            result = self.method.method(instance, *self.lifecycle_callable.args(self.decorator, self.method, environment))
            return result

        async def execute_async(self, instance, environment: Environment):
            """Execute lifecycle method, awaiting if async."""
            result = self.method.method(instance, *self.lifecycle_callable.args(self.decorator, self.method, environment))
            if inspect.iscoroutinefunction(self.method.method):
                return await result
            return result

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

    async def process_lifecycle_async(self, lifecycle: Lifecycle, instance: object, environment: Environment) -> object:
        if lifecycle is self.lifecycle:
            callables = self.callables_for(type(instance))

            for callable in callables[lifecycle.value]:
                await callable.execute_async(instance, environment)

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
        annotated_params = method.get_annotated_params()
        result = []

        for param in annotated_params:
            # Check for Environment type - automatic injection
            if param.type is Environment:
                result.append(environment)
                continue

            # Check for annotations
            resolver_found = False
            for meta in param.metadata:
                resolver = AnnotationResolvers.get_resolver(type(meta))
                if resolver:
                    # Resolve dependencies
                    deps = [environment.get(dep) for dep in resolver.dependencies()]
                    value = resolver.resolve(meta, param.type, environment, *deps)
                    result.append(value)
                    resolver_found = True
                    break

            if not resolver_found:
                # Normal DI
                result.append(environment.get(param.type))

        return result

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

@scope("environment", register=False)
class EnvironmentScope(SingletonScope):
    # properties

    __slots__ = [
    ]

    # constructor

    def __init__(self):
        super().__init__()


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

@module()
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
