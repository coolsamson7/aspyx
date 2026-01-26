"""
event management
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid

from abc import ABC, abstractmethod
from typing import Type, TypeVar, Generic, Any, Optional, Coroutine, Dict, Callable, List

from aspyx.exception import ExceptionManager
from aspyx.reflection import Decorators

from aspyx.di import Environment, inject_environment, Providers, ClassInstanceProvider, on_destroy, on_running

from aspyx.util import get_deserializer, get_serializer

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

class EventManager:
    """
    Central class that manages sending and receiving/dispatching events.
    """
    # local classes

    class EventSubscription:
        """
        Unified descriptor for all event subscriptions (both decorator-based and runtime).
        """
        def __init__(
            self,
            subscription_id: str,
            event_descriptor: 'EventManager.EventDescriptor',
            callback: Callable,
            name: str = "",
            group: str = "",
            per_process: bool = False,
            metadata: Optional[Dict[str, Any]] = None
        ):
            self.subscription_id = subscription_id
            self.event_descriptor = event_descriptor
            self.callback = callback
            self.name = name if name else f"subscription_{subscription_id[:8]}"
            self.group = group
            self.per_process = per_process
            self.metadata = metadata or {}

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

    T = TypeVar("T")

    class Envelope(Generic[T], ABC):
        """
        Wrapper around an event while being received or sent.
        """

        # constructor

        def __init__(self, event: Optional[Any] = None):
            self.event = event

        # encoding

        @abstractmethod
        def encode(self) -> T:
            ...

        @abstractmethod
        def decode(self, message) -> Any:
            ...

        # convenience methods

        def to_json(self, obj) -> str:
            dict = get_serializer(type(obj))(obj)

            return json.dumps(dict)

        def from_json(self, json_str: str, type: Type) -> str:
            return get_deserializer(type)(json.loads(json_str))

        # header methods

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

    class AbstractEnvelope(Envelope):
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

    class EnvelopeFactory(ABC):
        @abstractmethod
        def for_send(self, provider: EventManager.Provider, event: Any) -> EventManager.Envelope:
            pass

        @abstractmethod
        def for_receive(self,  provider: EventManager.Provider, message: Any, descriptor: EventManager.EventDescriptor) -> EventManager.Envelope:
            pass

    class EnvelopePipeline(ABC):
        """
        An interceptor for sending and receiving events
        """
        @abstractmethod
        async def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
            """
            interceptor on the sending side
            Args:
                envelope: the envelope
                event_descriptor: the event descriptor
            """

    class Provider(EnvelopePipeline):
        """
        The bridge to a low-level queuing library.
        """

        # slots

        __slots__ = [
            "manager",
            "envelope_factory"
        ]

        # constructor

        def __init__(self, envelope_factory: EventManager.EnvelopeFactory):
            self.manager : Optional[EventManager] = None
            self.envelope_factory = envelope_factory

        # abstract

        async def start(self):
            pass

        async def stop(self):
            pass

        def create_sender_envelope(self, event: Any) -> EventManager.Envelope:
            return self.envelope_factory.for_send(self, event)

        def create_receiver_envelope(self, message: Any, descriptor: EventManager.EventDescriptor) -> EventManager.Envelope:
            return self.envelope_factory.for_receive(self, message, descriptor=descriptor)

        @abstractmethod
        def listen_to_subscription(self, subscription: EventManager.EventSubscription) -> None:
            """
            Setup underlying queue/topic subscription for a given EventSubscription.
            This is called by EventManager.subscribe() and should set up the provider-specific
            infrastructure (e.g., NSQ reader, AMQP consumer, etc.)
            """
            pass

    # class properties

    logger = logging.getLogger("aspyx.event")  # __name__ = module name

    pipelines: list[Type] = []

    events: dict[Type, EventDescriptor] = {}

    # Store decorator info as tuples: (listener_class, event_type, name, group, per_process)
    event_listener_decorators: list[tuple[Type, Type, str, str, bool]] = []

    events_by_name: dict[str, EventDescriptor] = {}

    # Instance properties for subscriptions
    subscriptions: Dict[str, EventSubscription]  # subscription_id -> EventSubscription
    subscriptions_by_event: Dict[str, List[EventSubscription]]  # event_name -> [subscriptions]

    # class methods

    @classmethod
    def register_envelope_pipeline(cls, handler: Type):
        cls.pipelines.append(handler)

    @classmethod
    def register_event(cls, descriptor: EventManager.EventDescriptor):
        cls.events[descriptor.type] = descriptor

        cls.events_by_name[descriptor.name] = descriptor

    @classmethod
    def register_event_listener_decorator(cls, listener_class: Type, event_type: Type, name: str, group: str, per_process: bool):
        """Register decorator-based listener info for later conversion to EventSubscription"""
        cls.event_listener_decorators.append((listener_class, event_type, name, group, per_process))

    _loop = None

    @property
    def loop(self):
        if self._loop is not None:
            return self._loop

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # fallback to default event loop policy
            self._loop = asyncio.get_event_loop()

        return self._loop

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

        # Initialize subscription tracking
        self.subscriptions: Dict[str, EventManager.EventSubscription] = {}
        self.subscriptions_by_event: Dict[str, List[EventManager.EventSubscription]] = {}

        provider.manager = self

        #self.setup()

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
    async def on_destroy(self):
        await self.provider.stop()

    async def _start_provider(self):
        """Start the provider during setup"""
        await self.provider.start()

    # internal

    def get_event_descriptor(self, type: Type) -> EventManager.EventDescriptor:
        descriptor =  self.events.get(type, None)

        if descriptor is None:
            raise EventException(f"{type.__name__} is not an event")

        return descriptor

    def get_event_descriptor_by_name(self, event_name: str) -> EventManager.EventDescriptor:
        descriptor = self.events_by_name.get(event_name, None)

        if descriptor is None:
            raise EventException(f"No event found with name '{event_name}'")

        return descriptor

    async def subscribe(
        self,
        event_type: Type | str,
        callback: Callable,
        name: str = "",
        group: str = "",
        per_process: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Unified subscription API for both decorator-based and runtime subscriptions.

        Args:
            event_type: Event class Type or event name string
            callback: Callable (sync or async) to handle the event
            name: Subscription name
            group: Subscription group
            per_process: If True, only one listener per process handles the event
            metadata: Optional metadata dictionary
            is_static: True if this is a decorator-based subscription

        Returns:
            str: subscription_id for later unsubscribe
        """
        # Resolve event descriptor
        if isinstance(event_type, str):
            event_descriptor = self.get_event_descriptor_by_name(event_type)
        else:
            event_descriptor = self.get_event_descriptor(event_type)

        # Generate unique subscription ID
        subscription_id = str(uuid.uuid4())

        # Create subscription
        subscription = EventManager.EventSubscription(
            subscription_id=subscription_id,
            event_descriptor=event_descriptor,
            callback=callback,
            name=name,
            group=group,
            per_process=per_process,
            metadata=metadata
        )

        # Store subscription
        self.subscriptions[subscription_id] = subscription

        # Index by event name
        event_name = event_descriptor.name
        if event_name not in self.subscriptions_by_event:
            self.subscriptions_by_event[event_name] = []
        self.subscriptions_by_event[event_name].append(subscription)

        # Notify provider to setup underlying queue/topic subscription
        self.provider.listen_to_subscription(subscription)

        self.logger.info(f"Subscribed to event '{event_name}' with subscription_id={subscription_id}, name={subscription.name}")

        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription by ID.

        Args:
            subscription_id: The subscription ID returned from subscribe()

        Returns:
            bool: True if subscription was found and removed, False otherwise
        """
        subscription = self.subscriptions.get(subscription_id)

        if subscription is None:
            self.logger.warning(f"Attempted to unsubscribe non-existent subscription: {subscription_id}")
            return False

        # Remove from event index
        event_name = subscription.event_descriptor.name
        if event_name in self.subscriptions_by_event:
            self.subscriptions_by_event[event_name] = [
                s for s in self.subscriptions_by_event[event_name]
                if s.subscription_id != subscription_id
            ]

        # Remove from main registry
        del self.subscriptions[subscription_id]

        self.logger.info(f"Unsubscribed subscription_id={subscription_id}, name={subscription.name}")

        return True

    def list_subscriptions(self, event_name: Optional[str] = None) -> List[EventManager.EventSubscription]:
        """
        List active subscriptions, optionally filtered by event name.

        Args:
            event_name: Optional event name to filter subscriptions

        Returns:
            List of EventSubscription objects
        """
        if event_name:
            return self.subscriptions_by_event.get(event_name, [])
        else:
            return list(self.subscriptions.values())

    @on_running()
    async def setup(self):
        """
        Setup the EventManager:
        1. Start the provider (connect to message broker)
        2. Convert decorator-based listeners to subscriptions

        This is called automatically via @on_running() lifecycle hook.
        """
        # Start the provider
        await self._start_provider()

        # Convert decorator-based listeners to unified subscriptions

        for listener_class, event_type, name, group, per_process in self.event_listener_decorators:
            # Get the listener instance from DI
            listener_instance = self.environment.get(listener_class)

            if listener_instance is None:
                self.logger.error(f"Could not get listener instance for {listener_class.__name__}")
                continue

            # Resolve name
            listener_name = name if name else listener_class.__name__

            # Create wrapper callback that delegates to listener.on()
            async def create_callback(listener_inst, cls_name):
                async def callback_wrapper(event):
                    try:
                        if inspect.iscoroutinefunction(listener_inst.on):
                            await listener_inst.on(event)
                        else:
                            listener_inst.on(event)
                    except Exception as e:
                        if self.exception_manager is not None:
                            self.exception_manager.handle(e)
                        else:
                            self.logger.error(
                                f"Exception in listener {cls_name}: {e}",
                                exc_info=True
                            )
                            raise e

                return callback_wrapper

            callback = await create_callback(listener_instance, listener_name)

            # Use unified subscribe API
            await self.subscribe(
                event_type=event_type,
                callback=callback,
                name=listener_name,
                group=group,
                per_process=per_process,
                metadata={"is_static": True, "listener_class": listener_class.__name__}
            )

    def get_listener(self, type: Type) -> Optional[EventListener]:
        return self.environment.get(type)

    def to_json(self, obj) -> str:
        dict = get_serializer(type(obj))(obj)

        return json.dumps(dict)

    def dispatch_event(self, event_name: str, event: Any):
        """
        Dispatch an event to all subscriptions for that event.

        Args:
            event_name: The name of the event
            event: The event object
        """
        subscriptions = self.subscriptions_by_event.get(event_name, [])

        if not subscriptions:
            self.logger.warning(f"No subscriptions found for event '{event_name}'")
            return

        def safe_schedule(coro: Coroutine):
            try:
                loop = self.loop
                running_loop = asyncio.get_running_loop()
                if running_loop == loop:
                    asyncio.create_task(coro)
                else:
                    loop.call_soon_threadsafe(asyncio.create_task, coro)
            except RuntimeError:
                asyncio.run(coro)

        async def call_handler(subscription: EventManager.EventSubscription, event: Any):
            try:
                if inspect.iscoroutinefunction(subscription.callback):
                    await subscription.callback(event)
                else:
                    subscription.callback(event)
            except Exception as e:
                if self.exception_manager is not None:
                    try:
                        self.exception_manager.handle(e)
                    except Exception as handled_exception:
                        self.logger.error(
                            f"Exception in subscription '{subscription.name}' for event '{event_name}': {handled_exception}",
                            exc_info=True
                        )
                        raise handled_exception
                else:
                    self.logger.error(
                        f"Exception in subscription '{subscription.name}' for event '{event_name}': {e}",
                        exc_info=True
                    )
                    raise e

        # Dispatch to all subscriptions
        for subscription in subscriptions:
            safe_schedule(call_handler(subscription, event))

    # public

    async def send_event(self, event: Any) -> None:
        """
        send an event.

        Args:
            event: the event
        """
        descriptor = self.get_event_descriptor(type(event))

        envelope = self.provider.create_sender_envelope(event)

        await self.pipeline.send(envelope, descriptor)

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

        EventManager.register_event_listener_decorator(cls, event, name, group, per_process)
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

    async def proceed_send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        await self.next.send(envelope, event_descriptor)
