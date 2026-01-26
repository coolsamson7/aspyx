"""
test for events
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aspyx.exception import ExceptionManager, handle
from aspyx.util import Logger
#from .provider import LocalProvider

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

from aspyx.di import module, Environment, create, on_running, injectable, inject


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
api_event_received   : Optional[asyncio.Event] = None
multi_subscriber_1_received : Optional[asyncio.Event] = None
multi_subscriber_2_received : Optional[asyncio.Event] = None
multi_subscriber_3_received : Optional[asyncio.Event] = None

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

# API-based subscription component
# This demonstrates subscribing to events using the subscribe() API
# instead of @event_listener decorator
@injectable()
class ApiEventSubscriber:
    """
    Component that subscribes to events using the EventManager.subscribe() API
    """
    def __init__(self):
        self.event_manager: Optional[EventManager] = None
        self.subscription_id: Optional[str] = None
        self.received_event: Optional[HelloEvent] = None

    # Inject the EventManager
    @inject()
    def set_event_manager(self, event_manager: EventManager):
        self.event_manager = event_manager

    # Subscribe in the on_running callback (async)
    @on_running()
    async def setup_subscriptions(self):
        """
        This is where you should call EventManager.subscribe()
        - Runs after EventManager.setup() is complete
        - Can be async (as shown here)
        - Returns subscription_id for later unsubscribe
        """
        logger.info("Setting up API-based event subscriptions...")

        # Subscribe to HelloEvent using the API
        self.subscription_id = await self.event_manager.subscribe(
            event_type=HelloEvent,  # Can also use string: "HelloEvent"
            callback=self.handle_hello_event,
            name="api-hello-listener",
            group="api-group",
            per_process=False,
            metadata={"source": "api", "version": "1.0"}
        )

        logger.info(f"Subscribed with ID: {self.subscription_id}")

    # Event handler (async)
    async def handle_hello_event(self, event: HelloEvent):
        """
        This callback is invoked when a HelloEvent is received
        """
        logger.info(f"API subscriber received: {event}")
        self.received_event = event
        api_event_received.set()

    # Optional: cleanup on destroy
    async def cleanup(self):
        if self.event_manager and self.subscription_id:
            await self.event_manager.unsubscribe(self.subscription_id)

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

        # Start environment to execute @on_running callbacks (including EventManager.setup())
        await environment.start()

        event_manager = environment.get(EventManager)

        sync_event_received  = asyncio.Event()
        async_event_received = asyncio.Event()

        await asyncio.sleep(0.5)

        event = HelloEvent("world")

        await event_manager.send_event(event)

        await asyncio.sleep(0.5)

        #await asyncio.wait_for(sync_event_received.wait(), timeout=10000)
        await asyncio.wait_for(async_event_received.wait(), timeout=10000)

        #assert event == SyncListener.received, "events not =="
        assert event == AsyncListener.received, "events not =="

        # Cleanup using Environment.stop()
        await environment.stop()

    async def test_api_based_subscription(self):
        """
        Test API-based event subscription using EventManager.subscribe()
        This demonstrates how to subscribe to events programmatically
        instead of using the @event_listener decorator
        """
        environment = Environment(Module)

        global api_event_received

        # Start the environment to execute @on_running callbacks (including EventManager.setup())
        await environment.start()

        event_manager = environment.get(EventManager)
        api_event_received = asyncio.Event()

        # Get the API subscriber
        api_subscriber = environment.get(ApiEventSubscriber)

        # Give @on_running callbacks time to complete
        await asyncio.sleep(0.2)

        # Verify subscription was created
        assert api_subscriber.subscription_id is not None, "Subscription ID should be set"

        # List subscriptions to verify
        subscriptions = event_manager.list_subscriptions(event_name="HelloEvent")
        logger.info(f"Active subscriptions for HelloEvent: {len(subscriptions)}")

        # Find our API subscription
        api_subscription = next(
            (s for s in subscriptions if s.name == "api-hello-listener"),
            None
        )
        assert api_subscription is not None, "API subscription should exist"
        assert api_subscription.group == "api-group"
        assert api_subscription.metadata["source"] == "api"

        await asyncio.sleep(0.5)

        # Send event
        event = HelloEvent("API test world")
        await event_manager.send_event(event)

        await asyncio.sleep(0.5)

        # Wait for the event to be received
        await asyncio.wait_for(api_event_received.wait(), timeout=10.0)

        # Verify the event was received
        assert api_subscriber.received_event == event, "API subscriber should receive the event"
        logger.info(f"✓ API subscriber successfully received event: {api_subscriber.received_event}")

        # Test unsubscribe
        success = await event_manager.unsubscribe(api_subscriber.subscription_id)
        assert success, "Unsubscribe should succeed"

        # Verify subscription is removed
        subscriptions_after = event_manager.list_subscriptions(event_name="HelloEvent")
        api_subscription_after = next(
            (s for s in subscriptions_after if s.name == "api-hello-listener"),
            None
        )
        assert api_subscription_after is None, "API subscription should be removed after unsubscribe"

        logger.info("✓ API-based subscription test passed!")

        # Cleanup using Environment.stop()
        await environment.stop()

    async def test_multiple_async_subscribers(self):
        """
        Test that multiple async event subscribers work concurrently
        This verifies that:
        1. Multiple subscribers can listen to the same event
        2. All async callbacks execute concurrently (not blocking each other)
        3. Each subscriber receives the event independently
        """
        environment = Environment(Module)

        global multi_subscriber_1_received, multi_subscriber_2_received, multi_subscriber_3_received

        # Start environment to execute @on_running callbacks (including EventManager.setup())
        await environment.start()

        event_manager = environment.get(EventManager)

        multi_subscriber_1_received = asyncio.Event()
        multi_subscriber_2_received = asyncio.Event()
        multi_subscriber_3_received = asyncio.Event()

        # Track execution order and timing
        execution_log = []

        # Subscriber 1: Fast (100ms delay)
        async def subscriber_1(event: HelloEvent):
            execution_log.append(("subscriber_1_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.1)  # 100ms
            execution_log.append(("subscriber_1_end", asyncio.get_event_loop().time()))
            logger.info("✓ Subscriber 1 received event (fast)")
            multi_subscriber_1_received.set()

        # Subscriber 2: Slow (300ms delay)
        async def subscriber_2(event: HelloEvent):
            execution_log.append(("subscriber_2_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.3)  # 300ms
            execution_log.append(("subscriber_2_end", asyncio.get_event_loop().time()))
            logger.info("✓ Subscriber 2 received event (slow)")
            multi_subscriber_2_received.set()

        # Subscriber 3: Medium (200ms delay)
        async def subscriber_3(event: HelloEvent):
            execution_log.append(("subscriber_3_start", asyncio.get_event_loop().time()))
            await asyncio.sleep(0.2)  # 200ms
            execution_log.append(("subscriber_3_end", asyncio.get_event_loop().time()))
            logger.info("✓ Subscriber 3 received event (medium)")
            multi_subscriber_3_received.set()

        # Subscribe all three
        sub_id_1 = await event_manager.subscribe(HelloEvent, subscriber_1, name="fast-subscriber")
        sub_id_2 = await event_manager.subscribe(HelloEvent, subscriber_2, name="slow-subscriber")
        sub_id_3 = await event_manager.subscribe(HelloEvent, subscriber_3, name="medium-subscriber")

        # Verify all subscriptions exist
        subscriptions = event_manager.list_subscriptions(event_name="HelloEvent")
        assert len([s for s in subscriptions if s.subscription_id in [sub_id_1, sub_id_2, sub_id_3]]) == 3

        await asyncio.sleep(0.1)

        # Send one event
        event = HelloEvent("concurrent test")
        start_time = asyncio.get_event_loop().time()
        await event_manager.send_event(event)

        # Wait for all subscribers to receive the event
        # If they run sequentially, this would take 600ms (100+300+200)
        # If they run concurrently, this should take ~300ms (max of all)
        await asyncio.wait_for(
            asyncio.gather(
                multi_subscriber_1_received.wait(),
                multi_subscriber_2_received.wait(),
                multi_subscriber_3_received.wait()
            ),
            timeout=5.0
        )
        total_time = asyncio.get_event_loop().time() - start_time

        # Verify all received
        assert multi_subscriber_1_received.is_set(), "Subscriber 1 should receive event"
        assert multi_subscriber_2_received.is_set(), "Subscriber 2 should receive event"
        assert multi_subscriber_3_received.is_set(), "Subscriber 3 should receive event"

        # Verify concurrent execution (should be ~300ms, not 600ms)
        logger.info(f"Total execution time: {total_time:.3f}s")
        assert total_time < 0.5, f"Expected concurrent execution (~0.3s), but took {total_time:.3f}s (would be ~0.6s if sequential)"

        # Verify execution order shows concurrency
        # All subscribers should start before any ends (concurrent execution)
        start_times = [time for label, time in execution_log if "start" in label]
        end_times = [time for label, time in execution_log if "end" in label]

        # The last start should happen before the first end (proves concurrency)
        if start_times and end_times:
            assert max(start_times) < min(end_times) + 0.15, "All subscribers should start before any completes (concurrent execution)"

        logger.info("✓ Multiple async subscribers executed concurrently!")
        logger.info(f"   Execution log: {[(label, f'{time:.3f}') for label, time in execution_log]}")

        # Cleanup
        await event_manager.unsubscribe(sub_id_1)
        await event_manager.unsubscribe(sub_id_2)
        await event_manager.unsubscribe(sub_id_3)

        # Cleanup using Environment.stop()
        await environment.stop()
