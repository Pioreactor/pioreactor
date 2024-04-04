# -*- coding: utf-8 -*-
from __future__ import annotations

import click

from pioreactor.whoami import am_I_leader

if am_I_leader():
    from pioreactor.cluster_management import add_worker
    from pioreactor.cluster_management import remove_worker
    from pioreactor.cluster_management import assign_worker_to_experiment
    from pioreactor.cluster_management import unassign_worker_from_experiment
    from pioreactor.cluster_management import update_active
    from pioreactor.cluster_management import discover_workers
    from pioreactor.cluster_management import cluster_status

    @click.group(short_help="manage workers")
    def workers():
        pass

    workers.add_command(add_worker)
    workers.add_command(remove_worker)
    workers.add_command(assign_worker_to_experiment)
    workers.add_command(unassign_worker_from_experiment)
    workers.add_command(update_active)
    workers.add_command(discover_workers)
    workers.add_command(cluster_status)
