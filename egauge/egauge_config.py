import httplib2
import urllib
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("eg_cfg")

class egcfg:
    def __init__(s,devurl,username,password,lg):
        s.devurl=devurl
        s.username=username
        s.password=password
        s.lg=lg
        s.req = httplib2.Http(timeout=60)
        s.req.add_credentials(username, password)   # Digest Authentication

    def request(s,uri,method="GET", body=None):
        requrl=s.devurl+uri
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

        print response, content
        return response, content
    
    def regs(s):
        registers = {}
        response, content = s.cfg()
        from elementtree import ElementTree as ET
        from collections import namedtuple
        Reg = namedtuple('reg','id,name,val,type')
        root = ET.XML(content)
        # <settings> <team> <tmember> if type=='local'
        team = root.findall('team')[0]
        tmembers = team.findall('tmember')
        if len(tmembers)==0:
            tmember = tmembers[0]
        else:
            for tm in tmembers:
               ttype=tm.find('type').text 
               print "ttype", ttype
               if ttype == 'local':
                   tmember=tm
                   break
        # tm is set now 
        for reg in tm.findall('reg'):
            rg=Reg._make((int(reg.find('id').text),
                          reg.find('name').text,
                          reg.find('val').text,
                          reg.find('type').text))
            registers[rg.name] = rg


        print registers
        return registers

    def cfg(s):
        uri="/cgi-bin/protected/egauge-cfg"
        return s.request(uri)

    """
     <pushURI></pushURI>
      <pushInterval>600</pushInterval>
       <pushOptions></pushOptions>
    """
    def register(s,pushURI,pushInterval=60,sec=False):
        uri="/cgi-bin/protected/egauge-cfg"
        body='pushURI="%s"'%pushURI
        s.request(uri,method="POST",body=body)
        if pushInterval:
            body="pushInterval=%d"%pushInterval
            s.request(uri,method="POST",body=body)
        if sec:
            body='pushOptions="sec"'
            s.request(uri,method="POST",body=body)
        print body

    def upgrade(s):
        uri = "/cgi-bin/protected/sw-upgrade"
        return s.request(uri)

    def reboot(s):
        uri = "/cgi-bin/protected/reboot"
        return s.request(uri)

def main():
    from optparse import OptionParser
    parser = OptionParser(usage="""usage: %prog action device_url [options]
                action = getconfig | getregisters | register | reboot | upgrade """)
    parser.add_option("--seconds", default=False, action="store_true",
                    help="will try to fetch seconds data if specified")
    parser.add_option( "--username", default="owner")
    parser.add_option( "--password", default="default")
    parser.add_option( "--pushInterval")
    parser.add_option( "--pushURI")
    (options, args) = parser.parse_args()

    if len(args)<2:
        parser.print_help()
        exit(2)

    action = args[0]
    device_url = args[1]

    if action not in [ "register", "reboot", "upgrade" , "getconfig" ,"getregisters"]:
        parser.print_help()
        exit(2)

    eg=egcfg(device_url, options.username, options.password, logger)

    pushInterval=None
    if options.pushInterval:
        pushInterval = int(options.pushInterval)
    if action == "register":
        eg.register(options.pushURI, pushInterval, options.seconds)
    elif action == "reboot":
        eg.reboot()
    elif action == "upgrade":
        eg.upgrade()
    elif action == "getconfig":
        eg.cfg()
    elif action == "getregisters":
        eg.regs()
    
if __name__ == "__main__":
    main()
   
