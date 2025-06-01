import os
import subprocess
import time
import importlib # For dynamic topology loading
import argparse
import traceback

from mininet.net import Mininet
from mininet.log import setLogLevel, info
from mininet.link import TCLink
from qemu_cli import QemuCLI as CLI # Or your custom CLI

from qemu_mininet_components import (
    QemuHost, QemuSwitch, LinuxRouter,
    create_common_hosts_file, BASE_QEMU_IMAGE, MININET_HOSTS_FILE
)

def configure_vlan_ports(net, topo_obj):
    """Configure OVS port tags (on TAPs) and router sub-interfaces for VLANs."""
    info("*** Configuring VLANs (on TAP ports and Router)...\n")
    
    r0 = net.nameToNode.get('r0')
    s1 = net.nameToNode.get('s1')

    if not r0 or not s1:
        info("*** Router r0 or Switch s1 not found, skipping VLAN configuration.\n")
        return

    router_physical_trunk_intf_name = None
    switch_port_to_router = None

    # Find physical link between s1 and r0
    for link in net.links:
        node1, node2 = link.intf1.node, link.intf2.node
        if (node1 == s1 and node2 == r0):
            switch_port_to_router = link.intf1.name
            router_physical_trunk_intf_name = link.intf2.name
            break
        elif (node1 == r0 and node2 == s1):
            switch_port_to_router = link.intf2.name
            router_physical_trunk_intf_name = link.intf1.name
            break
    
    if not router_physical_trunk_intf_name or not switch_port_to_router:
        info(f"*** ERROR: Could not find link between r0 and s1 for VLAN trunk setup.\n")
        return

    info(f"*** Router physical trunk interface to s1: {r0.name}-{router_physical_trunk_intf_name}\n")
    info(f"*** Switch port for trunk to router: {s1.name}-{switch_port_to_router}\n")

    # Ensure router's physical trunk interface is UP and has NO IP
    r0.cmd(f'ip addr flush dev {router_physical_trunk_intf_name}')
    r0.cmd(f'ip link set {router_physical_trunk_intf_name} up')
    
    all_vlan_ids_for_trunk = set()

    # First, add all TAP interfaces to OVS bridge
    for host in net.hosts:
        if isinstance(host, QemuHost) and host.params.get('bridge_name') == s1.name:
            tap_if_name = host.tap
            if tap_if_name:
                info(f"*** Adding TAP interface {tap_if_name} to OVS bridge {s1.name}\n")
                # First ensure the TAP interface exists and is up
                s1.cmd(f'sudo ip link set {tap_if_name} up')
                # Then add it to OVS bridge
                s1.cmd(f'sudo ovs-vsctl --may-exist add-port {s1.name} {tap_if_name}')
                # Wait a moment for OVS to process the port
                time.sleep(1)

    # Then configure VLAN tags on TAP ports
    for host in net.hosts:
        if isinstance(host, QemuHost) and host.params.get('bridge_name') == s1.name:
            vlan_tag = host.params.get('vlan_access_tag')
            tap_if_name = host.tap
            
            if vlan_tag and tap_if_name:
                info(f"*** Setting OVS port {tap_if_name} (for {host.name}) on {s1.name} as ACCESS for VLAN {vlan_tag}\n")
                # First check if port exists
                port_check = s1.cmd(f'sudo ovs-vsctl list port {tap_if_name}')
                if "no row" not in port_check:
                    s1.cmd(f'sudo ovs-vsctl set port {tap_if_name} tag={vlan_tag}')
                    all_vlan_ids_for_trunk.add(str(vlan_tag))
                else:
                    info(f"*** ERROR: Port {tap_if_name} not found in OVS bridge {s1.name}\n")
            else:
                info(f"*** WARNING: No VLAN tag or TAP name for QemuHost {host.name} to configure on {s1.name}.\n")

    # Configure trunk port on s1
    if all_vlan_ids_for_trunk and switch_port_to_router:
        trunk_vlans_str = ",".join(sorted(list(all_vlan_ids_for_trunk)))
        info(f"*** Setting switch port {switch_port_to_router} on {s1.name} as TRUNK for VLANs: {trunk_vlans_str}\n")
        s1.cmd(f'sudo ovs-vsctl set port {switch_port_to_router} trunks={trunk_vlans_str}')
    elif not all_vlan_ids_for_trunk:
        info(f"*** No VLANs found from QemuHost params, skipping trunk port setup on {s1.name}.\n")
        return 
    elif not switch_port_to_router:
        info(f"*** Switch port to router not identified, cannot set up trunk on {s1.name}.\n")
        return

    # Configure VLAN sub-interfaces on router r0
    for vlan_id_str in sorted(list(all_vlan_ids_for_trunk)):
        vlan_id = int(vlan_id_str)
        # Use a simpler name format for VLAN interfaces
        sub_intf_name = f"vlan{vlan_id}" 
        router_vlan_ip = f"10.0.{vlan_id}.1/24" 
        
        info(f"*** Creating sub-interface {sub_intf_name} on {r0.name} with IP {router_vlan_ip}\n")
        # Remove any existing interface with this name
        r0.cmd(f'ip link del {sub_intf_name} 2>/dev/null || true') 
        # Create VLAN interface
        r0.cmd(f'ip link add link {router_physical_trunk_intf_name} name {sub_intf_name} type vlan id {vlan_id}')
        # Configure IP and bring up
        r0.cmd(f'ip addr add {router_vlan_ip} dev {sub_intf_name}')
        r0.cmd(f'ip link set {sub_intf_name} up')
        # Wait a moment for interface to be ready
        time.sleep(1)

    # Enable IP forwarding on router
    r0.cmd('sysctl net.ipv4.ip_forward=1')
    info('*** VLAN configuration complete\n')

