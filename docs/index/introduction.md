
# Motivation

While working on AI-related projects in Python, I was looking for a dependency injection (DI) framework. After evaluating existing options, my impression was that the most either lacked key features — such as integrated AOP — or had APIs that felt overly technical and complex, which made me develop a library on my own with the following goals

- bring both DI and AOP features together in a lightweight library,
- be as minimal invasive as possible,
- offering mechanisms to easily extend and customize features without touching the core,
- while still offering a _simple_ and _readable_ api that doesnt overwhelm developers and only requires a minimum initial learning curve

Especially the AOP integration definitely makes sense, as 

- aspects on their own also usually require a context, which in a DI world is simply injected, 
- and also should cover only objects of the owning container and _not_ act globally.

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
- bundling of injectable objects according to their module location including recursive imports and inheritance
- instantiation of - possibly multiple - container instances - so called environments - that manage the lifecycle of related objects
- hierarchical environments

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
I really don't think that this is too complex, and only for enterprise applications, isn`t it?

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