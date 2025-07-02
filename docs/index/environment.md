
# Environment

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
⚠️ **Attention:** Please make sure, that the class defines a local constructor, as this is _required_ to determine injected instances. 
All referenced types will be injected by the environment. 

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

`@factory` accepts the same arguments as `@injectable`

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

`@create`accepts the same arguments as `@injectable`

The respective method can have any number of additional - injectable - arguments.
This is handy, if the parameters are either required, or just to express a dependency, that will influence the order of instantiation.

**Example**:
```python
@module(imports=[ServiceModule])
class Module:
    def __init__(self):
        pass

    @create()
    def create_yaml_source(self) -> YamlConfigurationSource:
        return YamlConfigurationSource(f"{Path(__file__).parent}/config.yaml")

    @create()
    def create_registry(self, source: YamlConfigurationSource) -> ConsulComponentRegistry:
        return ConsulComponentRegistry(Server.port, consul.Consul(host="localhost", port=8000))
```
This will make sure, that the service classes already can access the yaml properties!


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

An `Environment` is the container that manages the lifecycle of objects. 
The set of classes and instances is determined by a 
constructor type argument called `module`.

**Example**: 
```python
@module()
class SampleModule:
    def __init__(self):
        pass
```

A module is a regular injectable class decorated with `@module` that controls the discovery of injectable classes, by filtering classes according to their module location relative to this class. 
  All eligible classes, that are implemented in the containing module or in any submodule will be managed.

In a second step the real container - the environment - is created based on a module:

**Example**: 
```python
environment = Environment(SampleModule)
```

The container will import the module and its children automatically. No need to add artificial import statements!

By adding the parameter `features: list[str]`, it is possible to filter injectables by evaluating the corresponding `@conditional` decorators.

**Example**: 
```python

@injectable()
@conditional(requires_feature("dev"))
class DevOnly:
     def __init__(self):
        pass

@module()
class SampleModule():
    def __init__(self):
        pass

environment = Environment(SampleModule, features=["dev"])
```


By adding an `imports: list[Type]` parameter, specifying other environment types, it will register the appropriate classes recursively.

**Example**: 
```python
@module()
class SampleModule(imports=[OtherModule]):
    def __init__(self):
        pass
```

Another possibility is to add a parent environment as an `Environment` constructor parameter

**Example**: 
```python
rootEnvironment = Environment(RootModule)

environment = Environment(SampleModule, parent=rootEnvironment)
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

Note that a base class are not _required_ to be annotated with `@injectable`, as this would mean, that it could be created on its own as well. ( Which is possible as well, btw. ) 

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
  Any custom post processors, that can add side effects or modify the instances

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
   called after an environment has initialized completely ( e.g. created all eager objects ).
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

Note that a post processor will only handle instances _after_ its _own_ registration.

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
- `argProvider` a function that can be called to compute the required arguments recursively

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