def create_common_hosts_file(nodes_for_hosts_file):
    info('*** Creating common /etc/hosts file for all nodes\n')
    hosts_content = [
        "127.0.0.1   localhost",
        "::1     localhost ip6-localhost ip6-loopback",
        "ff02::1 ip6-allnodes",
        "ff02::2 ip6-allrouters",
        ""
    ]
    
    hosts_content.append("# QEMU VM Data Plane IPs")
    for node in nodes_for_hosts_file:
        if isinstance(node, QemuHost) and node.app_ip and node.name:
            hosts_content.append(f"{node.app_ip}\t{node.name}")
    
    hosts_content.append("\n# Router Interface IPs")
    for node in nodes_for_hosts_file:
        if isinstance(node, LinuxRouter):
            # Add the router's name with its first interface IP
            for intf_name, intf_obj in node.nameToIntf.items():
                if getattr(intf_obj, 'ip', None):
                    hosts_content.append(f"{intf_obj.ip}\t{node.name}")
                    break
            # Add all router interfaces
            for intf_name, intf_obj in node.nameToIntf.items():
                if getattr(intf_obj, 'ip', None):
                    # For VLAN interfaces, use a simpler name format
                    if '.' in intf_name:
                        vlan_id = intf_name.split('.')[-1]
                        hostname = f"{node.name}-vlan{vlan_id}"
                    else:
                        hostname = f"{node.name}-{intf_name.replace(node.name + '-', '')}"
                    hosts_content.append(f"{intf_obj.ip}\t{hostname}")
    
    hosts_content.append("\n# End of Mininet host entries")
    with open(MININET_HOSTS_FILE, 'w') as f:
        f.write('\n'.join(hosts_content) + '\n')
    os.chmod(MININET_HOSTS_FILE, 0o644)
    info(f"*** Created common hosts file at {MININET_HOSTS_FILE}:\n" + "\n".join(hosts_content) + "\n")
    return MININET_HOSTS_FILE

