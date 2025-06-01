from mininet.topo import Topo
from qemu_mininet_components import QemuHost

class ScaledLanTopo(Topo):
    """
    Scaled LAN Topology: q1..q5 -- s1
    All VMs on 10.0.0.x/24 network.
    """
    def build(self, **_opts):
        s1 = self.addSwitch('s1')

        # Define VM parameters statically, similar to basic_lan
        vm_list = [
            {
                'name': 'q1',
                'overlay': '/tmp/qemu_scale1_overlay.qcow2',
                'tap': 'taps1',
                'mac': '52:54:00:5C:A1:10',
                'qemu_ip': '127.0.0.1',
                'ssh_host_port': 2221,
                'mgmt_mac_suffix': '10',
                'app_ip': '10.0.0.10/24',
                'exp_intf_name': 'ens4',
                'bridge_name': 's1',
            },
            {
                'name': 'q2',
                'overlay': '/tmp/qemu_scale2_overlay.qcow2',
                'tap': 'taps2',
                'mac': '52:54:00:5C:A1:11',
                'qemu_ip': '127.0.0.1',
                'ssh_host_port': 2222,
                'mgmt_mac_suffix': '11',
                'app_ip': '10.0.0.11/24',
                'exp_intf_name': 'ens4',
                'bridge_name': 's1',
            },
            {
                'name': 'q3',
                'overlay': '/tmp/qemu_scale3_overlay.qcow2',
                'tap': 'taps3',
                'mac': '52:54:00:5C:A1:12',
                'qemu_ip': '127.0.0.1',
                'ssh_host_port': 2223,
                'mgmt_mac_suffix': '12',
                'app_ip': '10.0.0.12/24',
                'exp_intf_name': 'ens4',
                'bridge_name': 's1',
            },
            {
                'name': 'q4',
                'overlay': '/tmp/qemu_scale4_overlay.qcow2',
                'tap': 'taps4',
                'mac': '52:54:00:5C:A1:13',
                'qemu_ip': '127.0.0.1',
                'ssh_host_port': 2224,
                'mgmt_mac_suffix': '13',
                'app_ip': '10.0.0.13/24',
                'exp_intf_name': 'ens4',
                'bridge_name': 's1',
            },
            {
                'name': 'q5',
                'overlay': '/tmp/qemu_scale5_overlay.qcow2',
                'tap': 'taps5',
                'mac': '52:54:00:5C:A1:14',
                'qemu_ip': '127.0.0.1',
                'ssh_host_port': 2225,
                'mgmt_mac_suffix': '14',
                'app_ip': '10.0.0.14/24',
                'exp_intf_name': 'ens4',
                'bridge_name': 's1',
            },
        ]

        for vm in vm_list:
            host = self.addHost(vm['name'], cls=QemuHost,
                                overlay=vm['overlay'],
                                tap=vm['tap'],
                                mac=vm['mac'],
                                qemu_ip=vm['qemu_ip'],
                                ssh_host_port=vm['ssh_host_port'],
                                mgmt_mac_suffix=vm['mgmt_mac_suffix'],
                                app_ip=vm['app_ip'],
                                exp_intf_name=vm['exp_intf_name'],
                                bridge_name=vm['bridge_name'])
            self.addLink(host, s1)