# charm-vsm-controller
Charm of juju for Virtual-Storage-Manager(VSM) Controller.
- VSM consists of vsm-controller and vsm-agent nodes.
- The charm aims to deploy the vsm-controller with vsm-api, vsm-scheduler and vsm-conductor.

### Prepare
* You should install the juju by youself at first [juju](https://jujucharms.com/).

### Notice(Important)
* The charm-keystone is developed by openstack. So the valid service don't include the 'vsm'. So after you install the charm-keystone, you should change the code of it.
* You should run "juju ssh <keystone/*>", then "sudo vim /var/lib/juju/agents/unit-<keystone-*>/charm/hooks/keystone_utils.py".
* Of the keystone_utils.py, you should add as followed:
```py
valid_services = {
    "vsm": {
        "type": "vsm",
        "desc": "VSM Service"
    },
    ...
}
```

### Steps of Install from Source
```sh
$ cd ~
$ mkdir -p charms/trusty
$ cd charms/trusty
$ git clone https://github.com/flyingfish007/charm-vsm-controller.git
$ mv charm-vsm-controller vsm-controller
$ juju deploy --repository=$HOME/charms local:trusty/vsm-controller
```
