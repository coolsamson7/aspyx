"""
Service management and dependency injection framework.
"""
from __future__ import annotations

import json
import typing
from dataclasses import is_dataclass, fields
from typing import Type, Optional, Any, Callable

import httpx
import msgpack
from httpx import Client, AsyncClient, USE_CLIENT_DEFAULT
from httpx._types import QueryParamTypes, HeaderTypes, TimeoutTypes
from pydantic import BaseModel

from aspyx.di.configuration import inject_value
from aspyx.reflection import DynamicProxy, TypeDescriptor
from aspyx.threading import ThreadLocal
from .service import ServiceManager, ServiceCommunicationException

from .service import ComponentDescriptor, ChannelInstances, ServiceException, channel, Channel, RemoteServiceException
from .serialization import get_deserializer


class HTTPXChannel(Channel):
    __slots__ = [
        "client",
        "async_client",
        "service_names",
        "deserializers",
        "timeout"
    ]

    # class methods

    @classmethod
    def remember_token(cls, service: Any, token: str):
        if isinstance(service.invocation_handler, HTTPXChannel):
            channel: HTTPXChannel = service.invocation_handler

            channel.token = token

    @classmethod
    def clear_token(cls, service: Any, token: str):
        if isinstance(service.invocation_handler, HTTPXChannel):
            channel: HTTPXChannel = service.invocation_handler

            channel.token = token

    # class properties

    client_local = ThreadLocal[Client]()
    async_client_local = ThreadLocal[AsyncClient]()

    # class methods

    @classmethod
    def to_dict(cls, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.dict()


        elif is_dataclass(obj):
            return {
                f.name: cls.to_dict(getattr(obj, f.name))

                for f in fields(obj)
            }

        elif isinstance(obj, (list, tuple)):
            return [cls.to_dict(item) for item in obj]

        elif isinstance(obj, dict):
            return {key: cls.to_dict(value) for key, value in obj.items()}

        return obj

    @classmethod
    def to_json(cls, obj) -> str:
        return json.dumps(cls.to_dict(obj))

    # constructor

    def __init__(self):
        super().__init__()

        self.token = None
        self.timeout = 100000.0 #TODO
        self.service_names: dict[Type, str] = {}
        self.deserializers: dict[Callable, Callable] = {}

    # inject

    @inject_value("http.timeout", default=1000.0)
    def set_timeout(self, timeout: float) -> None:
        self.timeout = timeout

    # protected

    def get_deserializer(self, type: Type, method: Callable) -> Type:
        deserializer = self.deserializers.get(method, None)
        if deserializer is None:
            return_type = TypeDescriptor.for_type(type).get_method(method.__name__).return_type

            deserializer = get_deserializer(return_type)

            self.deserializers[method] = deserializer

        return deserializer

    # override

    def setup(self, component_descriptor: ComponentDescriptor, address: ChannelInstances):
        super().setup(component_descriptor, address)

        # remember service names

        for service in component_descriptor.services:
            self.service_names[service.type] = service.name

    # public

    def get_client(self) -> Client:
        client = self.client_local.get()

        if client is None:
            client = self.make_client()
            self.client_local.set(client)

        return client

    def get_async_client(self) -> AsyncClient:
        async_client = self.async_client_local.get()

        if async_client is None:
            async_client = self.make_async_client()
            self.async_client_local.set(async_client)

        return async_client

    def make_client(self) -> Client:
        return Client()  # base_url=url

    def make_async_client(self) -> AsyncClient:
        return AsyncClient()  # base_url=url

    def request(self, http_method: str, url: str, json: Optional[typing.Any] = None,
                params: Optional[Any] = None, headers: Optional[Any] = None,
                timeout: Any = USE_CLIENT_DEFAULT, content: Optional[Any] = None) -> httpx.Response:

        if self.token is not None:
            if headers is None:  # None is also valid!
                headers = {}

            ## add bearer token

            headers["Authorization"] = f"Bearer {self.token}"

        return self.get_client().request(http_method, url, params=params, json=json, headers=headers, timeout=timeout, content=content)

    async def request_async (self, http_method: str, url: str, json: Optional[typing.Any] = None,
                params: Optional[Any] = None, headers: Optional[Any] = None,
                timeout: Any = USE_CLIENT_DEFAULT, content: Optional[Any] = None) -> httpx.Response:

        if self.token is not None:
            if headers is None:  # None is also valid!
                headers = {}

            ## add bearer token

            headers["Authorization"] = f"Bearer {self.token}"

        return await self.get_async_client().request(http_method, url, params=params, json=json, headers=headers, timeout=timeout, content=content)

class Request(BaseModel):
    method: str  # component:service:method
    args: tuple[Any, ...]

class Response(BaseModel):
    result: Optional[Any]
    exception: Optional[Any]

@channel("dispatch-json")
class DispatchJSONChannel(HTTPXChannel):
    """
    A channel that calls a POST on the endpoint `ìnvoke` sending a request body containing information on the
    called component, service and method and the arguments.
    """
    # constructor

    def __init__(self):
        super().__init__()

    # internal

    # implement Channel

    def set_address(self, address: Optional[ChannelInstances]):
        ServiceManager.logger.info("channel %s got an address %s", self.name, address)

        super().set_address(address)

    def setup(self, component_descriptor: ComponentDescriptor, address: ChannelInstances):
        super().setup(component_descriptor, address)

    def invoke(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)

        dict = self.to_dict(request)
        try:
            http_result = self.request( "post", f"{self.get_url()}/invoke", json=dict, timeout=self.timeout)
            result = Response(**http_result.json())
            if result.exception is not None:
                raise RemoteServiceException(f"server side exception {result.exception}")

            return self.get_deserializer(invocation.type, invocation.method)(result.result)
        except ServiceCommunicationException:
            raise

        except RemoteServiceException:
            raise

        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e


    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)
        dict = self.to_dict(request)
        try:
            data =  await self.request_async("post", f"{self.get_url()}/invoke", json=dict, timeout=self.timeout)
            result = Response(**data.json())

            if result.exception is not None:
                raise RemoteServiceException(f"server side exception {result.exception}")

            return self.get_deserializer(invocation.type, invocation.method)(result.result)

        except ServiceCommunicationException:
            raise

        except RemoteServiceException:
            raise

        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e


