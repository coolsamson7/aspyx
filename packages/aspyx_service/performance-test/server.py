"""
Tests
"""
import os
from typing import Optional

from consul import Consul
from fastapi import FastAPI

from aspyx_service import HealthCheckManager, ServiceModule, ConsulComponentRegistry, SessionManager, FastAPIServer, \
    ProtobufManager

from client import ClientModule, TestService, TestAsyncService, Data, Pydantic, TestRestService, TestAsyncRestService, TestComponent

from aspyx_service.service import ChannelAddress, Server, \
    component_services, AbstractComponent, implementation, health, ComponentRegistry, ServiceManager
from aspyx.di import on_running, module, create
from aspyx.di.aop import Invocation, advice, error
from aspyx.exception import handle, ExceptionManager

# implementation classes

@implementation()
class TestServiceImpl(TestService):
    def __init__(self):
        pass

    def hello(self, message: str) -> str:
        return message

    def throw(self, message: str) -> str:
        raise Exception(message)

    def data(self, data: Data) -> Data:
        return data

    def pydantic(self, data: Pydantic) -> Pydantic:
        return data

@implementation()
class TestAsyncServiceImpl(TestAsyncService):
    def __init__(self):
        pass

    async def hello(self, message: str) -> str:
        return message

    async def data(self, data: Data) -> Data:
        return data

    async def pydantic(self, data: Pydantic) -> Pydantic:
        return data

@implementation()
class TestRestServiceImpl(TestRestService):
    def __init__(self):
        pass

    def test_get(self, param:str, qp:str) -> str:
        return param + qp

    def get(self, message: str) -> str:
        return message

    def put(self, message: str) -> str:
        return message

    def post_pydantic(self, message: str, data: Pydantic) -> Pydantic:
        return data

    def post_data(self, message: str, data: Data) -> Data:
        return data

    def delete(self, message: str) -> str:
        return message

@implementation()
class TestAsyncRestServiceImpl(TestAsyncRestService):
    def __init__(self):
        pass

    async def get(self, message: str) -> str:
        return message

    async def put(self, message: str) -> str:
        return message

    async def post_pydantic(self, message: str, data: Pydantic) -> Pydantic:
        return data

    async def post_data(self, message: str, data: Data) -> Data:
        return data

    async def delete(self, message: str) -> str:
        return message

@implementation()
@health("/health")
@advice
class TestComponentImpl(AbstractComponent, TestComponent):
    # constructor

    def __init__(self):
        super().__init__()

        self.health_check_manager : Optional[HealthCheckManager] = None
        self.exception_manager = ExceptionManager()

    # exception handler

    @handle()
    def handle_exception(self, exception: Exception):
        print("caught exception!")
        return exception

    # aspects

    @error(component_services(TestComponent))
    def catch(self, invocation: Invocation):
        return self.exception_manager.handle(invocation.exception)

    # lifecycle

    @on_running()
    def setup_exception_handlers(self):
        self.exception_manager.collect_handlers(self)

    # implement

    async def get_health(self) -> HealthCheckManager.Health:
        return HealthCheckManager.Health()

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [
            ChannelAddress("rest", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-msgpack", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-protobuf", f"http://{Server.get_local_ip()}:{port}")
        ]

    def startup(self) -> None:
        print("### startup")

    def shutdown(self) -> None:
        print("### shutdown")

# module

@module(imports=[ClientModule, ServiceModule])
class ServerModule:
    fastapi: Optional[FastAPI] = None

    def __init__(self):
        pass

    #@create()
    #def create_yaml_source(self) -> YamlConfigurationSource:
    #    return YamlConfigurationSource(f"{Path(__file__).parent}/config.yaml")

    @create()
    def create_server(self, service_manager: ServiceManager, component_registry: ComponentRegistry, protobuf_manager: ProtobufManager) -> FastAPIServer:
        return FastAPIServer(self.fastapi, service_manager, component_registry)

    @create()
    def create_session_storage(self) -> SessionManager.Storage:
        return SessionManager.InMemoryStorage(max_size=1000, ttl=3600)

    @create()
    def create_registry(self) -> ComponentRegistry:
        return ConsulComponentRegistry(port=int(os.getenv("FAST_API_PORT", "8000")), consul=Consul(host="localhost", port=8500))
