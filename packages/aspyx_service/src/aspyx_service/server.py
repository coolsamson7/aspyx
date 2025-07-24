"""
FastAPI server implementation for the aspyx service framework.
"""
from __future__ import annotations
import atexit
import functools
import inspect
import threading
import typing
from datetime import datetime
from typing import Type, Optional, Callable, Any
import contextvars
import msgpack
import uvicorn

from fastapi import FastAPI, APIRouter, Request as HttpRequest, Response as HttpResponse, HTTPException


from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from aspyx.di import Environment, on_init, inject_environment, on_destroy
from aspyx.reflection import TypeDescriptor, Decorators
from aspyx.util import get_deserializer, get_serializer

from .protobuf import ProtobufManager
from .service import ComponentRegistry, ServiceDescriptor
from .healthcheck import HealthCheckManager

from .service import Server, ServiceManager
from .channels import Request, Response, TokenContext

from .restchannel import get, post, put, delete, rest

class ResponseContext:
    response_var = contextvars.ContextVar[Optional['ResponseContext.Response']]("response", default=None)

    class Response:
        def __init__(self):
            self.cookies = {}
            self.delete_cookies = {}

        def delete_cookie(self,
                           key: str,
                           path: str = "/",
                           domain: str | None = None,
                           secure: bool = False,
                           httponly: bool = False,
                           samesite: typing.Literal["lax", "strict", "none"] | None = "lax",
                           ):
            self.delete_cookies[key] = {
                "path": path,
                "domain": domain,
                "secure": secure,
                "httponly": httponly,
                "samesite": samesite
            }

        def set_cookie(self,
                key: str,
                value: str = "",
                max_age: int | None = None,
                expires: datetime | str | int | None = None,
                path: str | None = "/",
                domain: str | None = None,
                secure: bool = False,
                httponly: bool = False,
                samesite: typing.Literal["lax", "strict", "none"] | None = "lax"):
            self.cookies[key] = {
                "value": value,
                "max_age": max_age,
                "expires": expires,
                "path": path,
                "domain": domain,
                "secure": secure,
                "httponly": httponly,
                "samesite": samesite
            }

    @classmethod
    def create(cls) -> ResponseContext.Response:
        response = ResponseContext.Response()

        cls.response_var.set(response)

        return response

    @classmethod
    def get(cls) -> Optional[ResponseContext.Response]:
        return cls.response_var.get()

    @classmethod
    def reset(cls) -> None:
        cls.response_var.set(None)


class RequestContext:
    """
    A request context is used to remember the current http request in the current thread
    """
    request_var = contextvars.ContextVar("request")

    @classmethod
    def get_request(cls) -> Request:
        """
        Return the current http request

        Returns:
            the current http request
        """
        return cls.request_var.get()

    # constructor

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = HttpRequest(scope)
        token = self.request_var.set(request)
        try:
            await self.app(scope, receive, send)
        finally:
            self.request_var.reset(token)

class TokenContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        access_token = request.cookies.get("access_token") or request.headers.get("Authorization")
        #refresh_token = request.cookies.get("refresh_token")

        if access_token:
            TokenContext.set(access_token)#, refresh_token)

        try:
            return await call_next(request)
        finally:
            TokenContext.clear()

