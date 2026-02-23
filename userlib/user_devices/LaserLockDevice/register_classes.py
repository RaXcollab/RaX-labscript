from labscript_devices import register_classes

register_classes(
    'LaserLockDevice',
    BLACS_tab='user_devices.LaserLockDevice.blacs_tabs.LaserLockTab',
    runviewer_parser=None,
)
