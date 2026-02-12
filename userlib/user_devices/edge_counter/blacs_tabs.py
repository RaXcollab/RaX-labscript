# # user_devices/edge_counter/blacs_tabs.py
# from blacs.device_base_class import DeviceTab

# class EdgeCounterTab(DeviceTab):
#     def initialise_GUI(self):
#         self.supports_remote_value_check(False)

#     def initialise_workers(self):
#         # Pull device properties from the connection table (like NI_SCOPE does)
#         worker_initialisation_kwargs = self.connection_table.find_by_name(self.device_name).properties
#         # If you ever add a BLACS_connection to your device, you could forward it here.
#         # Not strictly needed for EdgeCounterWorker, but harmless:
#         worker_initialisation_kwargs['BLACS_connection'] = getattr(self, 'BLACS_connection', None)

#         self.create_worker(
#             'main_worker',
#             'user_devices.edge_counter.blacs_workers:EdgeCounterWorker',
#             worker_initialisation_kwargs,
#         )
#         self.primary_worker = 'main_worker'

# user_devices/edge_counter/blacs_tabs.py
from blacs.device_base_class import DeviceTab

class EdgeCounterTab(DeviceTab):
    def initialise_GUI(self):
        self.supports_remote_value_check(False)

    def initialise_workers(self):
        # Pass device properties from the connection table to the worker (harmless if unused)
        props = self.connection_table.find_by_name(self.device_name).properties
        self.create_worker(
            "main_worker",
            "user_devices.edge_counter.blacs_workers:EdgeCounterWorker",
            props,
        )
        self.primary_worker = "main_worker"
