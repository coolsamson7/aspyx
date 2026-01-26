import asyncio
from typing import Any, Dict, Optional
import cbor2
import ansq
from ansq.tcp.types import NSQMessage
from ansq.tcp.writer import NSQConnection

from .event import EventManager

from aspyx.util import get_deserializer, get_serializer

class NSQProvider(EventManager.Provider):
    # local classes

    class NSQEnvelope(EventManager.Envelope[bytes]):
        # constructor

        def __init__(self, provider: EventManager.Provider, from_event : Optional[Any] = None, from_message: Optional[Any] = None,  descriptor: Optional[EventManager.EventDescriptor] = None, encoding: str = "cbor"):
            super().__init__(from_event)

            self.encoding = encoding
            self.provider = provider
            self.descriptor = descriptor

            if from_event is not None:
                self.event = from_event
                self.headers : Dict[str, Any] = {}
            else:
                self.decode(from_message)

        # implement envelope

        def encode(self) -> bytes:
            if self.encoding == "cbor":
                dict =  get_serializer(type(self.event))(self.event)
                return cbor2.dumps(dict)

            # default

            return self.to_json(self.event).encode()

        def decode(self, message: Any):
            self.headers = {} # TODO for now!!!

            if self.encoding == "cbor":
                json = cbor2.loads(message)
                self.event = get_deserializer(self.descriptor.type)(json)
                return

            # default

            self.event = self.from_json(message.decode(),type=self.descriptor.type)

        def set(self, key: str, value: str):
            self.headers[key] = value

        def get(self, key: str) -> str:
            return self.headers.get(key, "")

    class NSQEnvelopeFactory(EventManager.EnvelopeFactory):
        def __init__(self, encoding: str):
            self.encoding = encoding

        # implement

        def for_send(self, provider: EventManager.Provider, event: Any) -> EventManager.Envelope:
            return NSQProvider.NSQEnvelope(provider, from_event=event, encoding=self.encoding)

        def for_receive(self,  provider: EventManager.Provider, message: Any, descriptor: EventManager.EventDescriptor) -> EventManager.Envelope:
            return NSQProvider.NSQEnvelope(provider, from_message=message, descriptor=descriptor, encoding=self.encoding)

    # slots

    __slots__ = ["host", "port", "writer", "readers", "reader_tasks", "loop", "writer_connections"]

    # constructor

    def __init__(self, nsqd_address: str, encoding: str):
        super().__init__(NSQProvider.NSQEnvelopeFactory(encoding=encoding))

        host, port = nsqd_address.split(":")
        self.host = host
        self.port = int(port)
        self.writer : Optional[NSQConnection] = None
        self.readers = []
        self.reader_tasks = []
        self.loop = None
        self.writer_connections = []

    # lifecycle
    # Note: start() and stop() are called by EventManager, not via lifecycle decorators

    async def start(self):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        self.writer = await ansq.create_writer(nsqd_tcp_addresses=[f"{self.host}:{self.port}"])

    async def stop(self):
        import logging
        logger = logging.getLogger("aspyx.event.nsq")
        logger.info("Stopping NSQ provider...")

        # Cancel all reader loop tasks first
        for task in self.reader_tasks:
            if not task.done():
                task.cancel()

        # Close all readers (this will cause reader loops to exit)
        for reader, _ in self.readers:
            try:
                await reader.close()
            except Exception as e:
                logger.warning(f"Error closing reader: {e}")

        # Wait for tasks to be cancelled with a short timeout
        if self.reader_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.reader_tasks, return_exceptions=True),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for reader tasks to complete")

        self.reader_tasks.clear()
        self.readers.clear()

        # Close writer and clean up its internal connection tasks
        if self.writer:
            try:
                # Collect internal tasks from writer connections before closing
                connection_tasks = []
                if hasattr(self.writer, 'connections'):
                    for conn in self.writer.connections:
                        if hasattr(conn, '_reader_task') and conn._reader_task:
                            connection_tasks.append(conn._reader_task)
                            logger.debug(f"Found writer connection task: {conn._reader_task}")

                # Close the writer (this should signal tasks to stop)
                await self.writer.close()

                # Wait for tasks to complete or timeout, then cancel remaining
                if connection_tasks:
                    # Wait up to 1 second for tasks to finish naturally
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*connection_tasks, return_exceptions=True),
                            timeout=1.0
                        )
                        logger.debug("All writer connection tasks completed cleanly")
                    except asyncio.TimeoutError:
                        logger.debug("Timeout waiting for writer tasks, cancelling remaining")
                        # Cancel any tasks that didn't finish
                        for task in connection_tasks:
                            if not task.done():
                                task.cancel()
                        # Wait for cancellations to complete
                        await asyncio.gather(*connection_tasks, return_exceptions=True)

                    # Give the event loop a final cycle to fully clean up the tasks
                    await asyncio.sleep(0.01)

            except Exception as e:
                logger.warning(f"Error closing writer: {e}")
            self.writer = None

        self.writer_connections.clear()
        logger.info("NSQ provider stopped")

    # implement Provider

    async def send(self, envelope: EventManager.Envelope, descriptor: EventManager.EventDescriptor):
        if not self.writer:
            raise RuntimeError("Writer not started yet")

        await self.writer.pub(descriptor.name, envelope.encode())

    def listen_to_subscription(self, subscription: EventManager.EventSubscription):
        """
        Setup NSQ reader for a subscription.
        """
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        async def _create_reader():
            async def handler(msg: NSQMessage):
                envelope = self.create_receiver_envelope(msg.body, descriptor=subscription.event_descriptor)

                # Dispatch directly to the event manager with event name
                self.manager.dispatch_event(subscription.event_descriptor.name, envelope.event)

                await msg.fin()

            # Use subscription name as NSQ channel
            # For per_process subscriptions, use the same channel name across processes
            # For non-per_process, each subscription gets its own channel

            channel_name = subscription.metadata.get("channel", "")
            if channel_name == "":
                channel_name = subscription.name if subscription.per_process else f"{subscription.name}_{subscription.subscription_id[:8]}"

            import logging
            logger = logging.getLogger("aspyx.event.nsq")
            logger.info(f"Creating NSQ reader - Topic: {subscription.event_descriptor.name}, Channel: {channel_name}, Per-process: {subscription.per_process}")

            reader = await ansq.create_reader(
                topic=subscription.event_descriptor.name,
                channel=channel_name,
                nsqd_tcp_addresses=[f"{self.host}:{self.port}"]
            )
            self.readers.append((reader, handler))

            # launch reader loop with reconnection
            async def reader_loop():
                import logging
                logger = logging.getLogger("aspyx.event.nsq")

                while True:
                    try:
                        async for msg in reader.messages():
                            await handler(msg)
                        # If we exit the loop normally, the connection was closed
                        logger.warning(f"NSQ reader connection closed for {subscription.event_descriptor.name}, reconnecting...")
                        # Reconnect by creating a new reader
                        await reader.reconnect()
                    except asyncio.CancelledError:
                        # Task was cancelled during shutdown
                        logger.info(f"NSQ reader for {subscription.event_descriptor.name} cancelled")
                        break
                    except Exception as e:
                        logger.error(f"Error in reader loop for {subscription.event_descriptor.name}: {e}", exc_info=True)
                        # Wait a bit before reconnecting
                        await asyncio.sleep(1)

            task = self.loop.create_task(reader_loop())
            self.reader_tasks.append(task)

        self.loop.create_task(_create_reader())
