"""
rest channel implementation
"""
from __future__ import annotations

import inspect
import re
from dataclasses import is_dataclass

from typing import get_type_hints, TypeVar, Annotated, Callable, get_origin, get_args, Type, Optional, Sequence, Any
from pydantic import BaseModel

from aspyx.reflection import DynamicProxy, Decorators
from aspyx.util import get_serializer

from .channels import HTTPXChannel
from .service import channel, ServiceCommunicationException

T = TypeVar("T")


# --- Parameter markers --- #

class ParamMarker:
    """
    Base class for parameter metadata.
    Similar to FastAPI's Path, Query, Body.
    """
    def __init__(self, default=..., *, description: str | None = None, example: Any = None):
        self.default = default
        self.description = description
        self.example = example
        self.required = default is ...


class BodyMarker(ParamMarker):
    pass


def Body(t: type, *, description: str | None = None, example: Any = None, default=...):
    marker = BodyMarker(default=default, description=description, example=example)
    return Annotated[t, marker]


class QueryParamMarker(ParamMarker):
    pass


def QueryParam(t: type, *, description: str | None = None, example: Any = None, default=...):
    marker = QueryParamMarker(default=default, description=description, example=example)
    return Annotated[t, marker]


class PathParamMarker(ParamMarker):
    pass


def PathParam(t: type, *, description: str | None = None, example: Any = None):
    marker = PathParamMarker(default=..., description=description, example=example)
    return Annotated[t, marker]


# --- Decorators --- #

def rest(url=""):
    """
    mark service interfaces to add a url prefix
    """
    def decorator(cls):
        Decorators.add(cls, rest, url)
        return cls
    return decorator


def get(url: str, *, description: Optional[str] = None, summary: Optional[str] = None, tags: Optional[Sequence[str]] = None):
    """
    mark method as HTTP GET
    """
    def decorator(cls):
        Decorators.add(cls, get, url, tags=tags, summary=summary, description=description)
        return cls
    return decorator


def post(url: str, *, description: Optional[str] = None, summary: Optional[str] = None, tags: Optional[Sequence[str]] = None):
    """
    mark method as HTTP POST
    """
    def decorator(cls):
        Decorators.add(cls, post, url, tags=tags, summary=summary, description=description)
        return cls
    return decorator


def put(url: str, *, description: Optional[str] = None, summary: Optional[str] = None, tags: Optional[Sequence[str]] = None):
    """
    mark method as HTTP PUT
    """
    def decorator(cls):
        Decorators.add(cls, put, url, tags=tags, summary=summary, description=description)
        return cls
    return decorator


def delete(url: str, *, description: Optional[str] = None, summary: Optional[str] = None, tags: Optional[Sequence[str]] = None):
    """
    mark method as HTTP DELETE
    """
    def decorator(cls):
        Decorators.add(cls, delete, url, tags=tags, summary=summary, description=description)
        return cls
    return decorator


def patch(url: str):
    """
    mark method as HTTP PATCH
    """
    def decorator(cls):
        Decorators.add(cls, patch, url)
        return cls
    return decorator


# --- RestChannel --- #

