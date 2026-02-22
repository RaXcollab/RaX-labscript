from labscript_devices import register_classes

register_classes(
    'BigSkyHub',
    BLACS_tab='user_devices.BigSkyHub.blacs_tabs.BigSkyTab',
    runviewer_parser=None,
)
