# -*- coding: utf-8 -*-
from morbidostat.background_jobs import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we there _must_ be a child,

    def init(self):
        self.state = self.INIT

        self.send_last_will_to_leader()
        self.declare_settable_properties_to_broker()
        self.start_general_passive_listeners()
