"""
service management framework allowing for service discovery and transparent remoting including multiple possible transport protocols.
"""
from __future__ import annotations

import re
import socket
import logging
import threading
from abc import abstractmethod, ABC
from dataclasses import dataclass
from enum import Enum, auto

from typing import Type, TypeVar, Generic, Callable, Optional, cast

from aspyx.di import injectable, Environment, Providers, ClassInstanceProvider, inject_environment, order, \
    Lifecycle, LifecycleCallable, InstanceProvider
from aspyx.reflection import Decorators, DynamicProxy, DecoratorDescriptor, TypeDescriptor
from aspyx.util import StringBuilder
from .healthcheck import HealthCheckManager

T = TypeVar("T")

class Service:
    """
    This is something like a 'tagging interface' for services.
    """

class ComponentStatus(Enum):
    """
    A component is in one of the following statuses:

    - VIRGIN: just constructed
    - RUNNING: registered and up and running
    - STOPPED: after shutdown
    """
    VIRGIN = auto()
    RUNNING = auto()
    STOPPED = auto()

class Server(ABC):
    """
    A server is a central entity that boots a main module and initializes the ServiceManager.
    It also is the place where http servers get initialized.
    """
    port = 0

    # constructor

    def __init__(self):
        pass

    @abstractmethod
    def boot(self, module_type: Type):
        pass

    @abstractmethod
    def route(self, url : str, callable: Callable):
        pass

    @abstractmethod
    def route_health(self, url: str, callable: Callable):
        pass

    @classmethod
    def get_local_ip(cls):
        """
        return the local ip address

        Returns: the local ip address
        """
        try:
            # create a dummy socket to an external address

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Doesn't actually send data
            ip = s.getsockname()[0]
            s.close()

            return ip
        except Exception:
            return "127.0.0.1"  # Fallback



@dataclass
class ChannelAddress:
    """
    A channel address is a combination of:

    - channel: the channel name
    - uri: uri of the appropriate endpoint
    """
    channel : str
    uri : str

    def __str__(self):
        return f"{self.channel}({self.uri})"

class Component(Service):
    """
    This is the base class for components.
    """
    @abstractmethod
    def startup(self) -> None:
        """
        startup callback
        """

    @abstractmethod
    def shutdown(self)-> None:
        """
        shutdown callback
        """

    @abstractmethod
    def get_addresses(self, port: int) -> list[ChannelAddress]:
        """
        returns a list of channel addresses that expose this components services.

        Args:
            port: the port of a server hosting this component

        Returns:
            list of channel addresses
        """

    @abstractmethod
    def get_status(self) -> ComponentStatus:
        """
        return the component status callback

        Returns: the component status
        """

    @abstractmethod
    async def get_health(self) -> HealthCheckManager.Health:
        """
        return the component health

        Returns: the component health
        """

class AbstractComponent(Component, ABC):
    """
    abstract base class for components
    """
    # constructor

    def __init__(self):
        self.status = ComponentStatus.VIRGIN

    def startup(self) -> None:
        self.status = ComponentStatus.RUNNING

    def shutdown(self) -> None:
        self.status = ComponentStatus.STOPPED

    def get_status(self) -> ComponentStatus:
        return self.status

def to_snake_case(name: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '-', name).lower()

def component(name = "", description="", services: list[Type] = []):
    """
    decorates component interfaces

    Args:
        name: the component name. If empty the class name converted to snake-case is used
        description: optional description
        services: the list of hosted services
    """
    def decorator(cls):
        component_name = name
        if component_name == "":
            component_name = to_snake_case(cls.__name__)

        Decorators.add(cls, component, component_name, description, services)

        ServiceManager.register_component(cls, services)

        #Providers.register(ServiceInstanceProvider(cls)) TODO why?

        return cls

    return decorator

def service(name = "", description = ""):
    """
    decorates service interfaces

    Args:
        name: the service name. If empty the class name converted to snake case is used
        description: optional description
    """
    def decorator(cls):
        service_name = name
        if service_name == "":
            service_name = to_snake_case(cls.__name__)

        Decorators.add(cls, service, service_name, description)

        Providers.register(ServiceInstanceProvider(cls))

        return cls

    return decorator

