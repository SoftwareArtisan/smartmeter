#!/usr/bin/env python

import httplib2
import httplib
import logging
import time
import urlparse
import urllib2
from elementtree import ElementTree as ET
from collections import namedtuple
import EG_CTCFG
import json
import StringIO

Total = namedtuple('map', 'id,val')
Reg = namedtuple('reg','id,name,val,type')
Channel = namedtuple('ch', 'id,val')

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("eg_cfg")

class egcfg:
    def __init__(s,devurl,username,password,lg):
        if not devurl.startswith('http'):
            devurl = "http://"+devurl
        uu = urlparse.urlparse(devurl)
        if "." not in uu.hostname:
            # we will assume that it is egauge1910, or just 1910
            if not uu.hostname.startswith("egauge"): 
                hn = "egauge"+uu.hostname
            else:
                hn = uu.hostname
            # add egauge.es at the end
            hn += ".egaug.es"
            uu = urlparse.urlparse("http://"+hn)

        s.devurl=uu
        s.username=username
        s.password=password
        s.lg=lg
        s.req = httplib2.Http(timeout=60)
        s.req.add_credentials(username, password)   # Digest Authentication

    def request(s,uri,method="GET", body=None):
        if not uri.startswith("/"):
            uri = "/"+uri
        requrl=s.devurl.geturl()+uri
        success = False
        print requrl
        response, content = s.req.request (requrl,method=method, 
                headers={'Connection': 'Keep-Alive', 
                        'accept-encoding': 'gzip',
                        'Content-Type':'application/xml'},
                body=body)
        if response['status'] == '401':
            s.lg.warning("Unauthorized request!")
            raise urllib2.HTTPError(requrl, 401, "Unauthorized Request", hdrs = None, fp = None)
        elif response['status'] == '400':
            s.lg.warning("Bad Request!")
            raise urllib2.HTTPError(requrl, 400, "Bad Request", hdrs = None, fp = None)
        elif response['status'] == '500':
            s.lg.warning("Internal Error!")
            raise urllib2.HTTPError(requrl, 500, "Internal Error", hdrs = None, fp = None)
        elif response['status'] == '408':
            s.lg.warning("Request timeout!")
            raise urllib2.HTTPError(requrl, 408, "Request Timeout", hdrs = None, fp = None)
        elif response['status'] == '404':
            s.lg.warning("device not found. Probably it is not up")
            raise urllib2.HTTPError(requrl, 404, "Device not found", hdrs = None, fp = None)
        elif 'not authorized' in content.lower():
            s.lg.warning("Unauthorized request! using username={} and password={}".format(s.username, s.password))
            response['status'] = 401
            raise urllib2.HTTPError(requrl, 401, "Unauthorized Request", hdrs = None, fp = None)
        else:
            success = True

        if not success:
          print response, content
          
        return response, content
 
    def setcfg(s, ifile):
        """
        use the xml file that is provided and set config
        """
        # first save existing config somewhere

        s.getcfg()

        content = open(ifile,'rt').read()
        channels, team, totals = s.parse_installation(content)
        body = s.get_installation_POST(channels, team, totals)

        uri="/cgi-bin/protected/egauge-cfg"
        resp, cont = s.request(uri,method="POST",body=body)

        print resp, cont
        return resp, cont
  
    def setntp(s,ntpServer):
        """
        set ntp server configuration and reboot
        """
        uri="/cgi-bin/protected/egauge-cfg"
        body='ntpServer=%s\n'%ntpServer
        resp, cont = s.request(uri,method="POST",body=body)
        print resp, cont
        return resp, cont

    def setregisters(s, ifile):
        """
        use json file to set register and CT configuration
        """
        s.getregisters()
        content = open(ifile,'rt').read()
        obj = json.loads(content)
        channels, team, totals = s._from_json(obj)
        body = s.get_installation_POST(channels, team, totals)

        uri="/cgi-bin/protected/egauge-cfg"
        resp, cont = s.request(uri,method="POST",body=body)

        print resp, cont
        return resp, cont
 
    def getregisters(s, ofile=None, skip_write=False):
        response, content = s.getcfg(skip_write=True)
        channels, team, totals = s.parse_installation(content)
        if ofile==None: ofile = "%s.conf.%d.json" %(s.devurl.hostname,int(time.time()))
        # create ouput json
        obj = s._to_json(channels, team, totals)
        obj_str = s._format_json(obj)

        if not skip_write:
            if ofile!="--":
                of=open(ofile,"wt")
                print >> of, obj_str
                of.close()
                print "saved config to ", ofile
            else:
                print obj_str

        return obj_str

    @staticmethod
    def _format_json(obj):
        op = StringIO.StringIO()
        print >>op, '{"CTs": {'
        CTs = obj['CTs']
        ctnames = sorted(CTs.keys(), key=lambda nm: int(nm[2:]))
        for idx, ctname in enumerate(ctnames):
            if idx != 0: print >>op, ",",
            print >>op, '"%s":'%(ctname), json.dumps(CTs[ctname])
        print >>op, '}, "Registers": {'
        REGS = obj['Registers']
        regnames = sorted(REGS.keys(), key=lambda rg: int(rg[1:]))
        for idx, regname in enumerate(regnames):
            if idx != 0: print >>op, ",",
            print >>op, '"%s":'%(regname), json.dumps(REGS[regname])
        print >>op, '}}' 
        return op.getvalue()

    @staticmethod
    def _to_json(channels, team, totals):
        chmap = dict( (ch.id, ch) for ch in channels)
        teammap = dict ( (tm.id, tm) for tm in team)

        obj = {}
        obj['Registers'] = REGS = {}
        obj['CTs'] = CTs = {}

        # we are only interested in CT1.. CT12 here
        # The PTs are considered
        for ctnum in range(1, 13):
            visualCTNAME = 'CT%d' % (ctnum)
            if visualCTNAME in EG_CTCFG.CT_MAP_REV and EG_CTCFG.CT_MAP_REV[visualCTNAME] in chmap:
                ct = chmap[EG_CTCFG.CT_MAP_REV[visualCTNAME]]
                mul, _, _, calibration, _ = ct.val.split(',')
                mul_str = "{:.3f}".format(float(mul))
                
            cts = {}
            if mul_str in EG_CTCFG.CT_CFG_BY_MULTIPLIER:
                ct_type = EG_CTCFG.CT_CFG_BY_MULTIPLIER[mul_str][0]
            else:
                ct_type = 'custom'
                cts['mul'] = mul_str

            cts['rating'] = ct_type
            if calibration:
                cts['cal'] = calibration
            CTs[visualCTNAME] = cts
        
        for regnum in range(17):
            if regnum in teammap:
                reg = teammap[regnum]
                REGS["R{}".format(regnum)] = {'name': reg.name,
                            'val': reg.val, 'type': reg.type}

        return obj

    @staticmethod
    def _from_json(obj):
        channels, teams, totals = [], [], []
        # <ch0> ... <ch15> .. not all will always be available
        CTs = obj['CTs']
        for ch_id in range(16):
            if ch_id not in EG_CTCFG.CT_MAP: continue

            ctname = EG_CTCFG.CT_MAP[ch_id]
            if ctname in [ "L1", "L2", "L3" ]:
                channels.append(Channel._make((ch_id,EG_CTCFG.get_ch_row('PT'))))
            else:
                ct = CTs[ctname]
                cal = None
                if 'cal' in ct:
                    cal = ct['cal']
                mul = None
                if 'mul' in ct:
                    mul = ct['mul']
                ch_row = EG_CTCFG.get_ch_row(ct['rating'], cal, mul)
                channels.append(Channel._make((ch_id,ch_row)))

        # process team --> registers
        REGS = obj['Registers']
        regnames = sorted(REGS.keys(), key=lambda rg: int(rg[1:]))
        for idx, regname in enumerate(regnames):
            ridx = regname[1:]
            reg = REGS[regname]
            rg=Reg._make((int(ridx),
                              reg['name'],
                              reg['val'],
                              reg['type']))
            teams.append(rg)

        return channels, teams, totals

    @staticmethod
    def get_installation_POST(channels,team,totals):
        # channels
        op = ""
        for ch in channels:
            op += "ch%d=%s\n" %(ch.id,ch.val)
        # team
        op += "team=\n"
        op += "member=\"local\"\n"
        op += "link=\"local\"\n"

        for reg in team:
            op += "name=\"%s\"\n" %reg.name
            op += "id=\"%d\"\n" %reg.id
            op += "val=\"%s\"\n" %reg.val
            op += "type=\"%s\"\n" %reg.type

        op += "team_end=\n"
        op += "totals=\n"
        for mp in totals:
            op += "map%d=%s\n" %(mp.id,mp.val)

        return op

    @staticmethod
    def parse_installation(content):
        teams = []
        totals = []
        channels = []
        root = ET.XML(content)
        # <ch0> ... <ch15> .. not all will always be available
        for ch_id in range(16):
            chid="ch%d"%ch_id
            ch=root.find(chid)
            if ch != None: 
                channels.append(Channel._make((ch_id,ch.text)))

        # <settings> <team> <tmember> if type=='local'
        team = root.findall('team')[0]
        tmembers = team.findall('tmember')
        # this will be set correctly to 'local' tmember
        tmember = None
        
        for tm in tmembers:
           ttype=tm.find('type').text 
           if ttype == 'local':
               tmember=tm
               break
        # tmember is set now 
        if tmember is not None:
            for reg in tmember.findall('reg'):
                rg=Reg._make((int(reg.find('id').text),
                              reg.find('name').text,
                              reg.find('val').text,
                              reg.find('type').text))
                teams.append(rg)

        # virtual registers
        total = root.findall('totals')[0]
        for idx,mp in enumerate(total.findall('map')):
            totals.append(Total._make((idx,mp.text)))

        return channels, teams, totals

    def getcfg(s, ofile=None, skip_write=False):
        uri="/cgi-bin/protected/egauge-cfg"
        if ofile==None: ofile = "%s.conf.backup.%d" %(s.devurl.hostname,int(time.time()))
            
        resp, cont = s.request(uri)
        if not skip_write:
            if ofile!="--":
                of=open(ofile,"wt")
                print >> of, cont
                of.close()
                print "saved config to ", ofile
            else:
                print resp, cont
        return resp, cont

    """
     <pushURI></pushURI>
      <pushInterval>600</pushInterval>
       <pushOptions></pushOptions>
    """
    def register(s,pushURI,pushInterval=60,sec=False):
        uri="/cgi-bin/protected/egauge-cfg"
        body='pushURI="%s"\n'%pushURI
        if pushInterval:
            body+="pushInterval=%d\n"%pushInterval
        if sec:
            body+='pushOptions="sec"\n'
        s.request(uri,method="POST",body=body)
        print body

    def upgrade(s):
        uri = "/cgi-bin/protected/sw-upgrade"
        ret = s.request(uri)
        ret1 = s.reboot()
        return (ret, ret1)

    def reboot(s):
        uri = "/cgi-bin/protected/reboot"
        ret = None
        try:
            ret = s.request(uri)
        except httplib.IncompleteRead as e:
            # it is possible to get this because the server reboots
            print "harmless received ", e

        return ret

    def netconfig(s):
        uri = "/cgi-bin/netcfg?live"
        ret = s.request(uri)
        print ret
        return ret

    def get(s, uri):
        ret = s.request(uri)
        print ret[1]
        return ret

    def getpushstatus(s):
        uri = "/cgi-bin/get?pushStatus"
        ret = s.request(uri)
        print ret[1]
        return ret

    def getntp(s):
        uri = "/cgi-bin/get?ntp"
        ret = s.request(uri)
        print ret[1]
        return ret

    def status(s):
        uri = "/status.xml"
        """
        <?xml version="1.0" encoding="UTF-8" ?>
        <status>
           <timestamp>0x52273a9b</timestamp>
           <swRev>1.35</swRev>
           <uptime>73442.63</uptime>
           <lastWebReboot>1378229174</lastWebReboot>
           <rebootReason>Software Reset</rebootReason>
           <tempC>52.00</tempC>
           <speed>12357142</speed>
           <osvers>#319 Fri Mar 22 14:57:37 MDT 2013</osvers>
           <model>egauge2</model>
        </status>
        """
        resp, content = s.request(uri)

        root = ET.XML(content)

        st = {}
        for child in root._children:
            st[child.tag] = child.text

        print st
        return st



