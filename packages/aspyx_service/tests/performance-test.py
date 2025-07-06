"""
Tests
"""
import asyncio
import threading
import time
import logging
from typing import Callable, TypeVar, Type, Awaitable, Any, Dict

from aspyx_service import ServiceManager

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

logging.getLogger("httpx").setLevel(logging.INFO)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({
    "aspyx.di": logging.INFO,
    "aspyx.di.aop": logging.INFO,
    "aspyx.service": logging.DEBUG
})


import pytest

from .common import service_manager, TestService, TestRestService, Pydantic, Data, \
   TestAsyncRestService, TestAsyncService, start_server

T = TypeVar("T")

# main

pydantic = Pydantic(i=1, f=1.0, b=True, s="s")
data = Data(i=1, f=1.0, b=True, s="s")

def run_loops(name: str, loops: int, type: Type[T], instance: T,  callable: Callable[[T], None]):
    start = time.perf_counter()
    for _ in range(loops):
        callable(instance)

    end = time.perf_counter()
    avg_ms = ((end - start) / loops) * 1000

    print(f"run {name}, loops={loops}: avg={avg_ms:.3f} ms")

async def run_async_loops(name: str, loops: int, type: Type[T], instance: T,  callable: Callable[[T], Awaitable[Any]]):
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

@pytest.mark.asyncio(scope="function")
class TestPerformance():
    async def test_local(self, service_manager):
        # get service manager

        manager = service_manager
        loops = 100

        # tests

        run_loops("rest", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"), lambda service: service.get("world"))
        run_loops("json", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-json"), lambda service: service.hello("world"))
        run_loops("msgpack", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-msgpack"), lambda service: service.hello("world"))

        # pydantic

        run_loops("rest & pydantic", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"), lambda service: service.post_pydantic("hello", pydantic))
        run_loops("json & pydantic", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-json"), lambda service: service.pydantic(pydantic))
        run_loops("msgpack & pydantic", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-msgpack"), lambda service: service.pydantic(pydantic))

        # data class

        run_loops("rest & data", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"),
                  lambda service: service.post_data("hello", data))
        run_loops("json & data", loops, TestService,
                  manager.get_service(TestService, preferred_channel="dispatch-json"),
                  lambda service: service.data(data))
        run_loops("msgpack & data", loops, TestService,
                  manager.get_service(TestService, preferred_channel="dispatch-msgpack"),
                  lambda service: service.data(data))

        # async

        await run_async_loops("async rest", loops, TestAsyncRestService, manager.get_service(TestAsyncRestService, preferred_channel="rest"),
                  lambda service: service.get("world"))
        await run_async_loops("async json", loops, TestAsyncService, manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
                  lambda service: service.hello("world"))
        await run_async_loops("async msgpack", loops, TestAsyncService, manager.get_service(TestAsyncService, preferred_channel="dispatch-msgpack"),
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

        # a real thread test

        # sync

        run_threaded_sync_loops("threaded sync json, 1 thread", loops, 1, TestService,
                                 manager.get_service(TestAsyncService, preferred_channel="dispatch-json"),
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
