
### Construction and schematics
1. [3D printing designs](https://github.com/CamDavidsonPilon/morbidostat/tree/master/3D_files)

- more coming soon


### Software installation

1. On your RaspberryPi, git clone this repository (may need to `apt-get install git` first). Navigate into this directory.

2. `make install-leader` should set up what you need. If installing on a worker (not leader), run `make install-worker`


### Running

From the worker's command line:

`pio <job or action> <options>`

Running in the background (and append output to `morbidostat.log`)

`pio <job or action> <options> --background`

If you have many workers, you can run from the leader

`pios run <job or action> <options>`

to execute all of them.

Other `pios` commands:

- `pios kill <process>` to stop any process matching `<process>`
- `pios sync` to pull the latest code from git and run `setup.py` on the workers.


## Development

### Testing

`make test` on the command line.
