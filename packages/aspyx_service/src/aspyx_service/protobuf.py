"""
Protobuf channel and utilities
"""
from __future__ import annotations

import inspect
import logging
import threading
from dataclasses import is_dataclass, fields as dc_fields
from typing import Type, get_type_hints, Callable, Tuple, get_origin, get_args, List, Dict, Any, Union, Sequence, \
    Optional, cast

import httpx
from google.protobuf.message_factory import GetMessageClass
from pydantic import BaseModel

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message
from google.protobuf.descriptor import FieldDescriptor, Descriptor
from starlette.responses import PlainTextResponse

from aspyx.di import injectable, Environment
from aspyx.reflection import DynamicProxy, TypeDescriptor
from aspyx.util import CopyOnWriteCache, StringBuilder

from .service import channel, ServiceException, Server, ComponentDescriptor
from .channels import HTTPXChannel
from .service  import ServiceManager, ServiceCommunicationException, AuthorizationException, RemoteServiceException

def get_inner_type(typ: Type) -> Type:
    """
    Extract the inner type from List[InnerType], Optional[InnerType], etc.
    """
    origin = getattr(typ, "__origin__", None)
    args = getattr(typ, "__args__", None)

    if origin in (list, List):
        return args[0] if args else Any

    # Handle Optional[X] -> X
    if origin is Union and len(args) == 2 and type(None) in args:
        return args[0] if args[1] is type(None) else args[1]

    return typ


def defaults_dict(model_cls: Type[BaseModel]) -> dict[str, Any]:
    result = {}
    for name, field in model_cls.model_fields.items():
        if field.default is not None:
            result[name] = field.default
        elif field.default_factory is not None:
            result[name] = field.default_factory()
    return result

