"""
Common test stuff
"""
#from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import jwt
from aspyx_service.restchannel import BodyMarker, PathParam
from fastapi import HTTPException, FastAPI

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, Annotated

from jwt import ExpiredSignatureError, InvalidTokenError

import pytest
from pydantic import BaseModel

from aspyx.reflection import Decorators

from aspyx_service import service, Service, component, Component, \
    implementation, health, AbstractComponent, ChannelAddress, inject_service, \
    FastAPIServer, Server, ServiceModule, ServiceManager, \
    HealthCheckManager, get, post, rest, put, delete, Body, SessionManager, RequestContext, \
    TokenContextMiddleware, ProtobufManager, QueryParam
from aspyx.di.aop import advice, error, Invocation
from aspyx.exception import ExceptionManager, handle
from aspyx.util import Logger
from aspyx_service.server import ResponseContext
from aspyx_service.service import LocalComponentRegistry, component_services, AuthorizationException, ComponentRegistry
from aspyx.di import module, create, injectable, on_running, Environment
from aspyx.di.configuration import YamlConfigurationSource
#from .other import EmbeddedPydantic

# configure logging

Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.INFO,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.INFO,
    "aspyx.event": logging.INFO
})

# classes

@dataclass
class EmbeddedDataClass:
    int_attr: int
    float_attr: float
    bool_attr: bool
    str_attr: str

class EmbeddedPydantic(BaseModel):
    int_attr: int
    float_attr: float
    bool_attr: bool
    str_attr: str

class Pydantic(BaseModel):
    int_attr : int
    float_attr : float
    bool_attr : bool
    str_attr : str

    int_list_attr : list[int]
    float_list_attr: list[float]
    bool_list_attr : list[bool]
    str_list_attr: list[str]

    embedded_pydantic: EmbeddedPydantic
    embedded_dataclass: EmbeddedDataClass

    embedded_pydantic_list: list[EmbeddedPydantic]
    embedded_dataclass_list: list[EmbeddedDataClass]

@dataclass
class Data:
    int_attr: int
    float_attr: float
    bool_attr: bool
    str_attr: str

    int_list_attr: list[int]
    float_list_attr: list[float]
    bool_list_attr: list[bool]
    str_list_attr: list[str]

class PydanticAndData(BaseModel):
    p: Pydantic

@dataclass
class DataAndPydantic:
    d: Data

# jwt

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class TokenManager:
    # constructor

    def __init__(self, secret: str, algorithm: str, access_token_expiry_minutes: int = 15, refresh_token_expiry_minutes: int = 60 * 24):
        self.secret = secret
        self.algorithm = algorithm
        self.access_token_expiry_minutes = access_token_expiry_minutes
        self.refresh_token_expiry_minutes = refresh_token_expiry_minutes

    # methods

    def create_jwt(self, subject: str, roles: list[str]) -> str:
        return self.create_access_token(subject, roles)

    def create_access_token(self, subject: str, roles: list[str]) -> str:
        now = datetime.now(tz=timezone.utc)
        expiry = now + timedelta(minutes=self.access_token_expiry_minutes)

        payload = {
            "sub": subject,
            "roles": roles,
            "exp": int(expiry.timestamp()),
            "iat": int(now.timestamp()),
            "type": "access"
        }

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def create_refresh_token(self, subject: str, roles: list[str]) -> str:
        now = datetime.now(tz=timezone.utc)
        expiry = now + timedelta(minutes=self.refresh_token_expiry_minutes)

        payload = {
            "sub": subject,
            "roles": roles,
            "exp": int(expiry.timestamp()),
            "iat": int(now.timestamp()),
            "type": "refresh"
        }

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def refresh_access_token(self, refresh_token: str) -> str:
        payload = self.decode_jwt(refresh_token)

        if payload.get("type") != "refresh":
            raise AuthorizationException("Expected a refresh token")

        subject = payload.get("sub")
        if not subject:
            raise AuthorizationException("Missing subject in refresh token")

        roles = payload.get("roles")

        return self.create_access_token(subject, roles)

    def decode_jwt(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except ExpiredSignatureError:
            raise HTTPException(status_code=401,
                                detail="Token has expired",
                                headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token has expired"'}
                                )
        except InvalidTokenError:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token is invalid"'}
            )


# service

@service(name="test-service", description="cool")
class TestService(Service):
    @abstractmethod
    def hello(self, message: str) -> str:
        pass

    @abstractmethod
    def throw(self, message: str) -> str:
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

