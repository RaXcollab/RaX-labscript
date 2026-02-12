# # user_devices/edge_counter/labscript_devices.py
# from labscript import IntermediateDevice

# class EdgeCounter(IntermediateDevice):
#     """Counts TTL edges between start() and stop() on a NI counter input and
#     writes a single integer to the shot file for the BLACS worker to pick up.
#     Attach to the SAME CLOCKLINE as your NI 6361.
#     """

#     description = 'NI DAQmx scalar edge counter (user device)'

#     def __init__(self, name, parent_device,
#                  MAX_name, counter='ctr0', pfi='PFI3', edge='rising',
#                  save_path='/results/counter/total', sync_to_ai=True):

#         # IntermediateDevice expects only (name, parent_device)
#         super().__init__(name, parent_device)

#         # Stash everything we need for the worker:
#         self._cfg = {
#             'MAX_name':   str(MAX_name),
#             'counter':    str(counter),     # 'ctr0' or 'ctr1'
#             'pfi':        str(pfi),         # e.g. 'PFI3'
#             'edge':       str(edge),        # 'rising' or 'falling'
#             'save_path':  str(save_path),   # e.g. '/results/counter/total'
#             'sync_to_ai': bool(sync_to_ai),
#         }

#         # Tell BLACS where the worker class lives:
#         self.BLACS_tab = 'user_devices.edge_counter.blacs_tabs:EdgeCounterTab'
#         self.BLACS_worker = 'user_devices.edge_counter.blacs_workers:EdgeCounterWorker'


#     def generate_code(self, hdf5_file):
#         grp = hdf5_file.create_group(f'/devices/{self.name}')
#         for k, v in self._cfg.items():
#             grp.attrs[k] = v


from labscript import IntermediateDevice

class EdgeCounter(IntermediateDevice):
    description = 'NI DAQmx scalar edge counter (user device)'

    # <-- add these as CLASS attributes:
    BLACS_tab = 'user_devices.edge_counter.blacs_tabs:EdgeCounterTab'
    BLACS_worker = 'user_devices.edge_counter.blacs_workers:EdgeCounterWorker'

    def __init__(self, name, parent_device,
                 MAX_name, counter='ctr0', pfi='PFI3', edge='rising',
                 save_path='/results/counter/total', sync_to_ai=True):
        super().__init__(name, parent_device)
        self._cfg = {
            'MAX_name':   str(MAX_name),
            'counter':    str(counter),
            'pfi':        str(pfi),
            'edge':       str(edge),
            'save_path':  str(save_path),
            'sync_to_ai': bool(sync_to_ai),
        }

    def generate_code(self, hdf5_file):
        grp = hdf5_file.create_group(f'/devices/{self.name}')
        for k, v in self._cfg.items():
            grp.attrs[k] = v
