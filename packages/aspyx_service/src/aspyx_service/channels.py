"""
Service management and dependency injection framework.
"""
from __future__ import annotations

import typing
from contextlib import contextmanager
from dataclasses import is_dataclass, fields
from typing import Type, Optional, Any, Callable

import httpx
import msgpack
from httpx import Client, AsyncClient, USE_CLIENT_DEFAULT
from pydantic import BaseModel

from aspyx.di.configuration import inject_value
from aspyx.reflection import DynamicProxy, TypeDescriptor
from aspyx.threading import ThreadLocal, ContextLocal
from aspyx.util import get_deserializer, TypeDeserializer, TypeSerializer, get_serializer, CopyOnWriteCache
from .service import ServiceManager, ServiceCommunicationException, TokenExpiredException, InvalidTokenException, \
    AuthorizationException, MissingTokenException

from .service import ComponentDescriptor, ChannelInstances, ServiceException, channel, Channel, RemoteServiceException

class TokenContext:
    """
    TokeContext covers two context locals for both the access and - optional - refresh topen
    """
    access_token = ContextLocal[str]("access_token", default=None)
    refresh_token = ContextLocal[str]("refresh_token", default=None)

    @classmethod
    def get_access_token(cls) -> Optional[str]:
        return cls.access_token.get()

    @classmethod
    def get_refresh_token(cls) -> Optional[str]:
        return cls.refresh_token.get()


    @classmethod
    def set(cls, access_token: str, refresh_token: Optional[str] = None):
        cls.access_token.set(access_token)
        if refresh_token:
            cls.refresh_token.set(refresh_token)

    @classmethod
    def clear(cls):
        cls.access_token.set(None)
        cls.refresh_token.set(None)

    @classmethod
    @contextmanager
    def use(cls, access_token: str, refresh_token: Optional[str] = None):
        access_token = cls.access_token.set(access_token)
        refresh_token = cls.refresh_token.set(refresh_token)
        try:
            yield
        finally:
            cls.access_token.reset(access_token)
            cls.refresh_token.reset(refresh_token)

