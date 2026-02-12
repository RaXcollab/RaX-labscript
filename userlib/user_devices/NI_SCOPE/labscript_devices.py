# #####################################################################
# #                                                                   #
# # /NI_SCOPE/labscript_devices.py                                    #
# #                                                                   #
# # A driver for interfacing NI-SCOPE devices in labscripts           #
# #                                                                   #
# # Last Revised Dec. 2024, Phelan Yu                                 #
# #                                                                   #
# #####################################################################


# from labscript import Device, LabscriptError, set_passed_properties

# class NI_SCOPE(Device):
#     """A labscript_device for National Instruments high-speed 
#        digitizers and oscilloscopes supported by NI-SCOPE
#           connection_table_properties (set once)
#           MAX_name
#     """
#     description = 'NI-SCOPE High-Speed Digitizer'

#     @set_passed_properties(
#         property_names = {
#             'connection_table_properties':[
#                 'MAX_name', 
#                 'vertical_range',
#                 'min_sample_rate',
#                 'min_num_pts',
#                 'trigger_source',
#                 'trigger_level',
#                 'trigger_delay'
#             ],
#             'device_properties': []}
#         )
#     def __init__(
#         self, 
#         name = None,
#         parent_device = None,
#         MAX_name = None, 
#         vertical_range = None,
#         min_sample_rate = None,
#         min_num_pts = None,
#         trigger_source = None,
#         trigger_level = 2.5,
#         trigger_delay  = 0.0,
#         **kwargs):

#         # formally instantiate labscripts.base.device
#         # with minimum needed declarations
#         Device.__init__(
#             self, 
#             name, 
#             parent_device,
#             MAX_name, 
#             **kwargs)

#         # define passed properties into class
#         self.name = name
#         self.BLACS_connection = MAX_name
#         self.vertical_range = vertical_range
#         self.min_sample_rate = min_sample_rate
#         self.min_num_pts = min_num_pts
#         self.trigger_source = trigger_source
#         self.trigger_delay_time = trigger_delay

#     def generate_code(self, hdf5_file):
#         Device.generate_code(self, hdf5_file)


#####################################################################
#                                                                   #
# /NI_SCOPE/labscript_devices.py                                    #
#                                                                   #
# A driver for interfacing NI-SCOPE devices in labscripts           #
#                                                                   #
# Last Revised Dec. 2024, Phelan Yu                                 #
#                                                                   #
#####################################################################

from labscript import Device, LabscriptError, set_passed_properties

class NI_SCOPE(Device):
    """A labscript_device for National Instruments high-speed 
       digitizers and oscilloscopes supported by NI-SCOPE

       connection_table_properties (set once)
         MAX_name
         vertical_range
         vertical_coupling
         min_sample_rate
         min_num_pts
         trigger_source
         trigger_level
         trigger_delay
    """
    description = 'NI-SCOPE High-Speed Digitizer'

    @set_passed_properties(
        property_names = {
            'connection_table_properties': [
                'MAX_name', 
                'vertical_range',
                'vertical_coupling',
                'min_sample_rate',
                'min_num_pts',
                'trigger_source',
                'trigger_level',
                'trigger_delay'
            ],
            'device_properties': []}
        )
    def __init__(
        self, 
        name = None,
        parent_device = None,
        MAX_name = None, 
        vertical_range = None,
        vertical_coupling = None,
        min_sample_rate = None,
        min_num_pts = None,
        trigger_source = None,
        trigger_level = 2.5,
        trigger_delay  = 0.0,
        **kwargs):

        # formally instantiate labscripts.base.device
        # with minimum needed declarations
        Device.__init__(
            self, 
            name, 
            parent_device,
            MAX_name, 
            **kwargs)

        # define passed properties into class
        self.name = name
        self.BLACS_connection = MAX_name
        self.vertical_range = vertical_range
        self.vertical_coupling = vertical_coupling
        self.min_sample_rate = min_sample_rate
        self.min_num_pts = min_num_pts
        self.trigger_source = trigger_source
        self.trigger_delay_time = trigger_delay
        self.trigger_level = trigger_level

    def generate_code(self, hdf5_file):
        Device.generate_code(self, hdf5_file)
