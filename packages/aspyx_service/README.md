# aspyx

![Pylint](https://github.com/coolsamson7/aspyx/actions/workflows/pylint.yml/badge.svg)
![Build Status](https://github.com/coolsamson7/aspyx/actions/workflows/ci.yml/badge.svg)
![Python Versions](https://img.shields.io/badge/python-3.9%20|%203.10%20|%203.11%20|%203.12-blue)
![License](https://img.shields.io/github/license/coolsamson7/aspyx)
![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)
[![PyPI](https://img.shields.io/pypi/v/aspyx)](https://pypi.org/project/aspyx/)
[![Docs](https://img.shields.io/badge/docs-online-blue?logo=github)](https://coolsamson7.github.io/aspyx/index/introduction)

![image](https://github.com/user-attachments/assets/e808210a-b1a4-4fd0-93f1-b5f9845fa520)

# Service

- [Introduction](#introduction)
- [Features](#features)
- [Service and Component declaration](#service-and-component-declaration)
- [Service and Component implementation](#service-and-component-implementation)
- [Health Checks](#health-checks)
- [Service Manager](#service-manager)
- [Component Registry](#component-registry)
- [Channels](#channels)
  - [Performance](#performance)
  - [Rest Calls](#rest-calls)
  - [Intercepting calls](#intercepting-calls)
- [FastAPI server](#fastapi-server)
- [Implementing Channels](#implementing-channels)
- [Version History](#version-history)

## Introduction

The Aspyx service library is built on top of the DI core framework and adds a microservice based architecture,
that lets you deploy, discover and call services with different remoting protocols and pluggable discovery services.

The basic design consists of four different concepts:

!!! info "Service"
  defines a group of methods that can be called either locally or remotely. 
  These methods represent the functional interface exposed to clients — similar to an interface in traditional programming

!!! info "Component"
  a component bundles one or more services and declares the channels (protocols) used to expose them.
  Think of a component as a deployment unit or module.

!!! info "Component Registry "
  acts as the central directory for managing available components.
  It allows the framework to register, discover, and resolve components and their services.

!!! info "Channel"
  is a pluggable transport layer that defines how service method invocations are transmitted and handled.

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
        return [ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}")]

@implementation()
class TestServiceImpl(TestService):
    def __init__(self):
        pass

    def hello(self, message: str) -> str:
        return f"hello {message}"
```

The interesting part if the `get_addresses` method that return a list of channel addresses, that can be used to execute remote calls.
In this case a channel is used that exposes a single http endpoint, that will dispatch to the correct service method.
This information is registered with the appropriate component registry and is used by other processes. 

The required - `FastAPI` - infrastructure to expose those services is started with the call:

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
- multiple - extensible - channel implementations supporting dataclasses and pydantic data models.
- ability to customize http calls with interceptors ( via the AOP abilities )
- `fastapi` based channels covering simple rest endpoints including `msgpack` support.
- `httpx` based clients for dispatching channels and simple rest endpoint with the help of low-level decorators.
- first registry implementation based on `consul`
- support for configurable health checks

As well as the DI and AOP core, all mechanisms are heavily optimized.
A simple benchmark resulted in message roundtrips in significanlty under a ms per call.

Let's see some details

## Service and Component declaration 

Every service needs to inherit from the "tagging interface" `Service`

```python
@service(name="test-service", description="test service")
class TestService(Service):
    @abstractmethod
    def hello(self, message: str) -> str:
        pass
```

The decorator can add a name and a description. If `name` is not set, the class name converted to snake case is used.

A component needs to derive from `Component`:

```python
@component(services =[TestService])
class TestComponent(Component):
    pass
```

The `services` argument references a list of service interfaces that are managed by this component, meaning that they all are 
exposed by the same channels.

`Component` defines the abstract methods:

- `def startup(self) -> None`
   called initially after booting the system

- `def shutdown(self) -> None:`
   called before shutting fown the system

- `def get_addresses(self, port: int) -> list[ChannelAddress]:`
   return  a list of available `ChannelAddress`es that this component exposes

- `def get_status(self) -> ComponentStatus:`
   return the status of this component ( one of the `ComponentStatus` enums `VIRGIN`, `RUNNING`, and `STOPPED`)

- `async def get_health(self) -> HealthCheckManager.Health:`
   return the health status of a component implementation.

## Service and Component implementation

Service implementations implement the corresponding interface and are decorated with `@implementation`

```python
@implementation()
class TestServiceImpl(TestService):
    def __init__(self):
        pass
```

The constructor is required since the instances are managed by the DI framework.

Component implementations derive from the interface and the abstract base class `AbstractComponent`

```python
@implementation()
class TestComponentImpl(AbstractComponent, TestComponent):
    # constructor

    def __init__(self):
        super().__init__()

    # implement Component

    def get_addresses(self, port: int) -> list[ChannelAddress]:
        return [ChannelAddress("dispatch-json", f"http://{Server.get_local_ip()}:{port}")]
```

As a minimum you have to declare the constructor and the `get_addresses` method, that exposes channel addresses

## Health Checks

Every component can declare a HTTP health endpoint and the corresponding logic to compute the current status.

Two additional things have to be done:

- adding a `@health(<endpoint>)` decorator to the class
- implementing the `get_health()` method that returns a `HealthCheckManager.Health`

While you can instantiate the `Health` class directly via
 
```
HealthCheckManager.Health(HealtStatus.OK)
```

it typically makes more sense to let the system execute a number of configured checks and compute the overall result automatically.

For this purpose injectable classes can be decorated with `@health_checks()` that contain methods in turn decorated with `@health_check`

**Example**:

```python
@health_checks()
@injectable()
class Checks:
    def __init__(self):
        pass

    @health_check(fail_if_slower_than=1)
    def check_performance(self, result: HealthCheckManager.Result):
        ... # should be done in under a second

    @health_check(name="check", cache=10)
    def check(self, result: HealthCheckManager.Result):
        ok = ...
        result.set_status(if ok HealthStatus.OK else HealthStatus.ERROR)
```

The methods are expected to have a single parameter of type `HealthCheckManager.Result` that can be used to set the status including detail information with

```
set_status(status: HealthStatus, details = "")
```

When called, the default is already `OK`.

The decorator accepts a couple of parameters:

- `fail_if_slower_than=0` 
   time in `s` that the check is expected to take as a maximum. As soon as the time is exceeded, the status is set to `ERROR`
- `cache`
   time in 's' that the last result is cached. This is done in order to prevent health-checks putting even more strain on a heavily used system.

## Service Manager

`ServiceManager` is the central class used to retrieve service proxies.

```python
def get_service(self, service_type: Type[T], preferred_channel="") -> T
```

- `type` is the requested service interface
- `preferred_channel` the name of the preferred channel.

If not specified, the first registered channel is used, which btw. is a local channel - called `local` -  in case of implementing services.

## Component Registry

The component registry is the place where component implementations are registered and retrieved.

In addition to a `LocalComponentRegistry` ( which is used for testing purposes ) the only implementation is

`ConsulComponentRegistry`

Constructor arguments are

- `port: int` the own port
- `consul: Consul` the consul instance

The component registry is also responsible to execute regular health-checks to track component healths.
As soon as - in our case consul - decides that a component is not alive anymore, it will notify the clients via regular heartbeats about address changes
which will be propagated to channels talking to the appropriate component.

Currently, this only affects the list of possible URLs which are required by the channels!

## Channels

Channels implement the possible transport layer protocols. In the sense of a dynamic proxy, they are the invocation handlers!

Several channels are implemented:

- `dispatch-json`
   channel that dispatches generic `Request` objects via a `invoke` POST-call
- `dispatch-msgpack`
   channel that dispatches generic `Request` objects via a `invoke` POST-call after packing the json with msgpack
- `rest`
  channel that executes regular rest-calls as defined by a couple of decorators.

All channels react on changed URLs as provided by the component registry.

A so called `URLSelector` is used internally to provide URLs for every single call. Two subclasses exist that offer a different logic

- `FirstURLSelector` always returns the first URL of the list of possible URLs
- `RoundRobinURLSelector` switches sequentially between all URLs.

To customize the behavior, an around advice can be implemented easily:

**Example**:
 
```python
@advice
class ChannelAdvice:
    def __init__(self):
        pass

@advice
class ChannelAdvice:
    def __init__(self):
        pass

    @around(methods().named("customize").of_type(Channel))
    def customize_channel(self, invocation: Invocation):
        channel = cast(Channel, invocation.args[0])

        channel.select_round_robin() # or select_first_url()

        return invocation.proceed()
```

### Performance

I benchmarked the different implementations with a recursive dataclass as an argument and return value.
The avg response times - on a local server - where all below 1ms per call.

- rest calls are the slowest ( about 0.7ms )
- dispatching-json 20% faster
- dispatching-msgpack 30% faster

The biggest advantage of the dispatching flavors is, that you don't have to worry about the additional decorators!

### Rest Calls

Invoking rest calls requires decorators and some marker annotations.

**Example**:

```python
@service()
@rest("/api")
class TestService(Service):
    @get("/hello/{message}")
    def hello(self, message: str) -> str:
        pass

    @post("/post/")
    def set_data(self, data: Body(Data)) -> Data:
        pass
```

The decorators `get`,  `put`,  `post` and  `delete` specify the methods.

If the class is decorated with `@rest(<prefix>)`, the corresponding prefix will be appended at the beginning.

Additional annotations are
- `Body` the post body
- `QueryParam`marked for query params

### Intercepting calls

The client side HTTP calling is done with `httpx` instances of type `Httpx.Client` or `Httpx.AsyncClient`.

To add the possibility to add interceptors - for token handling, etc. - the channel base class `HTTPXChannel` defines
the methods `make_client()` and `make_async_client` that can be modified with an around advice.

**Example**:

```python
class InterceptingClient(httpx.Client):
    # constructor

    def __init__(self, *args, **kwargs):
        self.token_provider = ...
        super().__init__(*args, **kwargs)

    # override

    def request(self, method, url, *args, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token_provider()}"
        kwargs["headers"] = headers

        return super().request(method, url, *args, **kwargs)
    
@advice
class ChannelAdvice:
    def __init__(self):
        pass

    @around(methods().named("make_client").of_type(HTTPXChannel))
    def make_client(self, invocation: Invocation):
        return InterceptingClient()
```

## FastAPI server

In order to expose components via HTTP, the corresponding infrastructure in form of a FastAPI server needs to be setup. 


```python
@module()
class Module():
    def __init__(self):
        pass
    
 server = FastAPIServer(host="0.0.0.0", port=8000)

 environment = server.boot(Module) # will start the http server
```

This setup will also expose all service interfaces decorated with the corresponding http decorators!
No need to add any FastAPI decorators, since the mapping is already done internally! 

## Implementing Channels

To implement a new channel, you only need to derive from one of the possible base classes ( `Channel` or `HTTPXChannel` that already has a `httpx` client)
and decorate it with `@channel(<name>)`

The main methods to implement are `ìnvoke` and `ìnvoke_async`

**Example**:

```python
@channel("fancy")
class FancyChannel(Channel):
    # constructor

    def __init__(self):
        super().__init__()

    # override

    def invoke(self, invocation: DynamicProxy.Invocation):
        return ...
    
     async def invoke_async(self, invocation: DynamicProxy.Invocation):
        return await ...
        
```

# Version History

**0.10.0**

- first release version





