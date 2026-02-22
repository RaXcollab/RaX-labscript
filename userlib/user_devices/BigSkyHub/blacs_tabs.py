import threading

import zmq

from user_devices.RemoteControl.blacs_tabs import RemoteControlTab


class BigSkyTab(RemoteControlTab):
    """BLACS tab for the BigSky YAG laser hub.

    Inherits all GUI setup from RemoteControlTab.  The only override is
    ``initialise_workers`` which points to the BigSkyWorker (for safe
    command ordering during buffered shots).
    """

    def initialise_workers(self):
        self.create_worker(
            "main_worker",
            "user_devices.BigSkyHub.blacs_workers.BigSkyWorker",
            {
                "mock": self.mock,
                "host": self.host,
                "port": self.reqrep_port,
                "child_output_connections": self.child_output_connections,
                "child_monitor_connections": self.child_monitor_connections,
            },
        )
        self.primary_worker = "main_worker"

        # PUB-SUB thread handles (must re-initialise here since we don't
        # call super().initialise_workers())
        self._heartbeat_thread = None
        self._subscriber_thread = None
        self._pubsub_stop_event = threading.Event()
        self._pubsub_context = zmq.Context()

        if self.mock:
            self.reqrep_connected = True
            self.pubsub_connected = True
            self._fetch_initial_values()
            self._start_polling()
        else:
            self.connect_to_remote()
