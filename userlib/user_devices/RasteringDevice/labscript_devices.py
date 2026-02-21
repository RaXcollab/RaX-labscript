from user_devices.RemoteControl.labscript_devices import RemoteControl


class RasteringDevice(RemoteControl):
    """RemoteControl variant for the rastering GUI with move_to_next support."""
    description = 'Rastering Device for Remote Motor Control'