class FastAPIServer(Server):
    """
    A server utilizing fastapi framework.
    """

    # class methods

    @classmethod
    def boot(cls, module: Type, host="0.0.0.0", port=8000, start_thread = True) -> Environment:
        """
        boot the DI infrastructure of the supplied module and optionally start a fastapi thread given the url
        Args:
            module: the module to initialize the environment
            host: listen address
            port: the port

        Returns:
            the created environment
        """

        cls.port = port

        environment = Environment(module)

        server = environment.get(FastAPIServer)

        if start_thread:
            server.start_server(host)

        return environment

    # constructor

    def __init__(self, fast_api: FastAPI, service_manager: ServiceManager, component_registry: ComponentRegistry, protobuf_manager: ProtobufManager):
        super().__init__()

        self.environment : Optional[Environment] = None
        self.protobuf_manager = protobuf_manager
        self.service_manager = service_manager
        self.component_registry = component_registry

        self.host = "localhost"
        self.fast_api = fast_api
        self.server_thread = None

        self.router = APIRouter()

        self.server : Optional[uvicorn.Server] = None
        self.thread : Optional[threading.Thread] = None

        # cache

        self.deserializers: dict[str, list[Callable]] = {}

        # that's the overall dispatcher

        self.router.post("/invoke")(self.invoke)

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # lifecycle

    @on_init()
    def on_init(self):
        self.service_manager.startup(self)

        # add routes

        self.add_routes()
        self.fast_api.include_router(self.router)

        # TODO: trace routes
        #for route in self.fast_api.routes:
        #    print(f"{route.name}: {route.path} [{route.methods}]")

        # add cleanup hook

        def cleanup():
            self.service_manager.shutdown()

        atexit.register(cleanup)

    @on_destroy()
    def on_destroy(self):
        if self.server is not None:
            self.server.should_exit = True
            self.thread.join()

    # private

    def add_routes(self):
        """
        add everything that looks like an http endpoint
        """

        def wrap_service_method(handler, return_type):
            sig = inspect.signature(handler)

            @functools.wraps(handler)
            async def wrapper(*args, **kwargs):
                try:
                    result = handler(*args, **kwargs)
                    if inspect.iscoroutine(result):
                        result = await result

                except HTTPException as e:
                    raise
                except Exception as e:
                    result = {"error": str(e)}

                json_response = JSONResponse(get_serializer(return_type)(result))

                local_response = ResponseContext.get()
                if local_response is not None:
                    # delete

                    for key, value in  local_response.delete_cookies.items():
                        json_response.delete_cookie(
                            key,
                            path=value["path"],
                            domain=value["domain"],
                            secure=value["secure"],
                            httponly=value["httponly"]
                            )

                    # create

                    for key, value in  local_response.cookies.items():
                        json_response.set_cookie(
                            key,
                            value=value["value"],
                            max_age=value["max_age"],
                            expires=value["expires"],
                            path=value["path"],
                            domain=value["domain"],
                            secure=value["secure"],
                            httponly=value["httponly"]
                            )

                    ResponseContext.reset()

                return json_response

            # Optionally attach response_model info for docs

            wrapper.__signature__ = sig
            wrapper.__annotations__ = {"return": return_type}

            return wrapper

        for descriptor in self.service_manager.descriptors.values():
            if not descriptor.is_component() and descriptor.is_local():
                prefix = ""

                type_descriptor = TypeDescriptor.for_type(descriptor.type)
                instance = self.environment.get(descriptor.implementation)

                if type_descriptor.has_decorator(rest):
                    prefix = type_descriptor.get_decorator(rest).args[0]

                for method in type_descriptor.get_methods():
                    decorator = next((decorator for decorator in Decorators.get(method.method) if decorator.decorator in [get, put, post, delete]), None)
                    if decorator is not None:
                        self.router.add_api_route(
                            path=prefix + decorator.args[0],
                            endpoint=wrap_service_method(getattr(instance, method.get_name()), method.return_type),
                            methods=[decorator.decorator.__name__],
                            name=f"{descriptor.get_component_descriptor().name}.{descriptor.name}.{method.get_name()}",
                            response_model=method.return_type,
                        )

    def start_server(self, host: str):
        """
        start the fastapi server in a thread
        """
        self.host = host

        config = uvicorn.Config(self.fast_api, host=host, port=self.port, access_log=False)

        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    def get_deserializers(self, service: Type, method):
        deserializers = self.deserializers.get(method, None)
        if deserializers is None:
            descriptor = TypeDescriptor.for_type(service).get_method(method.__name__)

            deserializers = [get_deserializer(type) for type in descriptor.param_types]
            self.deserializers[method] = deserializers

        return deserializers

    def deserialize_args(self, args: list[Any], type: Type, method: Callable) -> list:
        #args = list(request.args)

        deserializers = self.get_deserializers(type, method)

        for i, arg in enumerate(args):
            args[i] = deserializers[i](arg)

        return args

    def get_descriptor_and_method(self, method_name: str) -> typing.Tuple[ServiceDescriptor, Callable]:
        parts = method_name.split(":")

        # component = parts[0]
        service_name = parts[1]
        method_name = parts[2]

        service_descriptor : ServiceDescriptor = typing.cast(ServiceDescriptor, ServiceManager.descriptors_by_name[service_name])
        service = self.service_manager.get_service(service_descriptor.type, preferred_channel="local")

        return service_descriptor, getattr(service, method_name)

    async def invoke(self, http_request: HttpRequest):
        content_type = http_request.headers.get("content-type", "")
        response_name = ""

        service_descriptor : ServiceDescriptor
        method : Callable
        args : list[Any]

        content = "json"
        if "application/msgpack" in content_type:
            content = "msgpack"
            data = msgpack.unpackb(await http_request.body(), raw=False)
            service_descriptor, method = self.get_descriptor_and_method(data["method"])
            args = self.deserialize_args(data["args"], service_descriptor.type, method)

        elif "application/json" in content_type:
            data = await http_request.json()
            service_descriptor, method = self.get_descriptor_and_method(data["method"])
            args = self.deserialize_args(data["args"], service_descriptor.type, method)

        elif "application/x-protobuf" in content_type:
            content = "protobuf"
            service_descriptor, method = self.get_descriptor_and_method(http_request.headers.get("x-rpc-method") )
            self.protobuf_manager.check(service_descriptor.type)
            data = await http_request.body()

            request_name = ProtobufManager.get_message_name(service_descriptor.type, f"{method.__name__}Request")

            request = self.protobuf_manager.get_message_type(request_name)()
            request.ParseFromString(data)

            args = self.protobuf_manager.create_deserializer(request.DESCRIPTOR, method).deserialize(request)

        else:
            return HttpResponse(
                content="Unsupported Content-Type",
                status_code=415,
                media_type="text/plain"
            )

        request = data

        if content == "json":
            try:
                result = await self.dispatch(service_descriptor, method, args)

                return Response(result=result, exception=None).model_dump()
            except Exception as e:
                return Response(result=None, exception=str(e)).model_dump()

        elif content == "protobuf":
            response_name = ProtobufManager.get_message_name(service_descriptor.type, f"{method.__name__}Response")
            response_type = self.protobuf_manager.get_message_type(response_name)

            result_serializer = self.protobuf_manager.create_result_serializer(response_type, method)

            try:
                result = await self.dispatch(service_descriptor, method, args)

                result_message = result_serializer.serialize_result(result, None)

                return HttpResponse(
                    content=result_message.SerializeToString(),
                    media_type="application/x-protobuf"
                )

            except Exception as e:
                result_message = result_serializer.serialize_result(None, str(e))

                return HttpResponse(
                    content=result_message.SerializeToString(),
                    media_type="application/x-protobuf"
                )

        else:
            try:
                response = Response(result=await self.dispatch(service_descriptor, method, args), exception=None).model_dump()
            except Exception as e:
                response = Response(result=None, exception=str(e)).model_dump()

            return HttpResponse(
                content=msgpack.packb(response, use_bin_type=True),
                media_type="application/msgpack"
            )

    async def dispatch(self, service_descriptor: ServiceDescriptor, method: Callable, args: list[Any]) :
        ServiceManager.logger.debug("dispatch request %s.%s", service_descriptor, method.__name__)

        if inspect.iscoroutinefunction(method):
            return await method(*args)
        else:
            return method(*args)

    # override

    def route(self, url: str, callable: Callable):
        self.router.get(url)(callable)

    def route_health(self, url: str, callable: Callable):
        async def get_health_response():
            health : HealthCheckManager.Health = await callable()

            return JSONResponse(
                status_code= self.component_registry.map_health(health),
                content = health.to_dict()
            )

        self.router.get(url)(get_health_response)
