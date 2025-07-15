import logging
import sys
import time
import asyncio
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from aspyx.util import Logger

Logger.configure(default_level=logging.INFO, levels={
    "aspyx.di": logging.INFO,
    "aspyx.event": logging.WARNING,
    "aspyx.di.aop": logging.INFO,

    "proton": logging.WARNING,
    "proton._reactor": logging.WARNING,
    "proton._transport": logging.WARNING,
    "asyncio": logging.WARNING,
})

from aspyx_event import EventManager

from performance.common import HelloEvent, Module, SyncListener, AsyncListener

from aspyx.di import module, Environment, create


async def main():
    environment = Environment(Module)

    event_manager = environment.get(EventManager)

    last_received_sync = 0
    last_received_async = 0
    last_time = time.perf_counter()

    while True:
        now = time.perf_counter()
        if now - last_time >= 1.0:
            eps = 0#(sent - last_sent) / (now - last_time)
            recv_sync = SyncListener.received
            recv_async = AsyncListener.received
            recv_total = (recv_sync - last_received_sync) + (recv_async - last_received_async)
            print(
                f"{recv_sync} sync received | {recv_async} async received | EPS: {eps:.2f}, Received: {recv_total} ev/s")
            last_time = now
            last_received_sync = recv_sync
            last_received_async = recv_async

        await asyncio.sleep(0.001)

if __name__ == "__main__":
    asyncio.run(main())
