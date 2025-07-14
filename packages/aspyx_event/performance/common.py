"""
test for health checks
"""
from __future__ import annotations

import asyncio
import logging

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


@event_listener(HelloEvent, per_process=True)
class SyncListener(EventListener[HelloEvent]):
    received = None

    # constructor

    def __init__(self):
        pass

    # implement

    def on(self, event: HelloEvent):
        print(".")

@event_listener(HelloEvent, per_process=True)
class AsyncListener(EventListener[HelloEvent]):
    received = None

    # constructor

    def __init__(self):
        pass

    # implement

    async def on(self, event: HelloEvent):
        print(".")

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