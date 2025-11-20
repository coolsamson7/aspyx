"""
test for events
"""
from __future__ import annotations

import logging
import threading
import time

from aspyx.exception import ExceptionManager, handle_exception
from aspyx.util import Logger
from packages.aspyx_job.src.aspyx_job import JobModule, scheduled, interval, cron
from packages.aspyx_job.src.aspyx_job.job import Scheduler

Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.ERROR,
    "aspyx.event": logging.INFO,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR
})

logger = logging.getLogger("test")

logger.setLevel(logging.INFO)

import pytest

from aspyx.di import module, Environment, create, injectable


# test classes

event = threading.Event()

@injectable()
class Jobs:
    @scheduled(trigger=interval(minutes=1))
    def call_job(self):
        event.set()
        print("-")

    @scheduled(trigger=cron(second="0-59"), group="group", max=1)
    def call_job(self):
        event.set()
        print(".")

    @scheduled(trigger=cron(second="0-59"), group="group", max=1)
    def call_job1(self):
        event.set()
        print(".")

# test module

@module(imports=[JobModule])
class Module:
    # constructor

    def __init__(self):
        pass

    # create

    @create()
    def create_scheduler(self) -> Scheduler:
        return Scheduler(self.create_exception_manager())

    # handlers

    @handle_exception()
    def handle_exception(self, exception: Exception):
        print(exception)

    # internal

    def create_exception_manager(self):
        exception_manager = ExceptionManager()

        exception_manager.collect_handlers(self)

        return exception_manager

@pytest.fixture(scope="session")
def environment():
    environment = Environment(Module)  # start server

    yield environment

    environment.destroy()

@pytest.mark.asyncio(scope="function")
class TestJob:
    async def test_events(self, environment):
        event.wait()

        print("sleep")
