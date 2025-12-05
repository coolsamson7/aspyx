"""
Tests
"""
import logging

from aspyx.util import Logger
from aspyx_service.service import LocalComponentRegistry, ComponentRegistry

Logger.configure(default_level=logging.INFO, levels={
    "aspyx.di": logging.INFO,
    "aspyx.service": logging.DEBUG,
})

from abc import abstractmethod, ABC

from aspyx.di import module, Environment, create
from aspyx_service import service, implementation, component, Component, Service, AbstractComponent, ServiceManager, \
    ChannelAddress, Server, ServiceModule, SessionManager

service_version = 0
component_version = 0

@service()
class LifecycleService(Service, ABC):# ABC
    @abstractmethod
    def hello(self, message: str) -> str:
        pass

@component(services =[
    LifecycleService,
])
class LifecycleComponent(Component, ABC):# ABC
    pass

@module(imports=[ServiceModule])
class LifecycleModule:
    @create()
    def create_registry(self) -> ComponentRegistry:
        return LocalComponentRegistry()

    @create()
    def create_session_storage(self) -> SessionManager.Storage:
        return SessionManager.InMemoryStorage(max_size=1000, ttl=3600)

@implementation()
class LifecycleServiceImpl(LifecycleService):
    def __init__(self):
        global service_version

        self.version = service_version
        service_version += 1

    def hello(self, message: str) -> str:
        return message

@implementation()
class LifecycleComponentImpl(AbstractComponent, LifecycleComponent):
    # constructor

    def __init__(self):
        super().__init__()

        global component_version

        self.version = component_version
        component_version += 1

    # implement

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [
            ChannelAddress("rest", f"http://{Server.get_local_ip()}:{port}")
        ]


class TestLifecycle:
    def test_cache(self):
        # first environment

        env_1 = Environment(LifecycleModule)

        #print(env_1.report())

        #c1 = env_1.get(ServiceManager).get_service(LifecycleComponent)
        s1 = env_1.get(ServiceManager).get_service(LifecycleService, preferred_channel="local")

        env_1.destroy()

        # next environment

        env_2 = Environment(LifecycleModule)

        #print(env_1.report())

        #c2 = env_2.get(ServiceManager).get_service(LifecycleComponent)
        s2 = env_2.get(ServiceManager).get_service(LifecycleService, preferred_channel="local")

        #assert c1 is not c2
        assert s1 is not s2
