import logging
from aspyx.util import Logger

Logger.configure(default_level=logging.NOTSET, levels={
    "aspyx.di": logging.ERROR,
    "aspyx.event": logging.INFO,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR
})

from aspyx_event import EventManager, AMQPProvider

#from packages.aspyx_event.performance.common import Module, HelloEvent

###

"""
test for health checks
"""

import asyncio
import logging

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

    def on(self, event: HelloEvent):
        print(".")

# test module

@module(imports=[EventModule])
class Module:
    def __init__(self):
        pass

    @create()
    def create_event_manager(self) -> EventManager:
        #return EventManager(LocalProvider())
        #return EventManager(StompProvider(host="localhost", port=61616, user="artemis", password="artemis"))
        return EventManager(AMQPProvider("server-id", host="localhost", port=5672, user="artemis", password="artemis"))

###

#from .common import Module, HelloEvent




async def main():
    environment = Environment(Module)
    event_manager = environment.get(EventManager)

    event = HelloEvent("world")

    event_manager.send_event(event)

    while True:
        event_manager.send_event(event)
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(main())