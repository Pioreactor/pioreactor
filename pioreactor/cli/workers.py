# -*- coding: utf-8 -*-
from __future__ import annotations

import click

from pioreactor.whoami import am_I_leader

if am_I_leader():
    from pioreactor import cluster_management

    @click.group(short_help="manage workers")
    def workers():
        pass

    workers.add_command(cluster_management.add_worker)
    workers.add_command(cluster_management.remove_worker)
    workers.add_command(cluster_management.assign_worker_to_experiment)
    workers.add_command(cluster_management.unassign_worker_from_experiment)
    workers.add_command(cluster_management.update_active)
    workers.add_command(cluster_management.discover_workers)
    workers.add_command(cluster_management.cluster_status)
