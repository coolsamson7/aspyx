
# Introduction

Aspyx is a lightweight Python library that provides both Dependency Injection (DI) and Aspect-Oriented Programming (AOP) support.

The following DI features are supported:

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

bar = env.get(Bar)

bar.foo.hello("world")
```

The concepts should be pretty familiar as well as the names as they are inspired by both Spring and Angular.

Let's add some aspects...

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

The invocation parameter stores the complete context of the current execution, which are
- the method
- args
- kwargs
- the result
- the possible caught error

Let's look at the details