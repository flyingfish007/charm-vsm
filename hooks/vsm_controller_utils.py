from copy import deepcopy
from collections import OrderedDict
import os
import pwd
import subprocess
from subprocess import check_output
import ConfigParser

from charmhelpers.contrib.network.ip import (
    is_ipv6
)

from charmhelpers.contrib.openstack import (
    templating,
    context,
)

from charmhelpers.contrib.openstack.utils import (
    get_host_ip,
    get_hostname,
    is_ip
)

from charmhelpers.core.decorators import (
    retry_on_exception,
)

from charmhelpers.core.hookenv import (
    config,
    log,
    relation_get,
    remote_unit,
    ERROR
)


VSM_SSH_DIR = '/etc/vsm/agent_ssh/'
TEMPLATES = 'templates/'
VSM_CONF_DIR = "/etc/vsm"
VSM_CONF = '%s/vsm.conf' % VSM_CONF_DIR
PACKAGE_VSM = 'vsm'
PACKAGE_VSM_DASHBOARD = 'vsm-dashboard'
PACKAGE_PYTHON_VSMCLIENT = 'python-vsmclient'
PACKAGE_VSM_DEPLOY = 'vsm-deploy'
VSM_PACKAGES = [PACKAGE_VSM,
                PACKAGE_VSM_DASHBOARD,
                PACKAGE_PYTHON_VSMCLIENT,
                PACKAGE_VSM_DEPLOY]
PRE_INSTALL_PACKAGES = ['ceph', 'ceph-mds', 'librbd1', 'rbd-fuse',
                        'radosgw', 'apache2', 'libapache2-mod-wsgi',
                        'libapache2-mod-fastcgi', 'memcached', 'mariadb-server',
                        'ntp', 'openssh-server', 'openssl', 'keystone',
                        'expect', 'smartmontools']


BASE_RESOURCE_MAP = OrderedDict([
    (VSM_CONF, {
        'contexts': [context.SharedDBContext(),
                     context.AMQPContext(),
                     context.IdentityServiceContext(
                         service='vsm',
                         service_user='vsm')],
        'services': ['vsm-api', 'vsm-scheduler', 'vsm-conductor']
    }),
])


def register_configs():
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


def resource_map():
    """
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    """
    r_map = deepcopy(BASE_RESOURCE_MAP)
    return r_map


# NOTE(jamespage): Retry deals with sync issues during one-shot HA deploys.
#                  mysql might be restarting or suchlike.
@retry_on_exception(5, base_delay=3, exc_type=subprocess.CalledProcessError)
def migrate_database():
    'Runs vsm-manage to initialize a new database or migrate existing'
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
    log('[vsm-controller] %s' % msg)


def auth_token_config(setting):
    """
    Returns currently configured value for setting in vsm.conf's
    authtoken section, or None.
    """
    config = ConfigParser.RawConfigParser()
    config.read('/etc/vsm/vsm.conf')
    try:
        value = config.get('keystone_authtoken', setting)
    except:
        return None
    if value.startswith('%'):
        return None
    return value


def add_known_host(host, unit=None, user=None):
    '''Add variations of host to a known hosts file.'''
    cmd = ['ssh-keyscan', '-H', '-t', 'rsa', host]
    try:
        remote_key = subprocess.check_output(cmd).strip()
    except Exception as e:
        log('Could not obtain SSH host key from %s' % host, level=ERROR)
        raise e

    current_key = ssh_known_host_key(host, unit, user)
    if current_key and remote_key:
        if is_same_key(remote_key, current_key):
            log('Known host key for compute host %s up to date.' % host)
            return
        else:
            remove_known_host(host, unit, user)

    log('Adding SSH host key to known hosts for compute node at %s.' % host)
    with open(known_hosts(unit, user), 'a') as out:
        out.write(remote_key + '\n')


def ssh_known_host_key(host, unit=None, user=None):
    cmd = ['ssh-keygen', '-f', known_hosts(unit, user), '-H', '-F', host]
    try:
        # The first line of output is like '# Host xx found: line 1 type RSA',
        # which should be excluded.
        output = subprocess.check_output(cmd).strip()
    except subprocess.CalledProcessError:
        return None

    if output:
        # Bug #1500589 cmd has 0 rc on precise if entry not present
        lines = output.split('\n')
        if len(lines) > 1:
            return lines[1]

    return None


def known_hosts(unit=None, user=None):
    return os.path.join(ssh_directory_for_unit(unit, user), 'known_hosts')


def ssh_directory_for_unit(unit=None, user=None):
    if unit:
        remote_service = unit.split('/')[0]
    else:
        remote_service = remote_unit().split('/')[0]
    if user:
        remote_service = "{}_{}".format(remote_service, user)
    _dir = os.path.join(VSM_SSH_DIR, remote_service)
    for d in [VSM_SSH_DIR, _dir]:
        if not os.path.isdir(d):
            os.mkdir(d)
    for f in ['authorized_keys', 'known_hosts']:
        f = os.path.join(_dir, f)
        if not os.path.isfile(f):
            open(f, 'w').close()
    return _dir


def is_same_key(key_1, key_2):
    # The key format get will be like '|1|2rUumCavEXWVaVyB5uMl6m85pZo=|Cp'
    # 'EL6l7VTY37T/fg/ihhNb/GPgs= ssh-rsa AAAAB', we only need to compare
    # the part start with 'ssh-rsa' followed with '= ', because the hash
    # value in the beginning will change each time.
    k_1 = key_1.split('= ')[1]
    k_2 = key_2.split('= ')[1]
    return k_1 == k_2


def remove_known_host(host, unit=None, user=None):
    log('Removing SSH known host entry for compute host at %s' % host)
    cmd = ['ssh-keygen', '-f', known_hosts(unit, user), '-R', host]
    subprocess.check_call(cmd)


def authorized_keys(unit=None, user=None):
    return os.path.join(ssh_directory_for_unit(unit, user), 'authorized_keys')


def initialize_ssh_keys(user='root'):
    home_dir = pwd.getpwnam(user).pw_dir
    ssh_dir = os.path.join(home_dir, '.ssh')
    if not os.path.isdir(ssh_dir):
        os.mkdir(ssh_dir)

    priv_key = os.path.join(ssh_dir, 'id_rsa')
    if not os.path.isfile(priv_key):
        log('Generating new ssh key for user %s.' % user)
        cmd = ['ssh-keygen', '-q', '-N', '', '-t', 'rsa', '-b', '2048',
               '-f', priv_key]
        check_output(cmd)

    pub_key = '%s.pub' % priv_key
    if not os.path.isfile(pub_key):
        log('Generating missing ssh public key @ %s.' % pub_key)
        cmd = ['ssh-keygen', '-y', '-f', priv_key]
        p = check_output(cmd).strip()
        with open(pub_key, 'wb') as out:
            out.write(p)
    check_output(['chown', '-R', user, ssh_dir])


def public_ssh_key(user='root'):
    home = pwd.getpwnam(user).pw_dir
    try:
        with open(os.path.join(home, '.ssh', 'id_rsa.pub')) as key:
            return key.read().strip()
    except:
        return None
