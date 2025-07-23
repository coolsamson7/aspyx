"""
the server hosting the test services
"""
import logging
import os

from fastapi import FastAPI

from aspyx_service import FastAPIServer, RequestContext
from server import  ServerModule
from aspyx.util import Logger


Logger.configure(default_level=logging.INFO, levels={
    "httpx": logging.ERROR,
    "aspyx.di": logging.INFO,
    "aspyx.di.aop": logging.INFO,
    "aspyx.service": logging.INFO
})

PORT = int(os.getenv("FAST_API_PORT", "8000"))

app = FastAPI()

app.add_middleware(RequestContext)
#app.add_middleware(TokenContextMiddleware)

ServerModule.fastapi = app

FastAPIServer.boot(ServerModule, host="0.0.0.0", port=PORT, start_thread= False)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True, log_level="warning", access_log=False)
