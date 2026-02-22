from user_devices.RemoteControl.labscript_devices import (
    RemoteControl,
    RemoteAnalogOut,
    RemoteAnalogMonitor,
)


class BigSkyHub(RemoteControl):
    """RemoteControl subclass for BigSky YAG laser hub.

    Auto-creates RemoteAnalogOut and RemoteAnalogMonitor children for each
    laser.  Connection strings match the ZMQ server's expected channel names
    (e.g. ``YAG_1_voltage``, ``YAG_1_temperature_monitor``).
    """

    description = "BigSky YAG Laser Hub"

    # Channel definitions: (suffix, units, limits, decimals, step_size)
    _WRITABLE_CHANNELS = [
        ("voltage",       "V",  (500, 1400), 0, 1),
        ("shutter",       "",   (0, 1),      0, 1),
        ("lamps",         "",   (0, 1),      0, 1),
        ("qswitch",       "",   (0, 1),      0, 1),
        ("lamp_mode",     "",   (0, 1),      0, 1),
        ("qswitch_mode",  "",   (0, 2),      0, 1),
        ("warmup",        "",   (0, 1),      0, 1),
        ("start_lasing",  "",   (0, 1),      0, 1),
        ("stop",          "",   (0, 1),      0, 1),
    ]

    _MONITOR_CHANNELS = [
        ("temperature_monitor", "C",  (0, 100),  1, 0.1),
        ("voltage_monitor",     "V",  (0, 1500), 0, 1),
        ("lamps_monitor",       "",   (0, 1),    0, 1),
        ("shutter_monitor",     "",   (0, 1),    0, 1),
        ("qswitch_monitor",     "",   (0, 1),    0, 1),
    ]

    def __init__(self, name, num_lasers=2, laser_prefix="YAG",
                 host="127.0.0.1", reqrep_port=55540, pubsub_port=55541,
                 mock=False, **kwargs):
        super().__init__(
            name,
            host=host,
            reqrep_port=reqrep_port,
            pubsub_port=pubsub_port,
            mock=mock,
            **kwargs,
        )

        for n in range(1, num_lasers + 1):
            prefix = f"{laser_prefix}_{n}"

            for suffix, units, limits, decimals, step_size in self._WRITABLE_CHANNELS:
                conn_name = f"{prefix}_{suffix}"
                RemoteAnalogOut(
                    name=conn_name,
                    parent_device=self,
                    connection=conn_name,
                    units=units,
                    limits=limits,
                    decimals=decimals,
                    step_size=step_size,
                )

            for suffix, units, limits, decimals, step_size in self._MONITOR_CHANNELS:
                conn_name = f"{prefix}_{suffix}"
                RemoteAnalogMonitor(
                    name=conn_name,
                    parent_device=self,
                    connection=conn_name,
                    units=units,
                    limits=limits,
                    decimals=decimals,
                    step_size=step_size,
                )