@channel("dispatch-msgpack")
class DispatchMSPackChannel(HTTPXChannel):
    """
    A channel that sends a POST on the ìnvoke `endpoint`with an msgpack encoded request body.
    """
    # constructor

    def __init__(self):
        super().__init__()

    # override

    def set_address(self, address: Optional[ChannelInstances]):
        ServiceManager.logger.info("channel %s got an address %s", self.name, address)

        super().set_address(address)

    def invoke(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)

        try:
            packed = msgpack.packb(self.to_dict(request), use_bin_type=True)

            response = self.request("post",
                f"{self.get_url()}/invoke",
                content=packed,
                headers={"Content-Type": "application/msgpack"},
                timeout=self.timeout
            )

            result = msgpack.unpackb(response.content, raw=False)

            if result.get("exception", None):
                raise RemoteServiceException(f"server-side: {result['exception']}")

            return self.get_deserializer(invocation.type, invocation.method)(result["result"])

        except ServiceCommunicationException:
            raise

        except RemoteServiceException:
            raise

        except Exception as e:
            raise ServiceException(f"msgpack exception: {e}") from e

    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = Request(method=f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
                          args=invocation.args)

        try:
            packed = msgpack.packb(self.to_dict(request), use_bin_type=True)

            response = await self.request_async("post",
                f"{self.get_url()}/invoke",
                content=packed,
                headers={"Content-Type": "application/msgpack"},
                timeout=self.timeout
            )

            result = msgpack.unpackb(response.content, raw=False)

            if result.get("exception", None):
                raise RemoteServiceException(f"server-side: {result['exception']}")

            return self.get_deserializer(invocation.type, invocation.method)(result["result"])

        except ServiceCommunicationException:
            raise

        except RemoteServiceException:
            raise

        except Exception as e:
            raise ServiceException(f"msgpack exception: {e}") from e
