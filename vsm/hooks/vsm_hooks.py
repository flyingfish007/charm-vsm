#!/usr/bin/python

import sys
import utils
from subprocess import check_call
from charmhelpers.core.hookenv import (
    Hooks,
    config,
    network_get_primary_address,
    unit_get,
    relation_set,
    relation_get,
    UnregisteredHookError
)
from charmhelpers.contrib.openstack.utils import sync_db_with_multi_ipv6_addresses

hooks = Hooks()


@hooks.hook('shared-db-relation-joined')
def db_joined():
    utils.juju_log('info', '**********shared-db-relation-joined')
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
    utils.juju_log('info', '**********shared-db-relation-changed')

    # # to initial the vsm db
    # cmd = ['vsm-manage', 'db', 'sync']
    # check_call(cmd)


@hooks.hook('amqp-relation-joined')
def amqp_joined():
    utils.juju_log('info', '**********amqp-relation-joined')


@hooks.hook('amqp-relation-changed')
def amqp_changed():
    utils.juju_log('info', '**********amqp-relation-changed')


@hooks.hook('identity-service-relation-joined')
def identity_joined():
    utils.juju_log('info', '**********identity-service-relation-joined')


@hooks.hook('identity-service-relation-changed')
def identity_changed():
    utils.juju_log('info', '**********identity-service-relation-changed')


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        utils.juju_log('warn', 'Unknown hook {} - skipping.'.format(e))
