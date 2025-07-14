"""
event management
"""
from __future__ import annotations

import asyncio
import json
import logging

from abc import ABC, abstractmethod
from typing import Type, TypeVar, Generic, Any, Optional

from aspyx.exception import ExceptionManager
from aspyx.reflection import Decorators

from aspyx.di import Environment, inject_environment, Providers, ClassInstanceProvider, on_destroy

from aspyx_service.serialization import get_deserializer, get_serializer

class EventException(Exception):
    pass

T = TypeVar("T")

class EventListener(Generic[T]):
    """
    An `EventListener` listens to a single event.
    """
    def on(self, event: T) -> None:
        """
        Callback when an event occurs.

        Args:
            event: the event
        """
        pass

class EventManager:
    """
    Central class that manages sending and receiving/dispatching events.
    """
    # local classes

    class EventDescriptor:
        """
        Covers the meta-data of an event.
        """
        def __init__(self, type: Type):
            self.type = type

            args = Decorators.get_decorator(type, event).args

            self.name = args[0]
            if self.name == "":
                self.name = type.__name__

            self.broadcast : bool = args[1]
            self.durable : bool   = args[2]

    class EventListenerDescriptor:
        """
       Covers the meta-data of an event listener.
       """
        def __init__(self, type: Type, event_type: Type, name: str, group: str, per_process: bool):
            if name == "":
                name = type.__name__

            self.type : Type = type
            self.name = name
            self.event = EventManager.EventDescriptor(event_type)

            self.group = group
            self.per_process = per_process

    class Envelope(ABC):
        """
        Wrapper around an event while being received or sent.
        """
        @abstractmethod
        def get_body(self) -> str:
            """
            return the body as a str

            Returns:
                str: the body
            """
            pass

        @abstractmethod
        def set(self, key: str, value: str) -> None:
            """
            set a header value

            Args:
                key: a key
                value: the value
            """

        @abstractmethod
        def get(self, key: str) -> str:
            """
            retrieve a header value

            Args:
                key: a key

            Returns:
                str: the value
           """

    class EnvelopePipeline(ABC):
        """
        An interceptor for sending and receiving events
        """
        @abstractmethod
        def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
            """
            interceptor on the sending side
            Args:
                envelope: the envelope
                event_descriptor: the event descriptor
            """

        @abstractmethod
        def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
            """
            interceptor on the handling side
            Args:
                envelope: the envelope
                event_listener_descriptor: the listener descriptor
            """

    class Provider(EnvelopePipeline):
        """
        The bridge to a low-level queuing library.
        """
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
    event_listeners: list[EventManager.EventListenerDescriptor] = []

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
        cls.event_listeners.append(descriptor)

    # constructor

    def __init__(self, provider: EventManager.Provider, exception_manager: Optional[ExceptionManager] = None):
        """
        create a new `EventManager`

        Args:
            provider: an `EventManager.Provider`
        """
        self.environment : Optional[Environment] = None
        self.provider = provider
        self.pipeline = self.provider
        self.exception_manager = exception_manager

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
        descriptor =  self.events.get(type, None)

        if descriptor is None:
            raise EventException(f"{type.__name__} is not an event")

        return descriptor

    def listen_to(self, listener: EventManager.EventListenerDescriptor):
        self.provider.listen_to(listener)

    def setup(self):
        # start

        self.provider.start()

        # listeners

        for listener in self.event_listeners:
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

        try:
            listener.on(event)
        except Exception as e:
            if self.exception_manager is not None:
                raise self.exception_manager.handle(e)

            self.logger.error(f"caught an exception: {e} while dispatching event {descriptor.event.name}")
            raise e

        #async def call_handler(listener, event):
        #    if inspect.iscoroutinefunction(listener.on):
        #        await listener.on(event)
        #    else:
        #        listener.on(event)

        # schedule handler in main loop

        #self.loop.call_soon(asyncio.create_task, call_handler(listener, event))
        #asyncio.create_task(call_handler(listener, event))

    # public

    def send_event(self, event: Any) -> None:
        """
        send an event.

        Args:
            event: the event
        """
        descriptor = self.get_event_descriptor(type(event))

        envelope = self.provider.create_envelope(body=self.to_json(event), headers={})

        self.pipeline.send(envelope, descriptor)

def event(name="", broadcast=False, durable=False):
    """
    decorates event classes

    Args:
        name: the event name
        durable: if `True`, the corresponding queue is persistent

    Returns:

    """
    def decorator(cls):
        Decorators.add(cls, event, name, broadcast, durable)

        EventManager.register_event(EventManager.EventDescriptor(cls))

        return cls

    return decorator

def event_listener(event: Type, name="", group="", per_process = False):
    """
    decorates event listeners.

    Args:
        event: the event type
        name: the listener name
        per_process: if `True`, listeners will process events on different processes

    Returns:

    """
    def decorator(cls):
        Decorators.add(cls, event_listener, event, name, group, per_process)

        EventManager.register_event_listener(EventManager.EventListenerDescriptor(cls, event, name, group, per_process))
        Providers.register(ClassInstanceProvider(cls, False))

        return cls

    return decorator

def envelope_pipeline():
    """
    decorates an envelope pipeline
    """
    def decorator(cls):
        Decorators.add(cls, envelope_pipeline)

        EventManager.register_envelope_pipeline(cls)
        Providers.register(ClassInstanceProvider(cls, True, "singleton"))

        return cls

    return decorator

class AbstractEnvelopePipeline(EventManager.EnvelopePipeline):
    """
    abstract base-class for envelope pipelines
    """
    # constructor

    def __init__(self, envelope_handler: Optional[EventManager.EnvelopePipeline] = None):
        self.next = envelope_handler

    # public

    def proceed_send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        self.next.send(envelope, event_descriptor)

    def proceed_handle(self, envelope: EventManager.Envelope, descriptor: EventManager.EventListenerDescriptor):
        self.next.handle(envelope, descriptor)