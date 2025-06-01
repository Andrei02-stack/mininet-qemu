from mininet.topo import Topo
from qemu_mininet_components import QemuHost, LinuxRouter

class VlanTopo(Topo):
    """
    VLAN Topology REVISED:
    q1, q2 (VLAN 100, TAP-uri pe s1) -- s1 -- r0 (trunk)
    q3, q4 (VLAN 200, TAP-uri pe s1) -- s1
    s1 is a single switch. Router r0 connects to s1 via a trunk port.
    VMs' TAP interfaces are added to s1. OVS port for each TAP is configured as access.

    VLAN 100 Subnet: 10.0.100.0/24, Router (r0-phys-trunk.100): 10.0.100.1
    VLAN 200 Subnet: 10.0.200.0/24, Router (r0-phys-trunk.200): 10.0.200.1
    """
    def build(self, **_opts):
        s1 = self.addSwitch('s1')
        # The router's main IP is conceptual; sub-interfaces will have IPs.
        # The physical trunk interface should NOT have an IP.
        router = self.addNode('r0', cls=LinuxRouter, ip=None) 

        # Link between switch and router (this will be trunk)
        # Mininet will create s1-eth1 (or s1-trunk) and r0-eth1 (or r0-phys-trunk)
        self.addLink(s1, router, intfName1='s1-trunk-port', intfName2='r0-phys-trunk')

        vm_configs = [
            # VLAN 100 VMs
            {'name': 'q1', 'overlay': '/tmp/qemu_vlan1_overlay.qcow2', 'tap': 'tapv100q1', # Distinct TAP names
             'mac': '52:54:00:AA:01:10', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2261,
             'mgmt_mac_suffix': 'A1', 'app_ip': '10.0.100.10/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.100.1', 'bridge_name': 's1', 'vlan_access_tag': 100,
             'static_routes': [{'subnet': '10.0.200.0/24', 'via': '10.0.100.1'}]},
            {'name': 'q2', 'overlay': '/tmp/qemu_vlan2_overlay.qcow2', 'tap': 'tapv100q2',
             'mac': '52:54:00:AA:01:11', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2262,
             'mgmt_mac_suffix': 'A2', 'app_ip': '10.0.100.11/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.100.1', 'bridge_name': 's1', 'vlan_access_tag': 100,
             'static_routes': [{'subnet': '10.0.200.0/24', 'via': '10.0.100.1'}]},
            # VLAN 200 VMs
            {'name': 'q3', 'overlay': '/tmp/qemu_vlan3_overlay.qcow2', 'tap': 'tapv200q3',
             'mac': '52:54:00:BB:01:10', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2263,
             'mgmt_mac_suffix': 'B1', 'app_ip': '10.0.200.10/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.200.1', 'bridge_name': 's1', 'vlan_access_tag': 200,
             'static_routes': [{'subnet': '10.0.100.0/24', 'via': '10.0.200.1'}]},
            {'name': 'q4', 'overlay': '/tmp/qemu_vlan4_overlay.qcow2', 'tap': 'tapv200q4',
             'mac': '52:54:00:BB:01:11', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2264,
             'mgmt_mac_suffix': 'B2', 'app_ip': '10.0.200.11/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.200.1', 'bridge_name': 's1', 'vlan_access_tag': 200,
             'static_routes': [{'subnet': '10.0.100.0/24', 'via': '10.0.200.1'}]}
        ]

        for config in vm_configs:
            host_name = config.pop('name') 
            host_params = config 
            
            q_host = self.addHost(host_name, cls=QemuHost, **host_params)

            # DO NOT ADD self.addLink(q_host, s1) FOR QEMUHOSTS
            # Connection is made through TAP in QemuHost.startQemu() using 'bridge_name'
            # and VLAN configuration will be done on the TAP port on OVS.

        # Store VLAN info for runner's use
        self.vlans = {
            100: ['q1', 'q2'],
            200: ['q3', 'q4']
        }
        self.trunk_vlans = {100, 200}

    def get_router_interface(self):
        """Return the router's physical interface name that connects to the switch"""
        return 'r0-phys-trunk'

    def get_router_link(self):
        """Return the router's link to the switch"""
        return self.links[0]  # First link is router-switch