class ProtobufBuilder:
    """
    used to infer protobuf services and messages given component and service structures.
    """
    logger = logging.getLogger("aspyx.service.protobuf")  #

    # slots

    __slots__ = [
        "pool",
        "factory",
        "modules",
        "components",
        "lock"
    ]

    @classmethod
    def get_message_name(cls, type: Type, suffix="") -> str:
        module = type.__module__.replace(".", "_")
        name = type.__name__

        return f"{module}.{name}{suffix}"

    @classmethod
    def get_request_message_name(cls, type: Type, method: Callable) -> str:
        return cls.get_message_name(type, f"_{method.__name__}_Request")

    @classmethod
    def get_response_message_name(cls, type: Type, method: Callable) -> str:
        return cls.get_message_name(type, f"_{method.__name__}_Response")

    # local classes

    class Module:
        # constructor

        def __init__(self, builder: ProtobufBuilder, name: str):
            self.builder = builder
            self.name = name.replace(".", "_")
            self.file_desc_proto = descriptor_pb2.FileDescriptorProto()  # type: ignore
            self.file_desc_proto.name = f"{self.name}.proto"
            self.file_desc_proto.package = self.name
            self.types : dict[Type, Any] = {}
            self.sealed = False
            self.lock = threading.RLock()

        # public

        def get_fields_and_types(self, type: Type) -> List[Tuple[str, Type]]:
            hints = get_type_hints(type)

            if is_dataclass(type):
                return [(f.name, hints.get(f.name, str)) for f in dc_fields(type)]

            if issubclass(type, BaseModel):
                return [(name, hints.get(name, str)) for name in type.model_fields]

            raise TypeError("Expected a dataclass or Pydantic model class.")

        def add_message(self, cls: Type) -> str:
            if self.sealed:
                raise ServiceException(f"module {self.name} is already sealed")



            name = cls.__name__
            full_name = f"{self.name}.{name}"

            ProtobufBuilder.logger.debug(f"adding message %s", full_name)

            # Check if a message type is already defined

            if any(m.name == name for m in self.file_desc_proto.message_type):
                return f".{full_name}"

            desc = descriptor_pb2.DescriptorProto()  # type: ignore
            desc.name = name

            # Extract fields from dataclass or pydantic model

            if is_dataclass(cls) or issubclass(cls, BaseModel):
                index = 1
                for field_name, field_type in self.get_fields_and_types(cls):
                    field_type_enum, label, type_name = self.builder.to_proto_type(self, field_type)

                    f = desc.field.add()
                    f.name = field_name
                    f.number = index
                    f.label = label
                    f.type = field_type_enum
                    if type_name:
                        f.type_name = type_name
                    index += 1

            # add message type descriptor to the file descriptor proto

            self.file_desc_proto.message_type.add().CopyFrom(desc)

            return f".{full_name}"

        def check_message(self, origin, type: Type) -> str:
            if type not in self.types:
                if self is not origin:
                    if not self.name in  origin.file_desc_proto.dependency:
                        origin.file_desc_proto.dependency.append(self.file_desc_proto.name)

                self.types[type] = self.add_message(type)

            return self.types[type]

        def build_request_message(self, method: TypeDescriptor.MethodDescriptor, request_name: str):
            if self.sealed:
                raise ServiceException(f"module {self.name} is already sealed")

            request_msg = descriptor_pb2.DescriptorProto()  # type: ignore
            request_msg.name = request_name.split(".")[-1]

            ProtobufBuilder.logger.debug(f"adding request message %s", request_msg.name)

            # loop over parameters

            field_index = 1
            for param in method.params:
                field = request_msg.field.add()

                field.name = param.name
                field.number = field_index

                field_type, label, type_name = self.builder.to_proto_type(self, param.type)
                field.type = field_type
                field.label = label
                if type_name:
                    field.type_name = type_name

                field_index += 1

            # add to service file descriptor

            self.file_desc_proto.message_type.add().CopyFrom(request_msg)

        def build_response_message(self, method: TypeDescriptor.MethodDescriptor, response_name: str):
            if self.sealed:
                raise ServiceException(f"module {self.name} is already sealed")

            response_msg = descriptor_pb2.DescriptorProto()  # type: ignore
            response_msg.name = response_name.split(".")[-1]

            ProtobufBuilder.logger.debug(f"adding response message %s", response_msg.name)

            # return

            return_type = method.return_type
            response_field = response_msg.field.add()
            response_field.name = "result"
            response_field.number = 1

            field_type, label, type_name = self.builder.to_proto_type(self, return_type)
            response_field.type = field_type
            response_field.label = label
            if type_name:
                response_field.type_name = type_name

            # exception

            exception_field = response_msg.field.add()
            exception_field.name = "exception"
            exception_field.number = 2

            field_type, label, type_name = self.builder.to_proto_type(self, str)
            exception_field.type = field_type
            exception_field.label = label
            if type_name:
                exception_field.type_name = type_name

            # add to service file descriptor

            self.file_desc_proto.message_type.add().CopyFrom(response_msg)

        def build_service_method(self, service_desc: descriptor_pb2.ServiceDescriptorProto, service_type: TypeDescriptor, method: TypeDescriptor.MethodDescriptor):
            name = f"{service_type.cls.__name__}_{method.get_name()}"
            package = self.name

            method_desc =  descriptor_pb2.MethodDescriptorProto()

            request_name = f".{package}.{name}_Request"
            response_name = f".{package}.{name}_Response"

            method_desc.name = method.get_name()
            method_desc.input_type = request_name
            method_desc.output_type = response_name

            # Build request and response message types

            self.build_request_message(method, request_name)
            self.build_response_message(method, response_name)

            # Add method to service descriptor

            service_desc.method.add().CopyFrom(method_desc)

        def add_service(self, service_type: TypeDescriptor):
            if self.sealed:
                raise ServiceException(f"module {self.name} is already sealed")

            service_desc = descriptor_pb2.ServiceDescriptorProto()  # type: ignore
            service_desc.name = service_type.cls.__name__

            ProtobufBuilder.logger.debug(f"add service %s", service_desc.name)

            # check methods

            for method in service_type.get_methods():
                self.build_service_method(service_desc, service_type, method)

            # done

            self.file_desc_proto.service.add().CopyFrom(service_desc)

        def seal(self, builder: ProtobufBuilder):
            if not self.sealed:
                ProtobufBuilder.logger.debug(f"create protobuf {self.file_desc_proto.name}")

                self.sealed = True

                # add dependency first

                for dependency in self.file_desc_proto.dependency:
                    builder.modules[dependency].seal(builder)

                builder.pool.Add(self.file_desc_proto)

                #print(ProtobufDumper.dump_proto(self.file_desc_proto))

    # constructor

    def __init__(self):
        self.pool: DescriptorPool = descriptor_pool.Default()
        self.factory = message_factory.MessageFactory(self.pool)
        self.modules: Dict[str, ProtobufBuilder.Module] = {}
        self.components = {}
        self.lock = threading.RLock()

    # internal

    def to_proto_type(self, module_origin, py_type: Type) -> Tuple[int, int, Optional[str]]:
        """
        Convert Python type to protobuf (field_type, label, type_name).
        Returns:
            - field_type: int (descriptor_pb2.FieldDescriptorProto.TYPE_*)
            - label: int (descriptor_pb2.FieldDescriptorProto.LABEL_*)
            - type_name: Optional[str] (fully qualified message name for messages)
        """
        origin = get_origin(py_type)
        args = get_args(py_type)

        # Check for repeated fields (list / List)
        if origin in (list, List):
            # Assume single-argument generic list e.g. List[int], List[FooModel]
            item_type = args[0] if args else str
            field_type, _, type_name = self._resolve_type(module_origin, item_type)
            return (
                field_type,
                descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,  # type: ignore
                type_name,
            )

        return self._resolve_type(module_origin, py_type)

    def _resolve_type(self, origin, py_type: Type) -> Tuple[int, int, Optional[str]]:
        """Resolves Python type to protobuf scalar or message type with label=optional."""
        # Structured message (dataclass or Pydantic BaseModel)
        if is_dataclass(py_type) or (inspect.isclass(py_type) and issubclass(py_type, BaseModel)):
            type_name =  self.get_module(py_type).check_message(origin, py_type)
            return (
                descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE,  # type: ignore
                descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,  # type: ignore
                type_name,
            )

        # Scalar mappings

        scalar = self._map_scalar_type(py_type)

        return scalar, descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL, None  # type: ignore

    def _map_scalar_type(self, py_type: Type) -> int:
        """Map Python scalar types to protobuf field types."""
        mapping = {
            str: descriptor_pb2.FieldDescriptorProto.TYPE_STRING,  # type: ignore
            int: descriptor_pb2.FieldDescriptorProto.TYPE_INT32,  # type: ignore
            float: descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT,  # type: ignore
            bool: descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,  # type: ignore
            bytes: descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,  # type: ignore
        }

        return mapping.get(py_type, descriptor_pb2.FieldDescriptorProto.TYPE_STRING)  # type: ignore

    def check_type(self, type: Type):
        self.get_module(type).check_message(type)

    def get_message_type(self, full_name: str):
        return GetMessageClass(self.pool.FindMessageTypeByName(full_name))

    def get_request_message(self, type: Type, method: Callable):
        return self.get_message_type(self.get_request_message_name(type, method))

    def get_response_message(self, type: Type, method: Callable):
        return self.get_message_type(self.get_response_message_name(type, method))

    def get_module(self, type: Type):
        name = type.__module__#.replace(".", "_")
        key = name.replace(".", "_") + ".proto"
        module = self.modules.get(key, None)
        if module is None:
            module = ProtobufBuilder.Module(self, name)
            self.modules[key] = module

        return module

    def build_service(self, service: TypeDescriptor):
        self.get_module(service.cls).add_service(service)

    # public

    #@synchronized()
    def prepare_component(self, component_descriptor: ComponentDescriptor):
        with self.lock:
            if component_descriptor not in self.components:
                for service in component_descriptor.services:
                    self.build_service(TypeDescriptor.for_type(service.type))

                # finalize

                for module in self.modules.values():
                    module.seal(self)

                # done

                self.components[component_descriptor] = True


