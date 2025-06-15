# aspyx

![Pylint](https://github.com/coolsamson7/aspyx/actions/workflows/pylint.yml/badge.svg)
![Build Status](https://github.com/coolsamson7/aspyx/actions/workflows/ci.yml/badge.svg)
![Python Versions](https://img.shields.io/badge/python-3.9%20|%203.10%20|%203.11%20|%203.12-blue)
![License](https://img.shields.io/github/license/coolsamson7/aspyx)
![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)
[![PyPI](https://img.shields.io/pypi/v/aspyx)](https://pypi.org/project/aspyx/)

## Table of Contents

- [Motivation](#motivation)
- [Introduction](#introduction)
- [Installation](#installation)
- [Registration](#registration)
  - [Class](#class)
  - [Class Factory](#class-factory)
  - [Method](#method)
  - [Conditional](#conditional)
- [Environment](#environment)
  - [Definition](#definition)
  - [Retrieval](#retrieval)
- [Instantiation logic](#instantiation-logic)
  - [Injection Methods](#injection-methods)
  - [Lifecycle Methods](#lifecycle-methods)
  - [Post Processors](#post-processors)
- [Custom scopes](#custom-scopes)
- [AOP](#aop)
- [Configuration](#configuration)
- [Reflection](#reflection)
- [Version History](#version-history)

# Motivation

While working on some AI related topics in Python, i required a simple DI framework. 
Looking at the existing solutions - there are quite a number of - i was not quite happy. Either the solutions 
lacked functionality - starting with that usually aop and di are separate libraries -, that i am accustomed to from other languages, or the API was in my mind too clumsy and "technical".

So, why not develop one on my own...Having done that in other languages previously, the task was not that hard, and last but not least...it is fun :-) 

# Introduction

Aspyx is a small python libary, that adds support for both dependency injection and aop.

The following di features are supported 
- constructor and setter injection
- possibility to define custom injections
- post processors
- support for factory classes and methods
- support for eager construction
- support for scopes singleton, request and thread
- possibilty to add custom scopes
- conditional registration of classes and factories 
- lifecycle events methods `on_init`, `on_destroy`
- bundling of injectable objects according to their module location including recursive imports and inheritance
- instatiation of - possibly multiple - container instances - so called environments -  that manage the lifecylce of related objects
- filtering of classes by associating "features" sets to environment ( similar to spring profiles )
- hierarchical environments

With respect to aop:
- support for before, around, after and error aspects 
- sync and async method support
- `synchronized` decorator that adds locking to methods

The library is thread-safe!

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

    @on_init() # a lifecycle callback called after the constructor and all possible injections
    def init(self):
        ...


# this class will register all - specifically decorated - classes and factories in the own module
# In this case Foo and Bar

@environment()
class SampleEnvironment:
    def __init__(self):
        pass

# go, forrest

environment = Environment(SampleEnvironment)

bar = env.get(Bar)

bar.foo.hello("world")
```

The concepts should be pretty familiar as well as the names which are a combination of Spring and Angular names :-)

Let's add some aspects...

```python

@advice
class SampleAdvice:
    def __init__(self): # could inject additional stuff
        pass

    @before(methods().named("hello").of_type(Foo))
    def call_before(self, invocation: Invocation):
        print("before Foo.hello(...)")

    @error(methods().named("hello").of_type(Foo))
    def call_error(self, invocation: Invocation):
        print("error Foo.hello(...)")
        print(invocation.exception)

    @around(methods().named("hello"))
    def call_around(self, invocation: Invocation):
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

# Installation

Just install from PyPI with 

`pip install aspyx`

The library is tested with all Python version >= 3.9

# Registration

Different mechanisms are available that make classes eligible for injection

## Class

Any class annotated with `@injectable` is eligible for injection

**Example**: 

```python
@injectable()
class Foo:
    def __init__(self):
        pass
```
Please make sure, that the class defines a local constructor, as this is required to determine injected instances. 
All referenced types will be injected by the environemnt. 

Only eligible types are allowed, of course!

The decorator accepts the keyword arguments
- `eager : boolean`  
  if `True`, the container will create the instances automatically while booting the environment. This is the default.
- `scope: str`  
  the name of a - registered - scope which will determine how often instances will be created.

 The following scopes are implemented out of the box:
 - `singleton`  
   objects are created once inside an environment and cached. This is the default.
 - `request`  
   objects are created on every injection request
 - `thread`  
   objects are created and cached with respect to the current thread.

 Other scopes - e.g. session related scopes - can be defined dynamically. Please check the corresponding chapter.

## Class Factory

Classes that implement the `Factory` base class and are annotated with `@factory` will register the appropriate classes returned by the `create` method.

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

## Conditional

All `@injectable` declarations can be supplemented with 

```python
@conditional(<condition>, ..., <condition>)
```

decorators that act as filters in the context of an environment.

Valid conditions are created by:
- `requires_class(clazz: Type)`  
  the injectable is valid, if the specified class is registered as well.
- `requires_feature(feature: str)`  
  the injectable is valid, if the environment defines the specified feature.

# Environment

## Definition

An `Environment` is the container that manages the lifecycle of objects. The set of classes and instances is determined by a constructor argument that controls the class registry.

**Example**: 
```python
@environment()
class SampleEnvironment:
    def __init__(self):
        pass

environment = Environment(SampleEnvironment)
```

The default is that all eligible classes, that are implemented in the containing module or in any submodule will be managed.

By adding the parameter `features: list[str]`, it is possible to filter injectables by evaluating the corresponding `@conditional` decorators.

**Example**: 
```python

@injectable()
@conditional(requires_feature("dev"))
class DevOnly:
     def __init__(self):
        pass

@environment()
class SampleEnvironmen()):
    def __init__(self):
        pass

environment = Environment(SampleEnvironment, features=["dev"])
```


By adding an `imports: list[Type]` parameter, specifying other environment types, it will register the appropriate classes recursively.

**Example**: 
```python
@environment()
class SampleEnvironmen(imports=[OtherEnvironment])):
    def __init__(self):
        pass
```

Another possibility is to add a parent environment as an `Environment` constructor parameter

**Example**: 
```python
rootEnvironment = Environment(RootEnvironment)
environment = Environment(SampleEnvironment, parent=rootEnvironment)
```

The difference is, that in the first case, class instances of imported modules will be created in the scope of the _own_ environment, while in the second case, it will return instances managed by the parent.

The method

```shutdown()```

is used when a container is not needed anymore. It will call any `on_destroy()` of all created instances.

## Retrieval

```python
def get(type: Type[T]) -> T
```

is used to retrieve object instances. Depending on the respective scope it will return either cached instances or newly instantiated objects.

The container knows about class hierarchies and is able to `get` base classes, as long as there is only one implementation. 

In case of ambiguities, it will throw an exception.

Please be aware, that a base class are not _required_ to be annotated with `@injectable`, as this would mean, that it could be created on its own as well. ( Which is possible as well, btw. ) 

# Instantiation logic

Constructing a new instance involves a number of steps executed in this order
- Constructor call  
  the constructor is called with the resolved parameters
- Advice injection  
  All methods involving aspects are updated
- Lifecycle methods   
  different decorators can mark methods that should be called during the lifecycle ( here the construction ) of an instance.
  These are various injection possibilities as well as an optional final `on_init` call
- PostProcessors  
  Any custom post processors, that can add isde effects or modify the instances

## Injection methods

Different decorators are implemented, that call methods with computed values

- `@inject`  
   the method is called with all resolved parameter types ( same as the constructor call)
- `@inject_environment`  
   the method is called with the creating environment as a single parameter
- `@inject_value()`  
   the method is called with a resolved configuration value. Check the corresponding chapter

**Example**:
```python
@injectable()
class Foo:
    def __init__(self):
        pass

    @inject_environment()
    def initEnvironment(self, env: Environment):
        ...

    @inject()
    def set(self, baz: Baz) -> None:
        ...
```

## Lifecycle methods

It is possible to mark specific lifecyle methods. 
- `@on_init()` 
   called after the constructor and all other injections.
- `@on_running()` 
   called an environment has initialized all eager objects.
- `@on_destroy()` 
   called during shutdown of the environment

## Post Processors

As part of the instantiation logic it is possible to define post processors that execute any side effect on newly created instances.

**Example**: 
```python
@injectable()
class SamplePostProcessor(PostProcessor):
    def process(self, instance: object, environment: Environment):
        print(f"created a {instance}")
```

Any implementing class of `PostProcessor` that is eligible for injection will be called by passing the new instance.

Please be aware, that a post processor will only handle instances _after_ its _own_ registration.

As injectables within a single file will be handled in the order as they are declared, a post processor will only take effect for all classes after its declaration!

# Custom scopes

As explained, available scopes are "singleton" and "request".

It is easily possible to add custom scopes by inheriting the base-class `Scope`, decorating the class with `@scope(<name>)` and overriding the method `get`

```python
def get(self, provider: AbstractInstanceProvider, environment: Environment, argProvider: Callable[[],list]):
```

Arguments are:
- `provider` the actual provider that will create an instance
- `environment`the requesting environment
- `argPovider` a function that can be called to compute the required arguments recursively

**Example**: The simplified code of the singleton provider ( disregarding locking logic )

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

# AOP

It is possible to define different Aspects, that will be part of method calling flow. This logic fits nicely in the library, since the DI framework controls the instantiation logic and can handle aspects within a regular post processor. 

Advice classes need to be part of classes that add a `@advice()` decorator and can define methods that add aspects.

```python
@advice()
class SampleAdvice:
    def __init__(self):  # could inject dependencies
        pass

    @before(methods().named("hello").of_type(Foo))
    def call_before(self, invocation: Invocation):
        # arguments: invocation.args
        print("before Foo.hello(...)")

    @error(methods().named("hello").of_type(Foo))
    def call_error(self, invocation: Invocation):
        print("error Foo.hello(...)")
        print(invocation.exception)

    @around(methods().named("hello"))
    def call_around(self, invocation: Invocation):
        print("around Foo.hello()")

        return invocation.proceed()  # will leave a result in invocation.result or invocation.exception in case of an exception
```

Different aspects - with the appropriate decorator - are possible:
- `before`  
   methods that will be executed _prior_ to the original method
- `around`  
   methods that will be executed _around_ to the original method giving it the possibility to add side effects or even change the parameters.
- `after`  
   methods that will be executed _after_ to the original method
- `error`  
   methods that will be executed in case of a caught exception

All methods are expected to have single `Invocation` parameter, that stores

- `func` the target function
- `args` the suppliued args
- `kwargs` the keywords args
- `result` the result ( initially `None`)
- `exception` a possible caught excpetion ( initially `None`)

It is essential for `around` methods to call `proceed()` on the invocation, which will call the next around method in the chain and finally the original method.
If the `proceed` is called with parameters, they will replace the original parameters! 

**Example**: Parameter modifications

```python
@around(methods().named("say"))
def call_around(self, invocation: Invocation):
    args = [invocation.args[0],invocation.args[1] + "!"] # 0 is self!

    return invocation.proceed(*args)
```

The argument list to the corresponding decorators control which methods are targeted by the advice.

A fluent interface is used describe the mapping. 
The parameters restrict either methods or classes and are constructed by a call to either `methods()` or `classes()`.

Both add the fluent methods:
- `of_type(type: Type)`  
   defines the matching classes
- `named(name: str)`  
   defines method or class names
- `that_are_async()`  
   defines async methods
- `matches(re: str)`  
   defines regular expressions for methods or classes
- `decorated_with(type: Type)`  
   defines decorators on methods or classes

The fluent methods `named`, `matches` and `of_type` can be called multiple times!

**Example**: react on both `transactional` decorators on methods or classes

```python
@injectable()
class TransactionAdvice:
    def __init__(self):
        pass

    @around(methods().decorated_with(transactional), classes().decorated_with(transactional))
    def establish_transaction(self, invocation: Invocation):
        ...
```

With respect to async methods, you need to make sure, to replace a `proceeed()` with a `await proceed_async()` to have the overall chain async!

A handy decorator `@synchronized` is implemented that automatically synchronizes methods with a `RLock` associated with the instance.

# Configuration 

It is possible to inject configuration values, by decorating methods with `@inject-value(<name>)` given a configuration key.

```python
@injectable()
class Foo:
    def __init__(self):
        pass

    @inject_value("HOME")
    def inject_home(self, os: str):
        ...
```

If required a coercion will be executed.

This concept relies on a central object `ConfigurationManager` that stores the overall configuration values as provided by so called configuration sources that are defined as follows.

```python
class ConfigurationSource(ABC):
    def __init__(self):
        pass

   ...

    @abstractmethod
    def load(self) -> dict:
```

The `load` method is able to return a tree-like structure by returning a `dict`.

Configuration variables are retrieved with the method

```python
def get(self, path: str, type: Type[T], default : Optional[T]=None) -> T:
 ```

- `path`  
  a '.' separated path
- `type`  
  the desired type
- `default`  
  a default, if no value is registered

Sources can be added dynamically by registering them.

**Example**:
```python
@injectable()
class SampleConfigurationSource(ConfigurationSource):
    def __init__(self):
        super().__init__()

    def load(self) -> dict:
        return {
            "a": 1, 
            "b": {
                "d": "2", 
                "e": 3, 
                "f": 4
                }
            }
```

Two specific source are already implemented:
- `EnvConfigurationSource`  
   reads the os environment variables
- `YamlConfigurationSource`  
   reads a specific yaml file

Typically you create the required configuration sources in an environment class, e.g.

```python
@environment()
class SampleEnvironment:
    # constructor

    def __init__(self):
        pass

    @create()
    def create_env_source(self) -> EnvConfigurationSource:
        return EnvConfigurationSource()

    @create()
    def create_yaml_source(self) -> YamlConfigurationSource:
        return YamlConfigurationSource("config.yaml")
```

# Reflection

As the library heavily relies on type introspection of classes and methods, a utility class `TypeDescriptor` is available that covers type information on classes. 

After beeing instatiated with

```python
TypeDescriptor.for_type(<type>)
```

it offers the methods
- `get_methods(local=False)`  
   return a list of either local or overall methods
- `get_method(name: str, local=False)`  
   return a single either local or overall method
- `has_decorator(decorator: Callable) -> bool`  
   return `True`, if the class is decorated with the specified decorator
- `get_decorator(decorator) -> Optional[DecoratorDescriptor]`  
   return a descriptor covering the decorator. In addition to the callable, it also stores the supplied args in the `args` property

The returned method descriptors offer:
- `param_types`  
   list of arg types
- `return_type`  
   the return type
- `has_decorator(decorator: Callable) -> bool` 
   return `True`, if the method is decorated with the specified decorator
- `get_decorator(decorator: Callable) -> Optional[DecoratorDescriptor]`  
   return a descriptor covering the decorator. In addition to the callable, it also stores the supplied args in the `args` property

The management of decorators in turn relies on another utility class `Decorators` that caches decorators.

Whenver you define a custom decorator, you will need to register it accordingly.

**Example**:
```python
def transactional(scope):
    def decorator(func):
        Decorators.add(func, transactional, scope) # also add _all_ parameters in order to cache them
        return func

    return decorator
```


# Version History

**1.0.1**

- some internal refactorings

**1.1.0**

- added `@on_running()` callback
- added `thread` scope

**1.2.0**

- added `YamlConfigurationSource`

**1.2.1**


      

