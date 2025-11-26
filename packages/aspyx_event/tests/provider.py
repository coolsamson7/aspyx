from typing import Optional, Any

from aspyx.di import Environment, inject_environment
from aspyx_event import EventManager

class LocalProvider(EventManager.Provider):
    """
    A provider fot test purposes
    """
    # local classes

    class LocalEnvelope(EventManager.Envelope[Any]):
        # constructor

        def __init__(self, event: Any):
            super().__init__(event)

            self.headers = {}

        # implement envelope

        def encode(self) -> Any:
            return self.event

        def decode(self, message) -> Any:
            return message

        def set(self, key: str, value: str):
            self.headers[key] = value

        def get(self, key: str) -> str:
            return self.headers.get(key,"")

    class LocalEnvelopeFactory(EventManager.EnvelopeFactory):
        def __init__(self):
            pass

        # implement

        def for_send(self, provider: EventManager.Provider, event: Any) -> EventManager.Envelope:
            return LocalProvider.LocalEnvelope(event)

        def for_receive(self,  provider: EventManager.Provider, message: Any, descriptor: EventManager.EventDescriptor) -> EventManager.Envelope:
            return LocalProvider.LocalEnvelope(message)

    # constructor

    def __init__(self):
        super().__init__(LocalProvider.LocalEnvelopeFactory())

        self.environment : Optional[Environment] = None
        self.listeners : list[EventManager.EventListenerDescriptor] = []

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # implement Provider

    def listen_to(self, listener: EventManager.EventListenerDescriptor) -> None:
        self.listeners.append(listener)

    # implement EnvelopePipeline

    async def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        for listener in self.listeners:
            if listener.event is event_descriptor:
                self.manager.pipeline.handle(envelope, listener)

    def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
        self.manager.dispatch_event(event_listener_descriptor, envelope.event)