def requires_response():
    """
    methods marked with `requires_response` will...
    """
    def decorator(cls):
        Decorators.add(cls, requires_response)

        return cls

    return decorator

@service(name="test-rest-service", description="cool")
@rest("/api")
class TestRestService(Service):
    __test__ = False  # prevent pytest from collecting service methods as tests
    @get("/test_get/{param}", description="get description", summary="get summary", tags=["portal"])
    def test_get(self, param: PathParam(str, description="param is cool", example="param example"),
                 qp: QueryParam(str, description="query apram descritopn", example="qp example")) -> str:
        pass


    @abstractmethod
    @get("/get/{message}")
    @requires_response()
    def get(self, message: str) -> str:
        pass

    @put("/put/{message}")
    def put(self, message: str) -> str:
        pass

    @post("/post_pydantic/{message}")
    def post_pydantic(self, message: str, data: Body(Pydantic, description="foo")) -> Pydantic:
        pass

    @post("/post_data/{message}")
    def post_data(self, message: str, data: Body(Data, description="bar")) -> Data:
        pass

    @delete("/delete/{message}")
    def delete(self, message: str) -> str:
        pass

@service(name="test-async-rest-service", description="cool")
@rest("/async-api")
class TestAsyncRestService(Service):
    __test__ = False  # prevent pytest from collecting service methods as tests
    @abstractmethod
    @get("/get/{message}")
    async def get(self, message: str) -> str:
        pass

    @put("/put/{message}")
    async def put(self, message: str) -> str:
        pass

    @post("/post_pydantic/{message}")
    async def post_pydantic(self, message: str, data: Body(Pydantic)) -> Pydantic:
        pass

    @post("/post_data/{message}")
    async def post_data(self, message: str, data: Body(Data)) -> Data:
        pass

    @delete("/delete/{message}")
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
    async def hello(self, message: str) -> str:
        return message

    async def data(self, data: Data) -> Data:
        return data

    async def pydantic(self, data: Pydantic) -> Pydantic:
        return data

@implementation()
class TestRestServiceImpl(TestRestService):
    @get("get/{param}", description="get description", summary="get summary", tags=["portal"])
    def test_get(self, param: str,
                 qp: str) -> str:
        print(f"###### test_get/{param}/{qp}")
        return param + qp


    @requires_response()
    def get(self, message: str) -> str:
        #TODO response = ResponseContext.get()

        # TODO response.set_cookie("name", "value")

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
            ChannelAddress("dispatch-protobuf", f"http://{Server.get_local_ip()}:{port}"),
        ]

    def startup(self) -> None:
        print("### startup")

    def shutdown(self) -> None:
        print("### shutdown")

@injectable(eager=False)
class Foo:
    def __init__(self):
        self.service = None

    @inject_service(preferred_channel="local")
    def set_service(self, service: TestService):
        self.service = service

# module

fastapi = FastAPI()

fastapi.add_middleware(RequestContext)
fastapi.add_middleware(TokenContextMiddleware)

@module(imports=[ServiceModule])
class Module:
    @create()
    def create_server(self,  service_manager: ServiceManager, component_registry: ComponentRegistry) -> FastAPIServer:
        return FastAPIServer(fastapi, service_manager, component_registry)

    @create()
    def create_session_storage(self) -> SessionManager.Storage:
        return SessionManager.InMemoryStorage(max_size=1000, ttl=3600)

    @create()
    def create_token_manager(self) -> TokenManager:
        return TokenManager(SECRET_KEY, ALGORITHM, access_token_expiry_minutes = 15, refresh_token_expiry_minutes = 60 * 24)

    @create()
    def create_yaml_source(self) -> YamlConfigurationSource:
        return YamlConfigurationSource(f"{Path(__file__).parent}/config.yaml")

    @create()
    def create_registry(self, source: YamlConfigurationSource) -> LocalComponentRegistry:
        return LocalComponentRegistry()

# main

def start_environment() -> Environment:
    environment = FastAPIServer.boot(Module, host="0.0.0.0", port=8000)

    service_manager = environment.get(ServiceManager)
    descriptor = service_manager.get_descriptor(TestComponent).get_component_descriptor()

    # Give the server a second to start

    print("wait for server to start")
    while True:
        addresses = service_manager.component_registry.get_addresses(descriptor)
        if addresses:
            break

        print("zzz...")
        time.sleep(1)

    print("server running")

    return environment


@pytest.fixture()
def service_manager():
    environment = start_environment()

    try:
        yield environment.get(ServiceManager)
    finally:
        environment.destroy()
