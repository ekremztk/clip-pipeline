"""Stub for director_events — GPU service doesn't run the director module."""


class _NoOpEvents:
    def emit_sync(self, **kwargs):
        pass

    def emit(self, **kwargs):
        pass


director_events = _NoOpEvents()
