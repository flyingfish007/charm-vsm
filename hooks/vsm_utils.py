from copy import deepcopy
from collections import OrderedDict
import subprocess
import utils

from charmhelpers.contrib.openstack import (
    templating,
    context,
)

from charmhelpers.core.decorators import (
    retry_on_exception,
)

from charmhelpers.core.hookenv import (
    config,
    log
)


TEMPLATES = 'templates/'

VSM_CONF_DIR = "/etc/vsm"
VSM_CONF = '%s/vsm.conf' % VSM_CONF_DIR

BASE_RESOURCE_MAP = OrderedDict([
    (VSM_CONF, {
        'contexts': [context.SharedDBContext(),
                     context.AMQPContext(),
                     context.IdentityServiceContext(
                         service='vsm',
                         service_user='vsm')],
        'services': ['vsm-api', 'vsm-scheduler', 'vsm-conductor',
                     'vsm-agent', 'vsm-physical']
    }),
])


def register_configs(release=None):
    """Register config files with their respective contexts.
    Regstration of some configs may not be required depending on
    existing of certain relations.
    """
    # if called without anything installed (eg during install hook)
    # just default to earliest supported release. configs dont get touched
    # till post-install, anyway.
    release = "vsm"
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)
    for cfg, rscs in resource_map().iteritems():
        configs.register(cfg, rscs['contexts'])
    return configs

def resource_map(release=None):
    """
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    """
    resource_map = deepcopy(BASE_RESOURCE_MAP)
    return resource_map

def restart_map():
    '''Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    role = utils.config_get('role')

    if role == "controller":
        return OrderedDict([(cfg, ['vsm-api', 'vsm-scheduler', 'vsm-conductor'])
                            for cfg, v in resource_map().iteritems()])
    elif role == "agent":
        return OrderedDict([(cfg, ['vsm-agent', 'vsm-physical'])
                            for cfg, v in resource_map().iteritems()])

# NOTE(jamespage): Retry deals with sync issues during one-shot HA deploys.
#                  mysql might be restarting or suchlike.
@retry_on_exception(5, base_delay=3, exc_type=subprocess.CalledProcessError)
def migrate_database():
    'Runs cinder-manage to initialize a new database or migrate existing'
    cmd = ['vsm-manage', 'db', 'sync']
    subprocess.check_call(cmd)

def service_enabled(service):
    '''Determine if a specific cinder service is enabled in
    charm configuration.

    :param service: str: cinder service name to query (volume, scheduler, api,
                         all)

    :returns: boolean: True if service is enabled in config, False if not.
    '''
    enabled = config()['enabled-services']
    if enabled == 'all':
        return True
    return service in enabled

def juju_log(msg):
    log('[vsm] %s' % msg)
