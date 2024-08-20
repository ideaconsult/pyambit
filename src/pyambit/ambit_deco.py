#!/usr/bin/env python

from functools import wraps


def add_ambitmodel_method(cls):
    def decorator(fun):
        @wraps(fun)
        def retf(obj, *args, **kwargs):
            # print(f"Calling method {fun.__name__}")
            ret = fun(obj, *args, **kwargs)
            return ret

        setattr(cls, fun.__name__, retf)
        # print(f"Method {fun.__name__} added to {cls.__name__}")
        return retf

    return decorator
