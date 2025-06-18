
# AOP

It is possible to define different aspects, that will be part of method calling flow. This logic fits nicely in the library, since the DI framework controls the instantiation logic and can handle aspects within a regular post processor. 

Advice classes need to be part of classes that add a `@advice()` decorator and can define methods that add aspects.

```python
@advice
class SampleAdvice:
    def __init__(self):  # could inject dependencies
        pass

    @before(methods().named("hello").of_type(Foo))
    def call_before(self, invocation: Invocation):
        # arguments: invocation.args and invocation.kwargs
        ...

     @after(methods().named("hello").of_type(Foo))
    def call_after(self, invocation: Invocation):
        # arguments: invocation.args and invocation.kwargs
        ...

    @error(methods().named("hello").of_type(Foo))
    def call_error(self, invocation: Invocation):
         # error: invocation.exception
        ...

    @around(methods().named("hello"))
    def call_around(self, invocation: Invocation):
        try:
            ...
            return invocation.proceed()  # will leave a result in invocation.result or invocation.exception in case of an exception
        finally:
            ...
```

Different aspects - with the appropriate decorator - are possible:
- `before`  
   methods that will be executed _prior_ to the original method
- `around`  
   methods that will be executed _around_ to the original method allowing you to add side effects or even modify parameters.
- `after`  
   methods that will be executed _after_ to the original method
- `error`  
   methods that will be executed in case of a caught exception

The different aspects can be supplemented with an `@order(<prio>)` decorator that controls the execution order based on the passed number. Smaller values get executed first. 

All methods are expected to have single `Invocation` parameter, that stores

- `func` the target function
- `args` the supplied args ( including the `self` instance as the first element)
- `kwargs` the keywords args
- `result` the result ( initially `None`)
- `exception` a possible caught exception ( initially `None`)

⚠️ **Attention:** It is essential for `around` methods to call `proceed()` on the invocation, which will call the next around method in the chain and finally the original method.

If the `proceed` is called with parameters, they will replace the original parameters! 

**Example**: Parameter modifications

```python
@around(methods().named("say"))
def call_around(self, invocation: Invocation):
    return invocation.proceed(invocation.args[0], invocation.args[1] + "!") # 0 is self!
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
@advice
class TransactionAdvice:
    def __init__(self):
        pass

    @around(methods().decorated_with(transactional), classes().decorated_with(transactional))
    def establish_transaction(self, invocation: Invocation):
        ...
```

With respect to async methods, you need to make sure, to replace a `proceed()` with a `await proceed_async()` to have the overall chain async!