def health(endpoint = ""):
    """
    specifies the health endpoint that will return the component health

    Args:
        endpoint: the  health endpoint
    """
    def decorator(cls):
        Decorators.add(cls, health, endpoint)

        return cls

    return decorator

def implementation():
    """
    decorates service or component implementations.
    """
    def decorator(cls):
        Decorators.add(cls, implementation)

        Providers.register(ClassInstanceProvider(cls, True, "singleton"))

        ServiceManager.register_implementation(cls)

        return cls

    return decorator

class BaseDescriptor(Generic[T]):
    """
    the base class for the meta data of both services and components.
    """
    __slots__ = [
        "name",
        "description",
        "type",
        "implementation"
    ]

    # constructor

    def __init__(self, type: Type[T], decorator: Callable):
        self.name = type.__name__
        self.description = ""
        self.implementation : Type[T] = None
        self.type : Type[T] = type

        self.analyze_decorator(type, decorator)

    def report(self, builder: StringBuilder):
        pass

    # internal

    def analyze_decorator(self, type: Type, decorator: Callable):
        descriptor = next((decorator_descriptor for decorator_descriptor in Decorators.get(type) if decorator_descriptor.decorator is decorator), None)

        # name

        name = descriptor.args[0]
        if name is not None and name != "":
            self.name = name

        # description

        description = descriptor.args[1]
        if description is not None and description != "":
            self.description = description

    # public

    @abstractmethod
    def get_component_descriptor(self) -> ComponentDescriptor:
        pass

    def is_component(self) -> bool:
        return False

    def is_local(self):
        return self.implementation is not None

class ServiceDescriptor(BaseDescriptor[T]):
    """
    meta data for services
    """
    __slots__ = [
        "component_descriptor"
    ]

    # constructor

    def __init__(self, component_descriptor: ComponentDescriptor, service_type: Type[T]):
        super().__init__(service_type, service)

        self.component_descriptor = component_descriptor

    # override

    def report(self, builder: StringBuilder):
        builder.append(self.name).append("(").append(self.type.__name__).append(")")

    def get_component_descriptor(self) -> ComponentDescriptor:
        return self.component_descriptor

class ComponentDescriptor(BaseDescriptor[T]):
    """
    meta data for components
    """

    __slots__ = [
        "services",
        "health",
        "addresses"
    ]

    # constructor

    def __init__(self,  component_type: Type[T], service_types: Type[T]):
        super().__init__(component_type, component)

        self.health = ""# Decorators.get_decorator(component_type, health).args[0]
        self.services = [ServiceDescriptor(self, type) for type in service_types]
        self.addresses : list[ChannelAddress] = []

    # override

    def report(self, builder: StringBuilder):
        builder.append(self.name).append("(").append(self.type.__name__).append(")")
        if self.is_local():
            builder.append("\n\t").append("implementation: ").append(self.implementation.__name__)
            builder.append("\n\t").append("health: ").append(self.health)
            builder.append("\n\t").append("addresses: ").append(', '.join(map(str, self.addresses)))


        builder.append("\n\tservices:\n")
        for service in self.services:
            builder.append("\t\t")
            service.report(builder)
            builder.append("\n")

    def get_component_descriptor(self) -> ComponentDescriptor:
        return self

    def is_component(self) -> bool:
        return True

# a resolved channel address

@dataclass()
class ChannelInstances:
    """
    a resolved channel address containing:

    - component: the component name
    - channel: the channel name
    - urls: list of URLs
    """
    component: str
    channel: str
    urls: list[str]

    # constructor

    def __init__(self, component: str, channel: str, urls: list[str] = []):
        self.component = component
        self.channel  : str = channel
        self.urls : list[str] = sorted(urls)

class ServiceException(Exception):
    """
    base class for service exceptions
    """

class LocalServiceException(ServiceException):
    """
    base class for service exceptions occurring locally
    """

class ServiceCommunicationException(ServiceException):
    """
    base class for service exceptions thrown by remoting errors
    """

class RemoteServiceException(ServiceException):
    """
    base class for service exceptions occurring on the server side
    """

