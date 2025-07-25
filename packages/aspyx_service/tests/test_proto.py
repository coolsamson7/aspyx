from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, cast

from fastapi import FastAPI
from pydantic import BaseModel

from aspyx.di import module, Environment, create
from aspyx_service import Service, ProtobufManager, ServiceModule, service, component, AbstractComponent, \
    ServiceManager, ComponentDescriptor, FastAPIServer, ComponentRegistry


class DataModel(BaseModel):
    optional_attr: Optional[str]

    str_attr: str
    bool_attr: bool
    int_attr: int

    str_attr_list: list[str]
    bool_attr_list: list[bool]
    int_attr_list: list[int]

@dataclass
class DataClass:
    optional_attr: Optional[str]

    str_attr: str
    bool_attr: bool
    int_attr: int

    str_attr_list: list[str]
    bool_attr_list: list[bool]
    int_attr_list: list[int]

@dataclass
class ComplexDataClass:
    data_class: DataClass
    model_class: DataModel

    data_classes: list[DataClass]
    model_classes: list[DataModel]

# some constants

data_class = DataClass(optional_attr=None, str_attr="", bool_attr=False, int_attr=0, str_attr_list=[""], bool_attr_list=[False], int_attr_list=[1])
model_class = DataModel(optional_attr=None, str_attr="", bool_attr=False, int_attr=0, str_attr_list=[""], bool_attr_list=[False], int_attr_list=[1])

complex_data_class = ComplexDataClass(data_class=data_class, model_class=model_class,data_classes=[data_class], model_classes=[model_class])

@service()
class ProtobufService(Service):
    def call_scalars(self, n: int, b: bool, s: str):
        pass

    def call_scalar_lists(self, n: list[int], b: list[bool], s: list[str]):
        pass

    def call_data_class(self, data_class: DataClass):
        pass

    def call_data_model(self, data_class: DataModel):
        pass

    def call_complex(self, data_class: ComplexDataClass):
        pass

@component(services=[ProtobufService])
class TestComponent(AbstractComponent):
    pass

from .common import Module

environment = Environment(Module)
service_manager = environment.get(ServiceManager)
server = environment.get(FastAPIServer)

service_manager.channel_factory.prepare_channel(server,"dispatch-protobuf", cast(ComponentDescriptor, service_manager.get_descriptor(TestComponent)))
protobuf_manager = environment.get(ProtobufManager)

class TestProto:
    def test_complex_data_model(self):
        method = getattr(ProtobufService, "call_complex")

        serializer = protobuf_manager.create_serializer(ProtobufService, method)

        args = [complex_data_class]

        message = serializer.serialize_args(args)

        deserializer = protobuf_manager.create_deserializer(message.DESCRIPTOR, method)

        deserialized_args = deserializer.deserialize(message)

        assert args == deserialized_args

    def test_data_model(self):
        method = getattr(ProtobufService, "call_data_model")

        serializer = protobuf_manager.create_serializer(ProtobufService, method)

        args = [model_class]

        message = serializer.serialize_args(args)

        deserializer = protobuf_manager.create_deserializer(message.DESCRIPTOR, method)

        deserialized_args = deserializer.deserialize(message)

        assert args == deserialized_args

    def test_data_class(self):
        method = getattr(ProtobufService, "call_data_class")

        serializer = protobuf_manager.create_serializer(ProtobufService, method)

        args = [data_class]

        message = serializer.serialize_args(args)

        deserializer = protobuf_manager.create_deserializer(message.DESCRIPTOR, method)

        deserialized_args = deserializer.deserialize(message)

        assert args == deserialized_args

    def test_scalars(self):
        method = getattr(ProtobufService, "call_scalars")

        serializer = protobuf_manager.create_serializer(ProtobufService, method)

        args = [1, False, ""]

        message = serializer.serialize_args(args)

        deserializer = protobuf_manager.create_deserializer(message.DESCRIPTOR, method)

        deserialized_args = deserializer.deserialize(message)

        assert args == deserialized_args

    def test_scalar_lists(self):
        method = getattr(ProtobufService, "call_scalar_lists")

        serializer = protobuf_manager.create_serializer(ProtobufService, method)

        args = [[1], [False], [""]]

        message = serializer.serialize_args(args)

        deserializer = protobuf_manager.create_deserializer(message.DESCRIPTOR, method)

        deserialized_args = deserializer.deserialize(message)

        assert args == deserialized_args