@injectable()
class ProtobufManager(ProtobufBuilder):
    # local classes

    class MethodDeserializer:
        __slots__ = [
            "manager",
            "descriptor",
            "getters"
        ]

        # constructor

        def __init__(self, manager: ProtobufManager, descriptor: Descriptor):
            self.manager = manager
            self.descriptor = descriptor

            self.getters = []

        # internal

        def args(self, method: Callable)-> ProtobufManager.MethodDeserializer:
            type_hints = get_type_hints(method)

            # loop over parameters

            for param_name in inspect.signature(method).parameters:
                if param_name == "self":
                    continue

                field_desc = self.descriptor.fields_by_name[param_name]

                self.getters.append(self._create_getter(field_desc, param_name, type_hints.get(param_name, str)))

            return self

        def result(self, method: Callable) -> 'ProtobufManager.MethodDeserializer':
            type_hints = get_type_hints(method)

            return_type = type_hints.get('return')

            result_field_desc = self.descriptor.DESCRIPTOR.fields_by_name["result"]
            exception_field_desc = self.descriptor.DESCRIPTOR.fields_by_name["exception"]

            self.getters.append(self._create_getter(result_field_desc, "result", return_type))
            self.getters.append(self._create_getter(exception_field_desc, "exception", str))

            return self

        def get_fields_and_types(self, type: Type) -> List[Tuple[str, Type]]:
            hints = get_type_hints(type)

            if is_dataclass(type):
                return [(f.name, hints.get(f.name, str)) for f in dc_fields(type)]

            if issubclass(type, BaseModel):
                return [(name, hints.get(name, str)) for name in type.model_fields]

            raise TypeError("Expected a dataclass or Pydantic model class.")

        def _create_getter(self, field_desc: FieldDescriptor, field_name: str, type: Type):
            is_repeated = field_desc.label == field_desc.LABEL_REPEATED
            is_message = field_desc.message_type is not None

            ## local func

            def compute_class_getters(item_type: Type) -> list[Callable]:
                getters = []

                for sub_field_name, field_type in self.get_fields_and_types(item_type):
                    getters.append(self._create_getter(message_type.fields_by_name[sub_field_name], sub_field_name, field_type))

                return getters

            # list

            if is_repeated:
                item_type = get_args(type)[0] if get_origin(type) in (list, List) else str

                # list of messages

                if is_dataclass(item_type) or issubclass(item_type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(item_type))

                    getters = self.manager.getter_lambdas_cache.get(item_type, compute_class_getters)

                    def deserialize_dataclass_list(msg: Message, val: Any, setter=setattr, getters=getters):
                        list = []

                        for item in getattr(msg, field_name):
                            instance = item_type.__new__(item_type)

                            for getter in getters:
                                getter(item, instance, object.__setattr__)

                            list.append(instance)

                        setter(val, field_name,  list)

                    default = {}
                    if issubclass(item_type, BaseModel):
                        default = defaults_dict(item_type)

                    def deserialize_pydantic_list(msg: Message, val: Any, setter=setattr, getters=getters):
                        list = []

                        for item in getattr(msg, field_name):
                            #instance = type.__new__(type)

                            instance = item_type.model_construct(**default)

                            for getter in getters:
                                getter(item, instance, setattr)

                            list.append(instance)

                        setter(val, field_name, list)

                    if is_dataclass(item_type):
                        return deserialize_dataclass_list
                    else:
                        return deserialize_pydantic_list

                # list of scalars

                else:
                    def deserialize_list(msg: Message, val,  setter=setattr):
                        list = []

                        for item in getattr(msg, field_name):
                            list.append(item)

                        setter(val, field_name, list)

                    return deserialize_list

            # message

            elif is_message:
                if is_dataclass(type) or issubclass(type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(type))

                    sub_getters = self.manager.getter_lambdas_cache.get(type, compute_class_getters)

                    default = {}
                    if issubclass(type, BaseModel):
                        default = defaults_dict(type)

                    def deserialize_dataclass(msg: Message, val: Any,  setter=setattr, getters=sub_getters):
                        sub_message = getattr(msg, field_name)

                        instance = type.__new__(type)

                        for getter in getters:
                            getter(sub_message, instance, setattr)#object.__setattr__

                        setter(val, field_name, instance)

                    def deserialize_pydantic(msg: Message, val: Any, setter=setattr, getters=sub_getters):
                        sub_message = getattr(msg, field_name)

                        instance = type.model_construct(**default)

                        for getter in getters:
                            getter(sub_message, instance, setattr)

                        setter(val, field_name, instance)

                    if is_dataclass(type):
                        return deserialize_dataclass
                    else:
                        return deserialize_pydantic
                else:
                    raise TypeError(f"Expected dataclass or BaseModel for field '{field_name}', got {type}")

            # scalar

            else:
                def deserialize_scalar(msg: Message, val: Any,  setter=setattr):
                    if msg.HasField(field_name):
                        setter(val, field_name, getattr(msg, field_name))
                    else:
                        setter(val, field_name, None)

                return deserialize_scalar

        # public

        def deserialize(self, message: Message) -> list[Any]:
            # call setters

            list = []
            for getter in self.getters:
                getter(message, list, lambda obj, prop, value: list.append(value))

            return list

        def deserialize_result(self, message: Message) -> Any:
            result = None
            exception = None

            def set_result(obj, prop, value):
                nonlocal result, exception

                if prop == "result":
                    result = value
                else:
                    exception = value

            # call setters

            for getter in self.getters:
                getter(message, None, set_result)

            if result is None:
                raise RemoteServiceException(f"server side exception {exception}")

            return result

    class MethodSerializer:
        __slots__ = [
            "manager",
            "message_type",
            "setters"
        ]

        # constructor

        def __init__(self, manager: ProtobufManager, message_type):
            self.manager = manager
            self.message_type = message_type

            self.setters = []

        def result(self, method: Callable) -> ProtobufManager.MethodSerializer:
            msg_descriptor = self.message_type.DESCRIPTOR
            type_hints = get_type_hints(method)

            return_type = type_hints["return"]

            result_field_desc = msg_descriptor.fields_by_name["result"]
            exception_field_desc = msg_descriptor.fields_by_name["exception"]

            self.setters.append(self._create_setter(result_field_desc, "result", return_type))
            self.setters.append(self._create_setter(exception_field_desc, "exception", str))

            return self

        def args(self, method: Callable)-> ProtobufManager.MethodSerializer:
            msg_descriptor = self.message_type.DESCRIPTOR
            type_hints = get_type_hints(method)

            # loop over parameters

            for param_name in inspect.signature(method).parameters:
                if param_name == "self":
                    continue

                field_desc = msg_descriptor.fields_by_name[param_name]

                self.setters.append(self._create_setter(field_desc, param_name, type_hints.get(param_name, str)))

            # done

            return self

        def get_fields_and_types(self, type: Type) -> List[Tuple[str, Type]]:
            hints = get_type_hints(type)

            if is_dataclass(type):
                return [(f.name, hints.get(f.name, str)) for f in dc_fields(type)]

            if issubclass(type, BaseModel):
                return [(name, hints.get(name, str)) for name in type.model_fields]

            raise TypeError("Expected a dataclass or Pydantic model class.")

        def _create_setter(self, field_desc: FieldDescriptor, field_name: str, type: Type):
            is_repeated = field_desc.label == field_desc.LABEL_REPEATED
            is_message = field_desc.message_type is not None

            # local func

            def create(message_type: Descriptor, item_type: Type) -> Tuple[list[Callable],list[str]]:
                setters = []
                fields = []
                for field_name, field_type in self.get_fields_and_types(item_type):
                    fields.append(field_name)
                    setters.append(self._create_setter(message_type.fields_by_name[field_name], field_name, field_type))

                return setters, fields

            # list

            if is_repeated:
                item_type = get_args(type)[0] if get_origin(type) in (list, List) else str

                # list of messages

                if is_dataclass(item_type) or issubclass(item_type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(item_type))

                    setters, fields = self.manager.setter_lambdas_cache.get(item_type, lambda t: create(message_type, item_type))

                    def serialize_message_list(msg: Message, val: Any, fields=fields, setters=setters):
                        for item in val:
                            msg_item = getattr(msg, field_name).add()
                            for i in range(len(setters)):
                                setters[i](msg_item, getattr(item, fields[i]))

                    return serialize_message_list

                # list of scalars

                else:
                    return lambda msg, val: getattr(msg, field_name).extend(val)

            # message

            elif is_message:
                if is_dataclass(type) or issubclass(type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(type))

                    sub_setters, fields = self.manager.setter_lambdas_cache.get(type, lambda t: create(message_type, type))

                    def serialize_message(msg: Message, val: Any, fields=fields, setters=sub_setters):
                        field = getattr(msg, field_name)
                        for i in range(len(sub_setters)):
                            setters[i](field, getattr(val, fields[i]))

                    return serialize_message
                else:
                    raise TypeError(f"Expected dataclass or BaseModel for field '{field_name}', got {type}")

            # scalar

            else:
                def set_attr(msg, val):
                    if val is not None:
                        setattr(msg, field_name, val)
                    else:
                        pass#delattr(msg, field_name)

                return set_attr# lambda msg, val: setattr(msg, field_name, val)

        def serialize(self, value: Any) -> Any:
            # create message instance

            message = self.message_type()

            # call setters

            for i in range(len(self.setters)):
                self.setters[i](message, value)

            return message

        def serialize_result(self, value: Any, exception: str) -> Any:
            # create message instance

            message = self.message_type()

            # call setters

            if value is not None:
                self.setters[0](message, value)

            if exception is not None:
                self.setters[1](message, exception)

            return message

        def serialize_args(self, args: Sequence[Any]) -> Any:
            # create message instance

            message = self.message_type()

            # call setters

            for i in range(len(self.setters)):
                self.setters[i](message, args[i])

            #for setter, value in zip(self.setters, invocation.args):
            #    setter(message, value)

            return message

    # slots

    __slots__ = [
        "serializer_cache",
        "deserializer_cache",
        "result_serializer_cache",
        "result_deserializer_cache",
        "setter_lambdas_cache",
        "getter_lambdas_cache"
    ]

    # constructor

    def __init__(self):
        super().__init__()

        self.serializer_cache = CopyOnWriteCache[Callable, ProtobufManager.MethodSerializer]()
        self.deserializer_cache = CopyOnWriteCache[Descriptor, ProtobufManager.MethodDeserializer]()

        self.result_serializer_cache = CopyOnWriteCache[Descriptor, ProtobufManager.MethodSerializer]()
        self.result_deserializer_cache = CopyOnWriteCache[Descriptor, ProtobufManager.MethodDeserializer]()

        self.setter_lambdas_cache = CopyOnWriteCache[Type, list[Callable]]()
        self.getter_lambdas_cache = CopyOnWriteCache[Type, Tuple[list[Callable], list[str]]]()

    # public

    def create_serializer(self, type: Type, method: Callable) -> ProtobufManager.MethodSerializer:
        return self.serializer_cache.get(method, lambda m: ProtobufManager.MethodSerializer(self, self.get_request_message(type, m)).args(m) )

    def create_deserializer(self, descriptor: Descriptor, method: Callable) -> ProtobufManager.MethodDeserializer:
        return self.deserializer_cache.get(descriptor, lambda d:  ProtobufManager.MethodDeserializer(self, d).args(method))

    def create_result_serializer(self, descriptor: Descriptor, method: Callable) -> ProtobufManager.MethodSerializer:
        return self.result_serializer_cache.get(descriptor, lambda d: ProtobufManager.MethodSerializer(self, d).result(method))

    def create_result_deserializer(self, descriptor: Descriptor, method: Callable) -> ProtobufManager.MethodDeserializer:
        return  self.result_deserializer_cache.get(descriptor, lambda d: ProtobufManager.MethodDeserializer(self, d).result(method))

    def report(self) -> str:
        builder = StringBuilder()
        for module in self.modules.values():
            builder.append(ProtobufDumper.dump_proto(module.file_desc_proto))

        return str(builder)

