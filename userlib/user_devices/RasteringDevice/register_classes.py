from labscript_devices import register_classes

register_classes(
    'RasteringDevice',
    BLACS_tab='user_devices.RasteringDevice.blacs_tabs.RasteringTab',
    runviewer_parser=None,
)
