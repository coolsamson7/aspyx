"""
Tests
"""
import logging

from aspyx.reflection import TypeDescriptor
from aspyx.util import Logger

Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.INFO,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.DEBUG,
    "aspyx.event": logging.INFO
})


from .common import TestService, TestRestService, Pydantic, Data, service_manager, Foo, EmbeddedPydantic, \
    EmbeddedDataClass, UserService, User, UserEntity
from .json_schema_generator import JSONSchemaGenerator
from .openapi_generator import OpenAPIGenerator

embedded_pydantic=EmbeddedPydantic(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s")
embedded_dataclass=EmbeddedDataClass(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s")
pydantic = Pydantic(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s", int_list_attr=[1], float_list_attr=[1.0], bool_list_attr=[True], str_list_attr=[""],
                    embedded_pydantic=embedded_pydantic,
                    embedded_dataclass=embedded_dataclass,
                    embedded_pydantic_list =[embedded_pydantic],
                    embedded_dataclass_list=[embedded_dataclass])
data = Data(int_attr=1, float_attr=1.0, bool_attr=True, str_attr="s", int_list_attr=[1], float_list_attr=[1.0], bool_list_attr=[True], str_list_attr=[""])

def get_properties(cls):
    return {
        name: attr
        for name, attr in vars(cls).items()
        if isinstance(attr, property)
    }

def get_descriptors(cls):
    descriptors = {}
    for base in cls.__mro__:
        for name, attr in vars(base).items():
            if hasattr(attr, "__get__") or hasattr(attr, "__set__"):
                descriptors[name] = attr
    return descriptors

from dataclasses import is_dataclass, fields as dc_fields
from typing import Any, Dict, Type, get_type_hints, Callable
from pydantic import BaseModel
from sqlalchemy.orm import class_mapper, ColumnProperty

def collect_properties(cls: Type) -> Dict[str, Any]:
    """
    Collect properties from normal classes, dataclasses, Pydantic models, and SQLAlchemy models.
    Returns a dict: {name: type or descriptor}
    """
    props: dict[str, Any] = {}

    # 1️⃣ Dataclass
    if is_dataclass(cls):
        for f in dc_fields(cls):
            props[f.name] = f.type
        return props

    # 2️⃣ Pydantic (v2 and v1 compatible)
    if issubclass(cls, BaseModel):
        model_fields = getattr(cls, "model_fields", None) or getattr(cls, "__fields__", {})
        for name, field in model_fields.items():
            props[name] = getattr(field, "annotation", getattr(field, "type_", Any))
        return props

    # 3️⃣ SQLAlchemy model (has a mapper)
    try:
        from sqlalchemy.orm import class_mapper
        mapper = class_mapper(cls)
        for attr in mapper.attrs:
            if isinstance(attr, ColumnProperty):
                column = attr.columns[0]
                props[attr.key] = getattr(column.type, "python_type", Any)
        return props
    except Exception:
        pass

    # 4️⃣ Normal Python class (fallback)
    # Try annotations / type hints
    type_hints = get_type_hints(cls)
    if type_hints:
        return type_hints

    # Otherwise use __dict__ and @property attributes
    for name, attr in vars(cls).items():
        if isinstance(attr, property):
            props[name] = attr
        elif not name.startswith("__"):
            props[name] = type(attr)

    return props


def make_setter(cls: Type, field_name: str) -> Callable[[Any, Any], None]:
    attr = getattr(cls, field_name, None)

    # If it's a property with a fset, call that directly
    if isinstance(attr, property) and attr.fset:
        fset = attr.fset
        def setter(instance: Any, value: Any):
            fset(instance, value)
        return setter

    # Default: setattr
    def setter(instance: Any, value: Any):
        setattr(instance, field_name, value)

    return setter


class Foo:
    user_id : str
    locale: str


class TestLocalService:


    def test_properties(self, service_manager):
        # normal

        foo = Foo()
        foo.user_id="id"
        foo.locale="locale"
        p0 = collect_properties(Foo)
        make_setter(User, "id")(foo, "ID1")

        # dataclass

        user = User(user_id="id", locale="locale")

        p1 = collect_properties(User)

        make_setter(User, "id")(user, "ID1")

        # PYDANTIC

        p2 = collect_properties(Pydantic)
        make_setter(Pydantic, "int_attr")(pydantic, -1)

        # entity

        entity = UserEntity(user_id="user", locale="lcoale")
        p3 = collect_properties(UserEntity)
        make_setter(UserEntity, "user_id")(entity, "andi")

        d = TypeDescriptor.for_type(UserEntity)

        print(1)

    def test_orm(self, service_manager):
        user_desc = TypeDescriptor.for_type(User)
        user_entity_desc = TypeDescriptor.for_type(UserEntity)

        user_service = service_manager.get_service(UserService, preferred_channel="local")

        #user = user_service.create(User(user_id="2", locale="en-US"))

        user = user_service.read("2")

        print(user)

    def test_openapi(self, service_manager):
        open_api = OpenAPIGenerator(service_manager).generate()

        json_str = OpenAPIGenerator(service_manager).to_json()  # pretty-printed JSON
        print(json_str)
        json_str = JSONSchemaGenerator(service_manager).to_json()  # pretty-printed JSON
        print(json_str)


    def test_local(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="local")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def test_throw(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="local")

        try:
            test_service.throw("hello")
        except Exception as e:
            print(e)

    def test_inject(self, service_manager):
        test = service_manager.environment.get(Foo)

        assert test.service is not None

class TestSyncRemoteService:
    def test_dispatch_json(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def test_dispatch_protobuf(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-protobuf")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic


    def test_dispatch_msgpack(self, service_manager):
        test_service = service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

        result = test_service.hello("hello")
        assert result == "hello"

        result_data = test_service.data(data)
        assert result_data == data

        result_pydantic = test_service.pydantic(pydantic)
        assert result_pydantic == pydantic

    def test_dispatch_rest(self, service_manager):
        test_service = service_manager.get_service(TestRestService, preferred_channel="rest")

        #result = test_service.get("hello")
        #assert result == "hello"

        #result = test_service.put("hello")
        #assert result == "hello"

        #result = test_service.delete("hello")
        #assert result == "hello"

        # data and pydantic

        #result_pydantic = test_service.post_pydantic("message", pydantic)
        #assert result_pydantic == pydantic

        result_data= test_service.post_data("message", data)
        assert result_data == data
