#!/usr/bin/python

import sys
import utils

from vsm_utils import (
    register_configs,
    VSM_CONF,
    migrate_database,
    service_enabled,
    juju_log
)

from charmhelpers.core.hookenv import (
    Hooks,
    config,
    network_get_primary_address,
    unit_get,
    relation_set,
    UnregisteredHookError
)

from charmhelpers.contrib.openstack.ip import (
    canonical_url,
    PUBLIC, INTERNAL, ADMIN
)

from charmhelpers.contrib.openstack.utils import sync_db_with_multi_ipv6_addresses

hooks = Hooks()

CONFIGS = register_configs()


@hooks.hook('shared-db-relation-joined')
def db_joined():
    juju_log('**********shared-db-relation-joined')
    if config('prefer-ipv6'):
        sync_db_with_multi_ipv6_addresses(config('database'),
                                          config('database-user'))
    else:
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
    CONFIGS.write(VSM_CONF)
    migrate_database()

@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    juju_log('**********amqp-relation-joined')
    conf = config()
    relation_set(relation_id=relation_id,
                 username=conf['rabbit-user'], vhost=conf['rabbit-vhost'])

@hooks.hook('amqp-relation-changed')
def amqp_changed():
    juju_log('**********amqp-relation-changed')
    if 'amqp' not in CONFIGS.complete_contexts():
        juju_log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write(VSM_CONF)


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
        'region': config('region'),
        'service': 'vsm',
        'public_url': public_url,
        'internal_url': internal_url,
        'admin_url': admin_url,
        'vsm_region': config('region'),
        'vsm_service': 'vsm',
        'vsm_public_url': public_url,
        'vsm_internal_url': internal_url,
        'vsm_admin_url': admin_url,
    }
    relation_set(relation_id=rid, **settings)


@hooks.hook('identity-service-relation-changed')
def identity_changed():
    juju_log('**********identity-service-relation-changed')
    if 'identity-service' not in CONFIGS.complete_contexts():
        juju_log('identity-service relation incomplete. Peer not ready?')
        return
    CONFIGS.write(VSM_CONF)


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        utils.juju_log('warn', 'Unknown hook {} - skipping.'.format(e))
