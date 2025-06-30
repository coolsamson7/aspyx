# Service

## Introduction

The Aspyx service library is built on top of the DI core framework and adds a microservice based architecture,
that lets you deploy, discover and call services with different remoting protocols and pluggable discovery services.

The basic design consists of four different concepts:

- **Service**

  a service defines a set of methods that can be called
- **Component**
  a component bundles a list of services and determines the protocols that are available to call the services.
- **Component Registry**
  the registry is a central service that is used to register and discover components
- **Channel**
  channels implement any transport protocol that is used to execute remote calls.

Let's look at the "interface" layer first.

**Example**:
```python
@service(name="test-service", description="test service")
class TestService(Service):
    @abstractmethod
    def hello(self, message: str) -> str:
        pass

@component(name="test-component", services =[TestService])
class TestComponent(Component):
    pass
```

After booting the DI infrastructure with a main module we could already call a service:

**Example**:
```python
@module(imports=[ServiceModule])
class Module:
    def __init__(self):
        pass
    
    @create()
    def create_registry(self) -> ConsulComponentRegistry:
        return ConsulComponentRegistry(Server.port, "http://localhost:8500") # a consul based registry!

environment = Environment(Module)
service_manager = environment.get(ServiceManager)

service = service_manager.get_service(TestService)

service.hello("world")
```

The technical details are completely transparent, as a dynamic proxy encapsulates the internals.

As we can also host implementations, lets look at this side as well:

```python
@implementation()
class TestComponentImpl(AbstractComponent, TestComponent):
    # constructor

    def __init__(self):
        super().__init__()

    # implement Component

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [
            ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}"),
        ]

@implementation()
class TestServiceImpl(TestService):
    def __init__(self):
        pass

    def hello(self, message: str) -> str:
        return f"hello {message}"
```

The interesting part if the `get_addresses` method that return a list of channels, that can be used to execute remote calls.
In this case a channel is used that exposes a single http endpoint, that will dispatch to the correct service method.
This information is registered with the appropriate component registry and is used by other processes. 

The required - `FastAPI` - infrastructure is provided by the call:

```python
server = FastAPIServer(host="0.0.0.0", port=8000)

environment = server.boot(Module)
```

Of course, service can also be called locally. In case of multiple possible channels, a keyword argument is used to 
determine a specific channel. As a local channel has the name "local", the appropriate call is:

```python
 service = service_manager.get_service(TestService, preferred_channel="local")
```

## Features

The library offers:

- sync and async support
- multiple - extensible - channel implementations
- ability to customize http calls with interceptors ( via the AOP abilities )
- `fastapi` based channels covering simple rest endpoints including `msgpack` support.
- `httpx` based clients for dispatching channels and simple rest endpoint with the help of low-level decorators.
- first registry implementation based on `consul`
- support for configurable health checks

As well as the DI and AOP core, all mechanisms are heavily optimized.
A simple benchmark resulted in message roundtrips in significanlty under a ms per call.

Let's see some details

## Service and Component declaration 

TODO 

## Service and Component implementation

TODO 

## Health Checks

## Service Manager

TODO 

## Component Registry

TODO

## Channels

TODO

-> rest endpoints
-> intercepting calls

## FastAPI server

TODO

## Implementing Channels

TODO



