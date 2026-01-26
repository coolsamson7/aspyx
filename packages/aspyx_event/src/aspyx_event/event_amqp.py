"""
stomp
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from proton import Message, Event, Handler, Sender, Receiver
from proton.handlers import MessagingHandler
from proton.reactor import Container

from aspyx.di import on_destroy

from .event import EventManager

class AMQPProvider(MessagingHandler, EventManager.Provider):
    # class property

    logger = logging.getLogger("aspyx.event.amq")  # __name__ = module name

    # local classes

    class AMQHandler(Handler):
        def __init__(self, provider: AMQPProvider):
            super().__init__()

            self.provider = provider

    class AMQPEnvelope(EventManager.Envelope[str]):
        # constructor

        def __init__(self, provider: EventManager.Provider, from_event: Optional[Any] = None, from_message: Optional[Any] = None):
            super().__init__(from_event)

            self.provider = provider
            self.event = from_event
            self.headers : Dict[str,Any] = {}
            if from_message is not None:
                self.event = self.decode(from_message)

        # implement envelope

        def encode(self) -> str:
            return self.provider.to_json(self.event)

        def decode(self, message: Any):
            self.headers = message.properties
            self.event =  self.provider.from_json(message.body)

        def set(self, key: str, value: str):
            self.headers[key] = value

        def get(self, key: str) -> str:
            return self.headers.get(key,"")

    class AMQEnvelopeFactory(EventManager.EnvelopeFactory):
        # implement

        def for_send(self,  provider: EventManager.Provider, event: Any) -> EventManager.Envelope:
            #body = self.to_json(event), headers = {}
            return AMQPProvider.AMQEnvelope(provider, from_event=event)

        def for_receive(self,  provider: EventManager.Provider, message: Any, descriptor: EventManager.EventDescriptor) -> EventManager.Envelope:
            return AMQPProvider.AMQEnvelope(provider, from_message=message)

    # constructor

    def __init__(self, server_name: str,  host="localhost", port=61616, user = "", password = ""):
        super().__init__(AMQPProvider.AMQEnvelopeFactory())

        # TODO WTF?

        MessagingHandler.__init__(self)
        #EventManager.Provider.__init__(self)

        self.server_name = server_name
        self.host = host
        self.port = port
        self.user = user
        self.password = password

        self.container = Container(self)#, debug=True)
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

    def create_receiver_for_subscription(self, address: str, subscription: EventManager.EventSubscription) -> Receiver:
        """Create AMQP receiver for a subscription"""
        class DispatchMessageHandler(MessagingHandler):
            def __init__(self, provider: AMQPProvider, subscription: EventManager.EventSubscription):
                super().__init__()

                self.subscription = subscription
                self.provider = provider

            def on_message(self, event: Event):
                self.provider.dispatch_subscription(event, self.subscription)

        self.logger.info("create receiver for subscription %s at %s", subscription.name, address)

        receiver = self.container.create_receiver(self._connection, address, handler=DispatchMessageHandler(self, subscription))
        self._receivers[address] = receiver

        return receiver

    def dispatch_subscription(self, event: Event, subscription: EventManager.EventSubscription):
        """Dispatch message to subscription"""
        AMQPProvider.logger.debug("on_message for subscription %s", subscription.name)

        envelope = self.envelope_factory.for_receive(self, event.message, subscription.event_descriptor)

        try:
            self.manager.dispatch_event(subscription.event_descriptor.name, envelope.event)
            event.delivery.settle()
        except Exception as e:
            AMQPProvider.logger.error(f"Error dispatching to subscription {subscription.name}: {e}", exc_info=True)


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
                self.logger.warning("Error closing sender: %s", e)

        # close all receivers

        for receiver in self._receivers.values():
            try:
                receiver.close()
            except Exception as e:
                self.logger.warning("Error closing receiver: %s", e)

        # close connection

        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.warning("Error closing connection: %s", e)

        self.logger.info("AMQPProvider stopped.")

        # stop the container

        self.container.stop()

    async def stop(self):
        # local class

        class CloseHandler(AMQPProvider.AMQHandler):
            def __init__(self, provider: AMQPProvider):
                super().__init__(provider)

            def on_timer_task(self, event):
                self.provider.close_container()

        self.container.schedule(0, CloseHandler(self))

    # lifecycle
    # Note: start() and stop() are called by EventManager, not via lifecycle decorators

    async def start(self):
        self.thread.start()

    def listen_to_subscription(self, subscription: EventManager.EventSubscription) -> None:
        """
        Setup AMQP receiver for a subscription.
        """
        self._ready.wait(timeout=5)

        class CreateReceiverHandler(AMQPProvider.AMQHandler):
            def __init__(self, provider: AMQPProvider, address: str, subscription: EventManager.EventSubscription):
                super().__init__(provider)

                self.address = address
                self.subscription = subscription

            def on_timer_task(self, event):
                self.provider.create_receiver_for_subscription(self.address, self.subscription)

        # <event-name>::<subscription-name>[-<server-name>]
        address = subscription.event_descriptor.name + "::" + subscription.name
        if subscription.per_process:
            address = address + f"-{self.server_name}"

        if subscription.event_descriptor.durable:
            address = address + "?durable=true"

        if self._receivers.get(address, None) is None:
            self.container.schedule(0, CreateReceiverHandler(self, address, subscription))

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
