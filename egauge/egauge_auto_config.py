#!/usr/bin/env python

##
## Use egauge config to get the best possible phase and sign
## configuration based on certain assumptions
##

import pickle
from egauge_config import Reg

"""
    1. fetch current config
    2. get 30s of data
    3. store, config + generated data together
    4. Rotate all voltages and push config back in.
    5. 2 time and repeat steps 2 and 3

    6. After all the data is in for individual CTs decide if a CT is backwards

"""


def measure_and_rotate(cfg, samples=30):
    config = cfg.getregisters(skip_write=True, get_vals=True)
    chdata = cfg.channelchecker(samples=samples)

    cfg.rotate_voltage_cofig()
    cfg.timeout = 25
    cfg.reboot()
    return ((config, chdata))


def auto_phase_match(cfg, samples=8):
    data = []
    for i in range(3):
        data.append(measure_and_rotate(cfg, samples))

    from cloud.serialization.cloudpickle import dump
    dump(data, open("/tmp/{}.pckl".format(cfg.devurl.netloc), "wb"))
    print data
    return data

# For current less than this we cannot be certain
MIN_CURRENT = 3.0


def phase_match(data):
    """
    look at data and output the best configuration
    """
    # for all 3 configs (cfgdx)
    # we  check every CT and pick the max current rating for every CT
    # That gives us the best possible option
    rot = [[max([data[cfgdx][1][dx][1][idx] for dx in range(len(data[cfgdx][1]))],
            key=lambda v: v.I) for idx in range(12)]
           for cfgdx in range(3)]
    cfg_rot = [data[cfgdx][0][1] for cfgdx in range(3)]
    from copy import copy
    newRegs = copy(cfg_rot[0])
    for idx in range(len(rot[0])):
        ct = [(dx, rot[dx][idx]) for dx in range(3)]

        by_pf = sorted(ct, key=lambda v: v[1].pf, reverse=True)
        cts = None
        flip = False
        if by_pf[0][1].P < 0.0:
            if by_pf[0][1].I < 10.0:
                # low current
                if by_pf[1][1].P > 0.0 and by_pf[1][1].pf > 0.5:
                    # low pf at low load for motors
                    cts = by_pf[1]
                else:
                    # flip CT
                    flip = True
                    cts = by_pf[0]
            else:
                # flip CT
                flip = True
                cts = by_pf[0]
        else:
            # we good
            cts = by_pf[0]

        reg = cfg_rot[cts[0]][idx]

        val = reg.val
        if flip is True:
            print "Flipping {}".format(cts[1].ct)
            if val[0] == '-':
                val = val[1:]
            else:
                val = '-' + val
        name = reg.name
        name = "{}.{}".format(name[:-2], cts[1].l)

        newRegs[idx] = Reg._make((reg.id, name, val, reg.type))

    return newRegs


data9 = pickle.load(open("tests/egauge6599.egaug.es.pckl"))
data8 = pickle.load(open("tests/egauge6598.egaug.es.pckl"))
data7 = pickle.load(open("tests/egauge7227.egaug.es.pckl"))

