import asyncio
from typing import Any, Dict, Optional
import cbor2
import ansq
from ansq.tcp.types import NSQMessage
from nsq import Writer

from .event import EventManager
from aspyx.di import on_running, on_destroy, inject

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

    __slots__ = ["host", "port", "writer", "readers", "loop"]

    # constructor

    def __init__(self, nsqd_address: str, encoding: str):
        super().__init__(NSQProvider.NSQEnvelopeFactory(encoding=encoding))

        host, port = nsqd_address.split(":")
        self.host = host
        self.port = int(port)
        self.writer : Optional[Writer] = None
        self.readers = []
        self.loop = None

    # lifecycle

    @on_running()
    async def start(self):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        self.writer = await ansq.create_writer(nsqd_tcp_addresses=[f"{self.host}:{self.port}"])

    @on_destroy()
    async def stop(self):
        for reader, _ in self.readers:
            await reader.close()

        self.readers.clear()
        if self.writer:
            await self.writer.close()
            self.writer = None

    # implement Provider

    async def send(self, envelope: EventManager.Envelope, descriptor: EventManager.EventDescriptor):
        if not self.writer:
            raise RuntimeError("Writer not started yet")

        await self.writer.pub(descriptor.name, envelope.encode())

    def listen_to(self, listener: EventManager.EventListenerDescriptor):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        async def _create_reader():
            async def handler(msg: NSQMessage):
                envelope = self.create_receiver_envelope(msg.body, descriptor=listener.event)

                self.manager.pipeline.handle(envelope, listener)

                await msg.fin() # TODO exception handling?

            reader = await ansq.create_reader(
                topic=listener.event.name,
                channel=listener.name,  # could just be listener.name or unique per-listener
                nsqd_tcp_addresses=[f"{self.host}:{self.port}"]
            )
            self.readers.append((reader, handler))

            # launch reader loop
            async def reader_loop():
                async for msg in reader.messages():
                    await handler(msg)
            self.loop.create_task(reader_loop())

        self.loop.create_task(_create_reader())

    def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
        self.manager.dispatch_event(event_listener_descriptor, envelope.event)
