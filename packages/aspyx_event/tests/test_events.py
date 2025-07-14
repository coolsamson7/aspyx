"""
test for events
"""
from __future__ import annotations

import logging
import threading

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
    event_listener, EventListener, EventModule
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

    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        envelope.set("session", "session")

        self.proceed_send(envelope, event_descriptor)

    def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
        session = envelope.get("session")

        self.proceed_handle(envelope, event_listener_descriptor)


sync_event_received = threading.Event()
async_event_received = threading.Event()

@event_listener(HelloEvent, per_process=True)
class SyncListener(EventListener[HelloEvent]):
    received = None

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

    def on(self, event: HelloEvent):
        AsyncListener.received = event

        async_event_received.set()

# test module

@module(imports=[EventModule])
class Module:
    def __init__(self):
        pass

    @create()
    def create_event_manager(self) -> EventManager:
        return EventManager(LocalProvider())
        # EventManager(StompProvider(host="localhost", port=61616, user="artemis", password="artemis"))
        # EventManager(AMQPProvider("server-id", host="localhost", port=5672, user="artemis", password="artemis"))

@pytest.fixture(scope="session")
def environment():
    environment = Environment(Module)  # start server

    yield environment

    environment.destroy()

class TestLocalService():
    def test_events(self, environment):
        event_manager = environment.get(EventManager)

        event = HelloEvent("world")

        event_manager.send_event(event)

        assert sync_event_received.wait(timeout=1), "sync event not received"
        assert async_event_received.wait(timeout=1), "async event not received"

        assert event == SyncListener.received, "events not =="
        assert event == AsyncListener.received, "events not =="