def run_experiment(topo_class, topo_name="Experiment"):
    setLogLevel('debug')
    info(f"*** Starting Experiment: {topo_name} ***\n")

    try:
        subprocess.check_output(['sudo', 'ovs-vsctl', 'show'], stderr=subprocess.STDOUT)
        info("*** Open vSwitch is running.\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        info("--- ERROR: Open vSwitch is not running or ovs-vsctl is not found. Please start it. ---\n")
        return

    topo = topo_class()
    net = Mininet(topo=topo, switch=QemuSwitch, controller=None, link=TCLink,
                  autoSetMacs=True, autoStaticArp=False, build=False)

    info('*** Building network topology\n')
    net.build()

    all_qemu_hosts_in_net = [h for h in net.hosts if isinstance(h, QemuHost)]
    for node in all_qemu_hosts_in_net:
        node.params['_qemu_hosts'] = all_qemu_hosts_in_net

    info('*** Starting network (switches, controllers)\n')
    net.start() # Starts switches, controllers. Does NOT start QemuHosts.

    # Configure Routers (IP forwarding, static routes if any)
    for r_node in net.hosts:
        if isinstance(r_node, LinuxRouter):
            info(f"*** Configuring router {r_node.name}\n")
            # Add static routes on router if defined in topology (e.g., for multi-router)
            if r_node.name == 'r0' and 'MultiRouterTopo' in str(topo_class):
                # r0 needs route to 10.0.3.0/24 via 10.0.12.2 (r1's transit IP)
                r_node.cmd('ip route add 10.0.3.0/24 via 10.0.12.2 dev r0-r1-eth0')
                info(f"*** [{r_node.name}] Added static route to 10.0.3.0/24 via 10.0.12.2 dev r0-r1-eth0\n")
            if r_node.name == 'r1' and 'MultiRouterTopo' in str(topo_class):
                # r1 needs route to 10.0.1.0/24 via 10.0.12.1 (r0's transit IP)
                r_node.cmd('ip route add 10.0.1.0/24 via 10.0.12.1 dev r1-r0-eth0')
                info(f"*** [{r_node.name}] Added static route to 10.0.1.0/24 via 10.0.12.1 dev r1-r0-eth0\n")

    # Special configuration for VLANs (OVS port tags, router sub-interfaces)
    if 'VlanTopo' in str(topo_class): # Check if it's the VLAN topology
        configure_vlan_ports(net, topo)

    info('*** Starting QEMU hosts...\n')
    q_hosts_started_successfully = True
    for q_host in all_qemu_hosts_in_net:
        bridge_name_for_tap = q_host.params.get('bridge_name', 's1') # Default to s1 if not specified
        info(f"*** Starting QEMU for {q_host.name} (TAP on {bridge_name_for_tap})...\n")
        if not q_host.startQemu(ovs_bridge_name=bridge_name_for_tap):
            info(f"!!! Failed to start QEMU for {q_host.name}. Exiting.\n")
            q_hosts_started_successfully = False
            break 
    
    if not q_hosts_started_successfully:
        net.stop()
        return

    info('*** Configuring IPs, routes, and firewall in VMs...\n')
    for q_host in all_qemu_hosts_in_net:
        if q_host.booted:
            info(f"--- Configuring {q_host.name} ---")
            app_ip_to_set = q_host.app_ip_with_prefix
            default_gw_to_set = q_host.params.get('default_gw')
            
            # QemuHost.setIP now also handles default GW if provided
            if not q_host.setIP(app_ip_to_set, intf=q_host.exp_intf_name, defaultRoute=default_gw_to_set):
                info(f"*** Failed to set IP/GW for {q_host.name}. VM IP: {app_ip_to_set}, GW: {default_gw_to_set}\n")
            else:
                info(f"*** {q_host.name} IP set to {app_ip_to_set}, GW to {default_gw_to_set} (if provided)\n")

            # Add other static routes if defined in topology
            static_routes = q_host.params.get('static_routes', [])
            for route_info in static_routes:
                # route_info = {'subnet': '10.0.1.0/24', 'via': '10.0.0.1'}
                q_host.cmd(f'ip route add {route_info["subnet"]} via {route_info["via"]}')
                info(f"*** [{q_host.name}] Added static route: {route_info['subnet']} via {route_info['via']}\n")
            
            # Disable GRO/GSO/TSO and set firewall to ACCEPT (common setup)
            q_host.cmd(f'ip link set {q_host.exp_intf_name} up') # Ensure up
            q_host.cmd(f'ethtool -K {q_host.exp_intf_name} gro off gso off tso off ufo off')
            info(f"*** [{q_host.name}] Disabled offloading on {q_host.exp_intf_name}\n")
            q_host.cmd('iptables -F; iptables -P INPUT ACCEPT; iptables -P FORWARD ACCEPT; iptables -P OUTPUT ACCEPT')
            info(f"*** [{q_host.name}] Set iptables to ACCEPT on {q_host.name}\n")
        else:
            info(f"*** [{q_host.name}] Not booted, skipping IP/route/firewall configuration.\n")

    # Create and distribute /etc/hosts
    nodes_for_hosts_file = all_qemu_hosts_in_net + [h for h in net.hosts if isinstance(h, LinuxRouter)]
    hosts_file_path = create_common_hosts_file(nodes_for_hosts_file)
    
    info('*** Updating /etc/hosts in VMs for name resolution\n')
    for q_host in all_qemu_hosts_in_net:
        if q_host.booted:
            # Ensure /etc/hosts exists and is writable in VM, or create it.
            # QEMU images usually have it.
            q_host.cmd("touch /etc/hosts && chmod 644 /etc/hosts") # Ensure it exists and is writable by root
            
            scp_cmd = (f"sshpass -p '0944' scp -o StrictHostKeyChecking=no "
                       f"-o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "
                       f"-P {q_host.ssh_host_port} {hosts_file_path} "
                       f"root@{q_host.qemu_ip}:/etc/hosts")
            try:
                scp_run_result = subprocess.run(scp_cmd, shell=True, check=True, text=True, capture_output=True, timeout=10)
                info(f"*** [{q_host.name}] Successfully copied hosts file to VM\n")
            except subprocess.CalledProcessError as e:
                info(f"*** [{q_host.name}] Failed to copy hosts file. SCP RC: {e.returncode}, Error: {e.stderr.strip()}\n")
            except subprocess.TimeoutExpired:
                info(f"*** [{q_host.name}] Timeout copying hosts file via SCP.\n")
        else:
            info(f"*** [{q_host.name}] Not booted, skipping /etc/hosts update.\n")

    time.sleep(2) # Allow network to settle

    # Basic connectivity tests (ping gateways)
    info('*** Testing initial connectivity to gateways (if applicable)...\n')
    for q_host in all_qemu_hosts_in_net:
        if q_host.booted and q_host.params.get('default_gw'):
            gw_ip = q_host.params['default_gw']
            ping_gw_result, _, rc = q_host.pexec(f'ping -c 1 -W 2 {gw_ip}')
            info(f"*** {q_host.name} ping to its gateway ({gw_ip}): {'SUCCESSFUL' if rc == 0 else 'FAILED (RC='+str(rc)+')'}\n{ping_gw_result}\n")

    # More specific tests based on topology (optional, can be done in CLI)
    if 'BasicLanTopo' in str(topo_class) or 'ScaledLanTopo' in str(topo_class):
        if len(all_qemu_hosts_in_net) >= 2:
            q_first = all_qemu_hosts_in_net[0]
            q_second = all_qemu_hosts_in_net[1]
            if q_first and q_first.booted and q_second and q_second.booted:
                info(f"*** Testing {q_first.name} <-> {q_second.name} (same LAN)\n")
                res, _, rc = q_first.pexec(f'ping -c 2 -W 2 {q_second.name}') # Ping by name
                info(f"*** {q_first.name} ping {q_second.name}: {'SUCCESSFUL' if rc == 0 else 'FAILED'}\n{res}\n")

    if 'RoutedSubnetsTopo' in str(topo_class):
        q1 = net.nameToNode.get('q1')
        q3 = net.nameToNode.get('q3')
        if q1 and getattr(q1, "booted", False) and q3 and getattr(q3, "booted", False):
            info(f"*** Testing {q1.name} <-> {q3.name} (routed subnets)\n")
            res, _, rc = q1.pexec(f'ping -c 2 -W 2 {q3.name}') # Ping by name
            info(f"*** {q1.name} ping {q3.name}: {'SUCCESSFUL' if rc == 0 else 'FAILED'}\n{res}\n")

    if 'MultiRouterTopo' in str(topo_class):
        # Test connectivity between LANs through routers
        q1 = net.nameToNode.get('q1')  # In LAN1
        q3 = net.nameToNode.get('q3')  # In LAN2
        if q1 and getattr(q1, "booted", False) and q3 and getattr(q3, "booted", False):
            info(f"*** Testing {q1.name} (LAN1) <-> {q3.name} (LAN2) through routers\n")
            res, _, rc = q1.pexec(f'ping -c 2 -W 2 {q3.name}') # Ping by name
            info(f"*** {q1.name} ping {q3.name}: {'SUCCESSFUL' if rc == 0 else 'FAILED'}\n{res}\n")
            
            # Test connectivity between routers
            r0 = net.nameToNode.get('r0')
            r1 = net.nameToNode.get('r1')
            if r0 and r1:
                info(f"*** Testing router connectivity: {r0.name} <-> {r1.name}\n")
                res, _, rc = r0.pexec(f'ping -c 2 -W 2 10.0.12.2') # Ping r1's transit IP
                info(f"*** {r0.name} ping {r1.name}: {'SUCCESSFUL' if rc == 0 else 'FAILED'}\n{res}\n")

    if 'VlanTopo' in str(topo_class):
        q1 = net.nameToNode.get('q1')
        q3 = net.nameToNode.get('q3')
        if q1 and getattr(q1, "booted", False) and q3 and getattr(q3, "booted", False):
            info(f"*** Testing {q1.name} (VLAN100) <-> {q3.name} (VLAN200) via router\n")
            res, _, rc = q1.pexec(f'ping -c 2 -W 2 {q3.name}') # Ping by name
            info(f"*** {q1.name} ping {q3.name}: {'SUCCESSFUL' if rc == 0 else 'FAILED'}\n{res}\n")

    info('\\n*** Running CLI\\n')
    CLI(net)
    
    info('*** Stopping network\\n')
    net.stop() # This will call terminate on QemuHosts, which calls stopQemu

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run Mininet experiments with QEMU hosts.")
    parser.add_argument(
        '--topo', type=str, required=True,
        help="Topology to run. Format: <module_name>.<ClassName> (e.g., topology_basic_lan.BasicLanTopo)"
    )
    args = parser.parse_args()

    try:
        module_name, class_name = args.topo.rsplit('.', 1)
        if not module_name.startswith('topologies.'):
            module_name = f"topologies.{module_name}"
        topo_module = importlib.import_module(module_name)
        topo_class_to_run = getattr(topo_module, class_name)
        run_experiment(topo_class_to_run, topo_name=args.topo)
    except ImportError as e:
        print(f"Error importing topology module: {e!r}")
        print("Ensure the module exists in the 'topologies' directory and PYTHONPATH is set correctly if needed.")
    except AttributeError as e:
        print(f"Error: Class {class_name} not found in module {module_name}. Details: {e!r}")
    except Exception as e:
        print(f"An unexpected error occurred in main: {e!r}")
        traceback.print_exc()