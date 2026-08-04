from labscript import *
from labscriptlib.Main_Experiment.subsequences.subsequences import digital_pulse
from labscript_devices.PrawnBlaster.labscript_devices import PrawnBlaster
from labscript_devices.NI_DAQmx.models.NI_PXIe_6361 import NI_PXIe_6361
from labscript_devices.NI_DAQmx.models.NI_PXIe_6535 import NI_PXIe_6535
from user_devices.RemoteControl.labscript_devices import RemoteAnalogOut, RemoteAnalogMonitor
from user_devices.LaserLockDevice.labscript_devices import LaserLockDevice
from user_devices.RasteringDevice.labscript_devices import RasteringDevice
from user_devices.BigSkyHub.labscript_devices import BigSkyHub
from user_devices.NuvuCamera.labscript_devices import NuvuCamera
# The NI_SCOPE import lives inside its ENABLED block below, so a disabled
# scope costs no module import (mirrors the previously commented-out import).

# === Hardware switchboard -- one entry per BLACS tab ===========================
# Flip a value -> recompile the connection table in RunManager -> restart BLACS.
# The PrawnBlaster has no switch: BLACS requires the master pseudoclock.
# A block referencing a device from a disabled block fails at compile time
# with an UnboundLocalError (NameError subclass) naming the missing device —
# that is the intended guard.
ENABLED = dict(
    ni_6361    = False,  # NI PXIe-6361 analog card + daq_ai/daq_ao channels
    ni_6535    = False,  # NI PXIe-6535 digital card + YAG/ENH lines
    ni_scope   = False,  # NI PXIe-5922 digitizer
    camera     = False,  # Nuvu EMCCD (trigger parent: ni_6535 port0/line0)
    laser_lock = True,   # HF_Locking GUI
    rastering  = True,   # Rastering GUI
    bigsky     = True,   # BigSky YAG hub
)

# Reserved spare line per NI card for even-children padding.
PARITY_PAD_LINE = {
    'ni_6361': 'port0/line7',  # last buffered line (only port0 is buffered) - no DOs on the 6361 today, pad never fires
    'ni_6535': 'port3/line7',  # DIO 31, the card's last buffered line - keep physically unwired
}


def _pad_even_digitals(card):
    """NI-DAQmx requires an even number of DO children per card
    (NI_DAQmx labscript_devices._check_even_children). Count the DOs that
    actually ended up on the card - including auto-created Trigger lines,
    since Trigger subclasses DigitalOut, and StaticDigitalOut, which does
    not - and add one dummy DO on the card's reserved spare line if the
    count is odd. The reserved line must stay free: a real channel there
    would silently absorb the pad (generate_code keys DOs by connection),
    so any occupant is rejected outright."""
    pad_line = PARITY_PAD_LINE[card.name]
    # Plain loop, NOT any(): `from labscript import *` shadows builtin any()
    # with numpy's, which is always-truthy when handed a generator.
    for child in card.child_devices:
        if child.connection == pad_line:
            raise LabscriptError(
                f"{card.name} parity pad line {pad_line!r} is already in use - "
                f"move that channel, or reserve a different free line in PARITY_PAD_LINE"
            )
    n_do = sum(isinstance(child, (DigitalOut, StaticDigitalOut)) for child in card.child_devices)
    if n_do % 2:
        DigitalOut(f'parity_pad_{card.name}', card, pad_line)


