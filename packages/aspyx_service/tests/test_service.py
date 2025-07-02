"""
Tests
"""
import logging
import time
import unittest
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel

from aspyx.di import module, create, injectable, inject_environment, Environment
from aspyx.di.configuration import YamlConfigurationSource

from aspyx_service import service, Service, component, Component, \
    implementation, health, AbstractComponent, ChannelAddress, inject_service, \
    FastAPIServer, Server, ServiceModule, ServiceManager, \
    HealthCheckManager, get, post, Body, rest, put, delete
from aspyx_service.service import LocalComponentRegistry

# configure logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

logging.getLogger("httpx").setLevel(logging.ERROR)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({
    "aspyx.di": logging.INFO,
    "aspyx.service": logging.INFO
})

# classes

class Pydantic(BaseModel):
    i : int
    f : float
    b: bool
    s: str

@dataclass
class Data:
    i: int
    f: float
    b: bool
    s: str

    p: Pydantic

# service

@service(name="test-service", description="cool")
class TestService(Service):
    @abstractmethod
    def hello(self, message: str) -> str:
        pass

    @abstractmethod
    def data(self, data: Data) -> Data:
        pass

    @abstractmethod
    def pydantic(self, data: Pydantic) -> Pydantic:
        pass

@service(name="test-async-service", description="cool")
class TestAsyncService(Service):
    @abstractmethod
    async def hello(self, message: str) -> str:
        pass

    @abstractmethod
    async def data(self, data: Data) -> Data:
        pass

    @abstractmethod
    async def pydantic(self, data: Pydantic) -> Pydantic:
        pass

@service(name="test-rest-service", description="cool")
@rest("/api")
class TestRestService(Service):
    @abstractmethod
    @get("/hello/{message}")
    def get(self, message: str) -> str:
        pass

    @put("/hello/{message}")
    def put(self, message: str) -> str:
        pass

    @post("/hello/{message}")
    def post_pydantic(self, message: str, data: Pydantic) -> Pydantic:
        pass

    @post("/hello/{message}")
    def post_data(self, message: str, data: Data) -> Data:
        pass

    @delete("/hello/{message}")
    def delete(self, message: str) -> str:
        pass

@service(name="test-async-rest-service", description="cool")
@rest("/async-api")
class TestAsyncRestService(Service):
    @abstractmethod
    @get("/hello/{message}")
    async def get(self, message: str) -> str:
        pass

    @put("/hello/{message}")
    async def put(self, message: str) -> str:
        pass

    @post("/hello/{message}")
    async def post_pydantic(self, message: str, data: Pydantic) -> Pydantic:
        pass

    @post("/hello/{message}")
    async def post_data(self, message: str, data: Data) -> Data:
        pass

    @delete("/hello/{message}")
    async def delete(self, message: str) -> str:
        pass

@component(services =[
    TestService,
    TestAsyncService,
    TestRestService,
    TestAsyncRestService
])
class TestComponent(Component): # pylint: disable=abstract-method
    pass

# implementation classes

@implementation()
class TestServiceImpl(TestService):
    def __init__(self):
        pass

    def hello(self, message: str) -> str:
        return message

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
class TestComponentImpl(AbstractComponent, TestComponent):
    # constructor

    def __init__(self):
        super().__init__()

        self.health_check_manager : Optional[HealthCheckManager] = None

    # implement

    async def get_health(self) -> HealthCheckManager.Health:
        return HealthCheckManager.Health()

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [
            ChannelAddress("rest", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-msgpack", f"http://{Server.get_local_ip()}:{port}")
        ]

    def startup(self) -> None:
        print("### startup")

    def shutdown(self) -> None:
        print("### shutdown")

@injectable(eager=False)
class Test:
    def __init__(self):
        self.service = None

    @inject_service(preferred_channel="local")
    def set_service(self, service: TestService):
        self.service = service

# module

@module(imports=[ServiceModule])
class Module:
    def __init__(self):
        pass

    @create()
    def create_yaml_source(self) -> YamlConfigurationSource:
        return YamlConfigurationSource(f"{Path(__file__).parent}/config.yaml")

    @create()
    def create_registry(self, source: YamlConfigurationSource) -> LocalComponentRegistry:
        return LocalComponentRegistry()

# main

def start_server() -> ServiceManager:
    server = FastAPIServer(host="0.0.0.0", port=8000)

    server.boot(Module)

    service_manager = server.get(ServiceManager)
    descriptor = service_manager.get_descriptor(TestComponent).get_component_descriptor()

    # Give the server a second to start

    while True:
        addresses = service_manager.component_registry.get_addresses(descriptor)
        if len(addresses) > 0:
            break

        print("zzz...")
        time.sleep(1)

    print("server running")

    return service_manager

service_manager = start_server()
environment = service_manager.environment

pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s", p=pydantic)

class TestLocalService(unittest.TestCase):
    def test_local(self):
        test_service = service_manager.get_service(TestService, preferred_channel="local")

        result = test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    def test_inject(self):
        test = environment.get(Test)

        self.assertIsNotNone(test.service)

class TestSyncRemoteService(unittest.TestCase):
    def test_dispatch_json(self):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")

        result = test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    def test_dispatch_msgpack(self):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

        result = test_service.hello("hello")
        self.assertEqual(result, "hello")

        result_data = test_service.data(data)
        self.assertEqual(result_data, data)

        result_pydantic = test_service.pydantic(pydantic)
        self.assertEqual(result_pydantic, pydantic)

    def test_dispatch_rest(self):
        test_service = service_manager.get_service(TestRestService, preferred_channel="rest")

        result = test_service.get("hello")
        self.assertEqual(result, "hello")

        result = test_service.put("hello")
        self.assertEqual(result, "hello")

        result = test_service.delete("hello")
        self.assertEqual(result, "hello")

        #

        #result_pydantic = test_service.post_pydantic(pydantic)
        #self.assertEqual(result_pydantic, pydantic)

        ##result_pydantic = test_service.post_data(pydantic)
        #self.assertEqual(result_pydantic, pydantic)