@channel("dispatch-protobuf")
class ProtobufChannel(HTTPXChannel):
    """
    channel, encoding requests and responses with protobuf
    """
    # class methods

    @classmethod
    def prepare(cls,  server: Server, component_descriptor: ComponentDescriptor):
        protobuf_manager = server.get(ProtobufManager)
        protobuf_manager.prepare_component(component_descriptor)

        def report_protobuf():
            return protobuf_manager.report()

        server.add_route(path="/report-protobuf", endpoint=report_protobuf, methods=["GET"], response_class=PlainTextResponse)

    # local classes

    class Call:
        __slots__ = [
            "method_name",
            "serializer",
            "response_type",
            "deserializer"
        ]

        # constructor

        def __init__(self, method_name: str, serializer: ProtobufManager.MethodSerializer, response_type, deserializer: ProtobufManager.MethodDeserializer):
            self.method_name = method_name
            self.serializer = serializer
            self.response_type = response_type
            self.deserializer = deserializer

        # public

        def serialize(self, args: Sequence[Any]) -> Any:
            message = self.serializer.serialize_args(args)
            return message.SerializeToString()

        def deserialize(self, http_response: httpx.Response) -> Any:
            response = self.response_type()
            response.ParseFromString(http_response.content)

            return self.deserializer.deserialize_result(response)

    # slots

    __slots__ = [
        "manager",
        "environment",
        "protobuf_manager",
        "cache"
    ]

    # constructor

    def __init__(self, manager: ServiceManager, protobuf_manager: ProtobufManager):
        super().__init__()

        self.manager = manager
        self.environment = None
        self.protobuf_manager = protobuf_manager
        self.cache = CopyOnWriteCache[Callable, ProtobufChannel.Call]()

        # make sure, all protobuf messages are created

        for descriptor in manager.descriptors.values():
            if descriptor.is_component():
                protobuf_manager.prepare_component(cast(ComponentDescriptor, descriptor))

    # internal

    def get_call(self, type: Type, method: Callable) -> ProtobufChannel.Call:
        call = self.cache.get(method)
        if call is None:
            method_name   = f"{self.component_descriptor.name}:{self.service_names[type]}:{method.__name__}"
            serializer    = self.protobuf_manager.create_serializer(type, method)
            response_type = self.protobuf_manager.get_message_type(self.protobuf_manager.get_response_message_name(type, method))
            deserializer  = self.protobuf_manager.create_result_deserializer(response_type, method)

            call = ProtobufChannel.Call(method_name, serializer, response_type, deserializer)

            self.cache.put(method, call)

        return call

    # implement

    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        call = self.get_call(invocation.type, invocation.method)

        try:
            http_result = await self.request_async("post", f"{self.get_url()}/invoke", content=call.serialize(invocation.args),
                                       timeout=self.timeout, headers={
                    "Content-Type": "application/x-protobuf",
                    # "Accept": "application/x-protobuf",
                    "x-rpc-method": call.method_name
                })

            return call.deserialize(http_result)
        except (ServiceCommunicationException, AuthorizationException, RemoteServiceException) as e:
            raise

        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e

    def invoke(self, invocation: DynamicProxy.Invocation):
        call = self.get_call(invocation.type, invocation.method)

        try:
            http_result = self.request("post", f"{self.get_url()}/invoke", content=call.serialize(invocation.args), timeout=self.timeout,  headers={
                    "Content-Type": "application/x-protobuf",
                    #"Accept": "application/x-protobuf",
                    "x-rpc-method": call.method_name
            })

            return call.deserialize(http_result)
        except (ServiceCommunicationException, AuthorizationException, RemoteServiceException) as e:
            raise

        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e

