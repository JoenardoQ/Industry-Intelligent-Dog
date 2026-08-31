"""Minimal run tracking decorators with no framework dependency."""

from __future__ import annotations

from functools import wraps


def tracked_method(kind: str):
    def decorate(func):
        @wraps(func)
        def wrapped(instance, *args, **kwargs):
            store = getattr(instance, "store", None)
            service = getattr(store, "service", None)
            if service is None:
                return func(instance, *args, **kwargs)
            with service.run(store.folder, kind, func.__name__):
                return func(instance, *args, **kwargs)
        return wrapped
    return decorate


def tracked_function(kind: str, store_position: int = 0):
    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            store = kwargs.get("store")
            if store is None and len(args) > store_position:
                store = args[store_position]
            service = getattr(store, "service", None)
            if service is None:
                return func(*args, **kwargs)
            with service.run(store.folder, kind, func.__name__):
                return func(*args, **kwargs)
        return wrapped
    return decorate
