"""
Tests
"""

from abc import abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel

from aspyx_service import ServiceModule, delete, post, put, get, rest, Body, PathParam, QueryParam
from aspyx_service.service import  component, Component, Service, service

from aspyx.di import module


class Pydantic(BaseModel):
    i: int
    f: float
    b: bool
    s: str

    str0 : str
    str1: str
    str2: str
    str3: str
    str4: str
    str5: str
    str6: str
    str7: str
    str8: str
    str9: str


@dataclass
class Data:
    i: int
    f: float
    b: bool
    s: str

    str0: str
    str1: str
    str2: str
    str3: str
    str4: str
    str5: str
    str6: str
    str7: str
    str8: str
    str9: str

class PydanticAndData(BaseModel):
    p: Pydantic

@dataclass
class DataAndPydantic:
    d: Data

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

@service(name="test-rest-service", description="cool")
@rest("/api")
class TestRestService(Service):
    @get("get/{param}", description="get description", summary="get summary", tags=["portal"])
    def test_get(self, param: PathParam(str, description="param is cool", example="param example"),
                 qp: QueryParam(str, description="query apram descritopn", example="qp example")) -> str:
        pass

    @abstractmethod
    @get("/hello/{message}")
    def get(self, message: str) -> str:
        pass

    @put("/hello/{message}")
    def put(self, message: str) -> str:
        pass

    @post("/hello/{message}")
    def post_pydantic(self, message: str, data: Body(Pydantic)) -> Pydantic:
        pass

    @post("/hello/{message}")
    def post_data(self, message: str, data: Body(Data)) -> Data:
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
    async def post_pydantic(self, message: str, data: Body(Pydantic)) -> Pydantic:
        pass

    @post("/hello/{message}")
    async def post_data(self, message: str, data: Body(Data)) -> Data:
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

# module

@module(imports=[ServiceModule])
class ClientModule:
    def __init__(self):
        pass
