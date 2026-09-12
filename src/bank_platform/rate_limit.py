"""Shared slowapi Limiter instance (Phase 7 - Edge Layer).

Imported by main.py (to wire into the app/middleware) and any router that
needs to decorate an endpoint with @limiter.limit(...) - a single shared
instance so every limited endpoint counts against the same storage.

Uses slowapi's default in-memory storage: fine for today's single-process
deployment, but it doesn't persist across restarts and won't coordinate
across multiple app processes/instances. Revisit with a shared backend
(e.g. Redis) once there's more than one process serving this app.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
