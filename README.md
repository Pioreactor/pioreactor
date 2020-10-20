`Morbidostat`
--------------


The `morbidostat` project is a combination of software, hardware and biological cultures for easy, scalable, and inexpensive *directed evolution*.


### What is directed evolution?

_Directed evolution_ is the process of controlling an organism's environment such that the population will evolve to adapt to that environment. The environment need not be static, but could be changing as well. By controlling the environment, often in response to the population's simultaneous adaption, an organism can be _directed_ to have novel or desirable properties. In particular, the directed evolution of microorganism is more easily achieved due to their short generation time, high cell density, and simple environments. For microorganims, directed evolution uses turbidostats and morbidostats.


### What is a turbidostat?
The _turbidostat_, a combination of "turbidity static", is a bioreactor designed to maintain a constant cell density (through maintaining a constant turbidity). Volume is ejected from the bioreactor, and replenished with new nutrients. By keeping cultures in this condition, microorganisms have a selective pressure on increasing growth rate (multiply faster), and/or increasing yield (require less nutrients to multiply).



### What is a morbidostat?

The _morbidostat_, a combination of "morbid static", is a bioreactor designed expose the culture to a maximum amount of stress without causing the culture to completely die off. At the start of a morbidostat trial, the culture is exposed to minimal stress. As the population adapts, the morbidostat system responds by increasing the stress level. Thus there is feedback loop between `adaption 🔁 increasing stress`.



### What applications are there for the morbidostat or turbidostat?

1. Evolving a traditional brewer's yeast to thrive in new brewing environments. New environments for brewer's yeast could be higher/lower temperature, higher (alcohol, IBU, caffeine), concentration, lower pH, salt %.

2. Yeast can only ferment a short list of carbohydrates. By slowly depleting yeast's traditional carbon sources, it forces the yeast to adapt to new carbon sources, like lactose. See [Attfield, 2006]

3. Similarly, filamentous fungi can be evolved to consume new carbon sources, like raffinose, a sugar which is a cause of digestive discomfort after eating soybean _tempeh_.

4. Lactobacillus, used in sour beer production, can be evolved to be more alcohol, pH or IBU tolerant.

5. Some algae are facultative heterotrophs. A morbidostat can be used to evolve a stronger and faster growing heterotrophic metabolism.

6. Triton Algae Innovations has used directed evolution to evolve heme in algae. They accelerated the process by flashing the microbes with UV light which caused a high mutation rate.

7. Algae can be evolved to produce more carotenoids by changing the light conditions, see [Fu, 2013]

6. Improving yeast culture density, as demonstrated in [Wong, 2018]

7. Improving growth rates after "rational design". When modifying the genes of a microorganism though modern genetic engineering, the growth rate is typically lowered due to new proteins or metabolites being constructed. By subjecting the organism to an environment with abundant nutrients, over time, the population will evolve to increase its growth rate.

8. Improving metabolite production after rational design. After adding the genes of carotenoid production to yeast but wanting a higher yield, [Reyes, 2013] exploited the antioxidant of carotenoids. They exposed the yeast to high levels of hydrogen peroxide. The yeast evolved to counteract the hydrogen peroxide by producing more carotenoids.

1. The original inventors of the morbidostat [Toprak, 2013] were interested in antibiotic resistance in bacteria. They subjected E. coli to a slowly increasing level of antibiotics, and after two weeks, the bacteria had grown resistance to the highest antibiotic concentration in their experiment design.

4. In [Ekkers, 2020], the authors hint at evolving an _anticipatory_ response. Amazing!

How to use the morbidostat
---------------------------

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
 - [ ] add websockets to leader mqtt: https://pypi.org/project/paho-mqtt/

### Running

From the command line (web interface coming soon):

`mb <job or action> <options>`

Running in the background (and append output to `morbidostat.log`)

`mb <job or action> <options> --background`


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
