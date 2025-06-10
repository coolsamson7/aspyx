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
from aspyx.di import injectable, on_init, on_destroy, environment, Environment


@injectable()
class Foo:
    def __init__(self):
        pass

    def hello(msg: str):
        print(f"hello {msg}")


@injectable()  # eager and singleton by default
class Bar:
    def __init__(self, foo: Foo): # will inject the Foo dependency
        self.foo = foo

    @on_init() # a lifecycle callback called  after the constructor
    def init(self):
        ...


# this class will register all - specifically decorated - classes and factories in the own module
# In this case Foo and Bar

@environment()
class SampleEnvironment:
    # constructor

    def __init__(self):
        pass


# go, forrest

environment = SampleEnvironment(Configuration)

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

Let's look at the details

# Registration

Different mechanisms are available that make classes 'injectible' by the container 

## Class

Classes annotated with `@injectable` are registered

**Example**: 

```python
@injectable()
class Foo:
    def __init__(self):
        pass
```
 Please make sure, that the class defines a constructor, as this is required to determine injected instances. 

 The constructor can only define parameter types that are known as well to the container! 


 The decorator accepts the keyword arguments
 - `eager=True` if `True, the container will create the instances while booting automatically
 - `scope="singleton"` defines how often insatcens will be created. `singleton` will cerate it only once, while `request` will recreate it on every inejction request

 Other scopes can be defined. Please check the corresponding chapter.

## Class Factory

Classes that implement the `Factory` base class and are annotated wirh `@factory` will register the appropriate class.

**Example**: 
```python
@factory()
class TestFactory(Factory[Foo]):
    def __init__(self):
        pass

    def create(self) -> Foo:
        return Foo()
```

As in `@injectable`, the same arguments are possible.

## Method 

Any `injectable` can define methods decorated with `@create()`, that will create appropriate instances.

**Example**: 
```python
@injectable()
class Foo:
    def __init__(self):
        pass

    @create(scope="request")
    def create(self) -> Baz:
        return Baz()
```

 The same arguments as in `@injectable` are possible.

# Environment

An Environment is the container that manages the lifecycle of objects

**Example**: 
```python
@Environment()
class SampleEnvironment:
    def __init__(self):
        pass
```

The default is that all registered classes, that are implemented in the containing module or in any submodules will be managed.

By adding an `imports: list[Type]` parameter, specifying other environment types, it will inherit the appropriate classes.

**Example**: 
```python
@Environment()
class SampleEnvironmen(imports=[OtherEnvironment])):
    def __init__(self):
        pass
```


```python
def get(type: Type[T]) -> T
```

is used to retrieve object instances.

# Lifecycle methods

It is possible to decdlare methods that will be called from the conatiner
- `@on_init()` called after the constructor 
- `@on_destroy()` called after the container has shutdown

# Custom scopes

As explained, available scopes are "singleton" and "request".

It is easily possible to add custom scopes by inheriting the base-class `Scope`, decorating the class with `@scope(<name>)` and overriding the method `get`

```python
def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
```

Arguments are:
- `provider` the actial provider that will create an instance
- `environment`the requsting environment
- `argPovider` a function that can be called to compute the required arguments recursively

**Example**: The code of the singleton provider

```python
@scope("singleton")
class SingletonScope(Scope):
    # constructor

    def __init__(self):
        super().__init__()

        self.value = None

    # override

    def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
        if self.value is None:
            self.value = provider.create(environment, *argProvider())

        return self.value
```

# Aspects

TODO

# Configuration 

```python
@inejctable()
class Foo:
    def __init__(self):
        pass

    @value("OS")
    def inject_value(self, os: str):
        ...
      

