"""
Tests
"""
import asyncio
import logging
import threading
import time
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, cast, Optional

import consul
import httpx

from aspyx.di import module, create, injectable, inject_environment, Environment
from aspyx.di.aop import Invocation, advice, around, methods
from aspyx.di.configuration import YamlConfigurationSource

from aspyx_service import ConsulComponentRegistry, service, Service, component, Component, \
    implementation, health, AbstractComponent, ChannelAddress, inject_service, \
    FastAPIServer, Server, ServiceModule, DispatchJSONChannel, ServiceManager, ComponentDescriptor, health_checks, \
    health_check, HealthCheckManager, get, post, Body, rest

# configure logging

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

logging.getLogger("httpx").setLevel(logging.ERROR)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({
    "aspyx.di": logging.INFO,
    "aspyx.service": logging.INFO
})

# just a test

class InterceptingClient(httpx.Client):
    # constructor

    def __init__(self, *args, **kwargs):
        #self.token_provider = token_provider
        super().__init__(*args, **kwargs)

    # override

    def request(self, method, url, *args, **kwargs):
        #headers = kwargs.pop("headers", {})
        #headers["Authorization"] = f"Bearer {self.token_provider()}"
        #kwargs["headers"] = headers

        return super().request(method, url, *args, **kwargs)

@advice
class ChannelAdvice:
    def __init__(self):
        pass

    @around(methods().named("make_client").of_type(DispatchJSONChannel))
    def make_client(self, invocation: Invocation):
        rest_channel = cast(DispatchJSONChannel, invocation.args[0])

        rest_channel.select_round_robin()

        return InterceptingClient()

@advice
class ConsulAdvice:
    def __init__(self):
        pass

    @around(methods().named("make_consul").of_type(ConsulComponentRegistry))
    def make_consul(self, invocation: Invocation):
        host = invocation.kwargs["host"] # 0 is self
        port = invocation.kwargs["port"]
        return consul.Consul(host=host, port=port)

# test services & components
@dataclass
class Embedded:
    d1 : str
    d2 : str
    d3: str
    d4: str
    d5: str

@dataclass
class Data:
    d0: str
    d1 : str
    d2 : str
    d3: str
    d4: str
    d5: str
    d6: str
    d7: str
    d8: str
    d9: str

    e1: Embedded
    e2: Embedded
    e3: Embedded
    e4: Embedded
    e5: Embedded

data = Data("data-0", "data-1", "data-2", "data-3", "data-4", "data-5", "data-6", "data-7", "data-8", "data-9",
            Embedded("e1", "e2", "e3", "e4", "e5"),
            Embedded("e1", "e2", "e3", "e4", "e5"),
            Embedded("e1", "e2", "e3", "e4", "e5"),
            Embedded("e1", "e2", "e3", "e4", "e5"),
            Embedded("e1", "e2", "e3", "e4", "e5")
)

@service(name="test-service", description="cool")
@rest("/api")
class TestService(Service):
    @abstractmethod
    @get("/hello/{message}")
    def hello(self, message: str) -> str:
        pass

    @abstractmethod
    async def hello_async(self, message: str) -> str:
        pass

    @post("/data/")
    def data(self, data: Body(Data)) -> Data:
        pass

    async def data_async(self, data: Data) -> Data:
        pass

@component(services =[TestService])
class TestComponent(Component): # pylint: disable=abstract-method
    pass

# implementation classes

@implementation()
class TestServiceImpl(TestService):
    def __init__(self):
        pass

    def hello(self, message: str) -> str:
        return f"hello {message}"

    async def hello_async(self, message: str) -> str:
        return f"hello {message}"

    def data(self, data: Data) -> Data:
        return data

    async def data_async(self, data: Data) -> Data:
        return data

@implementation()
@health("/health")
class TestComponentImpl(AbstractComponent, TestComponent):
    # constructor

    def __init__(self):
        super().__init__()

        self.health_check_manager : Optional[HealthCheckManager] = None

    # lifecycle hooks

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.health_check_manager = environment.get(HealthCheckManager)

    # implement

    async def get_health(self) -> HealthCheckManager.Health:
        return await self.health_check_manager.check()

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [
            ChannelAddress("rest", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}"),
            ChannelAddress("dispatch-msgpack", f"http://{Server.get_local_ip()}:{port}")
        ]

    def startup(self) -> None:
        print("### startup")

    def shutdown(self) -> None:
        print("### shutdown")

@injectable()
class Bar:
    def __init__(self):
        pass

@injectable(eager=False)
class Test:
    def __init__(self):
        self.service = None

    @inject_service(preferred_channel="")
    def set_service(self, service: TestService, bla: str):
        self.service = service
        print(service)

