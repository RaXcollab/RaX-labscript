from user_devices.RemoteControl.labscript_devices import RemoteControl


class LaserLockDevice(RemoteControl):
    """RemoteControl subclass for wavemeter-locked lasers.

    No behavior change from RemoteControl — exists only to map to the
    custom LaserLockTab which provides paired setpoint+monitor layout
    with frequency error display and lock quality indicators.
    """

    description = "Laser Lock Wavemeter"
