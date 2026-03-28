"""Shared rate limiter instance — import this in routes to apply limits."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
