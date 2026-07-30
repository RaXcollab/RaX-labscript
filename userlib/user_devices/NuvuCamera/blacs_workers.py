from zprocess import rich_print
from labscript_devices.IMAQdxCamera.blacs_workers import MockCamera, IMAQdxCameraWorker

from labscript_utils import dedent
from labscript_utils.properties import set_attributes
import numpy as np
import sys
import h5py
import json

import threading

class NuvuCamera(object):

    def __init__(self, logger):
        global NuvuCam
        from .Nuvu_sdk.Nuvu_cam_utils import NuvuCamUtils
        self.logger = logger

        self.logger.debug("Trying to establish connection to Nuvu Cam")
        self.camera_utils = NuvuCamUtils(logger)
        self.initialized = False # we have not set the acquisition_attributes until we have called set_attributes the first time
        self.logger.debug("Connection Successful")

        self.attributes = self.camera_utils.default_acquisition_attributes
        
        self.exception_on_failed_shot = True
        self._abort_acquisition = False  

    def set_attributes(self, attr_dict):
        self.attributes.update(attr_dict)
        if not self.initialized:
            # If not initialized, need to set all the attribute values to the camera
            attr_dict = self.attributes
            self.initialized = True
        self.camera_utils.set_attributes(attr_dict)
    
    def set_attribute(self, name, value):
        # Pure dict-mutation lives in _helpers (SDK-free, unit-testable);
        # the SDK call stays on the class.
        from ._helpers import apply_attribute_update
        apply_attribute_update(self.attributes, name, value)
        self.camera_utils.set_attrs({name: value})

    def get_attribute_names(self, visibility_level, writeable_only=True):
        return list(self.attributes.keys())

    def get_attribute(self, name):
        return self.attributes[name]

    # Single image acquisition. FIrst call prepare for a single image, then begin
    def snap(self):
        # Manual mode uses the internal trigger (trigger_mode 0), so a 214
        # frame-wait timeout here should be rare — but protect the path anyway
        # (mirrors grab_multiple's 214 handling). get_image() propagates
        # NuvuTimeout WITHOUT closing the camera (disconnect_if_error_real), so
        # the handle stays valid across retries; we re-arm the single-frame
        # acquisition each attempt via configure_acquisition (cam_stop +
        # cam_start). On final failure raise a clear, camera-still-open error
        # instead of letting a raw 214 (or a closed-handle 101 cascade) hit the
        # tab. Lazy import mirrors grab_multiple: keeps module import DLL-free.
        from .Nuvu_sdk.nc_camera import NuvuTimeout
        from ._helpers import SNAP_MAX_ATTEMPTS, snap_should_retry, snap_timeout_message
        last_exc = None
        for attempt in range(1, SNAP_MAX_ATTEMPTS + 1):
            try:
                self.configure_acquisition(continuous=False, bufferCount=1)
                image = self.camera_utils.get_image()
                self.stop_acquisition()
                return image
            except NuvuTimeout as e:
                last_exc = e
                self.logger.debug(
                    f"snap frame-wait timeout (214) on attempt "
                    f"{attempt}/{SNAP_MAX_ATTEMPTS}; "
                    f"{'re-arming' if snap_should_retry(attempt) else 'giving up'}."
                )
                # Loop re-arms via configure_acquisition on the next iteration.
        # Best-effort disarm so the camera isn't left armed after the final
        # failure (configure_acquisition would self-heal via cam_stop anyway).
        try:
            self.stop_acquisition()
        except Exception:
            pass
        raise NuvuTimeout(snap_timeout_message(SNAP_MAX_ATTEMPTS)) from last_exc
    
    # Prepare acquisition
    def configure_acquisition(self, continuous=False, bufferCount=0):
        self.camera_utils.cam_stop()
        # if self.camera_utils.camIsAcquring() == 1:
            # self.camera_utils.cam_stop()
        if continuous:
            assert bufferCount == 0
        self.camera_utils.cam_start(bufferCount)
        self.logger.debug("configured acquisition")
    
    def get_cam_data(self): #added by Shungo, 02/25/2025
        Camera_all_info = self.camera_utils.getAllCamInfo() # This gives a dictionary
        cam_data = np.zeros(5)
        cam_data[0] = float(Camera_all_info['componentTemp']['detectorTemp'])
        cam_data[1] = float(Camera_all_info['rawEmGain'])
        cam_data[2] = float(Camera_all_info['calibratedEmGain'])
        cam_data[3] = float(Camera_all_info['exposureTime'])
        cam_data[4] = int(Camera_all_info['currentReadoutMode'])
        return cam_data


    # used for grabbing during buffered
    def grab(self):
        print("grab in user_devices/NuvuCamera/Nuvu_sdk/blacs_workers.py")
        return self.camera_utils.get_queued_image()
    
    # used for grabbing continuous
    def grab_most_recent(self):
        return self.camera_utils.get_image()
    
    # TODO: verify that the triggers are slower than the read out time
    # Begin acquisition for BUFFERED
    def grab_multiple(self, n_images, images, waitForNextBuffer=True):
        # Lazy import mirrors __init__/set_attribute: keeps `import
        # blacs_workers` free of the Nuvu DLL (NC_api.LoadLibrary runs at
        # nc_camera import time). By the time a buffered shot reaches here the
        # SDK is already loaded and cached in sys.modules, so this is free.
        from .Nuvu_sdk.nc_camera import NuvuTimeout
        for i in range(n_images):
            while True:
                if self._abort_acquisition:
                    self.logger.debug("Abort during acquisition.")
                    self._abort_acquisition = False
                    return
                try:
                    images.append(self.grab())
                except NuvuTimeout:
                    # Frame-wait timeout (SDK 214): trigger hasn't arrived
                    # yet (upstream devices still in T2B, or long shot).
                    # Re-arm and keep waiting; abort flag above is the exit.
                    continue
                self.logger.debug(f"Got image {i+1} of {n_images}.")
                break
    
    def start_continuous_acquisition(self, fps):
        # TODO: set trigger attribute to internal
        if fps == 0:
            fps = self.camera_utils.default_fps
        self.camera_utils.set_fps(fps)
        self.configure_acquisition(continuous=True)

    def stop_continuous_acquisition(self):
        self.camera_utils.cam_stop()
        self.camera_utils.set_waiting_time(0)
    
    def stop_acquisition(self):
        self.camera_utils.isrunning = False

    def abort_acquisition(self):
        self.camera_utils.cam_stop()
        self._abort_acquisition = True

    def _decode_image_data(self, img):
        pass

    def close(self):
        self.camera_utils.cam_close()

