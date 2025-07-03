"""
Tests
"""
import asyncio
import logging
import threading
import time

from typing import Callable, TypeVar, Type

from packages.aspyx_service.tests.common import service_manager, TestService, TestRestService, Pydantic, Data
from packages.aspyx_service.tests.test_async_service import data

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

async def main():
    # get service manager

    manager = service_manager()

    # tests

    loops = 10000

    run_loops("rest", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"), lambda service: service.get("world"))
    run_loops("json", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-json"), lambda service: service.hello("world"))
    run_loops("msgpack", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-msgpack"), lambda service: service.hello("world"))

    # pydantic

    run_loops("rest & pydantic", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"), lambda service: service.post_pydantic("hello", pydantic))
    run_loops("json & pydantic", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-json"), lambda service: service.pydantic(pydantic))
    run_loops("msgpack & pydantic", loops, TestService, manager.get_service(TestService, preferred_channel="dispatch-msgpack"), lambda service: service.pydantic(pydantic))

    # data class

    # pydantic

    run_loops("rest & data", loops, TestRestService, manager.get_service(TestRestService, preferred_channel="rest"),
              lambda service: service.post_data("hello", data))
    run_loops("json & data", loops, TestService,
              manager.get_service(TestService, preferred_channel="dispatch-json"),
              lambda service: service.data(data))
    run_loops("msgpack & data", loops, TestService,
              manager.get_service(TestService, preferred_channel="dispatch-msgpack"),
              lambda service: service.data(data))


if __name__ == "__main__":
    asyncio.run(main())

