"""
test for health checks
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from aspyx.util import Logger

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
    event_listener, EventListener, StompProvider, AMQPProvider

from aspyx.di import module, Environment, create, inject_environment


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


event_received = threading.Event()

@event_listener(HelloEvent, per_process=True)
class HelloEventListener(EventListener[HelloEvent]):
    # constructor

    def __init__(self):
        pass

    # implement

    def on(self, event: HelloEvent):
        #print("### hello " + event.hello, flush=True)
        logger.info("listen to hello " + event.hello)
        event_received.set()


@event_listener(HelloEvent, per_process=True)
class OtherHelloEventListener(EventListener[HelloEvent]):
    # constructor

    def __init__(self):
        pass

    # implement

    def on(self, event: HelloEvent):
        #print("### other hello " + event.hello)
        logger.info("other listen to hello " + event.hello)
        #event_received.set()

class TestProvider(EventManager.Provider):
    # local classes

    class TestEnvelope(EventManager.Envelope):
        # constructor

        def __init__(self, body="", headers=None):
            self.body = body
            self.headers = headers or {}

        # implement envelope

        def get_body(self) -> str:
            return self.body

        def set(self, key: str, value: str):
            self.headers[key] = value

        def get(self, key: str) -> str:
            return self.headers.get(key,"")

    # constructor

    def __init__(self):
        super().__init__()

        self.environment : Optional[Environment] = None
        self.listeners : list[EventManager.EventListenerDescriptor] = []

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # implement Provider

    def create_envelope(self, body="", headers = None) -> EventManager.Envelope:
        return TestProvider.TestEnvelope(body=body, headers=headers)

    def listen_to(self, listener: EventManager.EventListenerDescriptor) -> None:
        self.listeners.append(listener)

    # implement EnvelopePipeline

    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        #self.handle(envelope, event_descriptor)
        self.manager.pipeline.handle(envelope, event_descriptor)

    def handle(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        for listener in self.listeners:
            if listener.event is event_descriptor:
                self.manager.dispatch_event(listener, envelope.get_body())

# test module

@module(imports=[])
class Module:
    def __init__(self):
        pass

    @create()
    def create_event_manager(self) -> EventManager:
        return EventManager(TestProvider())
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

        event_manager.send_event(HelloEvent("world1"))

        while False:
            #print(">", flush=True)
            logger.info(".")
            event_manager.send_event(HelloEvent("WORLD"))
            #print(".", flush=True)
            #sleep(1)

        assert event_received.wait(timeout=100), "ouch"
