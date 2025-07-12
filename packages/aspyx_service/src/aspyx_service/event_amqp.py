"""
stomp
"""
from __future__ import annotations

import time

from proton._reactor import Selector
from proton.handlers import MessagingHandler

from aspyx_service import EventManager

from aspyx.di import on_destroy

from proton import Message, Event, Handler
from proton.reactor import Container
import threading


class RegisterHandler(Handler):
    def __init__(self, amqp_provider, address, queue_name):
        super().__init__()

        self.amqp_provider = amqp_provider
        self.address = address
        self.queue_name = queue_name

    def on_timer_task(self, event):
        if self.amqp_provider._conn:
            receiver = event.container.create_receiver(
                self.amqp_provider._conn,
                self.queue_name
            )
            self.amqp_provider._receivers[self.queue_name] = receiver

class SendHandler(Handler):
    def __init__(self, amqp_provider, envelope, address):
        super().__init__()

        self.amqp_provider = amqp_provider
        self.envelope = envelope
        self.address = address

    def on_timer_task(self, event):
        sender = self.amqp_provider._senders.get(self.address)
        if not sender:
            sender = event.container.create_sender(
                self.amqp_provider._conn,
                self.address
            )
            self.amqp_provider._senders[self.address] = sender
        msg = Message(body=self.envelope.get_body())
        sender.send(msg)

class AMQPProvider(MessagingHandler, EventManager.Provider):
    # local classes

    class AMQPEnvelope(EventManager.Envelope):
        # constructor

        def __init__(self, headers=None):
            self.body = ""
            self.headers = headers or {}

        # implement envelope

        def set_body(self, body: str):
            self.body = body

        def get_body(self) -> str:
            return self.body

        def set(self, key: str, value: str):
            self.headers[key] = value

        def get(self, key: str) -> str:
            return self.headers.get(key,"")

    # constructor

    def __init__(self, host="localhost", port=61616, user = "", password = ""):
        MessagingHandler.__init__(self)
        EventManager.Provider.__init__(self)

        self.host = host
        self.port = port
        self.user = user
        self.password = password

        self.container = Container(self, debug=True)
        self._conn = None

        self.thread= threading.Thread(target=self.container.run, daemon=True)

        self._ready = threading.Event()
        self._senders = {}  # address -> sender
        self._receivers = {}  # queue_name -> receiver

    # internal

    def bind_queue(self, address: str, queue_name: str, durable=False):
        """
        Binds a named queue to the given address and registers a message handler.

        address: the target address (should be MULTICAST for fan-out)
        queue_name: the unique queue bound to the address
        handler: function to call when messages arrive
        durable: whether the queue should be durable (default False)
        """

        self._ready.wait(timeout=5)

        self.container.schedule(0, RegisterHandler(self, address, queue_name))

    # implement MessagingHandler

    #def on_unhandled(self, method: str, *args):
    #    print(f"[AMQP] Unhandled event: {method}")

    def on_transport_error(self, event: Event):
        print(f"[AMQP] Transport error: {event.transport.condition}")

    def on_connection_error(self, event: Event):
        print(f"[AMQP] Connection error: {event.connection.condition}")

    def on_start(self, event: Event):
        self._conn = event.container.connect(
            f"{self.host}:{self.port}",
            user=self.user,
            password=self.password
        )

        self._ready.set()

    def on_connection_closed(self, event: Event):
        self._conn = None

    def on_message(self, event: Event):
        body = event.message.body
        address = getattr(event.receiver.source, "address", None)

        envelope = self.AMQPEnvelope()
        envelope.set_body(body)

        event_descriptor = EventManager.events_by_name.get(address, None)

        self.manager.pipeline.handle(envelope, event_descriptor)

    # ?

    def stop(self):
        def close():
            if self._conn:
                self._conn.close()

        self.container.schedule(0, close)

    # lifecycle

    @on_destroy()
    def on_destroy(self):
        self.stop()

    # implement Provider

    def start(self):
        self.thread.start()

    def create_envelope(self, headers = None) -> EventManager.Envelope:
        return AMQPProvider.AMQPEnvelope(headers)

    def listen_to(self, listener: EventManager.EventListenerDescriptor) -> None:
        address = f"{listener.event.name}"
        queue   = f"{listener.event.name}"

        durable = True

        self.bind_queue(address, queue, durable)

    # implement EnvelopePipeline

    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        address = f"{event_descriptor.name}"

        self._ready.wait(timeout=5)
        self.container.schedule(0, SendHandler(self, envelope, address))

    def handle(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
       self.manager.dispatch_event(event_descriptor, envelope.get_body())