# -*- coding: utf-8 -*-
import atexit
from morbidostat.background_jobs import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting this.

    def init(self):
        self.state = self.INIT

        def disconnect_gracefully(*args):
            self.set_state("disconnected")

        atexit.register(disconnect_gracefully)

        self.send_last_will_to_leader()
        self.declare_settable_properties_to_broker()
        self.start_general_passive_listeners()
