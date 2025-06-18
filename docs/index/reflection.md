
# Reflection

As the library heavily relies on type introspection of classes and methods, a utility class `TypeDescriptor` is available that covers type information on classes. 

After being instantiated with

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

The returned method descriptors provide:

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
