"""
Tests
"""
import asyncio
import threading
import time
import logging

from typing import Callable, TypeVar, Type, Awaitable, Any, cast

from consul import Consul

from aspyx_service import ConsulComponentRegistry, SessionManager

from aspyx.di import module, Environment, create
from aspyx.di.aop import advice, around, methods, Invocation
from aspyx.util import Logger


from aspyx_service.service import ServiceManager, ComponentRegistry, Channel

Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.CRITICAL,
    "aspyx.di": logging.INFO,
    "aspyx.di.aop": logging.INFO,
    "aspyx.service": logging.INFO
})

from client import TestService, TestRestService, Pydantic, Data, TestAsyncRestService, TestAsyncService, ClientModule

# main

@advice
class ChannelAdvice:
    def __init__(self):
        pass

    @around(methods().named("customize").of_type(Channel))
    def customize_channel(self, invocation: Invocation):
        channel = cast(Channel, invocation.args[0])

        channel.select_round_robin() # or select_first_url()

        return invocation.proceed()

@module(imports=[ClientModule])
class TestModule:
    def __init__(self):
        pass

    @create()
    def create_session_storage(self) -> SessionManager.Storage:
        return SessionManager.InMemoryStorage(max_size=1000, ttl=3600)

    @create()
    def create_registry(self) -> ComponentRegistry:
        return ConsulComponentRegistry(port=8000, consul=Consul(host="localhost", port=8500))

def boot() -> ServiceManager:
    environment = Environment(TestModule)

    service_manager = environment.get(ServiceManager)

    return service_manager

T = TypeVar("T")

# main

lorem_ipsum = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua"

pydantic = Pydantic(i=1, f=1.0, b=True, s="s",
                    str0=lorem_ipsum,
                    str1=lorem_ipsum,
                    str2=lorem_ipsum,
                    str3=lorem_ipsum,
                    str4=lorem_ipsum,
                    str5=lorem_ipsum,
                    str6=lorem_ipsum,
                    str7=lorem_ipsum,
                    str8=lorem_ipsum,
                    str9=lorem_ipsum
                    )
data = Data(i=1, f=1.0, b=True, s="s",
                    str0=lorem_ipsum,
                    str1=lorem_ipsum,
                    str2=lorem_ipsum,
                    str3=lorem_ipsum,
                    str4=lorem_ipsum,
                    str5=lorem_ipsum,
                    str6=lorem_ipsum,
                    str7=lorem_ipsum,
                    str8=lorem_ipsum,
                    str9=lorem_ipsum
            )

def run_loops(name: str, loops: int, type: Type[T], instance: T,  callable: Callable[[T], None]):
    callable(instance) # initialization

    start = time.perf_counter()
    for _ in range(loops):
        callable(instance)

    end = time.perf_counter()
    avg_ms = ((end - start) / loops) * 1000

    print(f"run {name}, loops={loops}: avg={avg_ms:.3f} ms")

async def run_async_loops(name: str, loops: int, type: Type[T], instance: T,  callable: Callable[[T], Awaitable[Any]]):
    await callable(instance)  # initialization

    start = time.perf_counter()
    for _ in range(loops):
        await callable(instance)

    end = time.perf_counter()
    avg_ms = ((end - start) / loops) * 1000

    print(f"run {name}, loops={loops}: avg={avg_ms:.3f} ms")

def run_threaded_async_loops(name: str, loops: int, n_threads: int,  type: Type[T], instance: T,  callable: Callable[[T], Awaitable[Any]]):
    threads = []

    def worker(thread_id: int):
        #print(f"worker {thread_id} running on thread {threading.current_thread().name}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run():
            for i in range(loops):
                await callable(instance)

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
    avg_ms = ((end - start) / (n_threads * loops)) * 1000

    print(f"{name} {loops} in {n_threads} threads: {took} ms, avg: {avg_ms}ms")

def run_threaded_sync_loops(name: str, loops: int, n_threads: int,  type: Type[T], instance: T,  callable: Callable[[T], Any]):
    threads = []

    def worker(thread_id: int):
        #print(f"worker {thread_id} running on thread {threading.current_thread().name}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run():
            for i in range(loops):
                callable(instance)

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
    avg_ms = ((end - start) / (n_threads * loops)) * 1000

    print(f"{name} {loops} in {n_threads} threads: {took} ms, avg: {avg_ms}ms")

manager = boot()

