"""
FastAPI server implementation for the aspyx service framework.
"""
import atexit
import inspect
import threading
from typing import Type, Optional, Callable

from fastapi.responses import JSONResponse
import msgpack
import uvicorn

from fastapi import FastAPI, APIRouter, Request as HttpRequest, Response as HttpResponse

from aspyx.di import Environment
from aspyx.reflection import TypeDescriptor, Decorators

from .service import ComponentRegistry
from .healthcheck import HealthCheckManager

from .serialization import get_deserializer

from .service import Server, ServiceManager
from .channels import Request, Response

from .restchannel import get, post, put, delete, rest


class FastAPIServer(Server):
    """
    A server utilizing fastapi framework.
    """
    # constructor

    def __init__(self, host="0.0.0.0", port=8000, **kwargs):
        super().__init__()

        self.host = host
        Server.port = port
        self.server_thread = None
        self.environment : Optional[Environment] = None
        self.service_manager : Optional[ServiceManager] = None
        self.component_registry: Optional[ComponentRegistry] = None

        self.router = APIRouter()
        self.fast_api = FastAPI()

        # cache

        self.deserializers: dict[str, list[Callable]] = {}

        # that's the overall dispatcher

        self.router.post("/invoke")(self.invoke)

    # private

    def add_routes(self):
        """
        add everything that looks like a http endpoint
        """

        # go

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
                            endpoint=getattr(instance, method.get_name()),
                            methods=[decorator.decorator.__name__],
                            name=f"{descriptor.get_component_descriptor().name}.{descriptor.name}.{method.get_name()}",
                            response_model=method.return_type,
                        )

    def start(self):
        """
        start the fastapi server in a thread
        """

        config = uvicorn.Config(self.fast_api, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)

        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        print(f"server started on {self.host}:{self.port}")

        return thread


    def get_deserializers(self, service: Type, method):
        deserializers = self.deserializers.get(method, None)
        if deserializers is None:
            descriptor = TypeDescriptor.for_type(service).get_method(method.__name__)

            deserializers = [get_deserializer(type) for type in descriptor.param_types]
            self.deserializers[method] = deserializers

        return deserializers

    def deserialize_args(self, request: Request, type: Type, method: Callable) -> list:
        args = list(request.args)

        deserializers = self.get_deserializers(type, method)

        for i, arg in enumerate(args):
            args[i] = deserializers[i](arg)

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

        args = self.deserialize_args(request, service_descriptor.type, method)
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

    def route_health(self, url: str, callable: Callable):
        async def get_health_response():
            health : HealthCheckManager.Health = await callable()

            return JSONResponse(
                status_code= self.component_registry.map_health(health),
                content = health.to_dict()
            )

        self.router.get(url)(get_health_response)

    def boot(self, module_type: Type) -> Environment:
        """
        startup the service manager, DI framework and the fastapi server based on the supplied module

        Args:
            module_type: the module

        Returns:

        """
        # setup environment

        self.environment = Environment(module_type)
        self.service_manager = self.environment.get(ServiceManager)
        self.component_registry = self.environment.get(ComponentRegistry)

        self.service_manager.startup(self)

        # add routes

        self.add_routes()
        self.fast_api.include_router(self.router)

        for route in self.fast_api.routes:
            print(f"{route.name}: {route.path} [{route.methods}]")

        # start server thread

        self.start()

        # shutdown

        def cleanup():
            self.service_manager.shutdown()

        atexit.register(cleanup)

        # done

        return self.environment
