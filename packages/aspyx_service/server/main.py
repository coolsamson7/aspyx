import logging
import os
from typing import Dict

from aspyx_service import ServiceManager, FastAPIServer
from server import  ServerModule

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

PORT = int(os.getenv("FAST_API_PORT", 8000))

print(PORT)

def boot() -> ServiceManager:
    server = FastAPIServer.start(module=ServerModule, host="0.0.0.0", port=PORT, start = False)

    return server.service_manager

manager = boot()

app = FastAPIServer.fast_api

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True, log_level="warning", access_log=False)