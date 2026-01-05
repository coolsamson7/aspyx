"""
test for events
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aspyx.exception import ExceptionManager, handle
from aspyx.util import Logger
from .provider import LocalProvider

Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.ERROR,
    "aspyx.event": logging.INFO,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR
})

logger = logging.getLogger("test")

logger.setLevel(logging.INFO)

from dataclasses import dataclass

import pytest

from aspyx_event import EventManager, event, envelope_pipeline, AbstractEnvelopePipeline, \
    event_listener, EventListener, EventModule, NSQProvider
#StompProvider, AMQPProvider

from aspyx.di import module, Environment, create


# test classes

@dataclass
@event(durable=False)
class HelloEvent:
    hello: str

@envelope_pipeline()
class SessionPipeline(AbstractEnvelopePipeline):
    # constructor

    def __init__(self):
        super().__init__()

    # implement

    async def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        envelope.set("session", "session")

        await self.proceed_send(envelope, event_descriptor)


sync_event_received  : Optional[asyncio.Event] = None
async_event_received : Optional[asyncio.Event] = None

#@event_listener(HelloEvent, per_process=True)
class SyncListener(EventListener[HelloEvent]):
    received = None
    foo = None

    # constructor

    def __init__(self):
        pass

    # implement

    def on(self, event: HelloEvent):
        SyncListener.received = event

        sync_event_received.set()

@event_listener(HelloEvent, per_process=True)
class AsyncListener(EventListener[HelloEvent]):
    received = None

    # constructor

    def __init__(self):
        pass

    # implement

    async def on(self, event: HelloEvent):
        AsyncListener.received = event

        async_event_received.set()

# test module

@module(imports=[EventModule])
class Module:
    # constructor

    def __init__(self):
        pass

    # handlers

    @handle()
    def handle_exception(self, exception: Exception):
        print(exception)

    # internal

    def create_exception_manager(self):
        exception_manager = ExceptionManager()

        exception_manager.collect_handlers(self)

        return exception_manager

    # @create()
    #def create_provider(self) -> EventManager:

    @create()
    def create_event_manager(self) -> EventManager:
        return EventManager(LocalProvider(), exception_manager=self.create_exception_manager())
        #return EventManager(NSQProvider(nsqd_address="127.0.0.1:4150", encoding="cbor"))
        # EventManager(StompProvider(host="localhost", port=61616, user="artemis", password="artemis"))
        # EventManager(AMQPProvider("server-id", host="localhost", port=5672, user="artemis", password="artemis"))

@pytest.mark.asyncio(scope="function")
class TestLocalService:
    async def test_events(self):
        environment = Environment(Module)

        global sync_event_received, async_event_received

        await environment.get(EventManager).setup()

        sync_event_received  = asyncio.Event()
        async_event_received = asyncio.Event()

        event_manager = environment.get(EventManager)

        await asyncio.sleep(0.5)

        event = HelloEvent("world")

        await event_manager.send_event(event)

        await asyncio.sleep(0.5)

        #await asyncio.wait_for(sync_event_received.wait(), timeout=10000)
        await asyncio.wait_for(async_event_received.wait(), timeout=10000)

        #assert event == SyncListener.received, "events not =="
        assert event == AsyncListener.received, "events not =="
