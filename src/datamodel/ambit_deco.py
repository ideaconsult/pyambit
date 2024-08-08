#!/usr/bin/env python

from functools import wraps

from . import ambit


def add_ambitmodel_method(cls):
    def decorator(fun):
        @wraps(fun)
        def retf(obj, *args, **kwargs):
            ret = fun(obj, *args, **kwargs)
            return ret

        setattr(cls, fun.__name__, retf)
        return retf

    return decorator
