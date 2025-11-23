"""
event management
"""
from __future__ import annotations

import inspect
from threading import Semaphore
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from aspyx.exception import ExceptionManager
from aspyx.reflection import Decorators
#get_method_class

from aspyx.di import Environment, inject_environment, on_destroy, on_init

def get_method_class(method):
    """
    return the class of the specified method
    Args:
        method: the method

    Returns:
        the class of the specified method

    """
    if inspect.ismethod(method) or inspect.isfunction(method):
        qualname = method.__qualname__
        module = inspect.getmodule(method)
        if module:
            cls_name = qualname.split('.<locals>', 1)[0].rsplit('.', 1)[0]
            cls = getattr(module, cls_name, None)
            if inspect.isclass(cls):
                return cls

    return None

# utility

def interval(seconds : Optional[int]=None, minutes: Optional[int]=None, hours: Optional[int]=None):
    args = {k: v for k, v in locals().items() if v is not None}

    return IntervalTrigger(**args)

def cron(year:Optional[str]=None, month:Optional[str]=None, day:Optional[str]=None, week:Optional[str]=None, day_of_week:Optional[str]=None, hour:Optional[str]=None, minute:Optional[str]=None, second:Optional[str]=None):
    args = {k: v for k, v in locals().items() if v is not None}

    return CronTrigger(**args)

def scheduled(trigger: BaseTrigger, group: Optional[str]=None, max: Optional[int]=None):
    def decorator(func):
        parameters = {
            "trigger": trigger,
        }

        if group is not None:
            parameters['group'] = group

        if max is not None:
            parameters['max'] = max

        Decorators.add(func, scheduled, parameters)

        Scheduler.register_scheduled(func, parameters)

        return func

    return decorator

# the scheduler

#@injectable()
class Scheduler:
    # class properties

    scheduled_functions = []

    # class methods

    @classmethod
    def register_scheduled(cls, func, parameters):
        cls.scheduled_functions.append(func)

    # constructor

    def __init__(self, exception_manager: Optional[ExceptionManager]=None):
        self.scheduler = BackgroundScheduler()
        self.environment = None
        self.exception_manager = exception_manager
        self.group_semaphores = {}  # group_name -> threading.Semaphore

    # inject

    @inject_environment()
    def set_environment(self, environment: Environment):
        self.environment = environment

    # internal

    def get_semaphore_for_group(self, group: str, max_concurrent: int):
        if group not in self.group_semaphores:
            self.group_semaphores[group] = Semaphore(max_concurrent)

        return self.group_semaphores[group]

    def register(self):
        for func in self.scheduled_functions:
            decorator = Decorators.get_decorator(func, scheduled)

            parameters = decorator.args[0]

            cls = get_method_class(func)

            semaphore = None
            if parameters.get("group") is not None:
                semaphore = self.get_semaphore_for_group(parameters.get("group"), parameters.get("max"))

            def make_wrapper(f, cls_, semaphore):
                def wrapper():
                    if semaphore is not None:
                        semaphore.acquire(blocking=False)

                    instance = self.environment.get(cls_)
                    bound = getattr(instance, f.__name__)

                    try:
                        bound()
                    except Exception as e:
                        if self.exception_manager is not None:
                            self.exception_manager.handle(e)
                        else:
                            pass
                    finally:
                        if semaphore is not None:
                            semaphore.release()

                return wrapper

            self.scheduler.add_job(
                make_wrapper(func, cls, semaphore),
                trigger=parameters.get("trigger"),
                id=func.__name__,#id=id or
                replace_existing=True,
            )

    # lifecycle

    @on_init()
    def on_init(self):
        # register

        self.register()

        # start the scheduler

        self.scheduler.start()

    @on_destroy()
    def on_destroy(self):
        self.scheduler.shutdown()