class Channel(DynamicProxy.InvocationHandler, ABC):
    """
    A channel is a dynamic proxy invocation handler and transparently takes care of remoting.
    """
    __slots__ = [
        "name",
        "component_descriptor",
        "address"
    ]

    class URLSelector:
        """
        a url selector retrieves a URL for the next remoting call.
        """
        @abstractmethod
        def get(self, urls: list[str]) -> str:
            """
            return the next URL given a list of possible URLS

            Args:
                urls: list of possible URLS

            Returns:
                a URL
            """

    class FirstURLSelector(URLSelector):
        """
        a url selector always retrieving the first URL given a list of possible URLS
        """
        def get(self, urls: list[str]) -> str:
            if len(urls) == 0:
                raise ServiceCommunicationException("no known url")

            return urls[0]

    class RoundRobinURLSelector(URLSelector):
        """
        a url selector that picks urls sequentially given a list of possible URLS
        """
        def __init__(self):
            self.index = 0

        def get(self, urls: list[str]) -> str:
            if len(urls) > 0:
                try:
                    return urls[self.index]
                finally:
                    self.index = (self.index + 1) % len(urls)
            else:
                raise ServiceCommunicationException("no known url")


    # constructor

    def __init__(self):
        self.name =  Decorators.get_decorator(type(self), channel).args[0]
        self.component_descriptor : Optional[ComponentDescriptor] = None
        self.address: Optional[ChannelInstances] = None
        self.url_selector : Channel.URLSelector = Channel.FirstURLSelector()

    # public

    def customize(self):
        pass

    def select_round_robin(self) -> None:
        """
        enable round robin
        """
        self.url_selector = Channel.RoundRobinURLSelector()

    def select_first_url(self):
        """
        pick the first URL
        """
        self.url_selector = Channel.FirstURLSelector()

    def get_url(self) -> str:
        return self.url_selector.get(self.address.urls)

    def set_address(self, address: Optional[ChannelInstances]):
        self.address = address

    def setup(self, component_descriptor: ComponentDescriptor, address: ChannelInstances):
        self.component_descriptor = component_descriptor
        self.address = address


class ComponentRegistry:
    """
    A component registry keeps track of components including their health
    """
    @abstractmethod
    def register(self, descriptor: ComponentDescriptor[Component], addresses: list[ChannelAddress]) -> None:
        """
        register a component to the registry
        Args:
            descriptor: the descriptor
            addresses: list of addresses
        """

    @abstractmethod
    def deregister(self, descriptor: ComponentDescriptor[Component]) -> None:
        """
        deregister a component from the registry
        Args:
            descriptor: the component descriptor
        """

    @abstractmethod
    def watch(self, channel: Channel) -> None:
        """
        remember the passed channel and keep it informed about address changes
        Args:
            channel: a channel
        """

    @abstractmethod
    def get_addresses(self, descriptor: ComponentDescriptor) -> list[ChannelInstances]:
        """
        return a list of addresses that can be used to call services belonging to this component

        Args:
            descriptor: the component descriptor

        Returns:
            list of channel instances
        """

    def map_health(self, health:  HealthCheckManager.Health) -> int:
        return 200


@injectable()
class ChannelManager:
    """
    Internal factory for channels.
    """
    factories: dict[str, Type] = {}

    @classmethod
    def register_channel(cls, channel: str, type: Type):
        ServiceManager.logger.info("register channel %s", channel)

        ChannelManager.factories[channel] = type

    # constructor

    def __init__(self):
        self.environment = None

    # lifecycle hooks

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # public

    def make(self, name: str, descriptor: ComponentDescriptor, address: ChannelInstances) -> Channel:
        ServiceManager.logger.info("create channel %s: %s", name, self.factories.get(name).__name__)

        result =  self.environment.get(self.factories.get(name))

        result.setup(descriptor, address)

        return result

def channel(name: str):
    """
    this decorator is used to mark channel implementations.

    Args:
        name: the channel name
    """
    def decorator(cls):
        Decorators.add(cls, channel, name)

        Providers.register(ClassInstanceProvider(cls, False, "request"))

        ChannelManager.register_channel(name, cls)

        return cls

    return decorator

