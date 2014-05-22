__author__ = 'willr'

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# create a file handler
handler = logging.FileHandler('egauge_upgrade.log')
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

from datetime import datetime

from egauge_config import get_opts,egcfg
extra_args = ['--timeout', '60']

def should_upgrade(status,new_version):
    return True

def check_status(status):
    if not status:
        raise Exception("Can't get current status.")
    return status

def check_upgrade((upgrade_resp,reboot_resp)):
    if not upgrade_resp:
        raise Exception("Upgrade response invalid {}".format(upgrade_resp))
    check_reboot(reboot_resp)

def check_reboot(resp):
    if not resp:
        raise Exception("Reboot response invalid {}".format(resp))

def check_getregisters(resp):
    if not resp:
        raise Exception("getregisters response invalid {}".format(resp))

def check_register(resp):
    if not resp:
        raise Exception("register response invalid {}".format(resp))

def upgrade(options):

    eg = egcfg(options.url, options.username, options.password, logger)
    eg.timeout = int(options.timeout)

    if not options.cfgfile:
        options.cfgfile = '{}_{}_backup.json'.format(eg.device,datetime.utcnow().isoformat().translate(None, '[:\.]'))

    try:
        status = check_status(eg.status())
        if should_upgrade(status, options.branch):
            check_getregisters(eg.getregisters(options.cfgfile, version=options.version))
            check_upgrade(eg.upgrade(options.branch))
            logger.info("{} was successfully upgraded to most recent firmware.".format(eg.device))
            check_register(eg.register(options.pushURI, options.pushInterval, options.seconds))
            check_reboot(eg.reboot())
            check_status(eg.status())
            logger.info("{} finished upgrading.".format(eg.device))
        else:
            logger.info("{} not upgraded to firmware {} because already at {}.".format(eg.device,options.branch,status['swRev']))

    except Exception as ex:
        logger.error("{} was not upgraded to most recent firmware {}".format(eg.device, ex))

def main():
    upgrade(get_opts())

if __name__ == "__main__":
    main()