actions = [ "register", "de-register", "reboot", "upgrade" , "getconfig"
            ,"getregisters", "setconfig", "setregisters", "netconfig", "getntp", "setntp", 
            "getpushstatus", "status", "get" ]

def cfg_opts():
    from optparse import OptionParser
    parser = OptionParser(usage="""usage: %prog action device_url [options]
                action = {}""".format("|".join(actions)))
    parser.add_option("--seconds", default=False, action="store_true",
                    help="will try to fetch seconds data if specified")
    parser.add_option( "--username", default="owner")
    parser.add_option( "--password", default="default")
    parser.add_option( "--cfgfile", default=None, help ="-- will write to stdout")
    parser.add_option( "--pushInterval")
    parser.add_option( "--pushURI")
    parser.add_option( "--ntpServer")
    parser.add_option( "--path")

    return parser
 
def main():
    parser = cfg_opts()
    (options, args) = parser.parse_args()
    main_opts(parser, options, args)

def main_opts(parser, options, args):
    if len(args)<2:
        parser.print_help()
        exit(2)

    action = args[0]
    device_url = args[1]

    if action not in actions:
        print "unknown", action
        parser.print_help()
        exit(2)
    eg=egcfg(device_url, options.username, options.password, logger)

    pushInterval=None
    if options.pushInterval:
        pushInterval = int(options.pushInterval)
    if action == "register":
        eg.register(options.pushURI, pushInterval, options.seconds)
    if action == "de-register":
        eg.register("", pushInterval, options.seconds)
    elif action == "reboot":
        eg.reboot()
    elif action == "upgrade":
        eg.upgrade()
    elif action == "netconfig":
        eg.netconfig()
    elif action == "status":
        eg.status()
    elif action == "getntp":
        eg.getntp()
    elif action == "get":
        eg.get(options.path)
    elif action == "getpushstatus":
        eg.getpushstatus()
    elif action == "getconfig":
        eg.getcfg(options.cfgfile)
    elif action == "setconfig":
        eg.setcfg(options.cfgfile)
    elif action == "setntp":
        if options.ntpServer is None:
          print "ntpServer is required for setntp"
          exit(2)
        eg.setntp(options.ntpServer)
    elif action == "getregisters":
        eg.getregisters(options.cfgfile)
    elif action == "setregisters":
        eg.setregisters(options.cfgfile)
    
if __name__ == "__main__":
    main()
   