@dataclass(frozen=True)
class TypeAndChannel:
    type: Type
    channel: str

@injectable()
class ServiceManager:
    """
    Central class that manages services and components and is able to return proxies.
    """
    # class property

    logger = logging.getLogger("aspyx.service")  # __name__ = module name

    descriptors_by_name: dict[str, BaseDescriptor] = {}
    descriptors: dict[Type, BaseDescriptor] = {}
    channel_cache : dict[TypeAndChannel, Channel] = {}
    proxy_cache: dict[TypeAndChannel, DynamicProxy[T]] = {}
    lock: threading.Lock = threading.Lock()

    instances : dict[Type, BaseDescriptor] = {}

    # class methods

    @classmethod
    def register_implementation(cls, type: Type):
        cls.logger.info("register implementation %s", type.__name__)
        for base in type.mro():
            if Decorators.has_decorator(base, service):
                ServiceManager.descriptors[base].implementation = type
                return

            elif Decorators.has_decorator(base, component):
                ServiceManager.descriptors[base].implementation = type
                return

    @classmethod
    def register_component(cls, component_type: Type, services: list[Type]):
        component_descriptor = ComponentDescriptor(component_type, services)

        cls.logger.info("register component %s", component_descriptor.name)

        ServiceManager.descriptors[component_type] = component_descriptor
        ServiceManager.descriptors_by_name[component_descriptor.name] = component_descriptor

        for component_service in component_descriptor.services:
            ServiceManager.descriptors[component_service.type] = component_service
            ServiceManager.descriptors_by_name[component_service.name] = component_service

    # constructor

    def __init__(self, component_registry: ComponentRegistry, channel_manager: ChannelManager):
        self.component_registry = component_registry
        self.channel_manager = channel_manager
        self.environment = None

        self.ip = Server.get_local_ip()

    # internal

    def report(self) -> str:
        builder = StringBuilder()

        for descriptor in self.descriptors.values():
            if descriptor.is_component():
                descriptor.report(builder)

        return str(builder)

    @classmethod
    def get_descriptor(cls, type: Type) -> BaseDescriptor[BaseDescriptor[Component]]:
        return cls.descriptors.get(type)

    def get_instance(self, type: Type[T]) -> T:
        instance = self.instances.get(type)
        if instance is None:
            ServiceManager.logger.info("create implementation %s", type.__name__)

            instance = self.environment.get(type)
            self.instances[type] = instance

        return instance

    # lifecycle

    def startup(self, server: Server) -> None:
        self.logger.info("startup on port %s", server.port)

        for descriptor in self.descriptors.values():
            if descriptor.is_component():
                # register local address

                if descriptor.is_local():
                    # create

                    instance = self.get_instance(descriptor.type)
                    descriptor.addresses = instance.get_addresses(server.port)

                    # fetch health

                    descriptor.health = Decorators.get_decorator(descriptor.implementation, health).args[0]

                    self.component_registry.register(descriptor.get_component_descriptor(), [ChannelAddress("local", "")])

                    health_name = next((decorator.args[0] for decorator in Decorators.get(descriptor.type) if decorator.decorator is health), None)

                    # startup

                    instance.startup()

                    # add health route

                    server.route_health(health_name, instance.get_health)

                    # register addresses

                    self.component_registry.register(descriptor.get_component_descriptor(), descriptor.addresses)

        print(self.report())

    def shutdown(self):
        self.logger.info("shutdown")

        for descriptor in self.descriptors.values():
            if descriptor.is_component():
                if descriptor.is_local():
                    self.get_instance(descriptor.type).shutdown()

                    self.component_registry.deregister(cast(ComponentDescriptor, descriptor))


    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # public

    def find_service_address(self, component_descriptor: ComponentDescriptor, preferred_channel="") -> ChannelInstances:
        addresses = self.component_registry.get_addresses(component_descriptor)  # component, channel + urls
        address = next((address for address in addresses if address.channel == preferred_channel), None)
        if address is None:
            if len(addresses) > 0:
                # return the first match
                address = addresses[0]
            else:
                raise ServiceException(f"no matching channel found for component  {component_descriptor.name}")

        return address

    def get_service(self, service_type: Type[T], preferred_channel="") -> T:
        """
        return a service proxy given a service type and preferred channel name

        Args:
            service_type:  the service type
            preferred_channel:  the preferred channel name

        Returns:
            the proxy
        """
        service_descriptor = ServiceManager.get_descriptor(service_type)
        component_descriptor = service_descriptor.get_component_descriptor()

        ## shortcut for local implementation

        if preferred_channel == "local" and service_descriptor.is_local():
            return self.get_instance(service_descriptor.implementation)

        # check proxy

        key = TypeAndChannel(type=component_descriptor.type, channel=preferred_channel)

        proxy = self.proxy_cache.get(key, None)
        if proxy is None:
            channel_instance = self.channel_cache.get(key, None)

            if channel_instance is None:
                address = self.find_service_address(component_descriptor, preferred_channel)

                # again shortcut

                if address.channel == "local":
                    return self.get_instance(service_descriptor.type)

                # channel may have changed

                if address.channel != preferred_channel:
                    key = TypeAndChannel(type=component_descriptor.type, channel=address.channel)

                channel_instance = self.channel_cache.get(key, None)
                if channel_instance is None:
                    # create channel

                    channel_instance = self.channel_manager.make(address.channel, component_descriptor, address)

                    # cache

                    self.channel_cache[key] =  channel_instance

                    # and watch for changes in the addresses

                    self.component_registry.watch(channel_instance)

            # create proxy

            proxy = DynamicProxy.create(service_type, channel_instance)
            self.proxy_cache[key] = proxy

        return proxy

