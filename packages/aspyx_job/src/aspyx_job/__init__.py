"""
This module provides the core Aspyx event management framework .
"""
from aspyx.di import module

from .job import scheduled, interval, cron

@module()
class JobModule:
    def __init__(self):
        pass

__all__ = [
    # package

    "JobModule",

    # job

    "scheduled",
    "interval",
    "cron",
]
