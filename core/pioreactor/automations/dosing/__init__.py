# -*- coding: utf-8 -*-
"""
Dosing automations intervene in the environment of the bioreactor by introducing
(or not introducing) media into the vial, called dosing. The automations execute
based on signals from sensors, or simply based on time.
"""
from .chemostat import Chemostat
from .fed_batch import FedBatch
from .pid_morbidostat import PIDMorbidostat
from .silent import Silent as DosingSilent
from .turbidostat import EventBasedTurbidostat
from .turbidostat import Turbidostat
