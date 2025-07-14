from typing import Optional

from aspyx.di import Environment, inject_environment
from aspyx_event import EventManager


class LocalProvider(EventManager.Provider):
    # local classes

    class TestEnvelope(EventManager.Envelope):
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

    def __init__(self):
        super().__init__()

        self.environment : Optional[Environment] = None
        self.listeners : list[EventManager.EventListenerDescriptor] = []

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # implement Provider

    def create_envelope(self, body="", headers = None) -> EventManager.Envelope:
        return LocalProvider.TestEnvelope(body=body, headers=headers)

    def listen_to(self, listener: EventManager.EventListenerDescriptor) -> None:
        self.listeners.append(listener)

    # implement EnvelopePipeline

    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        #self.handle(envelope, event_descriptor)
        self.manager.pipeline.handle(envelope, event_descriptor)

    def handle(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        for listener in self.listeners:
            if listener.event is event_descriptor:
                self.manager.dispatch_event(listener, envelope.get_body())
