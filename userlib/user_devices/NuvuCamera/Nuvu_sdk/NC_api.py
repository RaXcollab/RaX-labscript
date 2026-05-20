from ctypes import *
from .structures import *
from .defines import *
import platform as p

(bit, os) = p.architecture()

if os == "ELF": # Ubuntu
    nuvuLib = CDLL("libnuvu.so", mode=RTLD_GLOBAL)
elif os == "WindowsPE":
    if bit == "64bit":
        nuvuLib = cdll.LoadLibrary("C:\\Windows\\System32\\nc_driver_x64.dll")
    elif bit == "32bit":
        nuvuLib = cdll.LoadLibrary("C:\\Windows\\system32\\nc_driver_Win32.dll")



#Cam open
ncCamOpen = nuvuLib.ncCamOpen
ncCamOpen.restype = c_int
ncCamOpen.argtypes = [c_int, c_int, c_int,  POINTER(NCCAM)]

#Cam Close
ncCamClose = nuvuLib.ncCamClose
ncCamClose.restype = c_int
ncCamClose.argtypes = [NCCAM]

#Set Readout Mode
ncCamSetReadoutMode = nuvuLib.ncCamSetReadoutMode
ncCamSetReadoutMode.restype = c_int
ncCamSetReadoutMode.argtypes = [NCCAM, c_int]

#Get Readout Time
ncCamGetReadoutTime = nuvuLib.ncCamGetReadoutTime
ncCamGetReadoutTime.restype = c_int
ncCamGetReadoutTime.argtypes = [NCCAM, POINTER(c_double)]

#Set Trigger mode
ncCamSetTriggerMode = nuvuLib.ncCamSetTriggerMode
ncCamSetTriggerMode.restype = c_int
ncCamSetTriggerMode.argtypes = [NCCAM, c_int, c_int]

#Get Trigger mode
ncCamGetTriggerMode = nuvuLib.ncCamGetTriggerMode
ncCamGetTriggerMode.restype = c_int
ncCamGetTriggerMode.argtypes = [NCCAM, c_int, POINTER(c_int), POINTER(c_int)]


#Set Exposure TIme
ncCamSetExposureTime = nuvuLib.ncCamSetExposureTime
ncCamSetExposureTime.restype = c_int
ncCamSetExposureTime.argtypes = [NCCAM, c_double]

#Get Exposure TIme
ncCamGetExposureTime = nuvuLib.ncCamGetExposureTime
ncCamGetExposureTime.restype = c_int
ncCamGetExposureTime.argtypes = [NCCAM, c_int, POINTER(c_double)]

#Set Waiting Time
ncCamSetWaitingTime = nuvuLib.ncCamSetWaitingTime
ncCamSetWaitingTime.restype = c_int
ncCamSetWaitingTime.argtypes = [NCCAM, c_double]

#Get Waiting Time
ncCamGetWaitingTime = nuvuLib.ncCamGetWaitingTime
ncCamGetWaitingTime.restype = c_int
ncCamGetWaitingTime.argtypes = [NCCAM, c_int, POINTER(c_double)]

#Set Timeout
ncCamSetTimeout = nuvuLib.ncCamSetTimeout
ncCamSetTimeout.restype = c_int
ncCamSetTimeout.argtypes = [NCCAM, c_int]

#Get Timeout
ncCamGetTimeout = nuvuLib.ncCamGetTimeout
ncCamGetTimeout.restype = c_int
ncCamGetTimeout.argtypes = [NCCAM, POINTER(c_int)]

#Set Shutermode
ncCamSetShutterMode = nuvuLib.ncCamSetShutterMode
ncCamSetShutterMode.restype = c_int
ncCamSetShutterMode.argtypes = [NCCAM, c_int]

#Get Shutermode
ncCamGetShutterMode = nuvuLib.ncCamGetShutterMode
ncCamGetShutterMode.restype = c_int
ncCamGetShutterMode.argtypes = [NCCAM, c_int, POINTER(c_int)]

