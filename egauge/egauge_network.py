__author__ = 'willr'

import requests
from datetime import datetime

from ConfigParser import SafeConfigParser
import codecs
from StringIO import StringIO

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("egauge_network")

class NetworkConfiguration(object):

    SECTION_NETWORK = 'network'
    VALID_KEYS = ['ipaddr','dhcp', 'netmask', 'network', 'broadcast', 'gateway', 'dns0', 'dns1', 'dns2', 'dns3', 'bridging']

    def __init__(self, options=None):

        if options and len(options):

            if 'base' in options:
                print options['base']
                self.load_config(options['base'])

            for k, v in options.items():
                if v:
                    setattr(self, k, v)

    def load_config(self, filenames):
        if not filenames:
            return
        cfg = SafeConfigParser()
        cfg.read(filenames)
        for k, v in cfg.items(self.SECTION_NETWORK):
            setattr(self, k, v)

    def _as_config(self):
        config = SafeConfigParser()
        config.add_section(self.SECTION_NETWORK)
        for k in dir(self):
            if k in self.VALID_KEYS:
                config.set(self.SECTION_NETWORK, k, getattr(self, k, ''))
        return config

    def save_config(self, filename):
        config = self._as_config()
        with codecs.open(os.path.join(BACKUP_FOLDER, filename), 'w', encoding='utf-8') as fp:
            config.write(fp)
        print("Backed up configuration as CFG: {}".format(filename))

    def as_config(self):
        config = self._as_config()
        sfile = StringIO()
        config.write(sfile)
        contents = sfile.getvalue()
        sfile.close()
        return contents

    def as_payload(self):
        payload = ""
        for k in dir(self):
            if k in self.VALID_KEYS:
                payload += k + "=" + getattr(self, k) + "\n"
        return payload

    def validate(self):

        from ipaddress import ip_address, ip_network

        if hasattr(self, 'network'):
            if hasattr(self, 'netmask'):
                self.ip_network = ip_network(self.network + '/' + self.netmask)
            else:
                self.ip_network = ip_network(self.network + '/24')

        if hasattr(self, 'gateway'):
            self.ip_gateway = ip_address(self.gateway)
            if not self.ip_gateway in self.ip_network:
                raise Exception('Gateway address {} not in network {}'.format(self.ip_gateway, self.ip_network))

        if hasattr(self, 'ipaddr'):
            self.ip_address = ip_address(self.ipaddr)
            if not ip_address(self.ipaddr) in self.ip_network:
                raise Exception('Assigned address {} not in network {}'.format(self.ip_address, self.ip_network))


########## TODO: Import from egauge_config

def resolve_url(devurl):
    if not devurl.startswith('http'):
        devurl = "http://" + devurl

    import urlparse

    uu = urlparse.urlparse(devurl)
    if "." not in uu.hostname:
        # we will assume that it is egauge1910, or just 1910
        if not uu.hostname.startswith("egauge"):
            hn = "egauge" + uu.hostname
        else:
            hn = uu.hostname

        # add egauge.es at the end
        hn += ".egaug.es"
        uu = urlparse.urlparse("http://" + hn)

    return uu

#########

import xmltodict
import os


class ConfigureNetwork(object):
    def __init__(self, url, username, password):
        self.url = resolve_url(url)
        self.username = username
        self.password = password

        self.egauge_id = self.url.hostname

        from requests.auth import HTTPDigestAuth

        self.auth = HTTPDigestAuth(username, password)
        self.url_configured = self.url.geturl() + '/cgi-bin/netcfg'
        self.url_live = self.url_configured + '?live'

        print self.url_configured, self.url_live

    @staticmethod
    def convert_from_xml(content):

        if content:
            try:
                return xmltodict.parse(content)
            except xmltodict.ParsingInterrupted as ex:
                logging.error('Error converting XML\n{}'.format(content))
            except Exception as ex:
                logging.exception('converting xml:'.format(content))

        return None

    def backup_existing_live(self):
        existing_live_cfg = self.get_egauge_network_cfg(live=True)
        return self.backup(existing_live_cfg,'live')

    def backup_existing_configured(self):
        existing_live_cfg = self.get_egauge_network_cfg(live=False)
        return self.backup(existing_live_cfg,'configured')

    def backup(self,cfg,type):
        if cfg:
            nc = NetworkConfiguration(cfg)
            curtime = datetime.utcnow().isoformat().translate(None, ':')
            newest_backup = '{}_{}_{}_backup.cfg'.format(self.egauge_id, curtime,type)
            nc.save_config(newest_backup)
            return nc

    def retrieve_most_recent(self):
        import os
        import glob

        saved_backups = glob.iglob(os.path.join(BACKUP_FOLDER, '{}_*live*.cfg'.format(self.egauge_id)))
        newest_backup = max([f for f in saved_backups], key=os.path.getctime) if saved_backups else None
        if newest_backup:
            nc = NetworkConfiguration()
            nc.load_config([newest_backup])

    def display_most_recent(self):
        print self.retrieve_most_recent()

    def configure_egauge_network(self, network_cfg):
        payload = network_cfg.as_payload()
        self.backup_existing_live()
        resp = requests.post(url=self.url_configured, data=payload, auth=self.auth)
        return resp.content

    def get_egauge_network_cfg(self, live=False):
        url = self.url_live if live else self.url_configured
        resp = requests.get(url=url, auth=self.auth)
        settings = self.convert_from_xml(resp.content)
        return settings['settings'] if settings and 'settings' in settings else None

    def configure(self, nc, dryrun=False):

        print("Requested network configuration")
        print nc.as_config()

        print("Backup current {} live network configuration.".format(self.egauge_id))
        existing_live = self.backup_existing_live()
        print existing_live.as_config()

        print("{} configured network configuration:".format(self.egauge_id))
        existing_configured = self.backup_existing_configured()
        print existing_configured.as_config()

        if 'no' in existing_live.dhcp:
            raise Exception('{} currently configured for static networking.')

        if dryrun:
            print("Finished dry run.")
            return

        print("Reconfigure {} with new IP and requested base network configuration.".format(self.egauge_id))
        nc.dhcp = 'no'
        print(self.configure_egauge_network(nc))

        print("Reconfigure {} with DHCP = yes to maintain network connectivity.".format(self.egauge_id))
        nc.dhcp = 'yes'
        print(self.configure_egauge_network(nc))

        print("Backup current {} live network configuration.".format(self.egauge_id))
        existing_live = self.backup_existing_live()
        print existing_live.as_config()

        print("Backup current {} configured network configuration.".format(self.egauge_id))
        existing_configured = self.backup_existing_configured()
        print existing_configured.as_config()


