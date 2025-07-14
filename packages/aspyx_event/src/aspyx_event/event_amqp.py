"""
stomp
"""
from __future__ import annotations

import logging

from proton.handlers import MessagingHandler

from .event import EventManager

from aspyx.di import on_destroy

from proton import Message, Event, Handler, Sender, Receiver
from proton.reactor import Container
import threading

class AMQPProvider(MessagingHandler, EventManager.Provider):
    # class property

    logger = logging.getLogger("aspyx.event.amq")  # __name__ = module name

    # local classes

    class AMQHandler(Handler):
        def __init__(self, provider: AMQPProvider):
            super().__init__()

            self.provider = provider

    class AMQPEnvelope(EventManager.Envelope):
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

    # constructor

    def __init__(self, server_name: str,  host="localhost", port=61616, user = "", password = ""):
        MessagingHandler.__init__(self)
        EventManager.Provider.__init__(self)

        self.server_name = server_name
        self.host = host
        self.port = port
        self.user = user
        self.password = password

        self.container = Container(self)#, debug=True) # TODO
        self._connection = None

        self.thread= threading.Thread(target=self.container.run, daemon=True)

        self._ready = threading.Event()
        self._senders : dict[str,Sender] = {}  # queue -> sender
        self._receivers : dict[str, Receiver] = {}  # address -> receiver

    # implement MessagingHandler

    def on_transport_error(self, event: Event):
        print(f"[AMQP] Transport error: {event.transport.condition}")

    def on_connection_error(self, event: Event):
        print(f"[AMQP] Connection error: {event.connection.condition}")

    def on_start(self, event: Event):
        self._connection = event.container.connect(
            f"{self.host}:{self.port}",
            user=self.user,
            password=self.password
        )

        self._ready.set()

    def on_connection_closed(self, event: Event):
        self._connection = None

    # internal

    def create_receiver(self, address: str, listener: EventManager.EventListenerDescriptor) -> Receiver:
        class DispatchMessageHandler(MessagingHandler):
            # constructor

            def __init__(self, provider: AMQPProvider, listener: EventManager.EventListenerDescriptor):
                super().__init__()

                self.listener = listener
                self.provider = provider

            # override

            def on_message(self, event: Event):
                self.provider.dispatch(event, self.listener)

        self.logger.info("create receiver %s", address)

        receiver = self.container.create_receiver(self._connection, address, handler=DispatchMessageHandler(self, listener))

        #source = Source(address=address, durable=Terminus.DELIVERIES)
        self._receivers[address] = receiver  # if it exists?

        return receiver

    def dispatch(self, event: Event, listener: EventManager.EventListenerDescriptor):
        AMQPProvider.logger.info("on_message ")

        envelope = self.AMQPEnvelope(body=event.message.body, headers = event.message.properties)

        try:
            self.manager.pipeline.handle(envelope, listener)

            event.delivery.settle()
        except Exception as e:
            print(e) # TODO


    def get_sender(self, address: str) -> Sender:
        sender = self._senders.get(address, None)
        if not sender:
            self.logger.info("create sender %s", address)

            sender = self.container.create_sender(self._connection, address)

            self._senders[address] = sender

        return sender

    def close_container(self):
        # close all senders

        for sender in self._senders.values():
            try:
                sender.close()
            except Exception as e:
                self.provider.logger.warning("Error closing sender: %s", e)

        # close all receivers

        for receiver in self._receivers.values():
            try:
                receiver.close()
            except Exception as e:
                self.provider.logger.warning("Error closing receiver: %s", e)

        # close connection

        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                self.provider.logger.warning("Error closing connection: %s", e)

        self.provider.logger.info("AMQPProvider stopped.")

        # stop the container

        self.container.stop()

    def stop(self):
        # local class

        class CloseHandler(AMQPProvider.AMQHandler):
            def __init__(self, provider: AMQPProvider):
                super().__init__(provider)

            def on_timer_task(self, event):
                self.provider.close_container()

        self.container.schedule(0, CloseHandler(self))

    # lifecycle

    @on_destroy()
    def on_destroy(self):
        self.stop()

    # implement Provider

    def start(self):
        self.thread.start()

    def create_envelope(self, body="", headers = None) -> EventManager.Envelope:
        return AMQPProvider.AMQPEnvelope(body=body, headers=headers)

    def listen_to(self, listener: EventManager.EventListenerDescriptor) -> None:
        self._ready.wait(timeout=5)

        class CreateReceiverHandler(AMQPProvider.AMQHandler):
            def __init__(self, provider: AMQPProvider, address: str, listener: EventManager.EventListenerDescriptor):
                super().__init__(provider)

                self.address = address
                self.listener = listener

            def on_timer_task(self, event):
                self.provider.create_receiver(address, self.listener)

        # <event-name>::<listener-name>[-<server-name>]

        address = listener.event.name + "::" + listener.name
        if listener.per_process:
            address = address + f"-{self.server_name}"

        if listener.event.durable:
            address = address + "?durable=true"

        if  self._receivers.get(address, None) is None:
            self.container.schedule(0, CreateReceiverHandler(self, address, listener))

    # implement EnvelopePipeline

    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        # local class

        class SendHandler(AMQPProvider.AMQHandler):
            def __init__(self, provider: AMQPProvider, envelope: AMQPProvider.AMQPEnvelope, address):
                super().__init__(provider)

                self.envelope = envelope
                self.address = address

            def on_timer_task(self, event: Event):
                message = Message(body=self.envelope.get_body(), properties=self.envelope.headers)

                # TODO message.delivery_mode = Message.DeliveryMode.AT_LEAST_ONCE

                self.provider.get_sender(self.address).send(message)

        # go

        address = event_descriptor.name

        self._ready.wait(timeout=5)
        self.container.schedule(0, SendHandler(self, envelope, address))

    def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
       self.manager.dispatch_event(event_listener_descriptor, envelope.get_body())