class HTTPXChannel(Channel):
    """
    A channel using the httpx clients.
    """
    __slots__ = [
        "client",
        "async_client",
        "service_names",
        "deserializers",
        "timeout",
        "optimize_serialization"
    ]

    # class properties

    client_local = ThreadLocal[Client]()
    async_client_local = ThreadLocal[AsyncClient]()

    # constructor

    def __init__(self):
        super().__init__()

        self.timeout = 1000.0
        self.service_names: dict[Type, str] = {}
        self.serializers = CopyOnWriteCache[Callable, list[Callable]]()
        self.deserializers = CopyOnWriteCache[Callable, Callable]()

    # inject

    @inject_value("http.timeout", default=1000.0)
    def set_timeout(self, timeout: float) -> None:
        self.timeout = timeout

    # protected

    def serialize_args(self, invocation: DynamicProxy.Invocation) -> list[Any]:
        deserializers = self.get_serializers(invocation.type, invocation.method)

        args = list(invocation.args)
        for index, deserializer in enumerate(deserializers):
            args[index] = deserializer(args[index])

        return args

    def get_serializers(self, type: Type, method: Callable) -> list[TypeSerializer]:
        serializers = self.serializers.get(method, None)
        if serializers is None:
            param_types = TypeDescriptor.for_type(type).get_method(method.__name__).param_types

            serializers = [get_serializer(type) for type in param_types]

            self.serializers.put(method, serializers)

        return serializers

    def get_deserializer(self, type: Type, method: Callable) -> TypeDeserializer:
        deserializer = self.deserializers.get(method, None)
        if deserializer is None:
            return_type = TypeDescriptor.for_type(type).get_method(method.__name__).return_type

            deserializer = get_deserializer(return_type)

            self.deserializers.put(method, deserializer)

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

        token = TokenContext.get_access_token()
        if token is not None:
            if headers is None:  # None is also valid!
                headers = {}

            ## add bearer token

            headers["Authorization"] = f"Bearer {token}"

        try:
            response = self.get_client().request(http_method, url, params=params, json=json, headers=headers, timeout=timeout, content=content)

            #print("\n=== Response ===")
            #print("Status Code:", response.status_code)
            #try:
            #    print("Body:", json.dumps(response.json(), indent=2))
            #except Exception:
            #    print("Body (raw):", response.text)

            response.raise_for_status()
        except httpx.RequestError as e:
            raise ServiceCommunicationException(str(e)) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                www_auth = e.response.headers.get("www-authenticate", "")
                if "invalid_token" in www_auth:
                    if 'expired' in www_auth:
                        raise TokenExpiredException() from e

                    if 'missing' in www_auth:
                        raise MissingTokenException() from e

                    raise InvalidTokenException() from e

            raise AuthorizationException(str(e)) from e
        except httpx.HTTPError as e:
            raise RemoteServiceException(str(e)) from e

        return response

    async def request_async(self, http_method: str, url: str, json: Optional[typing.Any] = None,
                params: Optional[Any] = None, headers: Optional[Any] = None,
                timeout: Any = USE_CLIENT_DEFAULT, content: Optional[Any] = None) -> httpx.Response:

        token = TokenContext.get_access_token()
        if token is not None:
            if headers is None:  # None is also valid!
                headers = {}

            ## add bearer token

            headers["Authorization"] = f"Bearer {token}"

        try:
            response = await self.get_async_client().request(http_method, url, params=params, json=json, headers=headers,
                                                 timeout=timeout, content=content)
            response.raise_for_status()
        except httpx.RequestError as e:
            raise ServiceCommunicationException(str(e)) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                www_auth = e.response.headers.get("www-authenticate", "")
                if "invalid_token" in www_auth:
                    if 'expired' in www_auth:
                        raise TokenExpiredException() from e
                    elif 'missing' in www_auth:
                        raise MissingTokenException() from e
                    else:
                        raise InvalidTokenException() from e

            raise RemoteServiceException(str(e)) from e
        except httpx.HTTPError as e:
            raise RemoteServiceException(str(e)) from e

        return response

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

        request = {
            "method": f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
            "args": self.serialize_args(invocation)
        }

        try:
            http_result = self.request( "post", f"{self.get_url()}/invoke", json=request, timeout=self.timeout)
            result = http_result.json()
            if result["exception"] is not None:
                raise RemoteServiceException(f"server side exception {result['exception']}")

            return self.get_deserializer(invocation.type, invocation.method)(result["result"])
        except (ServiceCommunicationException, AuthorizationException, RemoteServiceException) as e:
            raise

        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e


    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = {
            "method": f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
            "args": self.serialize_args(invocation)
        }

        try:
            data =  await self.request_async("post", f"{self.get_url()}/invoke", json=request, timeout=self.timeout)
            result = data.json()

            if result["exception"] is not None:
                raise RemoteServiceException(f"server side exception {result['exception']}")

            return self.get_deserializer(invocation.type, invocation.method)(result["result"])

        except (ServiceCommunicationException, AuthorizationException, RemoteServiceException) as e:
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
        request = {
            "method": f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
            "args": self.serialize_args(invocation)
        }

        try:
            packed = msgpack.packb(request, use_bin_type=True)

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


        except httpx.RequestError as e:
            raise ServiceCommunicationException(str(e)) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                www_auth = e.response.headers.get("www-authenticate", "")
                if "invalid_token" in www_auth:
                    if 'expired' in www_auth:
                        raise TokenExpiredException() from e

                    if 'missing' in www_auth:
                        raise MissingTokenException() from e

                    raise InvalidTokenException() from e

            raise RemoteServiceException(str(e)) from e
        except httpx.HTTPError as e:
            raise RemoteServiceException(str(e)) from e

        except ServiceCommunicationException:
            raise

        except RemoteServiceException:
            raise

        except Exception as e:
            raise ServiceException(f"msgpack exception: {e}") from e

    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        service_name = self.service_names[invocation.type]  # map type to registered service name
        request = {
            "method": f"{self.component_descriptor.name}:{service_name}:{invocation.method.__name__}",
            "args": self.serialize_args(invocation)
        }

        try:
            packed = msgpack.packb(request, use_bin_type=True)

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

        except httpx.RequestError as e:
            raise ServiceCommunicationException(str(e)) from e

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                www_auth = e.response.headers.get("www-authenticate", "")
                if "invalid_token" in www_auth:
                    if 'expired' in www_auth:
                        raise TokenExpiredException() from e

                    if 'missing' in www_auth:
                        raise MissingTokenException() from e

                    raise InvalidTokenException() from e

            raise RemoteServiceException(str(e)) from e

        except httpx.HTTPError as e:
            raise RemoteServiceException(str(e)) from e

        except ServiceCommunicationException:
            raise

        except RemoteServiceException:
            raise

        except Exception as e:
            raise ServiceException(f"msgpack exception: {e}") from e
