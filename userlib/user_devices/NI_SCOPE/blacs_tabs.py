#####################################################################
#                                                                   #
# /NI_SCOPE/blacs_tabs.py                                           #
#                                                                   #
# A driver for interfacing NI-SCOPE devices in labscripts           #
#                                                                   #
# Last Revised Dec. 2024, Phelan Yu                                 #
#                                                                   #
#####################################################################

from blacs.device_base_class import DeviceTab

class NI_SCOPETab(DeviceTab):
    def initialise_GUI(self):
        pass

    def initialise_workers(self):
        worker_initialisation_kwargs = self.connection_table.find_by_name(self.device_name).properties
        worker_initialisation_kwargs['addr'] = self.BLACS_connection
        self.create_worker(
            'main_worker',
            'user_devices.NI_SCOPE.blacs_workers.NI_SCOPEWorker',
            worker_initialisation_kwargs,
        )
        self.primary_worker = 'main_worker'