class ServiceInstanceProvider(InstanceProvider):
    """
    A ServiceInstanceProvider is able to create instances of services.
    """

    # constructor

    def __init__(self, clazz : Type[T]):
        super().__init__(clazz, clazz, False, "singleton")

        self.service_manager = None

    # implement

    def get_dependencies(self) -> (list[Type],int):
        return [ServiceManager], 1

    def create(self, environment: Environment, *args):
        if self.service_manager is None:
            self.service_manager = environment.get(ServiceManager)

        Environment.logger.debug("%s create service %s", self, self.type.__qualname__)

        return self.service_manager.get_service(self.get_type())

    def report(self) -> str:
        return f"service {self.host.__name__}"

    def __str__(self):
        return f"ServiceInstanceProvider({self.host.__name__} -> {self.type.__name__})"

@channel("local")
class LocalChannel(Channel):
    # properties

    # constructor

    def __init__(self, manager: ServiceManager):
        super().__init__()

        self.manager = manager
        self.component = component
        self.environment = None

    # lifecycle hooks

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # implement

    def invoke(self, invocation: DynamicProxy.Invocation):
        instance = self.manager.get_instance(invocation.type)

        return getattr(instance, invocation.method.__name__)(*invocation.args, **invocation.kwargs)


#@injectable()
class LocalComponentRegistry(ComponentRegistry):
    # constructor

    def __init__(self):
        self.component_channels : dict[ComponentDescriptor, list[ChannelAddress]]  = {}

    # implement

    def register(self, descriptor: ComponentDescriptor[Component], addresses: list[ChannelAddress]) -> None:
        self.component_channels[descriptor] = addresses

    def deregister(self, descriptor: ComponentDescriptor[Component]) -> None:
        pass

    def watch(self, channel: Channel) -> None:
        pass

    def get_addresses(self, descriptor: ComponentDescriptor) -> list[ChannelInstances]:
        return self.component_channels.get(descriptor, [])

def inject_service(preferred_channel=""):
    def decorator(func):
        Decorators.add(func, inject_service, preferred_channel)

        return func

    return decorator

@injectable()
@order(9)
class ServiceLifecycleCallable(LifecycleCallable):
    def __init__(self,  manager: ServiceManager):
        super().__init__(inject_service, Lifecycle.ON_INJECT)

        self.manager = manager

    def args(self, decorator: DecoratorDescriptor, method: TypeDescriptor.MethodDescriptor, environment: Environment):
        return [self.manager.get_service(method.param_types[0], preferred_channel=decorator.args[0])]
