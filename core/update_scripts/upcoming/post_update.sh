#!/bin/bash

set -xeu


export LC_ALL=C

sudo systemctl restart pioreactor_startup_run@monitor.service || :
