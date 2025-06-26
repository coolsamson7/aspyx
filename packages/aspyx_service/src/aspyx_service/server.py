"""
FastAPI server implementation for the aspyx service framework.
"""
import inspect
import threading
from typing import Type, Optional, Callable

import msgpack
import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi import Request as HttpRequest, Response as HttpResponse

from aspyx.di import Environment
from aspyx.reflection import TypeDescriptor

from .serialization import deserialize

from .service import Server, ServiceManager
from .channels import Request, Response



class FastAPIServer(Server):
    # constructor

    def __init__(self, host="0.0.0.0", port=8000, **kwargs):
        super().__init__()

        self.host = host
        Server.port = port
        self.server_thread = None
        self.service_manager : Optional[ServiceManager] = None

        self.router = APIRouter()
        self.fast_api = FastAPI(host=self.host, port=Server.port)

        # cache

        self.param_types: dict[str, list[Type]] = {}

        # that's the overall dispatcher

        self.router.post("/invoke")(self.invoke)

    # private

    def start(self):
        def run():
            uvicorn.run(self.fast_api, host=self.host, port=self.port, access_log=False)

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

        print(f"server started on {self.host}:{self.port}")

    def deserialize_args(self, request: Request, param_types: list[Type]) -> list:
        args = list(request.args)

        for i in range(0, len(param_types)):
            args[i] = deserialize(args[i], param_types[i])

        return args

    async def invoke(self, http_request: HttpRequest):
        content_type = http_request.headers.get("content-type", "")

        content = "json"
        if "application/msgpack" in content_type:
            content = "msgpack"
            raw_data = await http_request.body()
            data = msgpack.unpackb(raw_data, raw=False)
        elif "application/json" in content_type:
            data = await http_request.json()
        else:
            return HttpResponse(
                content="Unsupported Content-Type",
                status_code=415,
                media_type="text/plain"
            )

        request = Request(**data)

        if content == "json":
            return await self.dispatch(request)
        else:
            return HttpResponse(
                content=msgpack.packb(await self.dispatch(request), use_bin_type=True),
                media_type="application/msgpack"
            )

    def get_param_types(self, method: str, compute: Callable) -> list[Type]:
        param_types = self.param_types.get(method, None)
        if param_types is None:
            param_types = compute()
            self.param_types[method] = param_types

        return param_types

    async def dispatch(self, request: Request) :
        ServiceManager.logger.debug("dispatch request %s", request.method)

        # <comp>:<service>:<method>

        parts = request.method.split(":")

        #component = parts[0]
        service_name = parts[1]
        method_name = parts[2]

        service_descriptor = ServiceManager.descriptors_by_name[service_name]
        service = self.service_manager.get_service(service_descriptor.type, preferred_channel="local")

        method = getattr(service, method_name)
        args = self.deserialize_args(request, self.get_param_types(request.method, lambda: TypeDescriptor.for_type(service_descriptor.type).get_method(method_name).param_types))
        try:
            if inspect.iscoroutinefunction(method):
                result = await method(*args)
            else:
                result = method(*args)

            return Response(result=result, exception=None).dict()
        except Exception as e:
            return Response(result=None, exception=str(e)).dict()

    # override

    def route(self, url: str, callable: Callable):
        self.router.get(url)(callable)

    def boot(self, module_type: Type) -> Environment:
        # setup environment

        environment = Environment(module_type)

        self.service_manager = environment.get(ServiceManager)

        self.service_manager.startup(self)

        # add routes

        self.fast_api.include_router(self.router)

        # start server thread

        self.start()

        return environment
