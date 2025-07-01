"""
health checks
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Type, Optional

from aspyx.di import injectable, Environment, inject_environment, on_init
from aspyx.reflection import Decorators, TypeDescriptor


def health_checks():
    """
    Instances of classes that are annotated with @injectable can be created by an Environment.
    """
    def decorator(cls):
        Decorators.add(cls, health_checks)

        #if not Providers.is_registered(cls):
        #    Providers.register(ClassInstanceProvider(cls, True, "singleton"))

        HealthCheckManager.types.append(cls)

        return cls

    return decorator

def health_check(name="", cache = 0, fail_if_slower_than = 0):
    """
    Methods annotated with `@on_init` will be called when the instance is created.
    """
    def decorator(func):
        Decorators.add(func, health_check, name, cache, fail_if_slower_than)
        return func

    return decorator

class HealthStatus(Enum):
    """
    A enum specifying the health status of a service. The values are:

    - `OK` service is healthy
    - `WARNING` service has some problems
    - `CRITICAL` service is unhealthy
    """
    OK = 1
    WARNING = 2
    ERROR = 3

    def __str__(self):
        return self.name


@injectable()
class HealthCheckManager:
    """
    The health manager is able to run all registered health checks and is able to return an overall status.
    """
    logger = logging.getLogger("aspyx.service.health")

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

        async def run(self, result: HealthCheckManager.Result):
            now = time.time()

            if self.cache > 0 and self.last_check is not None and now - self.last_check < self.cache:
                result.copy_from(self.last_value)
                return

            self.last_check = now
            self.last_value = result

            if asyncio.iscoroutinefunction(self.callable):
                await self.callable(self.instance, result)
            else:
                await asyncio.to_thread(self.callable, self.instance, result)

            spent = time.time() - now

            if result.status == HealthStatus.OK and 0 < self.fail_if_slower_than < spent:
                result.status = HealthStatus.ERROR
                result.details = f"spent {spent:.3f}s"


    class Result:
        def __init__(self, name: str):
            self.status = HealthStatus.OK
            self.name = name
            self.details = ""

        def copy_from(self, value: HealthCheckManager.Result):
            self.status  = value.status
            self.details = value.details

        def set_status(self, status: HealthStatus, details =""):
            self.status = status
            self.details = details

        def to_dict(self):
            result = {
                "name": self.name,
                "status": str(self.status),
            }

            if len(self.details) > 0:
                result["details"] = self.details

            return result

    class Health:
        def __init__(self, status: HealthStatus = HealthStatus.OK):
            self.status = status
            self.results : list[HealthCheckManager.Result] = []

        def to_dict(self):
            return {
                "status": str(self.status),
                "checks": [result.to_dict() for result in self.results]
            }

    # class data

    types : list[Type] = []

    # constructor

    def __init__(self):
        self.environment : Optional[Environment] = None
        self.checks: list[HealthCheckManager.Check] = []

    # check

    async def check(self) -> HealthCheckManager.Health:
        """
        run all registered health checks and return an overall result.
        Returns: the overall result.

        """
        self.logger.info("Checking health...")

        health = HealthCheckManager.Health()

        tasks = []
        for check in self.checks:
            result = HealthCheckManager.Result(check.name)
            health.results.append(result)
            tasks.append(check.run(result))

        await asyncio.gather(*tasks)

        for result in health.results:
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
                if method.has_decorator(health_check):
                    decorator = method.get_decorator(health_check)

                    name = decorator.args[0]
                    cache = decorator.args[1]
                    fail_if_slower_than = decorator.args[2]
                    if len(name) == 0:
                        name = method.get_name()

                    self.checks.append(HealthCheckManager.Check(name, cache, fail_if_slower_than, instance, method.method))
