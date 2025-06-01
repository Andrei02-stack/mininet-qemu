from mininet.topo import Topo
from qemu_mininet_components import QemuHost # Assuming components.py is in PYTHONPATH or same dir

class BasicLanTopo(Topo):
    """
    Basic LAN Topology: q1 -- s1 -- q2
    q1: 10.0.0.10/24
    q2: 10.0.0.11/24
    No router, no external gateway needed for intra-LAN communication.
    """
    def build(self, **_opts):
        s1 = self.addSwitch('s1')

        q1_params = {
            'overlay': '/tmp/qemu_basic1_overlay.qcow2', 'tap': 'tapb1',
            'mac': '52:54:00:B4:51:10', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2211,
            'mgmt_mac_suffix': 'b1', 'app_ip': '10.0.0.10/24', 'exp_intf_name': 'ens4',
            'bridge_name': 's1', 
        }
        q1 = self.addHost('q1', cls=QemuHost, **q1_params)
        # Do NOT add link for QemuHost - TAP is handled by QemuHost.startQemu()

        q2_params = {
            'overlay': '/tmp/qemu_basic2_overlay.qcow2', 'tap': 'tapb2',
            'mac': '52:54:00:B4:51:11', 'qemu_ip': '127.0.0.1', 'ssh_host_port': 2212,
            'mgmt_mac_suffix': 'b2', 'app_ip': '10.0.0.11/24', 'exp_intf_name': 'ens4',
            'bridge_name': 's1',
        }
        q2 = self.addHost('q2', cls=QemuHost, **q2_params)
        # Do NOT add link for QemuHost - TAP is handled by QemuHost.startQemu()