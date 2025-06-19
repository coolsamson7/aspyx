"""
The AOP module gives you the possibility to define aspects that will participate in method execution flows.

**Example**: all method executions of methods named "foo" will include a `before` aspect, that will be executed before the original method

```python
@advice
class Advice:
   @before(methods().named("foo"))
   def before_call(self, invocation: Invocation):
      ...

```

Note, that this requires that both the advice and the targeted methods need to be managed by an environment.
"""
from .aop import before, after, classes, around, error, advice, methods, Invocation, AspectTarget
__all__ = [
    "before",
    "after",
    "around",
    "error",
    "advice",
    "classes",
    "methods",
    "Invocation",
    "AspectTarget"
]