def connection_table():
    # === Initialize pseudoclock (always on - master clock) ===
    pb = PrawnBlaster(
        name='pb',
        com_port='COM4',
        num_pseudoclocks=2
    )

    # === NI 6361 Setup ===
    if ENABLED['ni_6361']:
        ni_6361_max_name = "PXI1Slot8"

        ni_6361 = NI_PXIe_6361(
            name='ni_6361',
            parent_device=pb.clocklines[0],  # Pseudoclock 0
            clock_terminal=f'/{ni_6361_max_name}/PFI1',
            MAX_name=f'{ni_6361_max_name}',
            acquisition_rate=100e3,
            stop_order=-1,
            AI_term='Diff',
            num_AI=6,
            num_AO=2
        )

        AnalogIn('daq_ai0', ni_6361, 'ai0')
        AnalogIn('daq_ai1', ni_6361, 'ai1')
        AnalogIn('daq_ai2', ni_6361, 'ai2')
        AnalogIn('daq_ai3', ni_6361, 'ai3')
        AnalogIn('daq_ai4', ni_6361, 'ai4')
        AnalogIn('daq_ai5', ni_6361, 'ai5')

        # AOs deliberately live (2026-08-03) so the channels stay configurable
        # whenever the card is on. Keep the AO count EVEN — _pad_even_digitals
        # pads DOs only; the NI even-children rule also applies to AOs.
        AnalogOut('daq_ao0', ni_6361, 'ao0')  # NI-5922 TRIG — labscript drives 0 V unless a sequence commands it
        AnalogOut('daq_ao1', ni_6361, 'ao1')  # not used

    # === NI 6535 Setup ===
    if ENABLED['ni_6535']:
        ni_6535_max_name = "PXI1Slot5"

        ni_6535 = NI_PXIe_6535(
            name='ni_6535',
            parent_device=pb.clocklines[1],  # Pseudoclock 1
            clock_terminal=f'/{ni_6535_max_name}/PFI4',  # adjust if needed
            MAX_name=ni_6535_max_name,
            stop_order=1
        )

        # Digital output lines on PXIe-6535
        DigitalOut('YAG1_line', ni_6535, 'port0/line1')
        DigitalOut('YAG2_trig', ni_6535, 'port0/line2')
        DigitalOut('ENH_line', ni_6535, 'port0/line3')

        # no latched lines in open-cell CT -- line0 is now the camera trigger (was LIF_shutter)
        ni_6535.set_property('latched_lines', [], location='device_properties')

    # === NI_SCOPE (PXIe-5922 digitizer) ===
    if ENABLED['ni_scope']:
        from user_devices.NI_SCOPE.labscript_devices import NI_SCOPE
        NI_SCOPE(
            name='NI_SCOPE',
            MAX_name='PXI1Slot2',
            vertical_range=[0.5, 0.1],       # Vpp for [Ch0, Ch1]
            vertical_coupling=['DC', 'DC'],  # Supported strings: 'DC', 'AC', 'GND', 'HF_REJECT', 'LF_REJECT'. (Need to check if working..)
            min_sample_rate=1_000_000,       # Hz
            min_num_pts=200_000,             # record length
            trigger_source='TRIG',
            trigger_level=1.0,               # triggers at +1V
            trigger_delay=0.0,               # 0s time offset between trigger event and when sampling starts
            channels_to_save=[0, 1],         # which NI-5922 channels to save to h5
        )

    # === Nuvu Camera ===
    # NOTE: The initialization of the NuvuCamera creates an implicit DO under
    # the name "camera_trigger" at the specified connection.
    if ENABLED['camera']:
        camera = NuvuCamera(
            name="camera",
            parent_device=ni_6535,
            connection="port0/line0",
            serial_number=0xDEADBEEF,  # NUVU camera initialization does not require serial_number, no need to touch this
            camera_attributes={
                "readoutMode": 1,  # 1 = EM
                "exposure_time": 20,  # Shafin: "Um miliseconds?"
                "timeout": 5000,  # ms; SDK frame-wait before error 214 — must outlast normal arm-to-trigger latency; grab_multiple retries on expiry
                "square_bin": 1,  # NxN bin size
                'target_detector_temp': -60,
                "emccd_gain": 500,  # Max 5000
                "trigger_mode": 2,  # 1 = EXT_LOW_HIGH, #0 = INT, 2 "EXT_LOW_HIGH_EXP" (minus for HIGH_LOW),
                "shutter_mode": 1,
            },
            manual_mode_camera_attributes={
                "readoutMode": 1,
                "exposure_time": 20,
                "timeout": 5000,
                "square_bin": 1,
                'target_detector_temp': -60,
                "emccd_gain": 500,
                "trigger_mode": 0,  # INT in manual mode so snap/continuous self-trigger (Lyman convention); buffered attrs above set 2 = EXT per shot
                "shutter_mode": 1,
            },
            mock=False  # True
        )

    # === Laser Lock Communication === #
    if ENABLED['laser_lock']:
        LaserLockDevice(name='LaserLockGUI', host="127.0.0.1", reqrep_port=3796, pubsub_port=3797, mock=False, wait_for_lock=True)

        # Name convention: <wavemeter channel>_Setpoint and <wavemeter channel>_Value

        RemoteAnalogOut(
            name='Vexlum_Setpoint',
            parent_device=LaserLockGUI,
            connection=3,
            units="THz",
            decimals=9
        )

        RemoteAnalogOut(
            name='TiSa_1_Setpoint',
            parent_device=LaserLockGUI,
            connection=1,
            units="THz",
            decimals=9
        )

        RemoteAnalogOut(
            name='TiSa_2_Setpoint',
            parent_device=LaserLockGUI,
            connection=6,
            units="THz",
            decimals=9
        )

        RemoteAnalogMonitor(
            name='TiSa_1_Value',
            parent_device=LaserLockGUI,
            connection=1,
            units="THz",
            decimals=9
        )

        RemoteAnalogMonitor(
            name='TiSa_2_Value',
            parent_device=LaserLockGUI,
            connection=6,
            units="THz",
            decimals=9
        )

    # === Rastering GUI Communication === #
    if ENABLED['rastering']:
        RasteringDevice(
            name='RasteringGUI',
            host="127.0.0.1",
            reqrep_port=55535,
            pubsub_port=55536,
            mock=False,
        )

        RemoteAnalogOut(
            name='Raster_X',
            parent_device=RasteringGUI,
            connection="laser_raster_x_coord",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
            step_size=0.001,
        )

        RemoteAnalogOut(
            name='Raster_Y',
            parent_device=RasteringGUI,
            connection="laser_raster_y_coord",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
            step_size=0.001,
        )

        RemoteAnalogMonitor(
            name='Raster_X_Monitor',
            parent_device=RasteringGUI,
            connection="laser_raster_x_coord_monitor",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
        )

        RemoteAnalogMonitor(
            name='Raster_Y_Monitor',
            parent_device=RasteringGUI,
            connection="laser_raster_y_coord_monitor",
            units="mm",
            limits=(0, 25.0),
            decimals=4,
        )

    # === BigSky YAG Laser Communication === #
    if ENABLED['bigsky']:
        BigSkyHub(name='BigSkyLasers', num_lasers=1, laser_prefix="YAG", host="127.0.0.1")
        # All channels auto-created

    # === Even-children padding ===
    # Runs after ALL blocks so auto-created Trigger lines (camera) are counted.
    if ENABLED['ni_6361']:
        _pad_even_digitals(ni_6361)
    if ENABLED['ni_6535']:
        _pad_even_digitals(ni_6535)

    return


if __name__ == '__main__':
    # Begin issuing labscript primitives
    connection_table()
    # start() elicits the commencement of the shot
    start()

    # Stop the experiment shot with stop()
    stop(1.0)
