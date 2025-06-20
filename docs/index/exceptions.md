
# Exceptions

The class `ExceptionManager` is used to collect dynamic handlers for specific exceptions and is able to dispatch to the concrete functions given a specific exception.

The handlers are declared by decorating a class with `@exception_handler` and decorating specific methods with `@handle`

**Example**:
```python
class DerivedException(Exception):
    def __init__(self):
        pass

@module()
class SampleModule:
    # constructor

    def __init__(self):
        pass

    @create()
    def create_exception_manager(self) -> ExceptionManager:
        return ExceptionManager()

@injectable()
@exception_handler()
class TestExceptionHandler:
    def __init__(self):
        pass

    @handle()
    def handle_derived_exception(self, exception: DerivedException):
        ExceptionManager.proceed()

    @handle()
    def handle_exception(self, exception: Exception):
        pass

    @handle()
    def handle_base_exception(self, exception: BaseException):
        pass


@advice
class ExceptionAdvice:
    def __init__(self, exceptionManager: ExceptionManager):
        self.exceptionManager = exceptionManager

    @error(methods().of_type(Service))
    def handle_error(self, invocation: Invocation):
        self.exceptionManager.handle(invocation.exception)

environment =  Environment(SampleModule)

environment.get(ExceptionManager).handle(DerivedException())
```

The exception maanger will first call the most appropriate method. 

Any 

`ExceptionManager.proceed()` 

will in turn call the next most applicable method ( if available).

Together with a simple around advice we can now add exception handling to any method:

**Example**:
```python
@injectable()
class Service:
    def __init__(self):
        pass

    def throw(self):
        raise DerivedException()

@advice
class ExceptionAdvice:
    def __init__(self, exception_manager: ExceptionManager):
        self.exception_manager = exception_manager

    @error(methods().of_type(Service))
    def handle_error(self, invocation: Invocation):
        self.exception_manager.handle(invocation.exception)
```
