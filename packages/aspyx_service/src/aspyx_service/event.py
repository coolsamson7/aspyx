"""
event management
"""
from __future__ import annotations
import json

from abc import ABC, abstractmethod
from dataclasses import is_dataclass, asdict
from typing import Type, TypeVar, Generic, Any, Optional

from pydantic import BaseModel

from aspyx.reflection import Decorators

from aspyx.di import Environment, inject_environment, Providers, ClassInstanceProvider

from aspyx_service.serialization import get_deserializer

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

            decorator = Decorators.get_decorator(type, event)

            self.name = type.__name__ # TODO

    class EventListenerDescriptor:
        def __init__(self, type: Type, event_type: Type):
            self.type : Type = type
            self.event = EventManager.EventDescriptor(event_type)

    class Envelope(ABC):
        @abstractmethod
        def get_body(self) -> str:
            pass

        @abstractmethod
        def set_body(self, body: str):
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
        def handle(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
            pass

    class Provider(EnvelopePipeline):
        # constructor

        def __init__(self):
            self.manager : Optional[EventManager] = None

        # abstract

        def start(self):
            pass

        @abstractmethod
        def create_envelope(self, headers = None) -> EventManager.Envelope:
            pass

        @abstractmethod
        def listen_to(self, listener: EventManager. EventListenerDescriptor) -> None:
            pass

    # class properties

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

        self.setup()

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

        # chain pipelines

        for type in self.pipelines:
            pipeline = environment.get(type)

            if isinstance(pipeline, AbstractEnvelopePipeline):
                pipeline.next = self.pipeline

            self.pipeline = pipeline

    # lifecycle

    # internal

    def get_event_descriptor(self, type: Type) -> EventManager.EventDescriptor:
        return self.events.get(type, None)

    def get_event_listener_descriptor(self, type: Type) -> EventManager.EventListenerDescriptor:
        return next((listener_descriptor for listener_descriptor in self.event_listeners.values() if listener_descriptor.event.type is type), None)
        #return self.event_listeners.get(type, None)

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
        descriptor = self.get_event_listener_descriptor(type)

        return self.environment.get(descriptor.type)

    def to_json(self, obj) -> str:
        if is_dataclass(obj):
            # dataclass: convert to dict first
            return json.dumps(asdict(obj))

        elif isinstance(obj, BaseModel):
            # pydantic model: use its json() method
            return obj.json()
        else:
            # fallback: try to serialize directly
            return json.dumps(obj)

    def dispatch_event(self, descriptor: EventManager.EventDescriptor, body: Any):
        event = get_deserializer(descriptor.type)(json.loads(body))

        self.get_listener(descriptor.type).on(event)

    # public

    def send_event(self, event: Any):
        descriptor = self.get_event_descriptor(type(event))

        envelope = self.provider.create_envelope({})

        envelope.set_body(self.to_json(event))

        self.pipeline.send(envelope, descriptor)

def event(broadcast=False):
    def decorator(cls):
        Decorators.add(cls, event, broadcast)

        EventManager.register_event(EventManager.EventDescriptor(cls))

        return cls

    return decorator

def event_listener(event: Type):
    def decorator(cls):
        Decorators.add(cls, event_listener, event)

        EventManager.register_event_listener(EventManager.EventListenerDescriptor(cls, event))
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

    def proceed_handle(self, envelope: EventManager.Envelope, descriptor: EventManager.EventDescriptor):
        self.next.handle(envelope, descriptor)