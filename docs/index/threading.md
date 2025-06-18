
# Threading

A handy decorator `@synchronized` in combination with the respective advice is implemented that automatically synchronizes methods with a `RLock` associated with the instance.

**Example**:
```python
@injectable()
class Foo:
    def __init__(self):
        pass

    @synchronized()
    def execute_synchronized(self):
        ...
```