@health_checks()
@injectable()
class Checks:
    def __init__(self):
        pass

    @health_check(fail_if_slower_than=1)
    def check_1(self, result: HealthCheckManager.Result):
        #result.set_status(HealthStatus.OK)
        #time.sleep(2)
        pass

    @health_check(name="check-2", cache=10)
    def check_2(self, result: HealthCheckManager.Result):
        pass # result.set_status(HealthStatus.OK)


@module(imports=[ServiceModule])
class Module:
    def __init__(self):
        pass

    @create()
    def create_yaml_source(self) -> YamlConfigurationSource:
        return YamlConfigurationSource(f"{Path(__file__).parent}/config.yaml")

    @create()
    def create_registry(self) -> ConsulComponentRegistry:
        return ConsulComponentRegistry(Server.port, "http://localhost:8500")

# main



async def main():
    server = FastAPIServer(host="0.0.0.0", port=8000)

    environment = server.boot(Module)

    # Give the server a second to start

    service_manager = environment.get(ServiceManager)

    descriptor: ComponentDescriptor = cast(ComponentDescriptor, service_manager.get_descriptor(TestComponent))

    while True:
        addresses = service_manager.component_registry.get_addresses(descriptor)
        if len(addresses) > 0:
            break

        print("zzz...")
        time.sleep(1)

    test_service = service_manager.get_service(TestService, preferred_channel="rest")

    r = test_service.hello("world")

    test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")
    msgpack_test_service = service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

    result = await test_service.hello_async("andi")
    result = test_service.data(data)
    result = msgpack_test_service.data(data)

    #####

    def test_thread_test(title: str, n_threads = 1, iterations = 10000):
        threads = []

        def worker(thread_id: int):
            test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")
            for i in range(iterations):
                test_service.data(data)

        start = time.perf_counter()

        for t_id in range(0, n_threads):
            thread = threading.Thread(target=worker, args=(t_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        end = time.perf_counter()
        took = (end - start) * 1000
        avg_ms = ((end - start) / (n_threads * iterations)) * 1000

        print(f"{title} {iterations} in {n_threads} threads: {took} ms, avg: {avg_ms}ms")

    def test_async_thread_test(title: str, n_threads = 1, iterations = 10000):
        threads = []

        def worker(thread_id: int):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def run():
                test_service = service_manager.get_service(TestService, preferred_channel="dispatch-json")
                for i in range(iterations):
                    await test_service.data_async(data)

            loop.run_until_complete(run())
            loop.close()

        start = time.perf_counter()

        for t_id in range(0, n_threads):
            thread = threading.Thread(target=worker, args=(t_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        end = time.perf_counter()
        took = (end - start) * 1000
        avg_ms = ((end - start) / (n_threads * iterations)) * 1000

        print(f"{title} {iterations} in {n_threads} threads: {took} ms, avg: {avg_ms}ms")


    #test_thread_test(title="sync call", n_threads=1, iterations=1000)
    #test_async_thread_test(title="async call",n_threads=1, iterations=1000)

    #####

    test_service = service_manager.get_service(TestService, preferred_channel="rest")

    loops = 1000
    start = time.perf_counter()
    for _ in range(loops):
        test_service.data(data)
        #test_service.hello("world")

    end = time.perf_counter()

    avg_ms = ((end - start) / loops) * 1000
    print(f"Average time per rest call: {avg_ms:.3f} ms")

    test_service = service_manager.get_service(TestService, preferred_channel="dispatch-msgpack")

    loops = 1000
    start = time.perf_counter()
    for _ in range(loops):
        #test_service.hello("andi")
        test_service.data(data)

    end = time.perf_counter()

    avg_ms = ((end - start) / loops) * 1000
    print(f"Average time per dispatch call: {avg_ms:.3f} ms")

    return

    #####

    print(result)

    loops = 1000
    start = time.perf_counter()
    for _ in range(loops):
        # test.hello("andi")
        test_service.data(data)

    end = time.perf_counter()

    avg_ms = ((end - start) / loops) * 1000
    print(f"Average time per call: {avg_ms:.3f} ms")

    #

    start = time.perf_counter()
    for _ in range(loops):
        # test.hello("andi")
        await test_service.data_async(data)

    end = time.perf_counter()

    avg_ms = ((end - start) / loops) * 1000
    print(f"Average time per async call: {avg_ms:.3f} ms")

    #

    start = time.perf_counter()
    for _ in range(loops):
        # test.hello("andi")
        msgpack_test_service.data(data)

    end = time.perf_counter()

    avg_ms = ((end - start) / loops) * 1000
    print(f"msgpack Average time per call: {avg_ms:.3f} ms")

    #

    start = time.perf_counter()
    for _ in range(loops):
        # test.hello("andi")
        await msgpack_test_service.data_async (data)

    end = time.perf_counter()

    avg_ms = ((end - start) / loops) * 1000
    print(f"msgpack Average time per async call: {avg_ms:.3f} ms")

    print("Press Enter to exit...")
    input()  # wait

if __name__ == "__main__":
    asyncio.run(main())

