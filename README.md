# aspyx

Aspyx is a small python libary, that adds support for both dependency injection and aop.

The following features are supported 
- constructor injection
- method injection
- factory classes and methods
- support for eager construction
- support for singletons
- lifecycle events methods
- bundling of injectable object sets by configuration classes including recursive imports
- container instances that relate to configration classes and manage the lifecylce of related objects
- hierarchical containers

Let's look at a simple example

```python
from aspyx.di import injectable, on_init, on_destroy, configuration, Environment

@injectable(singleton=False)
class Foo:
    def __init__(self):
        pass

    def hello(msg: str):
        print(f"hello {msg}")

@injectable() # eager and singleton by default
class Bar:
    def __init__(self, foo: Foo):
        self.foo = foo

    @on_init()
    def init(self):
        ...

    @on_destroy()
    def destroy(self):
        ...

# this class will register all - specifically decorated - classes and factories in the own module
# In this case Foo and Bar

@configuration()
class Configuration:
    # constructor

    def __init__(self):
        pass

# go, forrest

environment = Environment(Configuration)

bar = env.get(Bar)
bar.foo.hello("Andi")
```

The concepts should be pretty familiar , as well as the names which are a combination of Spring and Angular names :-)

Let's add some aspects...

```python
@advice
class SampleAdvice:
    def __init__(self):
        pass

    @before(methods().named("hello").ofType(Foo))
    def callBefore(self, invocation: Invocation):
        print("before Foo.hello(...)")

    @error(methods().named("hello").ofType(Foo))
    def callError(self, invocation: Invocation):
        print("error Foo.hello(...)")
        print(invocation.error)

    @around(methods().named("hello"))
    def callAround(self, invocation: Invocation):
        print("around Foo.hello()")

        return invocation.proceed()
```

The invocation parameter stores the complete context of the current execution, which are
- the method
- args
- kwargs
- the result
- the possible caught error