class NuvuCameraWorker(IMAQdxCameraWorker):

    interface_class = NuvuCamera

    def get_camera(self):
        """Andor/Nuvu cameras may not be specified by serial numbers.

        Wraps the SDK open (interface_class.__init__ -> NuvuCamUtils.__init__ ->
        openCam -> ncCamOpen) in a bounded retry with backoff so a transient
        open failure (camera briefly powered off, driver momentarily held by
        another process) does not immediately crash worker init. On final
        failure, raise a clear operator-facing error naming the likely causes
        instead of a bare ``NuvuException: 27``. The tab's fatal-error +
        restart-button flow still fires on the re-raised exception.
        """
        if self.mock:
            return MockCamera()

        import time as _time
        from ._helpers import open_retry_delays, camera_open_failure_message
        from .Nuvu_sdk.nc_camera import NuvuException

        delays = open_retry_delays()
        max_attempts = len(delays) + 1
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self.interface_class(self.logger)
            except NuvuException as exc:
                # Only SDK open failures (e.g. error 27, camera not found) are
                # retried; anything else (missing DLL, programming error) is a
                # different problem and propagates immediately. The constructor
                # raises before returning, so there is no partially-built
                # camera object to clean up between attempts.
                last_exc = exc
                self.logger.warning(
                    f"Nuvu camera open attempt {attempt}/{max_attempts} failed: "
                    f"{exc!r}"
                )
                if attempt < max_attempts:
                    _time.sleep(delays[attempt - 1])
        raise RuntimeError(
            camera_open_failure_message(last_exc, max_attempts)
        ) from last_exc
            
    def get_attributes_as_dict(self, visibility_level):
        """Return a dict of the attributes of the camera for the given visibility
        level"""
        return self.camera.attributes

    def continuous_loop(self):
        # Lazy import for the same reason as grab_multiple: keeps module
        # import free of the Nuvu DLL.
        from .Nuvu_sdk.nc_camera import NuvuTimeout
        while True:
            try:
                image = self.camera.grab_most_recent()
            except NuvuTimeout:
                # No frame within the SDK timeout (only reachable at very low
                # fps). Stay alive so continuous_stop is still serviced.
                if self.continuous_stop.is_set():
                    self.continuous_stop.clear()
                    break
                continue
            self._send_image_to_parent(image)

            if self.continuous_stop.is_set():
                self.continuous_stop.clear()
                break

    def start_continuous(self, dt):
        """Begin continuous acquisition in a thread with minimum repetition interval
        dt"""
        if self.continuous_thread is not None:
            # Idempotent guard: continuous acquisition is already running. Treat
            # a redundant resume as a no-op rather than an AssertionError that
            # would kill the worker and force a tab restart. The desired end
            # state (live view running) already holds. See should_resume_continuous
            # in _helpers and the transition_to_manual guard below.
            self.logger.debug(
                "start_continuous: continuous acquisition already running; "
                "ignoring redundant resume."
            )
            return

        fps = float(1/dt) if dt != 0 else 0
        self.camera.start_continuous_acquisition(fps)

        self.continuous_thread = threading.Thread(
            target=self.continuous_loop, daemon=True
        )
        self.continuous_thread.start()
        self.continuous_dt = dt

    def stop_continuous(self, pause=False):
        assert self.continuous_thread is not None
        self.continuous_stop.set()
        self.continuous_thread.join()
        self.continuous_thread = None
        self.camera.stop_continuous_acquisition()

        if not pause:
            self.continuous_dt = None
    
    def post_experiment(self):
        if self.h5_filepath is None:
            self.logger.debug('No camera exposures in this shot.\n')
            return True
        self.logger.debug("in post exp")
        assert self.acquisition_thread is not None
        self.acquisition_thread.join(timeout=self.stop_acquisition_timeout)
        if self.acquisition_thread.is_alive():
            msg = """Acquisition thread did not finish. Likely did not acquire expected
                number of images. Check triggering is connected/configured correctly"""
            if self.exception_on_failed_shot:
                self.abort()
                raise RuntimeError(dedent(msg))
            else:
                self.camera.abort_acquisition()
                self.acquisition_thread.join()
                self.logger.debug(dedent(msg), file=sys.stderr)
        self.acquisition_thread = None

        self.logger.debug("Stopping acquisition.")
        self.camera.stop_acquisition()

        self.logger.debug(f"Saving {len(self.images)}/{len(self.exposures)} images.")

        with h5py.File(self.h5_filepath, 'r+') as f:
            # Use orientation for image path, device_name if orientation unspecified
            if self.orientation is not None:
                image_path = 'images/' + self.orientation
            else:
                image_path = 'images/' + self.device_name
            image_group = f.require_group(image_path)
            image_group.attrs['camera'] = self.device_name

            # Save camera attributes to the HDF5 file:
            if self.attributes_to_save is not None:
                set_attributes(image_group, self.attributes_to_save)

            # Whether we failed to get all the expected exposures:
            image_group.attrs['failed_shot'] = len(self.images) != len(self.exposures)

            # key the images by name and frametype. Allow for the case of there being
            # multiple images with the same name and frametype. In this case we will
            # save an array of images in a single dataset.
            images = {
                (exposure['name'], exposure['frametype']): []
                for exposure in self.exposures
            }

            # Iterate over expected exposures, sorted by acquisition time, to match them
            # up with the acquired images:
            self.exposures.sort(order='t')
            for image, exposure in zip(self.images, self.exposures):
                images[(exposure['name'], exposure['frametype'])].append(image)

            # Save images to the HDF5 file:
            for (name, frametype), imagelist in images.items():
                data = imagelist[0] if len(imagelist) == 1 else np.array(imagelist)
                self.logger.debug(f"Saving frame(s) {name}/{frametype}.")
                group = image_group.require_group(name)
                dset = group.create_dataset(
                    frametype, data=data, dtype='uint16', compression='gzip'
                )
                # Specify this dataset should be viewed as an image
                dset.attrs['CLASS'] = np.string_('IMAGE')
                dset.attrs['IMAGE_VERSION'] = np.string_('1.2')
                dset.attrs['IMAGE_SUBCLASS'] = np.string_('IMAGE_GRAYSCALE')
                dset.attrs['IMAGE_WHITE_IS_ZERO'] = np.uint8(0)

            # Save camera settings to hdf5 file - added by Shungo, 02/25/2025
            cam_data = self.camera.get_cam_data()
            f.create_dataset('/data/cam_info/detectorTemp', data=cam_data[0])
            f.create_dataset('/data/cam_info/rawEMGain', data=cam_data[1])
            f.create_dataset('/data/cam_info/calibratedEmGain', data=cam_data[2])
            f.create_dataset('/data/cam_info/exposureTime', data=cam_data[3])
            f.create_dataset('/data/cam_info/currentReadoutMode', data=cam_data[4]) #(0=nothing, 1=EM, 2=CONV).




        # If the images are all the same shape, send them to the GUI for display:
        try:
            image_block = np.stack(self.images)
        except ValueError:
            self.logger.debug("Cannot display images in the GUI, they are not all the same shape")
        else:
            self._send_image_to_parent(image_block)

        self.images = None
        self.n_images = None
        self.attributes_to_save = None
        self.exposures = None
        self.h5_filepath = None
        self.stop_acquisition_timeout = None
        self.exception_on_failed_shot = None
        return True

    def transition_to_manual(self):
        from ._helpers import should_resume_continuous
        self.logger.debug("Setting manual mode camera attributes.\n")
        self.set_attributes_smart(self.manual_mode_camera_attributes)
        # If continuous manual mode acquisition was paused for the buffered run,
        # resume it. Guard on continuous_thread is None (via
        # should_resume_continuous) so a resume that already happened — e.g.
        # abort() re-started live view before the queue's pause-block fired a
        # transition_to_manual on this POST_EXP device — is NOT repeated. The
        # base IMAQdxCameraWorker.abort() already has this guard; this mirrors
        # it so the two resume paths are idempotent with respect to each other.
        # (continuous_dt == 0 means "max rate" and is still a resumable value,
        # so the check is `is not None`, not truthiness.)
        if should_resume_continuous(self.continuous_dt, self.continuous_thread is not None):
            self.start_continuous(self.continuous_dt)
        return True
    
    # function used to close the camera when it is running and the restart button is pressed. it is crucial to
    # always close the camera before trying to re-establish connection to it
    # if the camera was not initialized properly due to an error, it will throw a non-fatal error and move on.
    def restart_close(self):
        self.camera.close()
