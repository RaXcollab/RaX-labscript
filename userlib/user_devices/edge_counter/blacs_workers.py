# user_devices/edge_counter/blacs_workers.py
import h5py
import nidaqmx
from nidaqmx.constants import Edge as NIDQ_Edge, TriggerType
from blacs.tab_base_classes import Worker

class EdgeCounterWorker(Worker):
    def init(self):
        self.task = None
        self.dev_props = None
        self.shot_h5_path = None
        return {}

    def transition_to_buffered(self, device_name, h5file, initial_values, fresh):
        self.shot_h5_path = h5file
        with h5py.File(h5file, 'r') as f:
            attrs = dict(f[f'/devices/{device_name}'].attrs)
        self.dev_props = attrs

        max_name   = attrs['MAX_name']           # e.g. "PXI1Slot8"
        counter    = attrs.get('counter', 'ctr0')
        pfi        = attrs.get('pfi', 'PFI3')
        edge_str   = attrs.get('edge', 'rising')
        sync_to_ai = bool(attrs.get('sync_to_ai', True))

        edge = NIDQ_Edge.RISING if edge_str.lower() == 'rising' else NIDQ_Edge.FALLING

        counter_term = f'{max_name}/{counter}'   # e.g. "PXI1Slot8/ctr0"
        pfi_term     = f'/{max_name}/{pfi}'      # e.g. "/PXI1Slot8/PFI3"

        self.task = nidaqmx.Task(new_task_name=f'{device_name}_count_edges')
        chan = self.task.ci_channels.add_ci_count_edges_chan(
            counter=counter_term, edge=edge, initial_count=0
        )
        # route input:
        chan.ci_count_edges_term = pfi_term

        if sync_to_ai:
            self.task.triggers.arm_start_trigger.trig_type = TriggerType.DIGITAL_EDGE
            self.task.triggers.arm_start_trigger.dig_edge_src = f'/{max_name}/ai/StartTrigger'
            self.task.triggers.arm_start_trigger.dig_edge_edge = edge

        return {}

    def start_run(self):
        if self.task is not None:
            self.task.start()
        return {}

    def stop_run(self):
        total = 0
        if self.task is not None:
            try:
                self.task.stop()
                total = int(self.task.read())
            finally:
                self.task.close()
                self.task = None

        save_path = self.dev_props.get('save_path', '/results/counter/total')
        with h5py.File(self.shot_h5_path, 'r+') as f:
            parts = [p for p in save_path.split('/') if p]
            grp = f
            for p in parts[:-1]:
                grp = grp.require_group(p)
            dset = parts[-1]
            if dset in grp:
                del grp[dset]
            grp.create_dataset(dset, data=total, dtype='i8')

        return {}

    def abort_transition_to_manual(self):
        if self.task is not None:
            try:
                self.task.close()
            finally:
                self.task = None
        return {}

    transition_to_manual = abort_transition_to_manual