@channel("rest")
class RestChannel(HTTPXChannel):
    """
    Executes HTTP requests for methods annotated with rest decorators and parameter markers.
    """
    __slots__ = [
        "signature",
        "url_template",
        "type",
        "calls",
        "return_type",
        "path_param_names",
        "query_param_names",
        "body_param_name",
        "body_serializer",
        "param_metadata"
    ]

    class Call:
        __slots__ = [
            "type",
            "url_template",
            "path_param_names",
            "query_param_names",
            "body_param_name",
            "body_serializer",
            "return_type",
            "signature",
            "param_metadata"
        ]

        def __init__(self, cls_type: Type, method: Callable):
            self.signature = inspect.signature(method)
            type_hints = get_type_hints(method, include_extras=True)

            # URL prefix
            prefix = ""
            if Decorators.has_decorator(cls_type, rest):
                prefix = Decorators.get_decorator(cls_type, rest).args[0]

            # Determine HTTP method and url_template
            self.type = "get"
            self.url_template = ""
            self.param_metadata = {}

            decorators = Decorators.get_all(method)
            for decorator_func in [get, post, put, delete, patch]:
                descriptor = next((d for d in decorators if d.decorator is decorator_func), None)
                if descriptor:
                    self.type = decorator_func.__name__
                    # normalize joining of prefix and route path
                    self.url_template = prefix.rstrip("/") + "/" + descriptor.args[0].lstrip("/")

            # Path params
            self.path_param_names = set(re.findall(r"{(.*?)}", self.url_template))
            param_names = set(self.signature.parameters.keys()) - {"self"} - self.path_param_names

            # Body and query params
            self.body_param_name = None
            self.query_param_names = set()

            for name, hint in type_hints.items():
                origin = get_origin(hint)
                if origin is Annotated:
                    args = get_args(hint)
                    typ = args[0]
                    for meta in args[1:]:
                        if isinstance(meta, BodyMarker):
                            self.body_param_name = name
                            self.body_serializer = get_serializer(typ)
                            param_names.discard(name)
                            self.param_metadata[name] = meta
                        elif isinstance(meta, QueryParamMarker):
                            self.query_param_names.add(name)
                            param_names.discard(name)
                            self.param_metadata[name] = meta
                        elif isinstance(meta, PathParamMarker):
                            self.param_metadata[name] = meta

            # fallback: infer body param if POST/PUT/PATCH
            if self.body_param_name is None and self.type in ("post", "put", "patch"):
                for name in param_names.copy():
                    typ = type_hints.get(name)
                    if typ is None:
                        continue
                    if get_origin(typ) is Annotated:
                        typ = get_args(typ)[0]
                    if (isinstance(typ, type) and issubclass(typ, BaseModel)) or is_dataclass(typ):
                        self.body_param_name = name
                        self.body_serializer = get_serializer(typ)
                        param_names.discard(name)
                        break

            # remaining params are query params
            self.query_param_names.update(param_names)

            # Return type
            self.return_type = type_hints.get("return", None)

            # debug
            try:
                if getattr(method, "__name__", "") == "test_get":
                    print("[RestChannel.Call] type=", self.type, "url=", self.url_template,
                          "path_params=", self.path_param_names,
                          "query_params=", self.query_param_names,
                          "param_metadata keys=", list(self.param_metadata.keys()))
            except Exception:
                pass

    # --- RestChannel constructor --- #
    def __init__(self):
        super().__init__()
        self.calls: dict[Callable, RestChannel.Call] = {}

    # --- Helpers --- #
    def get_call(self, cls_type: Type, method: Callable) -> Call:
        call = self.calls.get(method)
        if call is None:
            call = RestChannel.Call(cls_type, method)
            self.calls[method] = call
        return call

    # --- Async invoke --- #
    async def invoke_async(self, invocation: DynamicProxy.Invocation):
        call = self.get_call(invocation.type, invocation.method)
        bound = call.signature.bind(self, *invocation.args, **invocation.kwargs)
        bound.apply_defaults()
        arguments = bound.arguments

        url = call.url_template.format(**arguments)
        # ensure there is a slash after '/api' prefix if missing (defensive)
        url = re.sub(r'^(/api)(?=[^/])', r'\1/', url)
        query_params = {k: arguments[k] for k in call.query_param_names if k in arguments}
        body = {}
        if call.body_param_name:
            body = call.body_serializer(arguments.get(call.body_param_name))

        try:
            if call.type in ["get", "put", "delete"]:
                result = await self.request_async(call.type, self.get_url() + url, params=query_params, timeout=self.timeout)
            elif call.type == "post":
                result = await self.request_async("post", self.get_url() + url, params=query_params, json=body, timeout=self.timeout)
            return self.get_deserializer(invocation.type, invocation.method)(result.json())
        except ServiceCommunicationException:
            raise
        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e

    # --- Sync invoke --- #
    def invoke(self, invocation: DynamicProxy.Invocation):
        call = self.get_call(invocation.type, invocation.method)
        bound = call.signature.bind(self, *invocation.args, **invocation.kwargs)
        bound.apply_defaults()
        arguments = bound.arguments

        url = call.url_template.format(**arguments)
        # ensure there is a slash after '/api' prefix if missing (defensive)
        url = re.sub(r'^(/api)(?=[^/])', r'\1/', url)
        query_params = {k: arguments[k] for k in call.query_param_names if k in arguments}
        body = {}
        if call.body_param_name:
            body = call.body_serializer(arguments.get(call.body_param_name))

        try:
            if call.type in ["get", "put", "delete"]:
                result = self.request(call.type, self.get_url() + url, params=query_params, timeout=self.timeout)
            elif call.type == "post":
                result = self.request("post", self.get_url() + url, params=query_params, json=body, timeout=self.timeout)
            return self.get_deserializer(invocation.type, invocation.method)(result.json())
        except ServiceCommunicationException:
            raise
        except Exception as e:
            raise ServiceCommunicationException(f"communication exception {e}") from e
