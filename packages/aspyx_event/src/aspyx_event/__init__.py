"""
This module provides the core Aspyx event management framework .
"""
from aspyx.di import module
from .event import EventManager, EventListener, event, event_listener, envelope_pipeline, AbstractEnvelopePipeline
from .event_stomp import StompProvider
from .event_amqp import AMQPProvider
from .event_nsq import NSQProvider
from .event_ws import WebSocketManager, websocket_endpoint, ClientSubscription

@module()
class EventModule:
    def __init__(self):
        pass

__all__ = [
    # event

    "EventModule",

    "EventManager",
    "EventListener",
    "event",
    "event_listener",
    "envelope_pipeline",
    "AbstractEnvelopePipeline",

    # stomp

    "StompProvider",

    # amqp

    "AMQPProvider",

    # event_nsq

    "NSQProvider",

    # websocket

    "WebSocketManager",
    "websocket_endpoint",
    "ClientSubscription"
]

# Export nested classes for external API usage
EventSubscription = EventManager.EventSubscription
__all__.append("EventSubscription")
