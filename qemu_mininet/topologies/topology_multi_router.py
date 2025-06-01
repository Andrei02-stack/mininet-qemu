from mininet.topo import Topo
from qemu_mininet_components import QemuHost, LinuxRouter

class MultiRouterTopo(Topo):
    """
    Topology with two interconnected LANs.
    LAN 1: q1, q2 -- s1 -- r0
           Network: 10.0.1.0/24
           q1: 10.0.1.10, gw 10.0.1.1
           q2: 10.0.1.11, gw 10.0.1.1
           r0 (on s1): 10.0.1.1

    LAN 2: q3, q4 -- s2 -- r1
           Network: 10.0.3.0/24
           q3: 10.0.3.10, gw 10.0.3.1
           q4: 10.0.3.11, gw 10.0.3.1
           r1 (on s2): 10.0.3.1


    Router Interconnection:
           r0 -- r1
           Network: 10.0.12.0/30
           r0: 10.0.12.1
           r1: 10.0.12.2
    """
    def build(self, **_opts):
        # --- LAN 1 ---
        s1 = self.addSwitch('s1')
        r0 = self.addNode('r0', cls=LinuxRouter, ip='10.0.1.1/24') # Conceptual IP for r0

        # Connect r0 to s1
        self.addLink(s1, r0, intfName2='r0-lan1-eth0', params2={'ip': '10.0.1.1/24'})

        # VMs for LAN 1
        lan1_vm_configs = [
            {
                'name': 'q1',
                'overlay': '/tmp/qemu_lan1_vm1_overlay.qcow2', 'tap': 'taplan1vm1',
                'mac': '52:54:00:12:01:10', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2251,
                'mgmt_mac_suffix': '11',
                'app_ip': '10.0.1.10/24', 'exp_intf_name': 'ens4',
                'default_gw': '10.0.1.1',
                'bridge_name': 's1',
            },
            {
                'name': 'q2',
                'overlay': '/tmp/qemu_lan1_vm2_overlay.qcow2', 'tap': 'taplan1vm2',
                'mac': '52:54:00:12:01:11', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2252,
                'mgmt_mac_suffix': '12',
                'app_ip': '10.0.1.11/24', 'exp_intf_name': 'ens4',
                'default_gw': '10.0.1.1',
                'bridge_name': 's1',
            }
        ]

        for config in lan1_vm_configs:
            host_name = config.pop('name')
            host_params = config
            host = self.addHost(host_name, cls=QemuHost, **host_params)
            # DO NOT add self.addLink for QemuHosts

        # --- LAN 2 ---
        s2 = self.addSwitch('s2')
        r1 = self.addNode('r1', cls=LinuxRouter, ip='10.0.3.1/24') # Conceptual IP for r1

        # Connect r1 to s2
        self.addLink(s2, r1, intfName2='r1-lan2-eth0', params2={'ip': '10.0.3.1/24'})

        # VMs for LAN 2
        lan2_vm_configs = [
            {
                'name': 'q3',
                'overlay': '/tmp/qemu_lan2_vm1_overlay.qcow2', 'tap': 'taplan2vm1',
                'mac': '52:54:00:12:02:10', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2253,
                'mgmt_mac_suffix': '13',
                'app_ip': '10.0.3.10/24', 'exp_intf_name': 'ens4',
                'default_gw': '10.0.3.1',
                'bridge_name': 's2',
            },
            {
                'name': 'q4',
                'overlay': '/tmp/qemu_lan2_vm2_overlay.qcow2', 'tap': 'taplan2vm2',
                'mac': '52:54:00:12:02:11', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2254,
                'mgmt_mac_suffix': '14',
                'app_ip': '10.0.3.11/24', 'exp_intf_name': 'ens4',
                'default_gw': '10.0.3.1',
                'bridge_name': 's2',
            }
        ]

        for config in lan2_vm_configs:
            host_name = config.pop('name')
            host_params = config
            host = self.addHost(host_name, cls=QemuHost, **host_params)
            # DO NOT add self.addLink for QemuHosts

        # --- Router Interconnection ---
        # Add direct link between r0 and r1
        self.addLink(r0, r1,
                    intfName1='r0-r1-eth0', params1={'ip': '10.0.12.1/30'},
                    intfName2='r1-r0-eth0', params2={'ip': '10.0.12.2/30'})
        