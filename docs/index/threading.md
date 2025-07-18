
# Threading

## ThreadLocal

The class `ThreadLocal` is a simple generic wrapper around `threading.local`

After creating an instance with `ThreadLocal[type]()` you can use the methods:
- `get(self) -> Optional[T]`
- `set(self, value: T) -> None`
- `clear(self)`

An optional constructor argument serves as a factory that is called in the `get` methiod whenever no value i set.

## ContextLocal

A similar class `ContextLocal` is implemented that uses `ContextVar`s.
In addition it defines a `use` method as a `@contextmanager`

## Synchronized

A handy decorator `@synchronized` in combination with the respective advice is implemented that automatically synchronizes methods with a `RLock` associated with the instance.

**Example**:
```python
@injectable()
class Foo:
    @synchronized()
    def execute_synchronized(self):
        ...
```