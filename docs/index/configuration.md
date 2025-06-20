
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

If required type coercion will be applied.

Configuration values are managed centrally using a `ConfigurationManager`, which aggregates values from various configuration sources that are defined as follows.

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
def get(self, path: str, type: Type[T], default : Optional[T]=None) -> T
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
@module()
class SampleModule:
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
