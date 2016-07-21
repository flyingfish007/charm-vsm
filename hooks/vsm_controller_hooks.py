#!/usr/bin/python

import sys
import subprocess
import utils

from vsm_controller_utils import (
    add_known_host,
    auth_token_config,
    initialize_ssh_keys,
    juju_log,
    migrate_database,
    public_ssh_key,
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
    open_port,
    relation_get,
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

from charmhelpers.contrib.openstack.utils import (
    get_host_ip,
    get_hostname
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
def db_joined(relation_id=None):
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
                 hostname=host,
                 relation_id=relation_id)


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
def agent_joined(relation_id=None):
    initialize_ssh_keys()
    host = unit_get('private-address')
    settings = {
        'hostname': get_hostname(host),
        'hostaddress': get_host_ip(host)
    }

    keystone_host = auth_token_config('identity_uri').split('/')[2].split(':')[0]
    admin_tenant_name = auth_token_config('admin_tenant_name')
    admin_user = auth_token_config('admin_user')
    admin_password = auth_token_config('admin_password')
    args = ['agent-token', admin_tenant_name, admin_user, admin_password, keystone_host]
    token_tenant = subprocess.check_output(args).strip('\n')
    settings['token_tenant'] = token_tenant

    settings['ssh_public_key'] = public_ssh_key()
    relation_set(relation_id=relation_id, **settings)


@hooks.hook('vsm-agent-relation-changed')
def agent_changed(rid=None, unit=None):
    if 'shared-db' not in CONFIGS.complete_contexts():
        juju_log('shared-db relation incomplete. Peer not ready?')
        return
    if 'amqp' not in CONFIGS.complete_contexts():
        juju_log('amqp relation incomplete. Peer not ready?')
        return
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('identity-service relation incomplete. Peer not ready?')
        return

    juju_log('**********rid is %s' % str(rid))
    juju_log('**********unit is %s' % str(unit))
    rel_settings = relation_get(rid=rid, unit=unit)
    agent_hostname = rel_settings.get('hostname')
    agent_hostaddress = rel_settings.get('hostaddress')
    juju_log('**********agent_hostname is %s' % agent_hostname)
    juju_log('**********agent_hostaddress is %s' % agent_hostaddress)
    host = unit_get('private-address')
    hostname = get_hostname(host)
    hostaddress = get_host_ip(host)
    juju_log('**********host is %s' % host)
    juju_log('**********hostname is %s' % hostname)
    juju_log('**********hostaddress is %s' % hostaddress)
    hosts = [agent_hostname, hostname, agent_hostaddress, hostaddress]
    for host in hosts:
        if host:
            add_known_host(host, unit=unit, user='root')


def config_vsm_controller():
    if 'shared-db' in CONFIGS.complete_contexts() and \
        'amqp' in CONFIGS.complete_contexts() and \
        'identity-service' in CONFIGS.complete_contexts():

        service_host = auth_token_config('identity_uri').split('/')[2].split(':')[0]
        net = '.'.join(service_host.split('.')[0:3]) + ".0\/24"
        subprocess.check_call(['sudo', 'sed', '-i', 's/^192.168.*/%s/g' % net,
                               '/etc/manifest/cluster.manifest'])
        subprocess.check_call(['sudo', 'service', 'vsm-api', 'restart'])
        subprocess.check_call(['sudo', 'service', 'vsm-scheduler', 'restart'])
        subprocess.check_call(['sudo', 'service', 'vsm-conductor', 'restart'])

        # TODO fix the hardcode of vsm-dashboard.
        subprocess.check_call(['sudo', 'sed', '-i', "s/'service'/'services'/g",
                               '/usr/share/vsm-dashboard/vsm_dashboard/api/vsm.py'])
        keystone_vsm_service_password = auth_token_config('admin_password')
        local_settings = "/usr/share/vsm-dashboard/vsm_dashboard/local/local_settings.py"
        etc_local_settings = "/etc/vsm-dashboard/local_settings"
        rsync(
            charm_dir() + '/files/local_settings.template',
            local_settings
        )
        subprocess.check_call(['sudo', 'sed', '-i',
                               's/^KEYSTONE_VSM_SERVICE_PASSWORD =*.*/KEYSTONE_VSM_SERVICE_PASSWORD = "%s"/g' % keystone_vsm_service_password,
                               local_settings])
        subprocess.check_call(['sudo', 'sed', '-i', 's/^OPENSTACK_HOST =*.*/OPENSTACK_HOST = "%s"/g' % service_host,
                               local_settings])
        subprocess.check_call(['sudo', 'sed', '-i', 's/^OPENSTACK_KEYSTONE_DEFAULT_ROLE =*.*/OPENSTACK_KEYSTONE_DEFAULT_ROLE = "_member_"/g',
                               local_settings])
        subprocess.check_call(['sudo', 'rm', '-rf', etc_local_settings])
        subprocess.check_call(['sudo', 'ln', '-sf', local_settings, etc_local_settings])

        rsync(
            charm_dir() + '/scripts/https',
            '/tmp/https'
        )
        subprocess.check_call(['sudo', 'bash', '/tmp/https'])
        subprocess.check_call(['sudo', 'service', 'apache2', 'restart'])
        open_port('443')
        open_port('80')


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        utils.juju_log('warn', 'Unknown hook {} - skipping.'.format(e))