async def main():
    print("start tests...")

    # get service manager

    loops = 1000

    # tests

    run_loops("rest", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"), lambda service: service.get("world"))
    run_loops("json", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-json"), lambda service: service.hello("world"))
    run_loops("msgpack", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-msgpack"), lambda service: service.hello("world"))
    run_loops("protobuf", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-protobuf"),
              lambda service: service.hello("world"))

    # pydantic

    run_loops("rest & pydantic", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"), lambda service: service.post_pydantic("hello", pydantic))
    run_loops("json & pydantic", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-json"), lambda service: service.pydantic(pydantic))
    run_loops("msgpack & pydantic", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-msgpack"), lambda service: service.pydantic(pydantic))
    run_loops("protobuf & pydantic", loops, TestService,
              manager.get_service(TestService, preferred_channel="dispatch-protobuf"),
              lambda service: service.pydantic(pydantic))

    # data class

    run_loops("rest & data", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"),
              lambda service: service.post_data("hello", data))
    run_loops("json & data", loops, TestService,
              manager.get_service(TestService, preferred_channel="dispatch-json"),
              lambda service: service.data(data))
    run_loops("msgpack & data", loops, TestService,
              manager.get_service(TestService, preferred_channel="dispatch-msgpack"),
              lambda service: service.data(data))
    run_loops("protobuf & data", loops, TestService,
              manager.get_service(TestService, preferred_channel="dispatch-protobuf"),
              lambda service: service.data(data))

    # async

    await run_async_loops("async rest", loops, TestAsyncRestService, manager.get_service(TestAsyncRestService, preferred_channel="rest"),
                          lambda service: service.get("world"))
    await run_async_loops("async json", loops, TestAsyncService, manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
              lambda service: service.hello("world"))
    await run_async_loops("async msgpack", loops, TestAsyncService, manager.get_service(TestAsyncService, preferred_channel="dispatch-msgpack"),
              lambda service: service.hello("world"))
    await run_async_loops("async protobuf", loops, TestAsyncService,
                          manager.get_service(TestAsyncService, preferred_channel="dispatch-protobuf"),
                          lambda service: service.hello("world"))

    # pydantic

    await run_async_loops("async rest & pydantic", loops, TestAsyncRestService, manager.get_service(TestAsyncRestService, preferred_channel="rest"),
              lambda service: service.post_pydantic("hello", pydantic))
    await run_async_loops("async json & pydantic", loops, TestAsyncService,
              manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
              lambda service: service.pydantic(pydantic))
    await run_async_loops("async msgpack & pydantic", loops, TestAsyncService,
              manager.get_service(TestAsyncService, preferred_channel="dispatch-msgpack"),
              lambda service: service.pydantic(pydantic))
    await run_async_loops("async protobuf & pydantic", loops, TestAsyncService,
                          manager.get_service(TestAsyncService, preferred_channel="dispatch-protobuf"),
                          lambda service: service.pydantic(pydantic))

    # data class

    # pydantic

    await run_async_loops("async rest & data", loops, TestAsyncRestService, manager.get_service(TestAsyncRestService, preferred_channel="rest"),
              lambda service: service.post_data("hello", data))
    await run_async_loops("async json & data", loops, TestAsyncService,
              manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
              lambda service: service.data(data))
    await run_async_loops("async msgpack & data", loops, TestAsyncService,
              manager.get_service(TestAsyncService, preferred_channel="dispatch-msgpack"),
              lambda service: service.data(data))
    await run_async_loops("async protobuf & data", loops, TestAsyncService,
                          manager.get_service(TestAsyncService, preferred_channel="dispatch-protobuf"),
                          lambda service: service.data(data))

    # a real thread test

    # sync

    run_threaded_sync_loops("threaded sync json, 1 thread", loops, 1, TestService,
                             manager.get_service(TestService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_sync_loops("threaded sync json, 2 thread", loops, 2, TestService,
                             manager.get_service(TestService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_sync_loops("threaded sync json, 4 thread", loops, 4, TestService,
                             manager.get_service(TestService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_sync_loops("threaded sync json, 8 thread", loops, 8, TestService,
                             manager.get_service(TestService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_sync_loops("threaded sync json, 16 thread", loops, 16, TestService,
                             manager.get_service(TestService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_sync_loops("threaded sync protobuf, 16 thread", loops, 16, TestService,
                            manager.get_service(TestService, preferred_channel="dispatch-protobuf"),
                            lambda service: service.hello("world"))

    # async

    run_threaded_async_loops("threaded async json, 1 thread", loops, 1, TestAsyncService,
                             manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world") )
    run_threaded_async_loops("threaded async json, 2 thread", loops, 2, TestAsyncService,
                             manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_async_loops("threaded async json, 4 thread", loops, 4, TestAsyncService,
                             manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_async_loops("threaded async json, 8 thread", loops, 8, TestAsyncService,
                             manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_async_loops("threaded async json, 16 thread", loops, 16, TestAsyncService,
                             manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
                             lambda service: service.hello("world"))
    run_threaded_async_loops("threaded async protobuf, 16 thread", loops, 16, TestAsyncService,
                             manager.get_service(TestAsyncService, preferred_channel="dispatch-protobuf"),
                             lambda service: service.hello("world"))

if __name__ == "__main__":
    asyncio.run(main())
