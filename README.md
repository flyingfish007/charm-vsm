# charm-vsm-controller
Charm of juju for Virtual-Storage-Manager(VSM) Controller.
- VSM consists of vsm-controller and vsm-agent nodes.
- The charm aims to deploy the vsm-controller with vsm-api, vsm-scheduler and vsm-conductor.

### Notice
* The charm-keystone is developed by openstack. So the valid service don't include the 'vsm'. So after you install the charm-keystone, you should change the code of it.
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
