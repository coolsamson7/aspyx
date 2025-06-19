
# Motivation

While working on AI-related projects in Python, I was looking for a dependency injection (DI) framework. After evaluating existing options, my impression was that the most either lacked key features — such as integrated AOP — or had APIs that felt overly technical and complex, which led me to develop a library on my own with the following goals

- bring both DI and AOP features together in a lightweight library,
- be as minimal invasive as possible,
- offering mechanisms to easily extend and customize features without touching the core,
- while still offering a _simple_ and _readable_ api that doesnt overwhelm developers and keeps the initial learning curve low.

The AOP integration, in particular, makes a lot of sense because:

- Aspects typically require context, which is naturally provided through DI,
- And they should only apply to objects managed by the container, rather than acting globally.

# Overview

Aspyx is a lightweight Python library - just about 2t loc - that provides both Dependency Injection (DI) and Aspect-Oriented Programming (AOP) support.

The following features are supported:

- constructor and setter injection
- injection of configuration variables
- possibility to define custom injections
- post processors
- support for factory classes and methods
- support for eager and lazy construction
- support for scopes singleton, request and thread
- possibility to add custom scopes
- conditional registration of classes and factories ( aka profiles in spring )
- lifecycle events methods `on_init`, `on_destroy`, `on_running`
- Automatic discovery and bundling of injectable objects based on their module location, including support for recursive imports
- Instantiation of one or possible more isolated container instances — called environments — each managing the lifecycle of a related set of objects,
 - Support for hierarchical environments, enabling structured scoping and layered object management.

With respect to AOP:

- support for before, around, after and error aspects 
- simple fluent interface to specify which methods are targeted by an aspect
- sync and async method support

The library is thread-safe and heavily performance optimized as most of the runtime information is precomputed and cached!

Let's look at a simple example

```python
from aspyx.di import injectable, on_init, on_destroy, environment, Environment

@injectable()
class Foo:
    def __init__(self):
        pass

    def hello(self, msg: str):
        print(f"hello {msg}")

@injectable()  # eager and singleton by default
class Bar:
    def __init__(self, foo: Foo): # will inject the Foo dependency
        self.foo = foo

    @on_init() # a lifecycle callback called after the constructor and all possible injections
    def init(self):
        ...

# this class will register all - specifically decorated - classes and factories in the own module
# In this case Foo and Bar

@environment()
class SampleEnvironment:
    def __init__(self):
        pass

# create environment

environment = Environment(SampleEnvironment)

# fetch an instance

bar = environment.get(Bar)

bar.foo.hello("world")
```

The concepts should be pretty familiar as well as the names as they are inspired by both Spring and Angular.

Let's have some fun and add some aspects...

```python

@advice
class SampleAdvice:
    def __init__(self): # could inject additional stuff
        pass

    @before(methods().named("hello").of_type(Foo))
    def call_before(self, invocation: Invocation):
        ...

    @error(methods().named("hello").of_type(Foo))
    def call_error(self, invocation: Invocation):
        ... # exception accessible in invocation.exception

    @around(methods().named("hello"))
    def call_around(self, invocation: Invocation):
        ...
        return invocation.proceed()
```

Especially the around and error aspects are usefull. Think of transactional support or general exception handling logic.

While features like DI and AOP are often associated with enterprise applcations, this example hopefully demonstrates that they work just as well in small- to medium-sized projects—without introducing significant overhead—while still providing powerful tools for achieving clean architecture, resulting in maintainable and easily testable code.