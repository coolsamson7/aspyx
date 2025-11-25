import asyncio
import ansq
from .event import EventManager
from aspyx.di import on_running, on_destroy, inject

class NSQProvider(EventManager.Provider):
    __slots__ = ["host", "port", "writer", "readers", "loop"]

    def __init__(self, nsqd_address: str):
        host, port = nsqd_address.split(":")
        self.host = host
        self.port = int(port)
        self.writer = None
        self.readers = []
        self.loop = None

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

    async def send(self, envelope: EventManager.Envelope, descriptor: EventManager.EventDescriptor):
        if not self.writer:
            raise RuntimeError("Writer not started yet")
        await self.writer.pub(descriptor.name, envelope.get_body().encode())

    def create_envelope(self, body: str = "", headers: dict = None):
        return EventManager.AbstractEnvelope(body, headers)

    def listen_to(self, listener: EventManager.EventListenerDescriptor):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

        async def _create_reader():
            async def handler(msg):
                self.manager.dispatch_event(listener, msg.body.decode())
                await msg.fin()

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
        self.manager.dispatch_event(event_listener_descriptor, envelope.get_body())
