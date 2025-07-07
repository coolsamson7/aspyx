"""
test for health checks
"""
import time

import pytest

from aspyx_service import health_checks, health_check, HealthCheckManager, ServiceModule, HealthStatus

from aspyx.di import injectable, module, Environment

@health_checks()
@injectable()
class Checks:
    def __init__(self):
        pass

    @health_check(fail_if_slower_than=1)
    def check_1(self, result: HealthCheckManager.Result):
        time.sleep(2)

    @health_check(name="check-2", cache=10)
    def check_2(self, result: HealthCheckManager.Result):
        pass # result.set_status(HealthStatus.OK)

# module

@module(imports=[ServiceModule])
class Module:
    def __init__(self):
        pass

@pytest.fixture(scope="session")
def environment():
    environment = Environment(Module)  # start server
    yield environment

@pytest.mark.asyncio(scope="function")
class TestLocalService():
    async def test_healthcheck(self, environment):
        manager = environment.get(HealthCheckManager)

        result = await manager.check()

        assert len(result.results) == 2
        assert result.status is HealthStatus.ERROR

        assert result.results[0].name == "check_1"
        assert result.results[1].name == "check-2"

        print()
