"""
stomp
"""
from __future__ import annotations

from typing import Optional

from .event import EventManager

from aspyx.di import on_destroy

import stomp


class StompProvider(EventManager.Provider, stomp.ConnectionListener):
    # local classes

    class StompEnvelope(EventManager.Envelope):
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

    def __init__(self, host="localhost", port=61616, user = "", password = ""):
        super().__init__()

        self.host = host
        self.port = port
        self.user = user
        self.password = password

        self.connection : Optional[stomp.Connection] = self.connect()

    # implement ConnectionListener

    def on_connected(self, frame):
        print('Connected to broker') # TODO

    def get_headers(self, frame):
        headers = frame.headers
        if isinstance(headers, dict):
            return headers
        else:
            return dict(headers)

    def on_message(self, frame):
        print(frame)

        headers = self.get_headers(frame)

        message_id = headers.get("message-id")
        destination = headers.get("destination")
        body = frame.body

        event_name = destination.split("/")[-1]

        event_descriptor = EventManager.events_by_name.get(event_name, None)

        envelope = self.create_envelope(body=body, headers=headers)

        self.manager.pipeline.handle(envelope, event_descriptor)

    # lifecycle

    @on_destroy()
    def on_destroy(self):
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    # internal

    def connect(self) -> stomp.Connection:
        connection = stomp.Connection([(self.host, self.port)])

        connection.set_listener('', self)

        connection.connect(self.user, self.password, wait=True)

        return connection

    # implement Provider

    def create_envelope(self, body="", headers = None) -> EventManager.Envelope:
        return StompProvider.StompEnvelope(body=body, headers=headers)

    def listen_to(self, listener: EventManager.EventListenerDescriptor) -> None:
        self.connection.subscribe(destination=f"/queue/{listener.event.name}", id=f"id-{listener.event.name}", ack="auto")

    # implement EnvelopePipeline

    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        self.connection.send(body=envelope.get_body(), destination=f"/queue/{event_descriptor.name}")

    def handle(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
       self.manager.dispatch_event(event_descriptor, envelope.get_body())