"""
rest channel implementation
"""
import inspect
import re
from dataclasses import is_dataclass, asdict

from typing import get_type_hints, TypeVar, Annotated, Callable, get_origin, get_args, Type

from pydantic import BaseModel

from aspyx.reflection import DynamicProxy, Decorators
from .service import ServiceException, channel

T = TypeVar("T")

from .channels import HTTPXChannel

class BodyMarker:
    pass

Body = lambda t: Annotated[t, BodyMarker]

class QueryParamMarker:
    pass

QueryParam = lambda t: Annotated[t, QueryParamMarker]

# decorators

def rest(url=""):
    """
    mark service interfaces to add a url prefix

    Args:
        url: prefix that will be added to all urls
    """
    def decorator(cls):
        Decorators.add(cls, rest, url)

        return cls
    return decorator

def get(url: str):
    """
    methods marked with `get` will be executed by calling a http get request.

    Args:
        url: the url
    """
    def decorator(cls):
        Decorators.add(cls, get, url)

        return cls
    return decorator


def post(url: str):
    """
    methods marked with `post` will be executed by calling a http get request.
    The body parameter should be marked with `Body(<param>)`

    Args:
        url: the url
    """
    def decorator(cls):
        Decorators.add(cls, post, url)

        return cls

    return decorator

def put(url: str):
    """
    methods marked with `put` will be executed by calling a http put request.

    Args:
        url: the url
    """
    def decorator(cls):
        Decorators.add(cls, put, url)

        return cls

    return decorator

def delete(url: str):
    """
    methods marked with `delete` will be executed by calling a http delete request.

    Args:
        url: the url
    """
    def decorator(cls):
        Decorators.add(cls, delete, url)

        return cls

    return decorator

def patch(url: str):
    """
    methods marked with `patch` will be executed by calling a http patch request.

    Args:
        url: the url
    """
    def decorator(cls):
        Decorators.add(cls, patch, url)

        return cls

    return decorator

@channel("rest")
class RestChannel(HTTPXChannel):
    """
    A rest channel executes http requests as specified by the corresponding decorators and annotations,
    """
    __slots__ = [
        "signature",
        "url_template",
        "type",
        "calls",
        "return_type",
        "path_param_names",
        "query_param_names",
        "body_param_name"
    ]

    # local class

    class Call:
        def __init__(self, type: Type, method : Callable):
            self.signature = inspect.signature(method)

            prefix = ""
            if Decorators.has_decorator(type, rest):
                prefix = Decorators.get_decorator(type, rest).args[0]

            # find decorator

            self.type = "get"
            self.url_template = ""

            decorators = Decorators.get_all(method)

            for decorator in [get, post, put, delete, patch]:
                descriptor = next((descriptor for descriptor in decorators if descriptor.decorator is decorator), None)
                if descriptor is not None:
                    self.type = decorator.__name__
                    self.url_template = prefix + descriptor.args[0]

            # parameters

            self.path_param_names = set(re.findall(r"{(.*?)}", self.url_template))

            hints = get_type_hints(method, include_extras=True)

            self.body_param_name = None
            self.query_param_names = set()

            for param_name, hint in hints.items():
                if get_origin(hint) is Annotated:
                    metadata = get_args(hint)[1:]
                    if BodyMarker in metadata:
                        self.body_param_name = param_name
                    elif QueryParamMarker in metadata:
                        self.query_param_names.add(param_name)

            # return type

            self.return_type = get_type_hints(method)['return']

    # constructor

    def __init__(self):
        super().__init__()

        self.calls : dict[Callable, RestChannel.Call] = {}

    # internal

    def get_call(self, type: Type ,method: Callable):
        call = self.calls.get(method, None)
        if call is None:
            call = RestChannel.Call(type, method)
            self.calls[method] = call

        return call

    def to_dict(self, obj):
        if obj is None:
            return None
        if is_dataclass(obj):
            return asdict(obj)
        elif isinstance(obj, BaseModel):
            return obj.dict()
        elif hasattr(obj, "__dict__"):
            return vars(obj)
        else:
            # fallback for primitives etc.
            return obj

    # override

    def invoke(self, invocation: DynamicProxy.Invocation):
        call = self.get_call(invocation.type, invocation.method)

        bound = call.signature.bind(self,*invocation.args, **invocation.kwargs)
        bound.apply_defaults()
        arguments = bound.arguments

        # url

        url = call.url_template.format(**arguments)
        query_params = {k: arguments[k] for k in call.query_param_names if k in arguments}
        body = {}
        if call.body_param_name is not None:
            body = self.to_dict(arguments.get(call.body_param_name))

        # call

        try:
            if self.client is not None:
                result = None
                if call.type == "get":
                    result = self.client.get(self.get_url() + url, params=query_params, timeout=30000.0).json()
                elif call.type == "put":
                    result = self.client.put(self.get_url() + url, params=query_params, timeout=30000.0).json()
                elif call.type == "delete":
                    result = self.client.delete(self.get_url() + url, params=query_params, timeout=30000.0).json()
                elif call.type == "post":
                    result = self.client.post(self.get_url() + url, params=query_params, json=body, timeout=30000.0).json()

                return self.get_deserializer(invocation.type, invocation.method)(result)
            else:
                raise ServiceException(
                    f"no url for channel {self.name} for component {self.component_descriptor.name} registered")
        except Exception as e:
            raise ServiceException(f"communication exception {e}") from e
