"""Registry attributes must exist before DeviceTab.__init__ runs
initialise_GUI (subclasses override it without super() and call
_register_subscriber) and before the daemon _subscriber_loop reads them.
Regression test for the 2026-05-26 rollback failure class.

SDK-free: constructs RemoteControlTab via __new__ (no BLACS runtime) and
exercises only _init_subscriber_registry + _register_subscriber.
"""
import threading
import pytest

from user_devices.RemoteControl.blacs_tabs import RemoteControlTab


def _bare_tab():
    tab = RemoteControlTab.__new__(RemoteControlTab)  # skip DeviceTab.__init__
    tab._init_subscriber_registry()
    return tab


def test_registry_attrs_exist_after_init_helper():
    tab = _bare_tab()
    assert tab._pubsub_monitor_cache == {}
    assert tab._extra_topics == {}
    assert tab._subscriber_thread is None


def test_register_subscriber_before_thread_start_stores_topic():
    tab = _bare_tab()
    sentinel = lambda payload: None
    tab._register_subscriber("raster_status", sentinel)
    assert tab._extra_topics == {"raster_status": sentinel}


def test_register_subscriber_after_thread_start_raises():
    tab = _bare_tab()
    t = threading.Thread(target=lambda: threading.Event().wait(5), daemon=True)
    t.start()
    tab._subscriber_thread = t
    with pytest.raises(RuntimeError):
        tab._register_subscriber("raster_status", lambda p: None)


def test_init_is_wired_before_super():
    # __init__ must call _init_subscriber_registry before DeviceTab.__init__.
    import inspect
    src = inspect.getsource(RemoteControlTab.__init__)
    assert src.index("_init_subscriber_registry") < src.index("super().__init__")
