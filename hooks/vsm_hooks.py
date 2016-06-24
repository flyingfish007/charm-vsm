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
from charmhelpers.contrib.openstack import context

hooks = Hooks()


# @hooks.hook('shared-db-relation-joined')
# def db_joined():
#     utils.juju_log('info', '**********shared-db-relation-joined')
#     if config('prefer-ipv6'):
#         sync_db_with_multi_ipv6_addresses(config('database'),
#                                           config('database-user'))
#     else:
#         try:
#             # NOTE: try to use network spaces
#             host = network_get_primary_address('shared-db')
#         except NotImplementedError:
#             # NOTE: fallback to private-address
#             host = unit_get('private-address')
#         conf = config()
#         relation_set(database=conf['database'],
#                      username=conf['database-user'],
#                      hostname=host)
#
#
# @hooks.hook('db-relation-changed')
# def db_changed():
#     utils.juju_log('info', '**********db-relation-changed')
#
#     # # to initial the vsm db
#     # cmd = ['vsm-manage', 'db', 'sync']
#     # check_call(cmd)


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    utils.juju_log('info', '**********amqp-relation-joined')
    conf = config()
    relation_set(relation_id=relation_id,
                 username=conf['rabbit-user'], vhost=conf['rabbit-vhost'])

@hooks.hook('amqp-relation-changed')
def amqp_changed():
    ctx = context.AMQPContext().__call__()
    rabbitmq_host = ctx['rabbitmq_host']
    rabbitmq_user = ctx['rabbitmq_user']
    rabbitmq_password = ctx['rabbitmq_password']
    rabbitmq_virtual_host = ctx['rabbitmq_virtual_host']

    utils.juju_log('info', '**********rabbitmq_host is %s' % rabbitmq_host)
    utils.juju_log('info', '**********rabbitmq_user is %s' % rabbitmq_user)
    utils.juju_log('info', '**********rabbitmq_password is %s' % rabbitmq_password)
    utils.juju_log('info', '**********rabbitmq_virtual_host is %s' % rabbitmq_virtual_host)
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
