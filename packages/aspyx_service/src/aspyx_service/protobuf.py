from __future__ import annotations

import inspect
from dataclasses import is_dataclass, fields as dc_fields
from typing import Type, get_type_hints, Callable, Tuple, get_origin, get_args, List, Dict, Any, Union, Sequence

import httpx
from pydantic import BaseModel

from .service import channel

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, text_format
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message
from google.protobuf.descriptor import FieldDescriptor, Descriptor

from aspyx.di import injectable
from aspyx.reflection import DynamicProxy, TypeDescriptor

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
    # class methods

    @classmethod
    def get_message_name(cls, type: Type, suffix="") -> str:
        module = type.__module__.replace(".", "_")
        name = type.__name__

        return f"{module}.{name}{suffix}"

    @classmethod
    def get_request_message_name(cls, type: Type, method: Callable) -> str:
        return cls.get_message_name(type, f"{method.__name__}Request")

    @classmethod
    def get_response_message_name(cls, type: Type, method: Callable) -> str:
        return cls.get_message_name(type, f"{method.__name__}Response")

    # inner classes

    class MessageBuilder:
        """Builds Protobuf fields for a Python type, including repeated and message types."""

        def to_proto_type(self, py_type: Type) -> Tuple[int, int, str | None]:
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
                field_type, _, type_name = self._resolve_type(item_type)
                return (
                    field_type,
                    descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,  # type: ignore
                    type_name,
                )

            return self._resolve_type(py_type)

        def _resolve_type(self, py_type: Type) -> Tuple[int, int, str | None]:
            """Resolves Python type to protobuf scalar or message type with label=optional."""
            # Structured message (dataclass or Pydantic BaseModel)
            if is_dataclass(py_type) or (inspect.isclass(py_type) and issubclass(py_type, BaseModel)):
                type_name = self.method_builder.service_builder.build_message_type(py_type)
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

    class RequestMessageBuilder(MessageBuilder):
        """Builds protobuf request message descriptor from method signature."""

        def __init__(self, method_builder: ProtobufBuilder.MethodBuilder):
            self.method_builder = method_builder

        def build(self, message_name: str, method: TypeDescriptor.MethodDescriptor):
            request_msg = descriptor_pb2.DescriptorProto()  # type: ignore
            request_msg.name = message_name.split(".")[-1]

            # loop over parameters

            field_index = 1
            for param in method.params:
                field = request_msg.field.add()

                field.name = param.name
                field.number = field_index

                field_type, label, type_name = self.to_proto_type(param.type)
                field.type = field_type
                field.label = label
                if type_name:
                    field.type_name = type_name

                field_index += 1

            # add to service file descriptor

            self.method_builder.service_builder.file_desc_proto.message_type.add().CopyFrom(request_msg)

    class ResponseMessageBuilder(MessageBuilder):
        """Builds protobuf response message descriptor from method return type."""

        def __init__(self, method_builder: ProtobufBuilder.MethodBuilder):
            self.method_builder = method_builder

        def build(self, message_name: str, method: TypeDescriptor.MethodDescriptor):
            response_msg = descriptor_pb2.DescriptorProto()  # type: ignore
            response_msg.name = message_name.split(".")[-1]

            return_type = method.return_type
            response_field = response_msg.field.add()
            response_field.name = "result"
            response_field.number = 1

            field_type, label, type_name = self.to_proto_type(return_type)
            response_field.type = field_type
            response_field.label = label
            if type_name:
                response_field.type_name = type_name

            # Add to service file descriptor
            self.method_builder.service_builder.file_desc_proto.message_type.add().CopyFrom(response_msg)

    class MethodBuilder:
        """Builds protobuf MethodDescriptorProto for a service method."""

        def __init__(self, service_builder: ProtobufBuilder.ServiceBuilder):
            self.service_builder = service_builder
            self.method_desc = descriptor_pb2.MethodDescriptorProto()  # type: ignore

        def method(self, service_type: Type, method: TypeDescriptor.MethodDescriptor):
            name = f"{service_type.__name__}{method.get_name()}"
            package = self.service_builder.file_desc_proto.package

            request_name = f".{package}.{name}Request"
            response_name = f".{package}.{name}Response"

            self.method_desc.name = method.get_name()
            self.method_desc.input_type = request_name
            self.method_desc.output_type = response_name

            # Build request and response message types

            ProtobufBuilder.RequestMessageBuilder(self).build(request_name, method)
            ProtobufBuilder.ResponseMessageBuilder(self).build(response_name, method)

            # Add method to service descriptor

            self.service_builder.service_desc.method.add().CopyFrom(self.method_desc)

    class ServiceBuilder:
        def __init__(self, pool: DescriptorPool, service_type: Type):
            self.pool = pool

            # create a new FileDescriptorProto

            self.file_desc_proto = descriptor_pb2.FileDescriptorProto()  # type: ignore
            self.file_desc_proto.name = f"{service_type.__name__.lower()}.proto"
            self.file_desc_proto.package = service_type.__module__.replace(".", "_")

            # create ServiceDescriptorProto

            self.service_desc = descriptor_pb2.ServiceDescriptorProto()  # type: ignore
            self.service_desc.name = service_type.__name__

            # check methods

            for method in TypeDescriptor.for_type(service_type).get_methods():
                ProtobufBuilder.MethodBuilder(self).method(service_type, method)

            # done

            self.file_desc_proto.service.add().CopyFrom(self.service_desc)
            self.pool.Add(self.file_desc_proto)

            #print(text_format.MessageToString(self.file_desc_proto))  # TODO

            print(ProtobufDumper.dump_proto(self.file_desc_proto))

        def get_fields_and_types(self, type: Type) -> List[Tuple[str, Type]]:
            hints = get_type_hints(type)

            if is_dataclass(type):
                return [(f.name, hints.get(f.name, str)) for f in dc_fields(type)]

            if issubclass(type, BaseModel):
                return [(name, hints.get(name, str)) for name in type.__fields__]

            raise TypeError("Expected a dataclass or Pydantic model class.")

        def build_message_type(self, cls: Type) -> str:
            module = cls.__module__.replace(".", "_")
            name = cls.__name__
            full_name = f"{module}.{name}"

            # Check if a message type is already defined

            if any(m.name == name for m in self.file_desc_proto.message_type):
                return f".{full_name}"

            desc = descriptor_pb2.DescriptorProto()  # type: ignore
            desc.name = name

            # Extract fields from dataclass or pydantic model

            if is_dataclass(cls) or issubclass(cls, BaseModel):
                index = 1
                for field_name, field_type in self.get_fields_and_types(cls):
                    # Use MessageBuilder to get proto field info TODO!
                    mb = ProtobufBuilder.MessageBuilder()

                    mb.method_builder = type("dummy", (),
                                             {"service_builder": self})()  # Hack to allow calling to_proto_type
                    field_type_enum, label, type_name = mb.to_proto_type(field_type)

                    f = desc.field.add()
                    f.name = field_name
                    f.number = index
                    f.label = label
                    f.type = field_type_enum
                    if type_name:
                        f.type_name = type_name
                    index += 1

            else:
                raise TypeError(f"Unsupported structured type for proto message: {cls}")

            # add message type descriptor to the file descriptor proto

            self.file_desc_proto.message_type.add().CopyFrom(desc)

            return f".{full_name}"

    # slots

    __slots__ = [
        "pool",
        "factory",
        "service_cache"
    ]

    # constructor

    def __init__(self):
        self.pool: DescriptorPool = descriptor_pool.Default()
        self.factory = message_factory.MessageFactory(self.pool)
        self.service_cache: Dict[Type, ProtobufManager.ServiceBuilder] = {}

    # public

    def check_service(self, service_type: Type):
        if self.service_cache.get(service_type, None) is None:
            self.service_cache[service_type] = ProtobufManager.ServiceBuilder(self.pool, service_type)

    def get_message_type(self, full_name: str):
        return self.factory.GetPrototype(self.pool.FindMessageTypeByName(full_name))

    def get_request_message(self,  type: Type, method: Callable):
        return self.get_message_type(self.get_request_message_name(type, method))

    def get_response_message(self, type: Type, method: Callable):
        return self.get_message_type(self.get_response_message_name(type, method))


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

        def args(self, method: Callable)-> 'ProtobufManager.MethodDeserializer':
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

            field_desc = self.descriptor.DESCRIPTOR.fields_by_name["result"]

            self.getters.append(self._create_getter(field_desc, "result", return_type))

            return self

        def get_fields_and_types(self, type: Type) -> List[Tuple[str, Type]]:
            hints = get_type_hints(type)

            if is_dataclass(type):
                return [(f.name, hints.get(f.name, str)) for f in dc_fields(type)]

            if issubclass(type, BaseModel):
                return [(name, hints.get(name, str)) for name in type.__fields__]

            raise TypeError("Expected a dataclass or Pydantic model class.")

        def _create_getter(self, field_desc: FieldDescriptor, field_name: str, type: Type):
            is_repeated = field_desc.label == field_desc.LABEL_REPEATED
            is_message = field_desc.message_type is not None

            # list

            if is_repeated:
                item_type = get_args(type)[0] if get_origin(type) in (list, List) else str

                # list of messages

                if is_dataclass(item_type) or issubclass(item_type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(item_type))

                    getters = []
                    fields = []
                    for sub_field_name, field_type in self.get_fields_and_types(item_type):
                        fields.append(sub_field_name)
                        getters.append(self._create_getter(message_type.fields_by_name[sub_field_name], sub_field_name, field_type))

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

                    sub_getters = []
                    fields = []

                    for sub_field_name, field_type in self.get_fields_and_types(type):
                        fields.append(sub_field_name)

                        field = message_type.fields_by_name[sub_field_name]

                        sub_getters.append(self._create_getter(field, sub_field_name, field_type))

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
                    setter(val, field_name, getattr(msg, field_name))

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

            return result #TODO exception

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

            field_desc = msg_descriptor.fields_by_name["result"]

            self.setters.append(self._create_setter(field_desc, "result", return_type))

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
                return [(name, hints.get(name, str)) for name in type.__fields__]

            raise TypeError("Expected a dataclass or Pydantic model class.")

        def _create_setter(self, field_desc: FieldDescriptor, field_name: str, type: Type):
            is_repeated = field_desc.label == field_desc.LABEL_REPEATED
            is_message = field_desc.message_type is not None

            # list

            if is_repeated:
                item_type = get_args(type)[0] if get_origin(type) in (list, List) else str

                # list of messages

                if is_dataclass(item_type) or issubclass(item_type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(item_type))

                    setters = []
                    fields = []
                    for sub_field_name, field_type in self.get_fields_and_types(item_type):
                        fields.append(sub_field_name)
                        setters.append(self._create_setter(message_type.fields_by_name[sub_field_name], sub_field_name, field_type))

                    def serialize_message_list(msg: Message, val: Any, fields=fields, setters=setters):
                        for item in val:
                            msg_item = getattr(msg, field_name).add()
                            for i in range(len(setters)):
                                setters[i](msg_item, getattr(item, fields[i]))

                    return serialize_message_list

                # list of scalars

                else:
                    return lambda msg, val: getattr(msg, field_name).extend(val) # TODO ???

            # message

            elif is_message:
                if is_dataclass(type) or issubclass(type, BaseModel):
                    message_type = self.manager.pool.FindMessageTypeByName(ProtobufManager.get_message_name(type))

                    sub_setters = []
                    fields = []

                    for sub_field_name, field_type in self.get_fields_and_types(type):
                        fields.append(sub_field_name)

                        field = message_type.fields_by_name[sub_field_name]

                        sub_setters.append(self._create_setter(field, sub_field_name, field_type))

                    def serialize_message(msg: Message, val: Any, fields=fields, setters=sub_setters):
                        field = getattr(msg, field_name)
                        for i in range(len(sub_setters)):
                            setters[i](field, getattr(val, fields[i]))

                    return serialize_message
                else:
                    raise TypeError(f"Expected dataclass or BaseModel for field '{field_name}', got {type}")

            # scalar

            else:
                return lambda msg, val: setattr(msg, field_name, val)

        def serialize(self, value: Any) -> Any:
            # create message instance

            message = self.message_type()

            # call setters

            for i in range(len(self.setters)):
                self.setters[i](message, value)

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
        "result_deserializer_cache"
    ]

    # constructor

    def __init__(self):
        super().__init__()

        self.serializer_cache: Dict[Callable, ProtobufManager.MethodSerializer] = {}
        self.deserializer_cache: Dict[Descriptor, ProtobufManager.MethodDeserializer] = {}

        self.result_serializer_cache: Dict[Descriptor, ProtobufManager.MethodSerializer] = {}
        self.result_deserializer_cache: Dict[Descriptor, ProtobufManager.MethodDeserializer] = {}

    # public

    def create_serializer(self, type: Type, method: Callable) -> ProtobufManager.MethodSerializer:
        # is it cached?

        serializer = self.serializer_cache.get(method, None)
        if serializer is None:
            self.check_service(type) # make sure all messages are created

            serializer = ProtobufManager.MethodSerializer(self, self.get_request_message(type, method)).args(method)

            self.serializer_cache[method] = serializer

        return serializer

    def create_deserializer(self, descriptor: Descriptor, method: Callable) -> ProtobufManager.MethodDeserializer:
        # is it cached?

        deserializer = self.deserializer_cache.get(descriptor, None)
        if deserializer is None:
            deserializer = ProtobufManager.MethodDeserializer(self, descriptor).args(method)

            self.deserializer_cache[descriptor] = deserializer

        return deserializer

    def create_result_serializer(self, descriptor: Descriptor, method: Callable) -> ProtobufManager.MethodSerializer:
        # is it cached?

        serializer = self.result_serializer_cache.get(descriptor, None)
        if serializer is None:
            serializer = ProtobufManager.MethodSerializer(self, descriptor).result(method)

            self.result_serializer_cache[descriptor] = serializer

        return serializer

    def create_result_deserializer(self, descriptor: Descriptor, method: Callable) -> ProtobufManager.MethodDeserializer:
        # is it cached?

        deserializer = self.result_deserializer_cache.get(descriptor, None)
        if deserializer is None:
            deserializer = ProtobufManager.MethodDeserializer(self, descriptor).result(method)

            self.result_deserializer_cache[descriptor] = deserializer

        return deserializer

@channel("dispatch-protobuf")
class ProtobufChannel(HTTPXChannel):
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
        self.cache: dict[Callable, ProtobufChannel.Call] = {}

    # internal

    def get_call(self, type: Type, method: Callable) -> ProtobufChannel.Call:
        call = self.cache.get(method, None)
        if call is None:
            method_name   = f"{self.component_descriptor.name}:{self.service_names[type]}:{method.__name__}"
            serializer    = self.protobuf_manager.create_serializer(type, method)
            response_type = self.protobuf_manager.get_message_type(self.protobuf_manager.get_response_message_name(type, method))
            deserializer  = self.protobuf_manager.create_result_deserializer(response_type, method)

            call = ProtobufChannel.Call(method_name, serializer, response_type, deserializer)

            self.cache[method] = call

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

            # if result["exception"] is not None: TODO: Will we do that as well?
            #    raise RemoteServiceException(f"server side exception {result['exception']}")

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

            #if result["exception"] is not None: TODO: Will we do that as well?
            #    raise RemoteServiceException(f"server side exception {result['exception']}")

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
