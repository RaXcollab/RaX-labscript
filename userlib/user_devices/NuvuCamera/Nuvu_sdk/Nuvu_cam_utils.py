# file: nuvu_cam_utils.py
# author: Shafinul Haque
# date: 10/08/24
# desc: Wrapper that englobes every methods we would like to use with the
#       nuvu. Essentially inherit most of the method from nc_camera but
#       wraps them in an easily readable class that add methods for init
#       and use of the camera

from user_devices.NuvuCamera.Nuvu_sdk.nc_camera import *
import numpy as np
import time

"""
TODO:

add trigger attr

"""
class Nuvu_wrapper_error(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class NuvuCamUtils(nc_camera):
    default_fps = 15
    default_acquisition_attributes = {
        "readoutMode":1,
        "exposure_time":20,
        "timeout": 2000,
        "square_bin": 1,
        'target_detector_temp':-60,
        "emccd_gain": 2,
        "trigger_mode":0,
        "shutter_mode":1, # 0= undefined 1 = on, 2= off, 3=auto
    }

    def __init__(self, logger):
        super().__init__(logger)

        self.logger = logger 

        self.attribute_setters = {
            "readoutMode": self.set_readout_mode,
            "exposure_time": self.set_exposure_time,
            "timeout": self.set_timeout,
            "square_bin": self.set_square_bin,
            "target_detector_temp": self.set_target_detector_temp,
            "emccd_gain": self.set_calibrated_em_gain,
            "trigger_mode": self.set_trigger_mode,
            "shutter_mode": self.set_shutter_mode
        }

        self.openCam(nbBuff=4)
        self.isrunning = False
    
    def set_attributes(self, attributes):
        for attr, value in attributes.items():
            if attr in self.attribute_setters:
                self.logger.debug(f"setting attribute: {attr}")
                self.attribute_setters[attr](value)
            else:
                raise ValueError(f"Unknown attribute: {attr}")
        self.logger.debug(self.getAllCamInfo())

    # disconnect_if_error
    def disconnect_if_error(f):
        """Decorator that disconnect the camera if the method fails"""
        def func(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                # args[0].closeCam()
                # print('Successfull emergency disconnect of Nuvu Camera')
                raise e from None
        return func
    
    def disconnect_if_error_real(f):
        """Decorator that disconnect the camera if the method fails"""
        def func(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                args[0].closeCam()
                args[0].logger.debug('Successfull emergency disconnect of Nuvu Camera')
                raise e from None
        return func
    
    # Methods to control camera start and stop
    @disconnect_if_error
    def cam_start(self, num_images):
        # Start camera in finite or continuous (num_images=0) acquisition
        if self.isrunning:
            raise Exception("Camera already started...")
        self.camStart(num_images)
        self.isrunning = True

    @disconnect_if_error
    def cam_stop(self):
        self.camAbort()
        self.isrunning = False

    def cam_close(self):
        self.closeCam()
    
    # Utility methods
    @property
    def real_fps(self):
        return self.__real_fps

    @disconnect_if_error
    def millisecond_to_fps(self,arg):
        return 1/(arg/1000)

    @disconnect_if_error
    def fps_to_millisecond(self,arg):
        return (1/arg)*1000
    
    # called both to change the fps and calibrate the real_fps being tracked
    # def set_trigger_mode(self, external=False):
    #     pass
    # Commented out by AJ on 02-10-2025 to debug camera triggering

    @disconnect_if_error
    def set_fps(self,new_fps):
        if self.fps_to_millisecond(new_fps) <= (self.exposureTime.value
                                               + self.readoutTime.value):
            raise Nuvu_wrapper_error("FPS to small, change exposure time first")
        
        current_exp_time = self.exposureTime.value
        current_read_time = self.readoutTime.value
        self.setWaitingTime(self.fps_to_millisecond(new_fps)
                            - current_exp_time
                            - current_read_time)
        self.getWaitingTime()
        self.__real_fps = self.millisecond_to_fps(self.exposureTime.value
                                                  + self.waitingTime.value
                                                  + self.readoutTime.value)
        self.__fps = new_fps
    
    def set_waiting_time(self,waiting_time):
        self.setWaitingTime(waiting_time)
        self.getWaitingTime()

    # Set methods
    # Each of the set methods should also call the corresponding get method to latch the 
    # value in the internal pointers of nc_camera
    # The order of set methods is the same order as the corresponding attributes appear in the 
    # attributes dictionary.
    # this is also the order in which attributes will be set
    # the order of attributes is important as some must be set before others
    @disconnect_if_error
    def set_readout_mode(self, readoutMode):
        self.setReadoutMode(readoutMode)
        self.getCurrentReadoutMode()
        # We can retrieve the initial latched values on the camera after setting ReadoutMode
        self.logger.debug(f"after setting readout mode:\n{self.getAllCamInfo()}")

    @disconnect_if_error
    def set_trigger_mode(self, triggerMode):
        self.setTriggerMode(triggerMode)
        self.getTriggerMode()
        self.logger.debug(f"after setting trigger mode:\n{self.getAllCamInfo()}")
        
    @disconnect_if_error
    def set_exposure_time(self, new_exposure_time):
        self.setExposureTime(new_exposure_time)
        self.setWaitingTime(0) # sets the exposure time to the readout time. in buffered acquisition we shouldnt have excess waiting time
        self.getExposureTime()
        self.getReadoutTime()
        self.logger.debug(f"after setting exposure time:\n{self.getAllCamInfo()}")
    
    @disconnect_if_error
    def set_timeout(self, timeout):
        self.setTimeout(timeout)

    @disconnect_if_error
    def set_square_bin(self, bin_size):
        self.setSquareBinning(bin_size)

    @disconnect_if_error
    def set_target_detector_temp(self,target):
        self.setTargetDetectorTemp(target)
        self.getTargetDetectorTemp()

    @disconnect_if_error
    def set_calibrated_em_gain(self, new_em_gain):
        self.setCalibratedEmGain(new_em_gain)
        self.getCalibratedEmGain()

    @disconnect_if_error
    def set_shutter_mode(self, new_shutter_mode):
        self.setShutterMode(new_shutter_mode)
        self.getShutterMode()
        self.logger.debug(f"after setting shutter mode:\n{self.getAllCamInfo()}")
    
    # Image collection Methods
    @disconnect_if_error
    def get_image64(self):
        """get directly 64bit image"""
        return self.get_image().astype(np.float64)

    @disconnect_if_error_real
    def get_image(self):
        """get a uint16 image"""
        self.flushReadQueue()
        return self.getImg()
    
    @disconnect_if_error
    def get_queued_image(self):
        """get a uint16 image"""
        print("get_queued_image in user_devices/Nuvu_sdk/Nuvu_cam_utils.py")
        return self.getImg()

    @disconnect_if_error
    def get_bias(self):
        exposure_old = self.exposureTime.value
        self.setExposureTime(0)
        time.sleep(0.1)
        img = self.get_image()
        self.setExposureTime(exposure_old)
        self.getExposureTime()
        return img

    @disconnect_if_error
    def get_bias64(self):
        return self.get_bias().astype(np.float64)

import matplotlib.pyplot as plt

if __name__ == '__main__':
    import sys
    import logging

    # Setup logging:
    logger = logging.getLogger('test_BLACS_tab')
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')

    # Create handler for terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)

    logger.info('\n\n===============starting camera test===============\n')

    camera = NuvuCamUtils(logger)
    attributes = camera.default_acquisition_attributes
    camera.set_attributes(attributes)
    
    # snap
    camera.cam_start(1)
    image = camera.get_image()

    # Convert the image to a numpy array if it's not already
    if not isinstance(image, np.ndarray):
        image = np.array(image)

    plt.imshow(image, cmap='gray')
    plt.colorbar()
    plt.title('Nuvu Camera Image')
    plt.show()

    camera.cam_stop()    
    camera.cam_close()

