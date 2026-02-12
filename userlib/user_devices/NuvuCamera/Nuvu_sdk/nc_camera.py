# file: nuvu_cam_wrapper.py
# author: Cédric Vallée
# date: 16/04/18
# desc: Sert d'interface plus classique à python, gère les pointeurs, références et typages de ctypes
# desc: Only for camlink interface

from .NC_api import *
import numpy as np
import sys

class NuvuException(Exception):
    """
    Custom exception for errors originating from the Nuvu SDK.
    :attribute error: Error number obtained.
    :type error: int
    """
    def __init__(self, error):
        self.error = error
    def __str__(self):
        return repr(self.error)
    def value(self):
        """
        Get the value of the error.
        :return: The error value, defined in the error.h file of the Nuvu SDK.
        :rtype: int
        """
        return self.error


class nc_camera:
    """
    Python-like interface to the Nuvu SDK.

    Attributes:
    macAddress (str): MAC address of the camera to control.
    ncCam: Pointer to the camera API handle.
    ncImage: Pointer to the camera image handle.
    readoutTime (float): Readout time, initialized to -1.
    WaitingTime (float): Waiting time, initialized to -1.
    ExposureTime (float): Exposure time, initialized to -1.
    shutterMode (int): Camera shutter state (0=NOT SET, 1=open, 2=closed, 3=auto).
    name (str): Name for saving images to disk using SDK functions.
    comment (str): Comment in the metadata of saved images.
    width (int): Image width in pixels.
    height (int): Image height in pixels.
    inMemoryAccess (bool): Determines if a pointer to an array is allocated for the image.
    saveFormat: Format of images saved by the SDK.
    targetdetectorTempMin (float): Minimum target temperature of the detector.
    targetdetectorTempMax (float): Maximum target temperature of the detector.
    """
    def __init__(self, logger, MacAdress = None):
        self.logger = logger
        self.macAdress = MacAdress
        self.ncCam = NCCAM()
        self.ncImage = NCIMAGE()
        self.nbBuff = 0
        self.ampliType = c_int(-2)
        self.vertFreq = c_int(0)
        self.horizFreq = c_int(0)
        self.readoutMode = c_int(-1)
        self.ampliString = "12345678"
        self.nbrReadoutMode = c_int(0)
        self.readoutTime = c_double(-1.0)
        self.waitingTime = c_double(-1.0)
        self.exposureTime = c_double(-1.0)
        self.shutterMode = c_int(0) 
        self.name = "image1"
        self.comment = ""
        self.width = c_int(-1)
        self.height = c_int(-1)
        self.saveFormat = 1
        self.detectorTemp = c_double(100.0)
        self.controllerTemp = c_double(100.0)
        self.powerSupplyTemp = c_double(100.0)
        self.fpgaTemp = c_double(100.0)
        self.heatsinkTemp = c_double(100.0)
        self.targetDetectorTemp = c_double(100.0)
        self.targetDetectorTempMin = c_double(100.0)
        self.targetDetectorTempMax = c_double(100.0)
        self.rawEmGain = c_int(-1)
        self.rawEmGainRangeMin = c_int(-1)
        self.rawEmGainRangeMax = c_int(-1)
        self.calibratedEmGain = c_int(-1)
        self.calibratedEmGainMin = c_int(-1)
        self.calibratedEmGainMax = c_int(-1)
        self.calibratedEmGainTempMin = c_double(100.0)
        self.calibratedEmGainTempMax = c_double(100.0)
        self.binx = c_int(0)
        self.biny = c_int(0)
        self.triggerMode = c_int(-4)

        self.cachedTriggerMode = False


    def errorHandling(self, error):
        """
        Handle errors appropriately.
        Currently, this function crashes the program, closes the driver, and throws an exception to Labscript Interface.
        :param error: Error number returned by the SDK.
        :type error: int
        """
        if error == 107:
            pass
            #print(error)
        # if error == 131:
        # Camera is started when it shouldn't be
        #     pass
        if error == 27:
            raise NuvuException("Error 27: Could not find camera")
        else:
            self.logger.debug("Error Code: " + str(error)+ ". \n Refer to error.h file in Nuvu SDK documentation.")
            self.closeCam(noRaise = True)
            raise NuvuException("Error Code: " + str(error)+ ". \n Refer to error.h file in Nuvu SDK documentation.")


    def openCam(self, nbBuff=4):
        """
        Open the connection with the camera.

        If the class was initialized with the camera's MAC address, it will attempt to connect directly to this camera.

        :param nbBuff: Number of buffers to initialize in the Nuvu API.
        :type nbBuff: int
        """
        try:
            if self.macAdress is None:
                error = ncCamOpen(NC_AUTO_UNIT, NC_AUTO_CHANNEL, nbBuff, byref(self.ncCam))
                if error:
                    raise NuvuException(error)
                self.nbBuff = nbBuff
            else:
                self.logger.debug("Still not implemented")

        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def closeCam(self, noRaise=False):
        """
        Close the camera driver.
        :param noRaise: Internal parameter to prevent raising an error if the driver is already closed.
        :type noRaise: bool
        """
        try:
            error = ncCamClose(self.ncCam)
            if (error and not noRaise):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setReadoutMode(self, mode):
        """
        Select the camera's reading mode.
        :param mode: Reading mode (0=nothing, 1=EM, 2=CONV).
        :type mode: int
        """
        try:
            error = ncCamSetReadoutMode(self.ncCam, mode)
            if (error):
                raise NuvuException(error)

        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getReadoutTime(self):
        """
        Get the camera's readout time and store it in the readoutTime attribute.
        """
        try:
            error = ncCamGetReadoutTime(self.ncCam, byref(self.readoutTime))
            if(error):
                raise NuvuException(error)

        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setTriggerMode(self, mode):
        """
        Set the trigger more of the camera.
        Use "-3" or "CONT_HIGH_LOW" 
        Use "-2" or "EXT_HIGH_LOW_EXP" 
        Use "-1" or "EXT_HIGH_LOW" 
        Use "0", or "INTERNAL"
        Use "1", or "EXT_LOW_HIGH" 
        Use "2", or "EXT_LOW_HIGH_EXP"
        Use "3" or "CONT_LOW_HIGH"
        """
        self.cachedTriggerMode = True
        try:
            error = ncCamSetTriggerMode(self.ncCam, mode, 1) #hardcoded to take only one image
            if(error):
                raise NuvuException(error)
        
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())

            
    def getTriggerMode(self):
        """
        Get the camera's trigger mode
        """
        try:
            if self.cachedTriggerMode:
                error = ncCamGetTriggerMode(self.ncCam,0, byref(self.triggerMode), byref(c_int(1))) #hardcoded to take only one image
            else:
                error = ncCamGetTriggerMode(self.ncCam,1, byref(self.triggerMode), byref(c_int(1))) #hardcoded to take only one image
            
            if(error):
                raise NuvuException(error)

        
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setExposureTime(self, exposureTime):
        """
        Set the camera's exposure time.

        :param exposure_time: Exposure time in milliseconds.
        :type exposure_time: float
        """
        try:
            error = ncCamSetExposureTime(self.ncCam, exposureTime)
            if (error):
                raise NuvuException(error)
            self.getExposureTime()
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getExposureTime(self, cameraCall = 1):
        """
        Get the camera's exposure time.
        :param cameraCall: Select whether to check the value in the driver (0) or in the camera (1).
        Note: A camera call takes time.
        :type cameraCall: int
        """
        try:
            error = ncCamGetExposureTime(self.ncCam, cameraCall, byref(self.exposureTime))
            if(error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setWaitingTime(self, waitTime):
        """
        Set the waiting time between two acquisitions.
        :param waitTime: Waiting time in milliseconds.
        :type waitTime: float
        """
        try:
            error = ncCamSetWaitingTime(self.ncCam, waitTime)
            if(error):
                raise NuvuException(error)
            self.getWaitingTime(cameraCall=0)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getWaitingTime(self, cameraCall = 1):
        """
        Get the waiting time between two acquisitions.
        :param cameraCall: Select whether to get the time from the driver (0) or from the camera (1).
        Note: A camera call takes more time.
        :type cameraCall: int
        """
        try:
            error = ncCamGetWaitingTime(self.ncCam, cameraCall, byref(self.waitingTime))
            if(error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setTimeout(self, timeout):
        """
        Set the timeout for image acquisition.
        :param timeout: Waiting time in milliseconds before the driver declares an error if it's waiting for a new image to enter a buffer.
        :type timeout: float
        """
        try:
            error = ncCamSetTimeout(self.ncCam, int(timeout))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setShutterMode(self, mode):
        """
        Set the shutter mode.
        :param mode: Shutter mode.
        :type mode: int
        """
        try:
            error = ncCamSetShutterMode(self.ncCam, mode)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getShutterMode(self, cameraCall = 1):
        """
        Get the shutter mode.
        :param mode: Shutter mode.
        :type mode: int
        """
        try:
            error = ncCamGetShutterMode(self.ncCam, cameraCall, byref(self.shutterMode))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getSize(self):
        """
        Get the height and width of the camera images.

        Updates the height and width attributes of the camera class.
        """
        try:
            error =  ncCamGetSize(self.ncCam, byref(self.width), byref(self.height))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())

    def camIsAcquring(self):
        """
        Start image acquisition and send images to the buffer.

        :param nbrImg: Number of images the driver will take. If 0, acquisition is continuous.
        :type nbrImg: int
        :return: 1 if acquiring, 0 otherwise
        :rtype: int
        """
        res = c_int(0)
        try:
            error = ncCamIsAcquiring(self.ncCam, byref(res))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())
        
        return res.value

    def camStart(self, nbrImg = 0):
        """
        Start image acquisition and send images to the buffer.

        :param nbrImg: Number of images the driver will take. If 0, acquisition is continuous.
        :type nbrImg: int
        """
        try:
            error = ncCamStart(self.ncCam, nbrImg)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def camAbort(self):
        """
        Stop all image acquisition on the camera.
        """
        try:
            error = ncCamAbort(self.ncCam)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def read(self):
        """
        Read the next image from the buffer and send it to memory.
        """
        try:
            error = ncCamReadChronological(self.ncCam, self.ncImage, byref(c_int()))
            if (error):
                print('error coming from ncCamReadChronological')
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getImg(self):
        """
        Call read() then cast the image pointer to a 16-bit array and copy it to another part of memory.
        """
        self.read()
        self.logger.info('getIMG in user_devices/Nuvu_sdk/nc_camera.py')
        return np.copy(np.ctypeslib.as_array(cast(self.ncImage, POINTER(c_uint16)),(self.width.value,self.height.value)))


    def saveImage(self, encode = 0):
        """
        Save the image stored in ncImage and encode it as TIFF (0) or FITS (1) on the hard drive.
        :param encode: Encoding mode.
        :type encode: int
        """
        try:
            error = ncCamSaveImage(self.ncCam, self.ncImage, self.name.encode(), encode, self.comment.encode(), 1)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getTargetDetectorTempRange(self):
        """
        Get the requested temperature range of the detector.
        """
        try:
            error = ncCamGetTargetDetectorTempRange(self.ncCam, byref(self.targetDetectorTempMin), byref(self.targetDetectorTempMax))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getControllerTemp(self):
        """
        Get the current temperature of the controller and store it in the controller_temp attribute.
        """
        try:
            error = ncCamGetControllerTemp(self.ncCam, byref(self.controllerTemp))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getComponentTemp(self, comp):
        """
        Get the current temperature of the controller and store it in the controller_temp attribute.
        """
        try:
            if (comp == 0):
                temp = self.detectorTemp
            elif (comp == 1):
                temp = self.controllerTemp
            elif (comp == 2):
                temp = self.powerSupplyTemp
            elif (comp == 3):
                temp = self.fpgaTemp
            elif (comp == 4):
                temp = self.heatsinkTemp
            else:
                comp = -1

            error = ncCamGetComponentTemp(self.ncCam, c_int(comp), byref(temp))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setTargetDetectorTemp(self, temp):
        """
        Set the target temperature for the detector.
        :param temp: Target temperature.
        :type temp: float
        """
        try:
            error = ncCamSetTargetDetectorTemp(self.ncCam, c_double(temp))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getTargetDetectorTemp(self, cameraCall=1):
        """
        Get the target temperature of the detector and store it in the targetDetectorTemp attribute.

        :param cameraCall: Determines whether to call the camera or the driver, set to camera by default.
        :type cameraCall: int
        """
        try:
            error = ncCamGetTargetDetectorTemp(self.ncCam, cameraCall, byref(self.targetDetectorTemp))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setRawEmGain(self, gain):
        """
        Set the gain for the camera.
        :param gain: Gain value to be sent to the camera.
        :type gain: float
        """
        try:
            error = ncCamSetRawEmGain(self.ncCam, gain)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getRawEmGain(self, cameracall=1):
        """
        Get the rawEmGain value from the camera and store it in the rawEmGain attribute.
        """
        try:
            error = ncCamGetRawEmGain(self.ncCam, cameracall, byref(self.rawEmGain))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getRawEmGainRange(self):
        """
        Get the available EM gain range and store it in the attributes.
        """
        try:
            error = ncCamGetRawEmGainRange(self.ncCam, byref(self.rawEmGainRangeMin), byref(self.rawEmGainRangeMax))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def setCalibratedEmGain(self, emGain):
        """
        Set a calibrated EM gain.
        :param emGain: EM gain value.
        :type emGain: int
        """
        try:
            error = ncCamSetCalibratedEmGain(self.ncCam, emGain)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getCalibratedEmGain(self, cameraCall=1):
        """
        Get the calibrated EM gain from the camera.
        :param cameraCall: Determines whether to access the camera or the driver.
        :type cameraCall: int
        """
        try:
            error = ncCamGetCalibratedEmGain(self.ncCam, cameraCall, byref(self.calibratedEmGain))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getCalibratedEmGainRange(self):
        """
        Get the range where the EM gain calibration is valid.
        """
        try:
            error = ncCamGetCalibratedEmGainRange(self.ncCam, byref(self.calibratedEmGainMin), byref(self.calibratedEmGainMax))
            if(error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getCalibratedEmGainTempRange(self):
        """
        Get the temperature range where the EM gain calibration is valid.
        """
        try:
            error = ncCamGetCalibratedEmGainTempRange(self.ncCam, byref(self.calibratedEmGainTempMin),byref(self.calibratedEmGainTempMax))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getCurrentReadoutMode(self):
        """
        Get information about the current readout mode.
        """
        try:
            error = ncCamGetCurrentReadoutMode(self.ncCam, byref(self.readoutMode), byref(self.ampliType), self.ampliString.encode(), byref(self.vertFreq), byref(self.horizFreq))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getNbrReadoutModes(self):
        """
        Get the number of available readout modes.
        """
        try:
            error = ncCamGetNbrReadoutModes(self.ncCam, byref(self.nbrReadoutMode))
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())


    def getAllCamInfo(self):
        """
        Retrieve all information about the camera.
        """
        self.getNbrReadoutModes()
        self.getCurrentReadoutMode()
        self.getReadoutTime()
        self.getSize()
        self.getWaitingTime()
        self.getExposureTime()
        self.getComponentTemp(0)
        self.getComponentTemp(1)
        self.getComponentTemp(2)
        self.getComponentTemp(3)
        self.getShutterMode()
        self.getCalibratedEmGain()
        self.getCalibratedEmGainRange()
        self.getCalibratedEmGainTempRange()
        self.getRawEmGain()
        self.getRawEmGainRange()
        self.getTargetDetectorTemp()
        self.getTargetDetectorTempRange()
        self.getTriggerMode()

        cam_info = {
            "nbrReadoutModes": self.nbrReadoutMode.value,
            "currentReadoutMode": self.readoutMode.value,
            "currentTriggerMode": self.triggerMode.value,
            "readoutTime": self.readoutTime.value,
            "width": self.width.value,
            "height": self.height.value,
            "waitingTime": self.waitingTime.value,
            "exposureTime": self.exposureTime.value,
            "componentTemp": {
                "detectorTemp": self.detectorTemp.value,
                "controllerTemp": self.controllerTemp.value,
                "powerSupplyTemp": self.powerSupplyTemp.value,
                "fpgaTemp": self.fpgaTemp.value
            },
            "shutterMode": self.shutterMode.value,
            "calibratedEmGain": self.calibratedEmGain.value,
            "calibratedEmGainMin": self.calibratedEmGainMin.value,
            "calibratedEmGainMax": self.calibratedEmGainMax.value,
            "calibratedEmGainTempMin": self.calibratedEmGainTempMin.value,
            "calibratedEmGainTempMax": self.calibratedEmGainTempMax.value,
            "rawEmGain": self.rawEmGain.value,
            "rawEmGainMin": self.rawEmGainRangeMin.value,
            "rawEmGainMax": self.rawEmGainRangeMax.value,
            "targetDetectorTemp": self.targetDetectorTemp.value,
            "targetDetectorTempMin": self.targetDetectorTempMin.value,
            "targetDetectorTempMax": self.targetDetectorTempMax.value,
        }

        return cam_info

    def updateCam(self):
        """
        Retrieve information about the camera.
        """
        pass


    def purgeBuffer(self):
        for i in range(self.nbBuff):
            self.read()

    def setSquareBinning(self, bin):
        """
        Set binning mode and update data in the camera class.
        :param bin: Binning mode to set.
        :type bin: int
        """
        try:
            error = ncCamSetBinningMode(self.ncCam, bin, bin)
            if(error):
                raise NuvuException(error)
            error = ncCamGetBinningMode(self.ncCam, byref(self.binx), byref(self.biny))
            if (error):
                raise NuvuException(error)
            self.getSize()

        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())

    def flushReadQueue(self):
        """
        Flush all images acquired prior to this call.
        """
        try:
            error = ncCamFlushReadQueue(self.ncCam)
            if (error):
                raise NuvuException(error)
        except NuvuException as nuvuException:
            self.errorHandling(nuvuException.value())
