"""
Common test stuff
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, FastAPI

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, Callable

from jwt import ExpiredSignatureError, InvalidTokenError

import pytest
from pydantic import BaseModel

from aspyx.mapper import MappingDefinition, Mapper, matching_properties
from aspyx.reflection import Decorators, TypeDescriptor
from aspyx.reflection.reflection import PropertyExtractor
from aspyx_service import service, Service, component, Component, \
    implementation, health, AbstractComponent, ChannelAddress, inject_service, \
    FastAPIServer, Server, ServiceModule, ServiceManager, \
    HealthCheckManager, get, post, rest, put, delete, Body, SessionManager, RequestContext, \
    TokenContextMiddleware, ProtobufManager
from aspyx.di.aop import advice, error, Invocation, around, methods, classes
from aspyx.exception import ExceptionManager, handle
from aspyx.util import Logger
from aspyx_service.server import ResponseContext
from aspyx_service.service import LocalComponentRegistry, component_services, AuthorizationException, ComponentRegistry
from aspyx.di import module, create, injectable, on_running, Environment
from aspyx.di.configuration import YamlConfigurationSource
from .other import EmbeddedPydantic

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

#class EmbeddedPydantic(BaseModel):
#    int_attr: int
#    float_attr: float
#    bool_attr: bool
#    str_attr: str

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

# TEST TODO

from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import sessionmaker, declarative_base


#@injectable()
class DatabaseEngine:
    def __init__(self, url: str):
        self.engine = create_engine(url, echo=False, future=True)

    def get_engine(self):
        return self.engine

@injectable()
class SessionFactory:
    def __init__(self, engine: DatabaseEngine):
        self._maker = sessionmaker(bind=engine.get_engine(), autoflush=False, autocommit=False)

    def create_session(self):
        return self._maker()

def transactional():
    def decorator(func):
        Decorators.add(func, transactional)
        return func #

    return decorator

from contextvars import ContextVar
from sqlalchemy.orm import Session

_current_session: ContextVar[Session] = ContextVar("_current_session", default=None)

def get_current_session():
    return _current_session.get()

@advice
@injectable()
class TransactionalAdvice:
    # constructor

    def __init__(self, factory: SessionFactory):
        self.session_factory = factory

    # internal

    # advice

    @around(methods().decorated_with(transactional), classes().decorated_with(transactional))
    def call_transactional1(self, invocation: Invocation):
        session = self.session_factory.create_session()
        token = _current_session.set(session)

        try:
            result = invocation.proceed()
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            _current_session.reset(token)

Base = declarative_base()

class PydanticUser(BaseModel):
    name: str

class UserEntity(Base):
    __tablename__ = "user_profile"

    user_id = Column(String, primary_key=True)
    #name = Column(String)
    #email = Column(String)
    locale = Column(String)

    def __repr__(self):
        return f"<User(id={self.user_id}, locale={self.locale})>"

@dataclass()
class User:
    user_id : str
    locale: str

# TODO wohin -> ??


from sqlalchemy.orm import DeclarativeMeta, class_mapper, ColumnProperty

class SQLAlchemyPropertyExtractor(PropertyExtractor):
    def extract(self, cls: Type):
        if not isinstance(cls, DeclarativeMeta):
            return None

        mapper = class_mapper(cls)
        props = {}
        for prop in mapper.attrs:
            if isinstance(prop, ColumnProperty):
                name = prop.key
                column = prop.columns[0]
                typ = getattr(column.type, "python_type", object)
                props[name] = TypeDescriptor.PropertyDescriptor(
                    cls,
                    name,
                    typ,
                    getattr(cls, name, None)
                )
        return props

TypeDescriptor.register_extractor(SQLAlchemyPropertyExtractor())


pydantic_desc = TypeDescriptor.for_type(PydanticUser)

type_desc = TypeDescriptor.for_type(User)
entity_desc = TypeDescriptor.for_type(UserEntity)

user_user_entity_mapper = Mapper(
    MappingDefinition(source=User, target=UserEntity)
        .map(from_="user_id", to="user_id")
        .map(from_="locale", to="locale")
    )

user_entity_user_mapper = Mapper(
    MappingDefinition(source=UserEntity, target=User)
        .map(from_="user_id", to="user_id")
        .map(from_="locale", to="locale")
        #.map(all=matching_properties())
)

@service(name="user-service", description="cool")
class UserService(Service):
    @abstractmethod
    def create(self, user: User) -> User:
        pass

    @abstractmethod
    def read(self, id: str) -> User:
        pass

from typing import Generic, Type, TypeVar
from sqlalchemy.orm import Session

T = TypeVar("T")

def query():
    """
    Methods decorated with `@query` are queries.
    """
    def decorator(func):
        Decorators.add(func, query)

        return func

    return decorator

class BaseRepository(Generic[T]):
    # instance data

    _query_cache: dict[str, Callable[..., Any]] = {}

    # constructor

    def __init__(self, model: Type[T]):
        self.model = model

    # internal

    def _invoke_dynamic_query(self, method_name: str, *args, **kwargs):
        cache_key = method_name
        if cache_key not in self._query_cache:
            # parse the method name
            self._query_cache[cache_key] = self._create_query_func(method_name)
        func = self._query_cache[cache_key]
        return func(self, *args, **kwargs)

    def _create_query_func(self, method_name: str) -> Callable[..., Any]:
        """
        Converts method names like find_by_name_and_locale into a query function.
        """
        m = re.match(r"find_by_(.+)", method_name)
        if not m:
            raise ValueError(f"Cannot parse method name {method_name}")
        fields = m.group(1).split("_and_")

        def query_func(instance: "BaseRepository", *args, **kwargs):
            if len(args) > 0:
                # map positional args to field names
                query_kwargs = dict(zip(fields, args))
            else:
                query_kwargs = kwargs
            return instance.filter(**query_kwargs)

        return query_func

    # public

    def get_current_session(self):
        return _current_session.get()

    # query stuff

    def find(self, id_, mapper: Optional[Mapper] = None) -> T | None:
        result = self.get_current_session().get(self.model, id_)
        if result is not None:
            return mapper.map(result) if mapper is not None else result

    def get(self, id_, mapper: Optional[Mapper] = None) -> T:
        result = self.get_current_session().get(self.model, id_)
        if result is not None:
            return mapper.map(result) if mapper is not None else result

    def find_all(self, mapper: Optional[Mapper] = None) -> list[T]:
        return list(self.get_current_session().query(self.model))

    def save(self, entity: T) -> T:
        self.get_current_session().add(entity)

        return entity

    def delete(self, entity: T):
        self.get_current_session().delete(entity)

    def filter(self, **kwargs) -> list[T]:
        return self.get_current_session().query(self.model).filter_by(**kwargs).all()

    def exists(self, **kwargs) -> bool:
        return self.get_current_session().query(self.get_current_session().query(self.model)
                                  .filter_by(**kwargs)
                                  .exists()).scalar()

@injectable()
class UserRepository(BaseRepository[UserEntity]):
    # constructor

    def __init__(self, factory: SessionFactory):
        super().__init__(UserEntity)

        self.session_factory = factory

    # public

    @query()
    def find_by_locale(self):
        ...

    def find_by_id(self, user_id: str, mapper: Optional[Mapper] = None):
        return self.find(user_id, mapper=mapper)

@advice
@injectable()
class QueryAdvice:
    # constructor

    def __init__(self):
        pass

    # internal

    # advice

    @around(methods().decorated_with(query))
    def call_query(self, invocation: Invocation):
        func = invocation.func
        instance = invocation.args[0]
        args = invocation.args
        kwargs = invocation.kwargs

        method_name = func.__name__
        result = instance._invoke_dynamic_query(method_name, *args[1:], **kwargs)
        return result

# TEST

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
    @abstractmethod
    @get("/get/{message}")
    @requires_response()
    def get(self, message: str) -> str:
        pass

    @put("/put/{message}")
    def put(self, message: str) -> str:
        pass

    @post("/post_pydantic/{message}")
    def post_pydantic(self, message: str, data: Body(Pydantic)) -> Pydantic:
        pass

    @post("/post_data/{message}")
    def post_data(self, message: str, data: Body(Data)) -> Data:
        pass

    @delete("/delete/{message}")
    def delete(self, message: str) -> str:
        pass

@service(name="test-async-rest-service", description="cool")
@rest("/async-api")
class TestAsyncRestService(Service):
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
    UserService,
    TestAsyncService,
    TestRestService,
    TestAsyncRestService
])
class TestComponent(Component): # pylint: disable=abstract-method
    pass

# implementation classes

@implementation()
class UserServiceImpl(UserService):
    # constructor

    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    # implement

    @transactional()
    def create(self, user: User) -> User:
        self.user_repository.save(user_user_entity_mapper.map(user))

        return user

    @transactional()
    def read(self, id: str) -> User:
        self.user_repository.find_by_locale("en-DE")
        # TEST
        return self.user_repository.find_by_id(id, mapper=user_entity_user_mapper)

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
    @requires_response()
    def get(self, message: str) -> str:
        response = ResponseContext.get()

        response.set_cookie("name", "value")

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
    def create_server(self,  service_manager: ServiceManager, component_registry: ComponentRegistry, protobuf_manager: ProtobufManager) -> FastAPIServer:
        return FastAPIServer(fastapi, service_manager, component_registry, protobuf_manager)

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

    @create()
    def create_engine(self,  source: YamlConfigurationSource) -> DatabaseEngine:
        return DatabaseEngine(url="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")

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
