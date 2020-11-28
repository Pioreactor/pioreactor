
### Construction and schematics
1. [3D printing designs](https://github.com/CamDavidsonPilon/morbidostat/tree/master/3D_files)

- more coming soon


### Software installation

1. On your RaspberryPi, git clone this repository (may need to `apt-get install git` first). Navigate into this directory.

2. `make install-leader` should set up what you need. If installing on a worker (not leader), run `make install-worker`

 - [ ] add leader to `/etc/hosts`
 - [ ] change password
 - [ ] push ssh keys?
 - [ ] tell leader about unit, and tell unit about leader

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



### Testing

`make test` on the command line.




References
-------------
1. Toprak, E., Veres, A., Yildiz, S. et al. Building a morbidostat: an automated continuous-culture device for studying bacterial drug resistance under dynamically sustained drug inhibition. Nat Protoc 8, 555–567 (2013). https://doi.org/10.1038/nprot.2013.021

1. A low-cost, open source, self-contained bacterial EVolutionary biorEactor (EVE)
Vishhvaan Gopalakrishnan, Nikhil P. Krishnan, Erin McClure, Julia Pelesko, Dena Crozier, Drew F.K. Williamson, Nathan Webster, Daniel Ecker, Daniel Nichol, Jacob G Scott
bioRxiv 729434; doi: https://doi.org/10.1101/729434

2. A user-friendly, low-cost turbidostat with versatile growth rate estimation based on an extended Kalman filter
Hoffmann SA, Wohltat C, Müller KM, Arndt KM (2017) A user-friendly, low-cost turbidostat with versatile growth rate estimation based on an extended Kalman filter. PLOS ONE 12(7): e0181923. https://doi.org/10.1371/journal.pone.0181923

3. Wong, B., Mancuso, C., Kiriakov, S. et al. Precise, automated control of conditions for high-throughput growth of yeast and bacteria with eVOLVER. Nat Biotechnol 36, 614–623 (2018). https://doi.org/10.1038/nbt.4151

4. Ekkers, DM, Branco dos Santos, F, Mallon, CA, Bruggeman, F, van Doorn, GS. The omnistat: A flexible continuous‐culture system for prolonged experimental evolution. Methods Ecol Evol. 2020; 11: 932– 942. https://doi.org/10.1111/2041-210X.13403

5. Improving carotenoids production in yeast via adaptive laboratory evolution

6.  Fu W, Guethmundsson O, Paglia G, Herjolfsson G, Andresson OS, Palsson BO, et al. 2013. Enhancement of carotenoid biosynthesis
in the green microalga Dunaliella salina with light-emitting diodes and adaptive laboratory evolution. Appl. Microbiol. Biotechnol.
97: 2395-2403.

7. Attfield PV Bell PJL (2006) Use of population genetics to derive nonrecombinant Saccharomyces cerevisiae strains that grow using xylose as a sole carbon source. FEMS Yeast Res6: 862–868.
