#!/usr/bin/env python

##
## Use egauge config to get the best possible phase and sign
## configuration based on certain assumptions
##

import pickle
import egauge_config
from egauge_config import Reg
import time
import os
from collections import defaultdict
import itertools


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
    cfg.wait()
    cfg.reboot()
    return ((config, chdata))


def auto_phase_match(cfg, samples=30, restore=False):
    data = []

    if 'PCKL_FILE' in os.environ:
        data = pickle.load(open(os.environ['PCKL_FILE'], "rb"))
    else:
        backupfile = "%s.conf.%d.json" % (cfg.devurl.hostname, int(time.time()))
        print "Making a backup config for later restore"
        cfg.getregisters(ofile=backupfile)
        for i in range(3):
            data.append(measure_and_rotate(cfg, samples))
        try:
            from cloud.serialization.cloudpickle import dump
            dump(data, open("{}/tests/{}T{}.pckl".format(egauge_config.THISDIR, cfg.devurl.netloc,
                                                         int(time.time())), "wb"))
        except ImportError as ex:
            print "unable to save pckl file", ex

    team = phase_match(data)

    for tt in team:
        print tt

    channels = data[0][0][0]
    totals = data[0][0][2]
    #from IPython.core.debugger import Pdb; Pdb().set_trace()

    if 'PCKL_FILE' not in os.environ:
        if restore is True:
            print "Restoring to original configuration on request"
            cfg.setregisters(ifile=backupfile, skip_backup=True)
        else:
            body = cfg.get_installation_POST(channels, team, totals)
            uri = "/cgi-bin/protected/egauge-cfg"
            resp, cont = cfg.request(uri, method="POST", body=body)
        cfg.wait()
        cfg.reboot()

    return ((channels, team, totals))

# For current less than this we cannot be certain
MIN_CURRENT = 3.0
MIN_PF = 0.5

def _get_ct_from_val(val, remove_sign=False):
    """
    given CT3*L3 --> CT3
    -CT4*L1 --> CT4
    """
    val = val.partition('*')[0]
    if remove_sign is True:
        if val.startswith("-"):
            val = val[1:]
    return val


class PhaseObj(object):
    def __init__(self, data):
        self.data = data

    def cfg(self, idx):
        return self.data[idx][0][1]

    def ctcfg(self, idx):
        return self.data[idx][0][0]

    def groups(self):
        if hasattr(self, "_groups") is False:
            self._groups = defaultdict(list)
            for cf in self.data[0][0][1]:
                if cf.val.startswith('L'):
                    continue
                self._groups[cf.name.partition('.')[0]].append(cf)
        return self._groups

    def groupdata(self, groupname):
        """
        get all available data for the group
        """
        for idx in range(len(self.data)):
            data = self.data[idx][1]
            for didx in range(len(data)):
                data[didx][1]

    def groupPerms(self, groupname):
        """
        for a group return all valid perms
        """
        grp = self.groups()[groupname]
        vct = [rg.val.partition('*')[0] for rg in grp]
        vct = [v[1:] if v[0] == '-' else v for v in vct]
        perms = []

        for perm in itertools.permutations('123', len(vct)):
            perms.append(tuple([(vct[idx], "L{}".format(phase)) for idx, phase in enumerate(perm)]))

        return perms

    def bestReadings(self):
        maxdict = {}
        for dt in self.data:
            for ts, rdg in dt[1]:
                for rdict in rdg:
                    if (rdict.ct, rdict.l) not in maxdict or maxdict[(rdict.ct, rdict.l)].I < rdict.I:
                        maxdict[(rdict.ct, rdict.l)] = rdict
        return maxdict


    def bestConfig(self):
        mr = self.bestReadings()
        cfgs = {}
        flipped = {}

        for group in self.groups():
            perms = self.groupPerms(group)
            # for each perm for the group, check best reading and rank it.
            perm_pf = []
            #print group, perms
            # sort and filter by pf
            for perm in perms:
                pf = 1.0
                for perm_element in perm:
                    if perm_element not in mr:
                        continue
                    if mr[perm_element].I < MIN_CURRENT:
                        print "Current too low for", perm, mr[perm_element].I
                        continue
                    #print perm_element, mr[perm_element]
                    pf = min(pf, mr[perm_element].pf)
                if pf > MIN_PF:
                    perm_pf.append((pf, perm))
                else:
                    print "pf too low for", pf, perm

            if len(perm_pf) == 0:
                print "unable to determine", group
                continue

            # consider best pfs first
            perm_pf = sorted(perm_pf, reverse=True)

            #from IPython.core.debugger import Pdb; Pdb().set_trace()
            # if only 1 is present, that that is the value
            if len(perm_pf) == 1:
                cfgs[group] = perm_pf[0][1]
                continue
            # check signs..
            # if the 1st one has all positive signs.. done.
            idx = 0
            #from IPython.core.debugger import Pdb; Pdb().set_trace()

            if len(perm_pf[idx][1]) == len([mr[pr] for pr in perm_pf[idx][1] if mr[pr].P > 0]):
                # all positive
                cfgs[group] = perm_pf[idx][1]
                continue

            idx = 1
            if len(perm_pf[idx][1]) == len([mr[pr] for pr in perm_pf[idx][1] if mr[pr].P > 0]):
                # all positive
                cfgs[group] = perm_pf[idx][1]
                continue

            # both 1st and 2nd have negative values
            # check who has the better average pf
            sumpf0 = sum([mr[perm_element].pf for perm_element in perm_pf[0][1]])
            sumpf1 = sum([mr[perm_element].pf for perm_element in perm_pf[1][1]])

            if sumpf0 > sumpf1:
                cfgs[group] = perm_pf[0][1]
            else:
                cfgs[group] = perm_pf[1][1]

            # flipping CT ?
            # whichever ones are negative should be flipped
            # we have already selected something
            for perm_element in cfgs[group]:
                if mr[perm_element].P < 0.0:
                    flipped[mr[perm_element].ct] = mr[perm_element]

        return cfgs, flipped


