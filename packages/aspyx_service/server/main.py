import logging
from typing import Dict

from aspyx_service import ServiceManager, FastAPIServer
from server import  ServerModule
from client import TestComponent

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s in %(filename)s:%(lineno)d - %(message)s'
)

logging.getLogger("httpx").setLevel(logging.ERROR)

def configure_logging(levels: Dict[str, int]) -> None:
    for name in levels:
        logging.getLogger(name).setLevel(levels[name])

configure_logging({
    "aspyx.di": logging.ERROR,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR
})


def boot() -> ServiceManager:
    server = FastAPIServer.start(module=ServerModule, host="0.0.0.0", port=8000, start = False)

    service_manager = server.service_manager
    descriptor = service_manager.get_descriptor(TestComponent).get_component_descriptor()

    # Give the server a second to start

    #print("wait for server to start")
    #while True:
    #    addresses = service_manager.component_registry.get_addresses(descriptor)
    #    if addresses:
    #        break#

    #    print("zzz...")
    #    time.sleep(1)

    #print("server running")

    return service_manager

manager = boot()

app = FastAPIServer.fast_api

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="warning", access_log=False)