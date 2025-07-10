import logging
import os

from aspyx.util import Logger
from aspyx_service import FastAPIServer
from server import  ServerModule

Logger.configure(default_level=logging.DEBUG, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.ERROR,
    "aspyx.di.aop": logging.ERROR,
    "aspyx.service": logging.ERROR
})

PORT = int(os.getenv("FAST_API_PORT", 8000))

FastAPIServer.boot(module=ServerModule, host="0.0.0.0", port=PORT, start_thread= False)

app = FastAPIServer.fast_api

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True, log_level="warning", access_log=False)