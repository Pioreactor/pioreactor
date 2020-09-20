# -*- coding: utf-8 -*-
import time, traceback


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
        time.sleep(max(0, next_time - time.time()))
        # skip tasks if we are behind schedule:
        next_time += (time.time() - next_time) // delay * delay + delay
