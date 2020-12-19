# -*- coding: utf-8 -*-
import time, sys
from threading import Timer
import logging


def every(delay, task, *args, **kwargs):
    """
    Executing `task` once initially, and then every `delay` seconds later.

    Yields the result back to the caller.

    from https://stackoverflow.com/questions/474528/what-is-the-best-way-to-repeatedly-execute-a-function-every-x-seconds
    """
    next_time = time.time() + delay
    counter = 0
    while True:
        try:
            counter += 1
            kwargs["counter"] = counter
            yield task(*args, **kwargs)
        except Exception as e:
            raise e
            # in production code you might want to have this instead of course:
            # logger.exception("Problem while executing repetitive task.")
        if "pytest" in sys.modules:
            time.sleep(0)
        else:
            time.sleep(max(0, next_time - time.time()))
        # skip tasks if we are behind schedule:
        next_time += (time.time() - next_time) // delay * delay + delay


class RepeatedTimer:
    """
    A class for repeating a function in the background every N seconds.

    Use like:

    >>thread = RepeatedTimer(seconds_to_wait, callback)
    >>thread.start()
    >>...
    >>thread.cancel()

    To run a job right away (i.e. don't wait interval seconds), use run_immediately

    """

    def __init__(self, interval, function, run_immediately=False, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.daemon = True
        self.start()
        # if run_immediately:
        #    Timer(0, self.function, self.args, self.kwargs).start()

    def _run(self):
        logging.getLogger("RepeatedTimer").debug("here")
        logging.getLogger("RepeatedTimer").debug(self.function)
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.daemon = True
            self._timer.start()
            self.is_running = True
        return self

    def cancel(self):
        self._timer.cancel()
        self.is_running = False
