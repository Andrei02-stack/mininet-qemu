from mininet.topo import Topo
from qemu_mininet_components import QemuHost, LinuxRouter

class RoutedSubnetsTopo(Topo):
    """
    Original Topology:
    q1, q2 -- s1 -- r0 -- s2 -- q3
    Network 1 (s1): 10.0.0.0/24, Router IP: 10.0.0.1
    Network 2 (s2): 10.0.1.0/24, Router IP: 10.0.1.1
    """
    def build(self, **_opts):
        # Router
        # The primary IP '10.0.0.1/24' for r0 in addNode is just a conceptual default for Mininet.
        # Actual interface IPs are set via params2 in addLink.
        router = self.addNode('r0', cls=LinuxRouter, ip='10.0.0.1/24') 
                                                            
        # Switch 1 and links
        s1 = self.addSwitch('s1')
        self.addLink(s1, router, intfName1='s1-eth1', params1={}, # Switch port to router
                                 intfName2='r0-eth1', params2={'ip': '10.0.0.1/24'}) # Router intf to s1

        # Switch 2 and links
        s2 = self.addSwitch('s2')
        self.addLink(s2, router, intfName1='s2-eth1', params1={},
                                 intfName2='r0-eth2', params2={'ip': '10.0.1.1/24'}) # Router intf to s2

        # VM configurations
        vm_configs = [
            {'name': 'q1', 'overlay': '/tmp/qemu_routed1_overlay.qcow2', 'tap': 'tapr1',
             'mac': '52:54:00:12:34:10', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2201,
             'mgmt_mac_suffix': '01', 'app_ip': '10.0.0.10/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.0.1', 'switch_node': s1, 'bridge_name': 's1',
             'static_routes': [{'subnet': '10.0.1.0/24', 'via': '10.0.0.1'}]},
            {'name': 'q2', 'overlay': '/tmp/qemu_routed2_overlay.qcow2', 'tap': 'tapr2',
             'mac': '52:54:00:12:34:11', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2202,
             'mgmt_mac_suffix': '02', 'app_ip': '10.0.0.11/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.0.1', 'switch_node': s1, 'bridge_name': 's1',
             'static_routes': [{'subnet': '10.0.1.0/24', 'via': '10.0.0.1'}]},
            {'name': 'q3', 'overlay': '/tmp/qemu_routed3_overlay.qcow2', 'tap': 'tapr3',
             'mac': '52:54:00:12:34:12', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2203,
             'mgmt_mac_suffix': '03', 'app_ip': '10.0.1.10/24', 'exp_intf_name': 'ens4',
             'default_gw': '10.0.1.1', 'switch_node': s2, 'bridge_name': 's2',
             'static_routes': [{'subnet': '10.0.0.0/24', 'via': '10.0.1.1'}]}
        ]

        for config in vm_configs:
            # Params to be stored on the QemuHost object directly by Mininet's addHost
            # These are accessible via host.params['key']
            host_params = {k: v for k, v in config.items() if k not in ['name', 'switch_node', 'cls']}
            
            host = self.addHost(config['name'], cls=QemuHost, **host_params)
            # Do NOT add a Mininet link for QemuHost; TAP is handled by QemuHost logic.
            # self.addLink(host, config['switch_node'])