class ProtobufDumper:
    @classmethod
    def dump_proto(cls, fd: descriptor_pb2.FileDescriptorProto) -> str:
        lines = []

        # Syntax

        syntax = fd.syntax if fd.syntax else "proto2"
        lines.append(f'syntax = "{syntax}";\n')

        # Package

        if fd.package:
            lines.append(f'package {fd.package};\n')

        # Imports

        for dep in fd.dependency:
            lines.append(f'import "{dep}";')

        if fd.dependency:
            lines.append('')  # blank line

        # Options (basic)

        for opt in fd.options.ListFields() if fd.HasField('options') else []:
            # Just a simple string option dump; for complex options you'd need more logic
            name = opt[0].name
            value = opt[1]
            lines.append(f'option {name} = {value};')
        if fd.HasField('options'):
            lines.append('')

        # Enums

        def dump_enum(enum: descriptor_pb2.EnumDescriptorProto, indent=''):
            enum_lines = [f"{indent}enum {enum.name} {{"]
            for value in enum.value:
                enum_lines.append(f"{indent}  {value.name} = {value.number};")
            enum_lines.append(f"{indent}}}\n")
            return enum_lines

        # Messages (recursive)

        def dump_message(msg: descriptor_pb2.DescriptorProto, indent=''):
            msg_lines = [f"{indent}message {msg.name} {{"]
            # Nested enums
            for enum in msg.enum_type:
                msg_lines.extend(dump_enum(enum, indent + '  '))

            # Nested messages

            for nested in msg.nested_type:
                # skip map entry messages (synthetic)
                if nested.options.map_entry:
                    continue
                msg_lines.extend(dump_message(nested, indent + '  '))

            # Fields

            for field in msg.field:
                label = {
                    1: 'optional',
                    2: 'required',
                    3: 'repeated'
                }.get(field.label, '')

                # Field type string
                if field.type_name:
                    # It's a message or enum type
                    # type_name is fully qualified, remove leading dot if present
                    type_str = field.type_name.lstrip('.')
                else:
                    # primitive type
                    type_map = {
                        1: "double",
                        2: "float",
                        3: "int64",
                        4: "uint64",
                        5: "int32",
                        6: "fixed64",
                        7: "fixed32",
                        8: "bool",
                        9: "string",
                        10: "group",  # deprecated
                        11: "message",
                        12: "bytes",
                        13: "uint32",
                        14: "enum",
                        15: "sfixed32",
                        16: "sfixed64",
                        17: "sint32",
                        18: "sint64",
                    }
                    type_str = type_map.get(field.type, f"TYPE_{field.type}")

                # Field options (only packed example)
                opts = []
                if field.options.HasField('packed'):
                    opts.append(f"packed = {str(field.options.packed).lower()}")

                opts_str = f" [{', '.join(opts)}]" if opts else ""

                msg_lines.append(f"{indent}  {label} {type_str} {field.name} = {field.number}{opts_str};")

            msg_lines.append(f"{indent}}}\n")

            return msg_lines

        # Services

        def dump_service(svc: descriptor_pb2.ServiceDescriptorProto, indent=''):
            svc_lines = [f"{indent}service {svc.name} {{"]
            for method in svc.method:
                input_type = method.input_type.lstrip('.') if method.input_type else 'Unknown'
                output_type = method.output_type.lstrip('.') if method.output_type else 'Unknown'
                client_streaming = 'stream ' if method.client_streaming else ''
                server_streaming = 'stream ' if method.server_streaming else ''
                svc_lines.append(f"{indent}  rpc {method.name} ({client_streaming}{input_type}) returns ({server_streaming}{output_type});")
            svc_lines.append(f"{indent}}}\n")
            return svc_lines

        # Dump enums at file level

        for enum in fd.enum_type:
            lines.extend(dump_enum(enum))

        # Dump messages

        for msg in fd.message_type:
            lines.extend(dump_message(msg))

        # Dump services

        for svc in fd.service:
            lines.extend(dump_service(svc))

        return "\n".join(lines)