#Check if acquiring
ncCamIsAcquiring = nuvuLib.ncCamIsAcquiring
ncCamIsAcquiring.restype = c_int
ncCamIsAcquiring.argtypes = [NCCAM, POINTER(c_int)]

#Cam Start
ncCamStart = nuvuLib.ncCamStart
ncCamStart.restype = c_int
ncCamStart.argtypes = [NCCAM, c_int]

#Cam Abort
ncCamAbort = nuvuLib.ncCamAbort
ncCamAbort.restype = c_int
ncCamAbort.argtypes = [NCCAM]

#Cam Read
ncCamRead = nuvuLib.ncCamRead
ncCamRead.restype = c_int
ncCamRead.argtypes = [NCCAM, POINTER(NCIMAGE)]

#Save Image
ncCamSaveImage = nuvuLib.ncCamSaveImage
ncCamSaveImage.restype = c_int
ncCamSaveImage.argtypes = [NCCAM, NCIMAGE, POINTER(c_char), c_int,POINTER(c_char),c_int]

#read Uint32
ncCamReadUInt32 = nuvuLib.ncCamReadUInt32
ncCamReadUInt32.restype = c_int
ncCamReadUInt32.argtypes =[NCCAM, POINTER(c_uint32)]

#alloc Uint32 Inutilisée
ncCamAllocUInt32Image = nuvuLib.ncCamAllocUInt32Image
ncCamAllocUInt32Image.restype = c_int
ncCamAllocUInt32Image.argtypes =[NCCAM, POINTER(POINTER(c_uint32))]

#free Uint32 Inutilisée
ncCamFreeUInt32Image = nuvuLib.ncCamFreeUInt32Image
ncCamFreeUInt32Image.restype = c_int
ncCamFreeUInt32Image.argtypes = [POINTER(POINTER(c_uint32))]

#getSizeImage
ncCamGetSize = nuvuLib.ncCamGetSize
ncCamGetSize.restype = c_int
ncCamGetSize.argtypes= [NCCAM, POINTER(c_int), POINTER(c_int)]

#save Uint32  Inutilisée
ncCamSaveUInt32Image = nuvuLib.ncCamSaveUInt32Image
ncCamSaveUInt32Image.restype =  c_int
ncCamSaveUInt32Image.argtypes = [NCCAM, POINTER(c_uint32),POINTER(c_char), c_int,POINTER(c_char),c_int ]

#set callback, permet d'activer une fonction a chaque fois que l'on effectue un call sur la sauvegarde d'un fichier
c_callback = CFUNCTYPE(None, NCCAM, c_int, POINTER(c_voidp))
ncCamSaveImageWriteCallback = nuvuLib.ncCamSaveImageWriteCallback
ncCamSaveImageWriteCallback.restype = c_int
ncCamSaveImageWriteCallback.argtypes = [NCCAM, c_callback, POINTER(c_void_p)]

#get detector target temp range
ncCamGetTargetDetectorTempRange = nuvuLib.ncCamGetTargetDetectorTempRange
ncCamGetTargetDetectorTempRange.restype = c_int
ncCamGetTargetDetectorTempRange.argtypes = [NCCAM, POINTER(c_double), POINTER(c_double)]

#get température du controleur
ncCamGetControllerTemp = nuvuLib.ncCamGetControllerTemp
ncCamGetControllerTemp.restype = c_int
ncCamGetControllerTemp.argtypes = [NCCAM, POINTER(c_double)]

#get température component
ncCamGetComponentTemp = nuvuLib.ncCamGetComponentTemp
ncCamGetComponentTemp.restype = c_int
ncCamGetComponentTemp.argtypes = [NCCAM, c_int, POINTER(c_double)]

#get Detector temp
ncCamGetDetectorTemp = nuvuLib.ncCamGetDetectorTemp
ncCamGetDetectorTemp.restype = c_int
ncCamGetDetectorTemp.argtypes = [NCCAM, POINTER(c_double)]

#set target detector temp
ncCamSetTargetDetectorTemp = nuvuLib.ncCamSetTargetDetectorTemp
ncCamSetTargetDetectorTemp.restype = c_int
ncCamSetTargetDetectorTemp.argtypes = [NCCAM, c_double]