def phase_match(data, enforce_phase_suffix=True, verbose=True):
    """
    look at data and output the best configuration
    """
    # for all 3 configs (cfgdx)
    # we  check every CT and pick the max current rating for every CT
    # That gives us the best possible option
    rot = [[max([data[cfgdx][1][dx][1][idx] for dx in range(len(data[cfgdx][1]))],
            key=lambda v: v.I) for idx in range(12)]
           for cfgdx in range(3)]
    cfg_rot = [sorted(data[cfgdx][0][1], key=lambda v: v.id) for cfgdx in range(3)]
    from copy import copy
    newRegs = sorted(copy(cfg_rot[0]), key=lambda v: v.id)
    if verbose:
        for idx, nr in enumerate(newRegs):
            print idx, nr

    ph = PhaseObj(data)

    bc, flipped = ph.bestConfig()
    
    by_ct = {}
    for group, pairs in bc.items():
        for (ct,l) in pairs:
            by_ct[ct]=l

    print by_ct
    #from IPython.core.debugger import Pdb; Pdb().set_trace()
    for idx in range(len(newRegs)):
        reg = newRegs[idx]
        ct = _get_ct_from_val(reg.val, True)
        if ct in by_ct:
            val = "{}*{}".format(ct, by_ct[ct])
            if ct in flipped:
                print "flip", ct, val, flipped[ct]
                val = "-"+val
            name = reg.name
            if enforce_phase_suffix:
                name = "{}.{}".format(name.rpartition(".")[0], by_ct[ct][1:])
            newRegs[idx] = Reg._make((reg.id, name, val, reg.type))
            

    return newRegs


def _load_test_data():
    data9 = pickle.load(open("tests/egauge6599.egaug.es.pckl"))
    data8 = pickle.load(open("tests/egauge6598.egaug.es.pckl"))
    data7 = pickle.load(open("tests/egauge7227.egaug.es.pckl"))

    return data7, data8, data9


def main():
    import sys
    data = pickle.load(open(sys.argv[1]))
    newregs = phase_match(data)
    for idx, nr in enumerate(newregs):
        print idx, nr

if __name__ == "__main__":
    main()
