"""
event management
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging

from abc import ABC, abstractmethod
from typing import Type, TypeVar, Generic, Any, Optional

from aspyx.reflection import Decorators

from aspyx.di import Environment, inject_environment, Providers, ClassInstanceProvider, on_destroy

from aspyx_service.serialization import get_deserializer, get_serializer

# abstraction

T = TypeVar("T")

class EventListener(Generic[T]):
    def on(self, event: T):
        pass

class EventManager:
    # local classes

    class EventDescriptor:
        def __init__(self, type: Type):
            self.type = type

            args = Decorators.get_decorator(type, event).args

            self.name = args[0]
            if self.name == "":
                self.name = type.__name__

            self.broadcast : bool = args[1]
            self.durable : bool   = args[2]

    class EventListenerDescriptor:
        def __init__(self, type: Type, event_type: Type, name: str, group: str, per_process: bool):
            if name == "":
                name = type.__name__

            self.type : Type = type
            self.name = name
            self.event = EventManager.EventDescriptor(event_type)

            self.group = group
            self.per_process = per_process

    class Envelope(ABC):
        @abstractmethod
        def get_body(self) -> str:
            pass

        @abstractmethod
        def set(self, key: str, value: str):
            pass

        @abstractmethod
        def get(self, key: str) -> str:
            pass

    class EnvelopePipeline(ABC):
        @abstractmethod
        def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
            pass

        @abstractmethod
        def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
            pass

    class Provider(EnvelopePipeline):
        # constructor

        def __init__(self):
            self.manager : Optional[EventManager] = None

        # abstract

        def start(self):
            pass

        def stop(self):
            pass

        @abstractmethod
        def create_envelope(self, body="", headers = None) -> EventManager.Envelope:
            pass

        @abstractmethod
        def listen_to(self, listener: EventManager. EventListenerDescriptor) -> None:
            pass

    # class properties

    logger = logging.getLogger("aspyx.event")  # __name__ = module name

    pipelines: list[Type] = []

    events: dict[Type, EventDescriptor] = {}
    event_listeners: dict[Type, EventManager.EventListenerDescriptor] = {}

    events_by_name: dict[str, EventDescriptor] = {}

    # class methods

    @classmethod
    def register_envelope_pipeline(cls, handler: Type):
        cls.pipelines.append(handler)

    @classmethod
    def register_event(cls, descriptor: EventManager.EventDescriptor):
        cls.events[descriptor.type] = descriptor

        cls.events_by_name[descriptor.name] = descriptor

    @classmethod
    def register_event_listener(cls, descriptor: EventManager.EventListenerDescriptor):
        cls.event_listeners[descriptor.type] = descriptor

    # constructor

    def __init__(self, provider: EventManager.Provider):
        self.environment : Optional[Environment] = None
        self.provider = provider
        self.pipeline = self.provider

        provider.manager = self

        self.loop = asyncio.get_event_loop()

        self.setup()

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

        # create & chain pipelines

        for type in self.pipelines:
            pipeline = environment.get(type)

            if isinstance(pipeline, AbstractEnvelopePipeline):
                pipeline.next = self.pipeline

            self.pipeline = pipeline

    # lifecycle

    @on_destroy()
    def on_destroy(self):
        self.provider.stop()

    # internal

    def get_event_descriptor(self, type: Type) -> EventManager.EventDescriptor:
        return self.events.get(type, None)

    def listen_to(self, listener: EventManager.EventListenerDescriptor):
        self.provider.listen_to(listener)

    def setup(self):
        # start

        self.provider.start()

        # listeners

        for listener in self.event_listeners.values():
            # replace initial object

            listener.event = self.get_event_descriptor(listener.event.type)

            # install listener

            self.listen_to(listener)


    def get_listener(self, type: Type) -> Optional[EventListener]:
        return self.environment.get(type)

    def to_json(self, obj) -> str:
        dict = get_serializer(type(obj))(obj)

        return json.dumps(dict)

    def dispatch_event(self, descriptor: EventManager.EventListenerDescriptor, body: Any):
        event = get_deserializer(descriptor.event.type)(json.loads(body))

        listener = self.get_listener(descriptor.type)

        listener.on(event)

        #async def call_handler(listener, event):
        #    if inspect.iscoroutinefunction(listener.on):
        #        await listener.on(event)
        #    else:
        #        listener.on(event)

        # schedule handler in main loop

        #self.loop.call_soon(asyncio.create_task, call_handler(listener, event))
        #asyncio.create_task(call_handler(listener, event))

    # public

    def send_event(self, event: Any):
        descriptor = self.get_event_descriptor(type(event))

        envelope = self.provider.create_envelope(body=self.to_json(event), headers={})

        self.pipeline.send(envelope, descriptor)

def event(name="", broadcast=False, durable=False):
    def decorator(cls):
        Decorators.add(cls, event, name, broadcast, durable)

        EventManager.register_event(EventManager.EventDescriptor(cls))

        return cls

    return decorator

def event_listener(event: Type, name="", group="", per_process = False):
    def decorator(cls):
        Decorators.add(cls, event_listener, event, name, group, per_process)

        EventManager.register_event_listener(EventManager.EventListenerDescriptor(cls, event, name, group, per_process))
        Providers.register(ClassInstanceProvider(cls, False, "singleton"))

        return cls

    return decorator

def envelope_pipeline():
    def decorator(cls):
        Decorators.add(cls, envelope_pipeline)

        EventManager.register_envelope_pipeline(cls)
        Providers.register(ClassInstanceProvider(cls, True, "singleton"))

        return cls

    return decorator

class AbstractEnvelopePipeline(EventManager.EnvelopePipeline):
    # constructor

    def __init__(self, envelope_handler: Optional[EventManager.EnvelopePipeline] = None):
        self.next = envelope_handler

    # public

    def proceed_send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        self.next.send(envelope, event_descriptor)

    def proceed_handle(self, envelope: EventManager.Envelope, descriptor: EventManager.EventListenerDescriptor):
        self.next.handle(envelope, descriptor)