#get target detector temp
ncCamGetTargetDetectorTemp = nuvuLib.ncCamGetTargetDetectorTemp
ncCamGetTargetDetectorTemp.restype = c_int
ncCamGetTargetDetectorTemp.argtypes = [NCCAM, c_int, POINTER(c_double)]

#set raw em gain
ncCamSetRawEmGain = nuvuLib.ncCamSetRawEmGain
ncCamSetRawEmGain.restype = c_int
ncCamSetRawEmGain.argtypes = [NCCAM, c_int]

#get raw em gain
ncCamGetRawEmGain = nuvuLib.ncCamGetRawEmGain
ncCamGetRawEmGain.restype = c_int
ncCamGetRawEmGain.argtypes = [NCCAM, c_int, POINTER(c_int)]

#get raw em gain range
ncCamGetRawEmGainRange = nuvuLib.ncCamGetRawEmGainRange
ncCamGetRawEmGainRange.restype = c_int
ncCamGetRawEmGainRange.argtypes = [NCCAM, POINTER(c_int), POINTER(c_int)]

#set calibrated em gain
ncCamSetCalibratedEmGain = nuvuLib.ncCamSetCalibratedEmGain
ncCamSetCalibratedEmGain.restype = c_int
ncCamSetCalibratedEmGain.argtypes = [NCCAM, c_int]

#get calibrated em gain
ncCamGetCalibratedEmGain = nuvuLib.ncCamGetCalibratedEmGain
ncCamGetCalibratedEmGain.restype = c_int
ncCamGetCalibratedEmGain.argtypes = [NCCAM, c_int, POINTER(c_int)]

#get calibrated em gain range
ncCamGetCalibratedEmGainRange = nuvuLib.ncCamGetCalibratedEmGainRange
ncCamGetCalibratedEmGainRange.restype = c_int
ncCamGetCalibratedEmGainRange.argtypes = [NCCAM, POINTER(c_int), POINTER(c_int)]

#get calibrated em gain temp range
ncCamGetCalibratedEmGainTempRange = nuvuLib.ncCamGetCalibratedEmGainTempRange
ncCamGetCalibratedEmGainTempRange.restype = c_int
ncCamGetCalibratedEmGainTempRange.argtypes = [NCCAM, POINTER(c_double), POINTER(c_double)]

#getcurrentReadoutMode
ncCamGetCurrentReadoutMode = nuvuLib.ncCamGetCurrentReadoutMode
ncCamGetCurrentReadoutMode.restype = c_int
ncCamGetCurrentReadoutMode.argtypes = [NCCAM, POINTER(c_int), POINTER(c_int), POINTER(c_char), POINTER(c_int), POINTER(c_int)]

#get number rreadout mode
ncCamGetNbrReadoutModes= nuvuLib.ncCamGetNbrReadoutModes
ncCamGetNbrReadoutModes.restype = c_int
ncCamGetNbrReadoutModes.argtypes = [NCCAM, POINTER(c_int)]

#read chronological
ncCamReadChronological = nuvuLib.ncCamReadChronological
ncCamReadChronological.restype = c_int
ncCamReadChronological.argtypes = [NCCAM, POINTER(NCIMAGE) ,POINTER(c_int)]

#set binning mode
ncCamSetBinningMode = nuvuLib.ncCamSetBinningMode
ncCamSetBinningMode.restype = c_int
ncCamSetBinningMode.argtypes = [NCCAM, c_int, c_int]

#get binning mode
ncCamGetBinningMode = nuvuLib.ncCamGetBinningMode
ncCamGetBinningMode.restype = c_int
ncCamGetBinningMode.argtypes = [NCCAM, POINTER(c_int), POINTER(c_int)]

# flush read queue
ncCamFlushReadQueue = nuvuLib.ncCamFlushReadQueues
ncCamFlushReadQueue.restype = c_int
ncCamFlushReadQueue.argtypes = [NCCAM]
