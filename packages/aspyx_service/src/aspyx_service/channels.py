"""
Service management and dependency injection framework.
"""
from __future__ import annotations

from typing import Type, Optional, Any, Callable

import msgpack
from httpx import Client, AsyncClient
from pydantic import BaseModel

from aspyx.reflection import DynamicProxy, TypeDescriptor

from .service import ComponentDescriptor, ServiceAddress, ServiceException, channel, Channel, RemoteServiceException
from .serialization import get_deserializer


class HTTPXChannel(Channel):
    __slots__ = [
        "client",
        "async_client",
        "service_names",
        "deserializers"
    ]

    # constructor

    def __init__(self, name):
        super().__init__(name)

        self.client: Optional[Client] = None
        self.async_client: Optional[AsyncClient] = None
        self.service_names: dict[Type, str] = {}
        self.deserializers: dict[Callable, Callable] = {}

    # protected

    def get_deserializer(self, type: Type, method: Callable) -> Type:
        deserializer = self.deserializers.get(method, None)
        if deserializer is None:
            return_type = TypeDescriptor.for_type(type).get_method(method.__name__).return_type

            deserializer = get_deserializer(return_type)

            self.deserializers[method] = deserializer

        return deserializer

    # override

    def setup(self, component_descriptor: ComponentDescriptor, address: ServiceAddress):
        super().setup(component_descriptor, address)

        # remember service names

        for service in component_descriptor.services:
            self.service_names[service.type] = service.name

        # make client

        self.client = self.make_client()
        self.async_client = self.make_async_client()

    # public

    def make_client(self):
        return Client()  # base_url=url

    def make_async_client(self):
        return AsyncClient()  # base_url=url

class Request(BaseModel):
    method: str  # component:service:method
    args: tuple[Any, ...]

class Response(BaseModel):
    result: Optional[Any]
    exception: Optional[Any]

@channel("dispatch-json")
class DispatchJSONChannel(HTTPXChannel):
    # constructor

    def __init__(self):
        super().__init__("dispatch-json")

    # internal

    # implement Channel

    # address has changed, lets check what to do
    def set_address(self, address: Optional[ServiceAddress]):
        should_reset = (
                address is None or
                not address.urls or
                (self.address and self.address.urls[0] not in address.urls) # TODO
        )

        self.client = self.make_client() if not should_reset else None
        self.async_client = self.make_async_client() if not should_reset else None

        super().set_address(address)

    def setup(self, component_descriptor: ComponentDescriptor, address: ServiceAddress):
        super().setup(component_descriptor, address)

    def invoke(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}", args=invocation.args)

        try:
            if self.client is not None:
                result = Response(**self.client.post(f"{self.get_url()}/invoke", json=request.dict(), timeout=30000.0).json())
                if result.exception is not None:
                    raise RemoteServiceException(f"server side exception {result.exception}")

                return self.get_deserializer(invocation.type, invocation.method)(result.result)
            else:
                raise ServiceException(f"no url for channel {self.name} for component {self.component_descriptor.name} registered")
        except Exception as e:
            raise ServiceException(f"communication exception {e}") from e

    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)

        try:
            if self.async_client is not None:
                data =  await self.async_client.post(f"{self.get_url()}/invoke", json=request.dict(), timeout=30000.0)
                result = Response(**data.json())
                if result.exception is not None:
                    raise RemoteServiceException(f"server side exception {result.exception}")

                return self.get_deserializer(invocation.type, invocation.method)(result.result)
            else:
                raise ServiceException(
                    f"no url for channel {self.name} for component {self.component_descriptor.name} registered")
        except Exception as e:
            raise ServiceException(f"communication exception {e}") from e

@channel("dispatch-msgpack")
class DispatchMSPackChannel(HTTPXChannel):
    # constructor

    def __init__(self):
        super().__init__("dispatch-msgpack")

    # override

    def set_address(self, address: Optional[ServiceAddress]):
        self.client = self.make_client() if address else None
        self.async_client = self.make_async_client() if address else None

        super().set_address(address)

    def invoke(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)

        try:
            packed = msgpack.packb(request.dict(), use_bin_type=True)

            if self.client is not None:
                response = self.client.post(
                    f"{self.get_url()}/invoke",
                    content=packed,
                    headers={"Content-Type": "application/msgpack"},
                    timeout=30.0
                )

                result = msgpack.unpackb(response.content, raw=False)

                if result.get("exception", None):
                    raise RemoteServiceException(f"server-side: {result['exception']}")

                return self.get_deserializer(invocation.type, invocation.method)(result["result"])

            else:
                raise ServiceException("No client available for msgpack.")

        except Exception as e:
            raise ServiceException(f"msgpack exception: {e}") from e

    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)

        try:
            packed = msgpack.packb(request.dict(), use_bin_type=True)

            if self.async_client is not None:
                response = await self.async_client.post(
                    f"{self.get_url()}/invoke",
                    content=packed,
                    headers={"Content-Type": "application/msgpack"},
                    timeout=30.0
                )

                result = msgpack.unpackb(response.content, raw=False)

                if result.get("exception", None):
                    raise RemoteServiceException(f"server-side: {result['exception']}")

                return self.get_deserializer(invocation.type, invocation.method)(result["result"])

            else:
                raise ServiceException("No client available for msgpack.")

        except Exception as e:
            raise ServiceException(f"msgpack exception: {e}") from e

