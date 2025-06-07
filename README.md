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

@injectable()
class Foo:
    def __init__(self):
        pass

@injectable()
class Bar:
    def __init__(self, foo: Foo):
        self.foo = foo

    @on_init()
    def init(self):
        ...

    @on_destroy()
    def destroy(self):
        ...

# this class will 

@configuration()
class Configuration:
    # constructor

    def __init__(self):
        pass

# go, forrest

environment = Environment(Configuration)

bar = env.get(Bar)

```
