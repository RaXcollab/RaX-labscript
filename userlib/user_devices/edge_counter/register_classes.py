# user_devices/edge_counter/register_classes.py
import labscript_devices
labscript_devices.register_classes(
    'EdgeCounter',
    BLACS_tab='user_devices.edge_counter.blacs_tabs:EdgeCounterTab',
    runviewer_parser=None,
)
