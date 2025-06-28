"""
health checks
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Type, Optional

from aspyx.di import Providers, ClassInstanceProvider, injectable, Environment, inject_environment, on_init
from aspyx.reflection import Decorators, TypeDescriptor


def health_checks():
    """
    Instances of classes that are annotated with @injectable can be created by an Environment.
    """
    def decorator(cls):
        Decorators.add(cls, health_checks)

        Providers.register(ClassInstanceProvider(cls, True, "singleton")) # TODO what if it is alread registered?

        HealthCheckManager.types.append(cls)

        return cls

    return decorator

def check(name="", cache = 0, fail_if_slower_than = 0):
    """
    Methods annotated with `@on_init` will be called when the instance is created."""
    def decorator(func):
        Decorators.add(func, check, name, cache, fail_if_slower_than)
        return func

    return decorator

class HealthStatus(Enum):
    OK = 1
    WARNING = 2
    ERROR = 3

    def __str__(self):
        return self.name


@injectable()
class HealthCheckManager:
    # local classes

    class Check:
        def __init__(self, name: str, cache: int, fail_if_slower_than: int, instance: Any, callable: Callable):
            self.name = name
            self.cache = cache
            self.callable = callable
            self.instance = instance
            self.fail_if_slower_than = fail_if_slower_than
            self.last_check = 0

            self.last_value : Optional[HealthCheckManager.Result] = None

        def run(self, result: HealthCheckManager.Result):
            now = time.time()

            if self.cache > 0 and self.last_check is not None and now - self.last_check < self.cache:
                result.copy_from(self.last_value)
            else:
                self.last_check = now
                self.last_value = result
                self.callable(self.instance, result)

                spent = time.time() - now

                if result.status == HealthStatus.OK:
                    if 0 < self.fail_if_slower_than < spent:
                        result.status = HealthStatus.ERROR
                        result.message = f"spent {spent}s"


    class Result:
        def __init__(self, name: str):
            self.status = HealthStatus.OK
            self.name = name
            self.message = ""

        def copy_from(self, value: HealthCheckManager.Result):
            self.status  = value.status
            self.message = value.message

        def set_status(self, status: HealthStatus, message =""):
            self.status = status
            self.message = message

        def to_dict(self):
            return {
                "name": self.name,
                "status": str(self.status),
                "message": self.message # TODO
            }

    class Health:
        def __init__(self):
            self.status = HealthStatus.OK
            self.results : list[HealthCheckManager.Result] = []

        def to_dict(self):
            return {
                "status": str(self.status),
                "checks": [r.to_dict() for r in self.results]
            }

    # class data

    types : list[Type] = []

    # constructor

    def __init__(self):
        self.environment : Optional[Environment] = None
        self.checks: list[HealthCheckManager.Check] = []

    # check

    def check(self) -> HealthCheckManager.Health:
        health = HealthCheckManager.Health()

        for check in self.checks:
            result = HealthCheckManager.Result(check.name)

            health.results.append(result)

            check.run(result)

            # update overall status

            if result.status.value > health.status.value:
                health.status = result.status

        return health

    # public

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    @on_init()
    def setup(self):
        for type in self.types:
            descriptor = TypeDescriptor(type).for_type(type)
            instance = self.environment.get(type)

            for method in descriptor.get_methods():
                if method.has_decorator(check):
                    decorator = method.get_decorator(check)

                    name = decorator.args[0]
                    cache = decorator.args[1]
                    fail_if_slower_than = decorator.args[2]
                    if len(name) == 0:
                        name = method.get_name()

                    self.checks.append(HealthCheckManager.Check(name, cache, fail_if_slower_than, instance, method.method))
