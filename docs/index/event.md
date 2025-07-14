# Eventing

## Introduction

As we already covered the foundation for microservices, only one aspect is missing for enterprise software: Asynchronous communication involving queues.

It's pretty simple to have a working example ready in Python using some of the low-level libraries related to stomp or amqp,
but the missing thing always is an abstraction layer on top to hide the technical details.

From a programmer perspective i essentially need a payload object, a listener and some means to define the routing logic.
I really shouldn't have to bother with connections, messages, serialization and deserialization logic, threads, exception handling, etc.

Let's look at a simple example, what the result looks like:

**Example**: 

```python
@dataclass
@event()
class HelloEvent:
    world: str

@event_listener(HelloEvent)
class HelloEventListener(EventListener[HelloEvent]):
    # constructor

    def __init__(self):
        pass

    # implement

    def on(self, event: HelloEvent):
       ...

environment = ...
event_manager = environment.get(EventManager)
event_manager.send_event(HelloEvent("world"))
```

Not bad, huh?

## Features

- Support for any pydantic model or dataclass as events
- Pluggable transport protocol, currently supporting AMQP and Stomp.
- Possibility to pass headers to events
- Event interceptors on the sending and receiving side ( e.g. session capturing )

Let's look at the details:

# API

## Event

An event is a dataclass or pydantic model, annotated with `@event()`

Parameters are:

- `name=""` name of the event, if not specified the class name is used.
- `durable=False` if `True`, the provider will try to create a persistent queue.

The name attribute will be used as a queue name!

## EventListener

An event listener derives from the base-class `EventListener ` with a generic argument specifying the handled event type and
are decorated with `@event_listener(...)`.

Parameters are:

- `name=""` name of the listener, if not specified the class name is used.
- `per_process=False` if `True`, the event will be dispatched all identical listeners, that run inside a cluster.

Listeners are injectable objects.

Currently, `on` is a sync method only.

## EnvelopePipeline

An envelope pipeline is something like an interceptor that both covers the sending and receiving side.

It is declared as:

```python
class EnvelopePipeline(ABC):
    @abstractmethod
    def send(self, envelope: EventManager.Envelope, event_descriptor: EventManager.EventDescriptor):
        pass

    @abstractmethod
    def handle(self, envelope: EventManager.Envelope, event_listener_descriptor: EventManager.EventListenerDescriptor):
        pass
```
with envelope being a wrapper around the event, with additional possibilities to set and retrieve header information. 

```python
class Envelope(ABC):
    @abstractmethod
    def get_body(self) -> str:
        pass

    @abstractmethod
    def set(self, key: str, value: str):
        pass

    @abstractmethod
    def get(self, key: str) -> str:
        pass
```

The purpose is to give the programmer the chance to set and retrieve meta data to an event. Think of passing and retrieving a session id, that will
be used to establish a session context.

Concrete pipelines are decorate with `@envelope_pipeline()` and are regular injectable objects.

## EventManager

The central class is the `EventManager` that offers the single API method

```python
def send_event(self, event: Any)-> None
```

The constructor expects an argument `provider: EnvironmentManager.Provider` that contains the technical queuing implementation.

## Providers

A provider encapsulates the technical queuing details based on existing 3rd party libs.
As different technologies offer different possibilities, some of the logical parameters -`durable`, `per_process` - may not be considered! 

### AMQP

The class `AMQProvider` is based on the proton library utilizing the AMQ protocol.

The constructor accepts:

- `server_name: str` a unique name identifying a specific server. Typically a name including the host and some port.
- `host="localhost"` the url of teh amq server ( e.g. Artemis )
- `port=61616` the port of the server
- `user = ""` the user name
- `password = ""` the password

If we think of an Artemis address model, this is how it is applied:

- addresses are event names
- a queue name is defined as `<event-name>::<listener-name>[-<server-name>]`

The server name is appended, if `per_process` is `True`, guaranteeing the even in clusters every server receives the corresponding events!

# Version History

- 0.9.0: Initial version