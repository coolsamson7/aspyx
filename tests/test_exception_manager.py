"""
Test cases for the Configuration system in aspyx.di
"""
from __future__ import annotations

import unittest

from aspyx.di import injectable, Environment, environment, create
from aspyx.di.aop import Invocation, advice, error, methods
from aspyx.exception import ExceptionManager, exception_handler, handle

class DerivedException(Exception):
    def __init__(self):
        pass

@environment()
class SampleEnvironment:
    # constructor

    def __init__(self):
        pass

    @create()
    def create_exception_manager(self) -> ExceptionManager:
        return ExceptionManager()

@injectable()
@exception_handler()
class Test:
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

@injectable()
class Service:
    def __init__(self):
        pass

    def throw(self):
        raise DerivedException()

@advice
class ExceptionAdvice:
    def __init__(self, exceptionManager: ExceptionManager):
        self.exceptionManager = exceptionManager

    @error(methods().of_type(Service))
    def handle_error(self, invocation: Invocation):
        self.exceptionManager.handle(invocation.exception)

class TestExceptionManager(unittest.TestCase):
    def test_exception_manager(self):
        environment =  Environment(SampleEnvironment)

        service = environment.get(Service)

        try:
            service.throw()
        except Exception as e:
            pass

if __name__ == '__main__':
    unittest.main()
