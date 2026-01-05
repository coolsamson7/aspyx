"""
FastAPI server implementation for the aspyx service framework.
"""
from __future__ import annotations
import atexit
import functools
import inspect
import threading
import typing
from typing import get_origin, get_args, get_type_hints, Annotated
from dataclasses import is_dataclass
from datetime import datetime
from typing import Type, Optional, Callable, Any, Dict
import contextvars
import msgpack
import uvicorn
import re
from fastapi import Body as FastAPI_Body
from fastapi import FastAPI, APIRouter, Request as HttpRequest, Response as HttpResponse, HTTPException
from fastapi.datastructures import DefaultPlaceholder, Default
from fastapi.encoders import jsonable_encoder

from fastapi.responses import JSONResponse
from fastapi import Body as FastAPI_Body, Path as FastAPI_Path, Query as FastAPI_Query
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware

from aspyx.di import Environment, on_init, inject_environment, on_destroy
from aspyx.reflection import TypeDescriptor, Decorators
from aspyx.util import get_deserializer, get_serializer, CopyOnWriteCache

from .protobuf import ProtobufManager
from .service import ComponentRegistry, ServiceDescriptor
from .healthcheck import HealthCheckManager

from .service import Server, ServiceManager
from .channels import Request, Response, TokenContext

from .restchannel import get, post, put, delete, rest, BodyMarker, ParamMarker, QueryParam, PathParam, QueryParamMarker, \
    PathParamMarker

# -------------------------
# Google-style docstring parser
# -------------------------
_doc_re = re.compile(r'^(\w+)(\([^)]*\))?:\s*(.*)$')

def parse_google_docstring(doc: Optional[str]) -> Dict[str, object]:
    """
    Parses a Google-style docstring into summary, description, arg descriptions, and return info.
    """
    if not doc:
        return {
            "summary": None,
            "description": None,
            "args": {},
            "returns": None,
        }

    lines = doc.strip().split("\n")

    # --- Extract summary (first non-empty line)
    summary = None
    for line in lines:
        if line.strip():
            summary = line.strip()
            break

    # --- Normalize indentation
    cleaned = [line.rstrip() for line in lines]

    # --- Sections detection
    args_section = []
    returns_section = []
    current = "body"

    for line in cleaned:
        stripped = line.strip()

        # Detect section headers
        if stripped.startswith("Args:"):
            current = "args"
            continue
        elif stripped.startswith("Returns:"):
            current = "returns"
            continue

        # Collect lines
        if current == "args":
            args_section.append(line)
        elif current == "returns":
            returns_section.append(line)

    # --- Parse Args ---
    args: Dict[str, str] = {}
    current_arg = None
    for line in args_section:
        s = line.strip()
        if not s:
            continue
        m = _doc_re.match(s)
        if m:
            current_arg = m.group(1)
            args[current_arg] = m.group(3).strip()
        elif current_arg:
            args[current_arg] += " " + s

    # --- Parse Returns ---
    return_desc = None
    if returns_section:
        # find first non-empty line
        for line in returns_section:
            s = line.strip()
            if not s:
                continue
            m = re.match(r'^([^:]+):\s*(.*)$', s)
            if m:
                return_desc = m.group(2).strip()
            else:
                return_desc = s
            break
        # continuation
        rest = [l.strip() for l in returns_section if l.strip()]
        if len(rest) > 1:
            return_desc = (return_desc or "") + " " + " ".join(rest[1:])

    # --- Full description (body)
    description = doc.strip()

    return {
        "summary": summary,
        "description": description,
        "args": args,
        "returns": return_desc,
    }

# -------------------------
# Helpers
# -------------------------
def join_paths(prefix: str, path: str) -> str:
    if not prefix:
        return path if path.startswith("/") else "/" + path
    return prefix.rstrip("/") + "/" + path.lstrip("/")