import argparse

def add_subparser(parser):
    subparsers = parser.add_subparsers(help='network configuration sub-command')
    subparser = subparsers.add_parser("network")
    subparser.add_argument("--dryrun", default=False, action="store_true")
    subparser.add_argument("--urls", default=False, action="store_true")
    subparser.add_argument("--base", nargs='+', type=str,
                           help='Configuration file setting common parameters. Command line arguments override.')
    subparser.add_argument('--dhcp', choices=['yes', 'no'],
                           help="Automatically obtain address using DHCP. If 'yes', everything but bridging option ignored.")
    subparser.add_argument('--ipaddr',
                           help='IP address (x.x.x.x). This option defines the static IP address used by the device (e.g., 192.168.1.77).')
    subparser.add_argument('--netmask',
                           help='Netmask (x.x.x.x). This options defines the IP network mask used by the device (e.g., 255.255.255.0).')
    subparser.add_argument('--network',
                           help='Network (x.x.x.x). This option defines the IP network number used by the device (e.g., 192.168.1.0).')
    subparser.add_argument('--broadcast',
                           help='Broadcast address (x.x.x.x). This option defines the IP broadcast address used by the device (e.g., 192.168.1.255).')
    subparser.add_argument('--gateway',
                           help='Gateway address (x.x.x.x). This option defines the IP address of the gateway used by the device (e.g., 192.168.1.1).')
    subparser.add_argument('--dns0', help='Primary server used by device to resolve domain-names(ex. "pool.ntp.org").')
    subparser.add_argument('--dns1',
                           help='Secondary server used by device to resolve domain-names(ex. "pool.ntp.org").')
    subparser.add_argument('--dns2',
                           help='Secondary server used by device to resolve domain-names(ex. "pool.ntp.org").')
    subparser.add_argument('--dns3',
                           help='Secondary server used by device to resolve domain-names(ex. "pool.ntp.org").')
    subparser.add_argument('--bridging', choices=['yes', 'no'],
                           help='Enable bridging. Normally, eGauge communicates through a single network interface at any given time (e.g., HomePlug or hardwired Ethernet). If you turn on this option, the interfaces are bridged together, meaning that eGauge will transparently forward all traffic between the interfaces, creating a single logical network. Bridging can be useful when multiple eGauges are installed at a single location. You can then hardwire one device and, assuming the other devices can communicate with the first one via HomePlug, enable bridging on the first device to tie all devices into the LAN. In effect, the first device acts as a HomePlug adapter for the others. In bridging mode, eGauge enables the spanning tree protocol (STP as defined by IEEE 802.1D) to support automatic loop detection. However, most consumer-grade networking equipment does not support STP, so it may still be possible to create a loop that could flood a LAN with packets. For example, this could happen if eGauge bridges traffic beteen HomePlug and LAN and another HomePlug adapter is plugged into the same LAN. In other words: when enabling bridging, make sure there are no loops or use only equipment that supports STP. Bridging works by putting the network interfaces into promiscuous mode, which means eGauge will receive and process any and all packets received over that link. This increases processing overheads and therefore is not recommend on LANs with lots of unrelated traffic.')

DEFAULT_PASSWORD = "default"
if 'EG_PASSWORD' in os.environ:
    DEFAULT_PASSWORD = os.environ['EG_PASSWORD']
DEFAULT_USERNAME = "owner"
if 'EG_USERNAME' in os.environ:
    DEFAULT_USERNAME = os.environ['EG_USERNAME']

UPLOAD_FOLDER = '/tmp/network/uploads'  #tempfile.mkdtemp()
BACKUP_FOLDER = '/tmp/network/backups'


def ensure_dirs(dirs=[UPLOAD_FOLDER, BACKUP_FOLDER]):
    for dir in dirs:
        try:
            os.makedirs(dir)
        except:
            logging.error('Error making directory ' + dir)

if __name__ == '__main__':
    ensure_dirs([UPLOAD_FOLDER, BACKUP_FOLDER])

    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str, help='eGauge ID or complete url')
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="export EG_PASSWORD instead of this")

    add_subparser(parser)

    #options = parser.parse_args(good_parameters)
    options = parser.parse_args()
    nc = NetworkConfiguration(vars(options))
    cfg_net = ConfigureNetwork(options.url, options.username, options.password)
    cfg_net.configure(nc,options.dryrun)

    if options.urls:
        print('live_url='+cfg_net.url_live)
        print('conf_url='+cfg_net.url_configured)
