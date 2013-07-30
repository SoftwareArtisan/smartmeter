import httplib2
import httplib
import urllib
import os
import logging
import time
import urlparse

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("eg_cfg")

class egcfg:
    def __init__(s,devurl,username,password,lg):
        if not devurl.startswith('http'):
            devurl = "http://"+devurl
        s.devurl=urlparse.urlparse(devurl)
        s.username=username
        s.password=password
        s.lg=lg
        s.req = httplib2.Http(timeout=60)
        s.req.add_credentials(username, password)   # Digest Authentication

    def request(s,uri,method="GET", body=None):
        if not uri.startswith("/"):
            uri = "/"+uri
        requrl=s.devurl.geturl()+uri
        print requrl
        response, content = s.req.request (requrl,method=method, 
                headers={'Connection': 'Keep-Alive', 
                        'accept-encoding': 'gzip',
                        'Content-Type':'application/xml'},
                body=body)
        if response['status'] == '401':
            s.lg.info("Unauthorized request!")
        elif response['status'] == '400':
            s.lg.info("Bad Request!")
        elif response['status'] == '500':
            s.lg.info("Internal Error!")
        elif response['status'] == '408':
            s.lg.info("Request timeout!")
        elif response['status'] == '404':
            s.lg.info("device not found. Probably it is not up")
        elif 'Not Authorized' in content:
            s.lg.info("Unauthorized request!")

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

    def regs(s):
        response, content = s.getcfg()
        channels, team, totals = s.parse_installation(content)
        post_body = s.get_installation_POST(channels, team, totals)
        print post_body

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
        from elementtree import ElementTree as ET
        from collections import namedtuple
        teams = []
        totals = []
        channels = []
        Total = namedtuple('map', 'id,val')
        Reg = namedtuple('reg','id,name,val,type')
        Channel = namedtuple('ch', 'id,val')
        root = ET.XML(content)
        # <ch0> ... <ch15> .. not all will always be available
        for ch_id in range(16):
            chid="ch%d"%ch_id
            ch=root.find(chid)
            if ch != None: channels.append(Channel._make((ch_id,ch.text)))

        # <settings> <team> <tmember> if type=='local'
        team = root.findall('team')[0]
        tmembers = team.findall('tmember')
        if len(tmembers)==0:
            tmember = tmembers[0]
        else:
            for tm in tmembers:
               ttype=tm.find('type').text 
               if ttype == 'local':
                   tmember=tm
                   break
        # tm is set now 
        for reg in tm.findall('reg'):
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

    def getcfg(s, ofile=None):
        uri="/cgi-bin/protected/egauge-cfg"
        if ofile==None: ofile = "%s.conf.backup.%d" %(s.devurl.hostname,int(time.time()))
            
        resp, cont = s.request(uri)
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
        return s.request(uri)

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

actions = [ "register", "de-register", "reboot", "upgrade" , "getconfig"
            ,"getregisters", "setconfig", "netconfig", "setntp" ]

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
        eg.regs()
    
if __name__ == "__main__":
    main()
   
