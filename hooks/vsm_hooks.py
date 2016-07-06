#!/usr/bin/python

import sys
import subprocess
import utils

from vsm_utils import (
    auth_token_config,
    juju_log,
    migrate_database,
    register_configs,
    service_enabled,
    PRE_INSTALL_PACKAGES,
    VSM_PACKAGES,
    VSM_CONF
)

from charmhelpers.core.hookenv import (
    charm_dir,
    config,
    network_get_primary_address,
    relation_set,
    unit_get,
    UnregisteredHookError,
    Hooks
)

from charmhelpers.core.host import (
    rsync
)

from charmhelpers.contrib.openstack.ip import (
    canonical_url,
    ADMIN,
    INTERNAL,
    PUBLIC
)

from charmhelpers.fetch import (
    add_source,
    apt_install,
    apt_update
)

hooks = Hooks()

CONFIGS = register_configs()


@hooks.hook('install.real')
def install():
    juju_log('**********install.real')
    rsync(
        charm_dir() + '/packages/vsm-dep-repo',
        '/opt'
    )
    rsync(
        charm_dir() + '/packages/vsmrepo',
        '/opt'
    )
    rsync(
        charm_dir() + '/files/apt.conf',
        '/etc/apt'
    )
    rsync(
        charm_dir() + '/files/vsm.list',
        '/etc/apt/sources.list.d'
    )
    rsync(
        charm_dir() + '/files/vsm-dep.list',
        '/etc/apt/sources.list.d'
    )
    apt_update()
    apt_install(VSM_PACKAGES)
    juju_log('**********finished to install vsm vsm-dashboard python-vsmclient')
    add_source(config('ceph-source'), config('ceph-key'))
    apt_update(fatal=True)
    apt_install(packages=PRE_INSTALL_PACKAGES, fatal=True)


@hooks.hook('shared-db-relation-joined')
def db_joined():
    juju_log('**********shared-db-relation-joined')
    try:
        # NOTE: try to use network spaces
        host = network_get_primary_address('shared-db')
    except NotImplementedError:
        # NOTE: fallback to private-address
        host = unit_get('private-address')
    conf = config()
    relation_set(database=conf['database'],
                 username=conf['database-user'],
                 hostname=host)


@hooks.hook('shared-db-relation-changed')
def db_changed():
    juju_log('**********shared-db-relation-changed')
    juju_log('**********CONFIGS.complete_contexts(): %s' % str(CONFIGS.complete_contexts()))
    if 'shared-db' not in CONFIGS.complete_contexts():
        juju_log('shared-db relation incomplete. Peer not ready?')
        return
    juju_log('**********CONFIGS is %s' % str(CONFIGS))
    CONFIGS.write(VSM_CONF)
    migrate_database()
    config_vsm_controller()


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    juju_log('**********amqp-relation-joined')
    juju_log('**********relation_id is %s' % str(relation_id))
    conf = config()
    relation_set(relation_id=relation_id,
                 username=conf['rabbit-user'], vhost=conf['rabbit-vhost'])


@hooks.hook('amqp-relation-changed')
def amqp_changed():
    juju_log('**********amqp-relation-changed')
    if 'amqp' not in CONFIGS.complete_contexts():
        juju_log('amqp relation incomplete. Peer not ready?')
        return
    juju_log('**********CONFIGS is %s' % str(CONFIGS))
    CONFIGS.write(VSM_CONF)
    config_vsm_controller()


@hooks.hook('identity-service-relation-joined')
def identity_joined(rid=None):
    juju_log('**********identity-service-relation-joined')
    if not service_enabled('api'):
        juju_log('api service not enabled; skipping endpoint registration')
        return

    public_url = '{}:{}/v1/$(tenant_id)s'.format(
        canonical_url(CONFIGS, PUBLIC),
        config('api-listening-port')
    )
    internal_url = '{}:{}/v1/$(tenant_id)s'.format(
        canonical_url(CONFIGS, INTERNAL),
        config('api-listening-port')
    )
    admin_url = '{}:{}/v1/$(tenant_id)s'.format(
        canonical_url(CONFIGS, ADMIN),
        config('api-listening-port')
    )
    settings = {
        'region': None,
        'service': None,
        'public_url': None,
        'internal_url': None,
        'admin_url': None,
        'vsm_region': config('region'),
        'vsm_service': 'vsm',
        'vsm_public_url': public_url,
        'vsm_internal_url': internal_url,
        'vsm_admin_url': admin_url,
    }
    juju_log("**********settings is %s" % str(settings))
    juju_log("**********relation_id is %s" % str(rid))
    relation_set(relation_id=rid, **settings)


@hooks.hook('identity-service-relation-changed')
def identity_changed():
    juju_log('**********identity-service-relation-changed')
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('identity-service relation incomplete. Peer not ready?')
        return
    juju_log('**********CONFIGS.write(VSM_CONF)')
    juju_log('**********CONFIGS is %s' % str(CONFIGS))
    CONFIGS.write(VSM_CONF)
    config_vsm_controller()


@hooks.hook('vsm-agent-relation-joined')
def agent_joined(rid=None):
    rel_settings = {}
    rel_settings.update(keystone_agent_settings())
    relation_set(relation_id=rid, **rel_settings)


@hooks.hook('vsm-agent-relation-changed')
def agent_changed():
    return


def keystone_agent_settings():
    ks_auth_config = _auth_config()
    rel_settings = {}
    rel_settings.update(ks_auth_config)
    return rel_settings

def _auth_config():
    '''Grab all KS auth token config from vsm.conf, or return empty {}'''
    cfg = {
        'service_host': auth_token_config('identity_uri').split('/')[2].split(':')[0],
        'admin_user': auth_token_config('admin_user'),
        'admin_password': auth_token_config('admin_password')
    }
    return cfg

def config_vsm_controller():
    if 'shared-db' in CONFIGS.complete_contexts() and \
        'amqp' in CONFIGS.complete_contexts() and \
        'identity-service' in CONFIGS.complete_contexts():

        service_host = auth_token_config('identity_uri').split('/')[2].split(':')[0]
        net = '.'.join(service_host.split('.')[0:3]) + ".0\/24"
        subprocess.check_call(['sudo', 'sed', '-i', 's/^192.168.*/%s/g' % net,
                               '/etc/manifest/cluster.manifest'])
        keystone_vsm_service_password = auth_token_config('admin_password')
        subprocess.check_call(['sudo', 'sed', '-i',
                               's/^KEYSTONE_VSM_SERVICE_PASSWORD =*.*/KEYSTONE_VSM_SERVICE_PASSWORD = %s/g' % keystone_vsm_service_password,
                               '/etc/vsm-dashboard/local_settings'])
        subprocess.check_call(['sudo', 'sed', '-i', 's/^OPENSTACK_HOST =*.*/OPENSTACK_HOST = %s/g' % service_host,
                               '/etc/vsm-dashboard/local_settings'])
        subprocess.check_call(['sudo', 'sed', '-i', 's/^OPENSTACK_KEYSTONE_DEFAULT_ROLE =*.*/OPENSTACK_KEYSTONE_DEFAULT_ROLE = "_member"/g',
                               '/etc/vsm-dashboard/local_settings'])

        subprocess.check_call(['sudo', 'service', 'vsm-api', 'restart'])
        subprocess.check_call(['sudo', 'service', 'vsm-scheduler', 'restart'])
        subprocess.check_call(['sudo', 'service', 'vsm-conductor', 'restart'])
        subprocess.check_call(['sudo', 'service', 'apache2', 'restart'])


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        utils.juju_log('warn', 'Unknown hook {} - skipping.'.format(e))