# -------------------------
# Response & Request context
# -------------------------
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
        """
        return cls.request_var.get()

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
        if access_token:
            TokenContext.set(access_token)
        try:
            return await call_next(request)
        finally:
            TokenContext.clear()


# -------------------------
# FastAPIServer
# -------------------------
class FastAPIServer(Server):
    """
    A server utilizing fastapi framework.
    """

    @classmethod
    def boot(cls, module: Type, host="0.0.0.0", port=8000, start_thread=True) -> Environment:
        cls.port = port
        environment = Environment(module)
        server = environment.get(FastAPIServer)
        if start_thread:
            server.start_server(host)
        return environment

    def __init__(self, fast_api: FastAPI, service_manager: ServiceManager, component_registry: ComponentRegistry):
        super().__init__()
        self.environment: Optional[Environment] = None
        self.protobuf_manager: Optional[ProtobufManager] = None
        self.service_manager = service_manager
        self.component_registry = component_registry

        self.host = "localhost"
        self.fast_api = fast_api
        self.server_thread = None

        self.router = APIRouter()
        self.server: Optional[uvicorn.Server] = None
        self.thread: Optional[threading.Thread] = None

        self.deserializers = CopyOnWriteCache[str, list[Callable]]()

        # dispatch endpoint
        self.router.post("/invoke", summary="generic method dispatcher", description="this endpoint is used to invoke any service method based on service, method and parameter info")(self.invoke)

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    @on_init()
    def on_init(self):
        self.service_manager.startup(self)
        self.add_routes()
        self.fast_api.include_router(self.router)

        # debug: print routes
        print("=== Registered FastAPI routes ===")
        for r in self.fast_api.routes:
            if isinstance(r, APIRoute):
                print(r.name, r.path, sorted(r.methods))

        def cleanup():
            self.service_manager.shutdown()
        atexit.register(cleanup)

    @on_destroy()
    def on_destroy(self):
        if self.server is not None:
            self.server.should_exit = True
            self.thread.join()

    # -------------------------
    # add_routes + wrapper
    # -------------------------
    def add_routes(self):
        """
        Add everything that looks like an HTTP endpoint
        """
        from pydantic import BaseModel

        def wrap_service_method(handler, method_descriptor, return_type, url_template=""):
            """
            Wrap a service method for FastAPI.

            - Detects BodyMarker, QueryParam, PathParam
            - Infers body parameter if none is explicitly annotated
            - Preserves metadata for OpenAPI (description, example)
            - Preserves docstring
            - Uses docstring (Google-style) for param descriptions only when annotation provides no description
            """

            sig = inspect.signature(handler)
            interface_fn = getattr(method_descriptor, "method", method_descriptor)
            type_hints_with_extras = get_type_hints(interface_fn, include_extras=True)

            # parse docstring for summary/description/param descriptions
            parsed_doc = parse_google_docstring(handler.__doc__ or interface_fn.__doc__ or "")

            param_metadata: dict[str, object] = {}
            body_param_name: Optional[str] = None
            path_param_names: set[str] = set(re.findall(r"{(.*?)}", url_template))
            # ensure only actual params are considered path params
            path_param_names &= set(sig.parameters.keys())
            query_param_names: set[str] = set(sig.parameters.keys()) - {"self"} - path_param_names

            # 1) Detect annotated parameters on interface function
            for name, hint in type_hints_with_extras.items():
                if name == "return":
                    continue
                origin = get_origin(hint)
                if origin is Annotated:
                    args = get_args(hint)
                    typ = args[0]
                    for meta in args[1:]:
                        param_metadata[name] = meta
                        cls_name = getattr(meta, "__class__", None).__name__
                        if cls_name == "BodyMarker":
                            body_param_name = name
                            query_param_names.discard(name)
                        elif cls_name == "QueryParamMarker":
                            query_param_names.add(name)
                        elif cls_name == "PathParamMarker":
                            path_param_names.add(name)
                            query_param_names.discard(name)

            # 2) Fallback: infer body param if POST/PUT/PATCH (pick first pydantic/dataclass)
            http_method = getattr(handler, "_http_method", "get").lower()
            if body_param_name is None and http_method in ("post", "put", "patch"):
                for name in list(query_param_names):
                    typ = type_hints_with_extras.get(name, sig.parameters[name].annotation)
                    if get_origin(typ) is Annotated:
                        typ = get_args(typ)[0]
                    if inspect.isclass(typ) and (issubclass(typ, BaseModel) or is_dataclass(typ)):
                        body_param_name = name
                        query_param_names.discard(name)
                        param_metadata[name] = BodyMarker()
                        break

            # 3) Build new signature with FastAPI params (use docstring param descriptions only if annotation has none)
            new_params = []
            annotations = dict(getattr(handler, "__annotations__", {}))

            for name, param in sig.parameters.items():
                ann = param.annotation
                default = param.default
                meta = param_metadata.get(name)

                # parameter description from docstring (if present)
                doc_param_desc = parsed_doc["args"].get(name)

                if name == body_param_name:
                    typ = ann
                    if get_origin(typ) is Annotated:
                        typ = get_args(typ)[0]
                    annotations[name] = typ
                    # body marker description: annotation wins; only use docstring if annotation missing description
                    if isinstance(meta, BodyMarker):
                        desc = getattr(meta, "description", None) or doc_param_desc
                        example = getattr(meta, "example", None)
                        default = FastAPI_Body(...) if default is inspect.Parameter.empty else FastAPI_Body(default)
                        # attach description/example into Body(...) via keyword args if available
                        if desc is not None or example is not None:
                            default = FastAPI_Body(default.default if hasattr(default, "default") else ..., description=desc, example=example)
                    else:
                        default = FastAPI_Body(...) if default is inspect.Parameter.empty else FastAPI_Body(default)
                    new_param = param.replace(annotation=typ, default=default)

                elif name in path_param_names:
                    typ = ann
                    if get_origin(typ) is Annotated:
                        typ = get_args(typ)[0]
                    annotations[name] = typ
                    if isinstance(meta, PathParamMarker):
                        # annotation wins: only use docstring if marker.description is falsy
                        desc = getattr(meta, "description", None) or doc_param_desc
                        example = getattr(meta, "example", None)
                        default = FastAPI_Path(..., description=desc, example=example) if (desc or example) else FastAPI_Path(...)
                    else:
                        # no annotation; use docstring if present
                        default = FastAPI_Path(..., description=doc_param_desc) if doc_param_desc else FastAPI_Path(...)
                    new_param = param.replace(annotation=typ, default=default)

                elif name in query_param_names:
                    typ = ann
                    if get_origin(typ) is Annotated:
                        typ = get_args(typ)[0]
                    annotations[name] = typ
                    if isinstance(meta, QueryParamMarker):
                        # annotation wins; only use docstring if no annotation description
                        desc = getattr(meta, "description", None) or doc_param_desc
                        example = getattr(meta, "example", None)
                        default_val = default if default is not inspect.Parameter.empty else None
                        if desc is not None or example is not None:
                            default = FastAPI_Query(default_val, description=desc, example=example)
                        else:
                            default = FastAPI_Query(default_val)
                    else:
                        default_val = default if default is not inspect.Parameter.empty else None
                        default = FastAPI_Query(default_val, description=doc_param_desc) if doc_param_desc else FastAPI_Query(default_val)
                    new_param = param.replace(annotation=typ, default=default)

                else:
                    new_param = param

                new_params.append(new_param)

            new_sig = sig.replace(parameters=new_params)

            # wrapper that calls handler and encodes result safely
            @functools.wraps(handler)
            async def wrapper(*args, **kwargs):
                bound = new_sig.bind(*args, **kwargs)
                bound.apply_defaults()

                result = handler(*bound.args, **bound.kwargs)
                if inspect.iscoroutine(result):
                    result = await result

                # Serialize result for FastAPI / Pydantic / dataclass
                return JSONResponse(jsonable_encoder(result))

            # preserve signature, annotations, docstring
            wrapper.__signature__ = new_sig
            wrapper.__annotations__ = annotations
            wrapper.__doc__ = handler.__doc__ or interface_fn.__doc__

            return wrapper

        # iterate over all service descriptors
        for descriptor in self.service_manager.descriptors.values():
            if not descriptor.is_component() and descriptor.is_local():
                prefix = ""

                type_descriptor = TypeDescriptor.for_type(descriptor.type)
                instance = self.environment.get(descriptor.implementation)

                if type_descriptor.has_decorator(rest):
                    prefix = type_descriptor.get_decorator(rest).args[0]

                for method in type_descriptor.get_methods():
                    decorator = next(
                        (
                            decorator
                            for decorator in Decorators.get(method.method)
                            if decorator.decorator in [get, put, post, delete]
                        ),
                        None,
                    )
                    if decorator is not None:
                        # prepare endpoint and metadata
                        handler = getattr(instance, method.get_name())
                        endpoint = wrap_service_method(handler, method, method.return_type, decorator.args[0])

                        # parse docstring from implementation or interface for summary/description/param docs
                        parsed = parse_google_docstring(handler.__doc__ or getattr(method, "method", None).__doc__ or "")

                        # summary and description: decorator kwargs override docstring
                        summary = decorator.kwargs.get("summary") or parsed["summary"]
                        description = decorator.kwargs.get("description") or parsed["description"]

                        path = join_paths(prefix, decorator.args[0])

                        self.router.add_api_route(
                            path=path,
                            endpoint=endpoint,
                            methods=[decorator.decorator.__name__],
                            name=f"{descriptor.get_component_descriptor().name}.{descriptor.name}.{method.get_name()}",
                            response_model=method.return_type,
                            summary=summary,
                            description=description,
                            tags=decorator.kwargs.get("tags"),
                        )

    # -------------------------
    # server control
    # -------------------------
    def start_server(self, host: str):
        """
        start the fastapi server in a thread
        """
        self.host = host

        config = uvicorn.Config(self.fast_api, host=host, port=self.port, access_log=False)

        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    # -------------------------
    def get_deserializers(self, service: Type, method):
        deserializers = self.deserializers.get(method)
        if deserializers is None:
            descriptor = TypeDescriptor.for_type(service).get_method(method.__name__)
            deserializers = [get_deserializer(type) for type in descriptor.param_types]
            self.deserializers.put(method, deserializers)
        return deserializers

    def deserialize_args(self, args: list[Any], type: Type, method: Callable) -> list:
        deserializers = self.get_deserializers(type, method)
        for i, arg in enumerate(args):
            args[i] = deserializers[i](arg)
        return args

    def get_descriptor_and_method(self, method_name: str) -> typing.Tuple[ServiceDescriptor, Callable]:
        parts = method_name.split(":")
        service_name = parts[1]
        method_name = parts[2]
        service_descriptor = typing.cast(ServiceDescriptor, ServiceManager.descriptors_by_name[service_name])
        service = self.service_manager.get_service(service_descriptor.type, preferred_channel="local")
        return service_descriptor, getattr(service, method_name)

    async def invoke_json(self, http_request: HttpRequest):
        data = await http_request.json()
        service_descriptor, method = self.get_descriptor_and_method(data["method"])
        args = self.deserialize_args(data["args"], service_descriptor.type, method)
        try:
            result = await self.dispatch(service_descriptor, method, args)
            return Response(result=result, exception=None).model_dump()
        except Exception as e:
            return Response(result=None, exception=str(e)).model_dump()

    async def invoke_msgpack(self, http_request: HttpRequest):
        data = msgpack.unpackb(await http_request.body(), raw=False)
        service_descriptor, method = self.get_descriptor_and_method(data["method"])
        args = self.deserialize_args(data["args"], service_descriptor.type, method)
        try:
            response = Response(result=await self.dispatch(service_descriptor, method, args), exception=None).model_dump()
        except Exception as e:
            response = Response(result=None, exception=str(e)).model_dump()
        return HttpResponse(
            content=msgpack.packb(response, use_bin_type=True),
            media_type="application/msgpack"
        )

    async def invoke_protobuf(self, http_request: HttpRequest):
        if self.protobuf_manager is None:
            self.protobuf_manager = self.environment.get(ProtobufManager)
        service_descriptor, method = self.get_descriptor_and_method(http_request.headers.get("x-rpc-method"))
        data = await http_request.body()
        request = self.protobuf_manager.get_request_message(service_descriptor.type, method)()
        request.ParseFromString(data)
        args = self.protobuf_manager.create_deserializer(request.DESCRIPTOR, method).deserialize(request)
        response_type = self.protobuf_manager.get_response_message(service_descriptor.type, method)
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

    async def invoke(self, http_request: HttpRequest):
        content_type = http_request.headers.get("content-type", "")
        if content_type == "application/x-protobuf":
            return await self.invoke_protobuf(http_request)
        elif content_type == "application/msgpack":
            return await self.invoke_msgpack(http_request)
        elif content_type == "application/json":
            return await self.invoke_json(http_request)
        else:
            return HttpResponse(
                content="Unsupported Content-Type",
                status_code=415,
                media_type="text/plain"
            )

    async def dispatch(self, service_descriptor: ServiceDescriptor, method: Callable, args: list[Any]) :
        ServiceManager.logger.debug("dispatch request %s.%s", service_descriptor, method.__name__)
        if inspect.iscoroutinefunction(method):
            return await method(*args)
        else:
            return method(*args)

    # override
    def add_route(self, path: str, endpoint: Callable, methods: list[str], response_class: typing.Union[Type[Response], DefaultPlaceholder] = Default(JSONResponse)):
        self.router.add_api_route(path=path, endpoint=endpoint, methods=methods, response_class=response_class)

    def route_health(self, url: str, callable: Callable):
        async def get_health_response():
            health : HealthCheckManager.Health = await callable()
            return JSONResponse(
                status_code= self.component_registry.map_health(health),
                content = health.to_dict()
            )
        self.router.get(url)(get_health_response)
