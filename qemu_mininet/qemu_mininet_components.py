#!/usr/bin/env python3
import os
import subprocess
import time
from mininet.topo import Topo
from mininet.node import Node, Switch, Intf
from mininet.log import setLogLevel, info
from mininet.link import TCLink

# Define the base QEMU image path
BASE_QEMU_IMAGE = '/home/shogun/Licenta/imagine_qemu/qemu_image.qcow2' # modify this path to your qcow2 image path
MININET_HOSTS_FILE = '/tmp/mininet_hosts'

class QemuHost(Node):
    def __init__(self, name, overlay, tap, mac, qemu_ip, ssh_host_port, mgmt_mac_suffix, exp_intf_name, app_ip, **kwargs):
        self.booted = False
        self.qemu_ip = qemu_ip
        self.ssh_host_port = ssh_host_port
        self.app_ip_with_prefix = app_ip
        self.app_ip = app_ip.split('/')[0] if app_ip else None
        self.intfs = {} # Dictionar portNum -> intfObj
        self.ports = {} # Dictionar intfObj -> portNum
        self.nameToIntf = {} # Dictionar intfName -> intfObj

        super().__init__(name, inNamespace=False, **kwargs)

        self.overlay = overlay
        self.tap = tap
        self.mac = mac # MAC for the experimental interface (e.g., ens4 inside QEMU)
        self.mgmt_mac_suffix = mgmt_mac_suffix # Suffix for the management interface MAC
        self.exp_intf_name = exp_intf_name # Name of the experimental intf inside QEMU (e.g., ens4)
        self.proc = None
        self.pid_file = f"/tmp/{name}.pid"

    # Mininet's Node.IP() calls this. We want it to return the application IP.
    def IP(self, intf=None):
        # If a specific Mininet interface object (like qX-eth0) is given,
        # Node.IP() might try to get its IP.
        # For QemuHost, the primary IP is self.app_ip.
        if intf is None or (hasattr(intf, 'name') and intf.name.startswith(self.name + "-eth")):
            return self.app_ip # Return just the IP, not prefix
        # For other interfaces, if QemuHost ever has them, use parent's logic.
        return super().IP(intf)

    # Overridden from Node to store interface details
    def addIntf(self, intf, port=None, moveIntf=True, **kwargs):
        info(f"*** [{self.name}] QemuHost: Recording Mininet conceptual intf {intf.name} on port {port}\n")
        if port is None:
            port = self.newPort()
        self.intfs[port] = intf
        self.ports[intf] = port
        self.nameToIntf[intf.name] = intf
        if intf.node is None: intf.node = self
        elif intf.node != self:
            raise Exception(f"Interface {intf.name} is already assigned to node {intf.node.name}")
        return intf

    _newPort = 1 # Start port numbers from 1 for conceptual interfaces
    def newPort(self):
        p = self._newPort
        self._newPort += 1
        return p

    # Overridden from Node
    def delIntf(self, intf, **kwargs):
        intf_name_for_log = getattr(intf, 'name', str(intf))
        info(f"*** [{self.name}] QemuHost: Removing records for Mininet conceptual intf '{intf_name_for_log}'\n")
        the_intf_obj = None
        if isinstance(intf, str):
            the_intf_obj = self.nameToIntf.get(intf)
        elif isinstance(intf, Intf):
            the_intf_obj = intf
        
        if the_intf_obj:
            port_to_delete = self.ports.get(the_intf_obj)
            if port_to_delete is not None and port_to_delete in self.intfs:
                del self.intfs[port_to_delete]
            if the_intf_obj in self.ports:
                del self.ports[the_intf_obj]
            if hasattr(the_intf_obj, 'name') and the_intf_obj.name in self.nameToIntf:
                del self.nameToIntf[the_intf_obj.name]
        return

    # Mininet calls this for its conceptual interfaces. QEMU's MAC is fixed at launch.
    def setMAC(self, mac_address, intf=None):
        intf_name = getattr(intf, 'name', str(intf))
        info(f"*** [{self.name}] QemuHost: Conceptual setMAC({mac_address}) for {intf_name}. QEMU MACs are fixed.\n")
        # Store it conceptually for Mininet if it tries to query
        if isinstance(intf, Intf):
            intf.mac = mac_address
        self.params['mac'] = mac_address # Store on node params for generic Mininet queries
        return

    # Mininet calls this to configure the node (primarily its conceptual interfaces).
    def config(self, mac=None, ip=None, ipAddrs=None, defaultRoute=None, lo='up', **_params):
        info(f"*** [{self.name}] QemuHost: Mininet config() call. MAC={mac}, IP={ip}, defaultRoute={defaultRoute}\n")
        
        # This config is for Mininet's conceptual interface (e.g., q1-eth0), if created.
        # It does NOT configure the VM's internal interface directly.
        # The self.app_ip is the source of truth for the VM's data plane IP.

        # If Mininet created a conceptual qX-eth0 for this QemuHost
        conceptual_intf_name = f"{self.name}-eth0"
        mininet_intf_obj = self.nameToIntf.get(conceptual_intf_name)

        if mac and mininet_intf_obj:
            mininet_intf_obj.mac = mac
        
        if ip and mininet_intf_obj: # IP is for the Mininet conceptual interface
            mininet_intf_obj.ip = ip.split('/')[0]
            if '/' in ip: mininet_intf_obj.prefixLen = int(ip.split('/')[1])
            info(f"*** [{self.name}] QemuHost: Conceptual IP {ip} recorded for Mininet intf {conceptual_intf_name}. VM data IP is {self.app_ip_with_prefix}.\n")

        # Bring up loopback inside the VM if booted
        if self.booted and lo == 'up':
            self.cmd('/sbin/ifconfig lo up')
        elif not self.booted and lo == 'up':
            info(f"*** [{self.name}] QemuHost: VM not booted, ignoring 'ifconfig lo up' during Mininet config().\n")
        return []

    def startQemu(self, ovs_bridge_name='s1'):
        info(f"*** [{self.name}] Starting QEMU setup...\n")
        if not os.path.exists(self.overlay):
            info(f"*** [{self.name}] Creating overlay image {self.overlay} from {BASE_QEMU_IMAGE}\n")
            try:
                subprocess.check_call([
                    'qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2',
                    '-b', BASE_QEMU_IMAGE, self.overlay
                ])
            except subprocess.CalledProcessError as e:
                info(f"*** [{self.name}] ERROR creating overlay image: {e}\n")
                return False

        info(f"*** [{self.name}] Setting up TAP interface {self.tap}\n")
        subprocess.call(['sudo', 'ip', 'link', 'set', self.tap, 'down'], stderr=subprocess.DEVNULL)
        subprocess.call(['sudo', 'ip', 'tuntap', 'del', 'dev', self.tap, 'mode', 'tap'], stderr=subprocess.DEVNULL)
        
        try:
            subprocess.check_call(['sudo', 'ip', 'tuntap', 'add', 'dev', self.tap, 'mode', 'tap'])
            subprocess.check_call(['sudo', 'ip', 'link', 'set', self.tap, 'up'])
        except subprocess.CalledProcessError as e:
            info(f"*** [{self.name}] ERROR creating TAP interface {self.tap}: {e}\n")
            return False

        # After creating the TAP:
        if self.tap and self.params.get('bridge_name'):
            bridge = self.params['bridge_name']
            try:
                subprocess.call(['sudo', 'ip', 'link', 'set', self.tap, 'up'])
                subprocess.call(['sudo', 'ovs-vsctl', '--may-exist', 'add-port', bridge, self.tap])
                info(f"*** [{self.name}] TAP {self.tap} added to OVS bridge {bridge} imediat după creare.\n")
            except Exception as e:
                info(f"*** [{self.name}] EROARE la adăugarea TAP {self.tap} la bridge {bridge}: {e}\n")
        
        base_mgmt_mac = "52:54:00:12:35:" 
        full_mgmt_mac = f"{base_mgmt_mac}{self.mgmt_mac_suffix}"

        qemu_cmd = [
            'sudo', 'qemu-system-x86_64',
            '-daemonize',
            '-m', '512',
            '-hda', self.overlay,
            '-netdev', f'user,id=netmgmt,hostfwd=tcp::{self.ssh_host_port}-:22',
            '-device', f'e1000,netdev=netmgmt,mac={full_mgmt_mac}',
            '-netdev', f'tap,id=netexp,ifname={self.tap},script=no,downscript=no',
            '-device', f'e1000,netdev=netexp,mac={self.mac}', 
            '-pidfile', self.pid_file
        ]
        info(f"*** [{self.name}] Starting QEMU: {' '.join(qemu_cmd)}\n")
        try:
            if os.path.exists(self.pid_file): os.remove(self.pid_file)
            self.proc = subprocess.Popen(qemu_cmd)
            time.sleep(1) 
            if not os.path.exists(self.pid_file):
                if self.proc.poll() is not None:
                    info(f"*** [{self.name}] ERROR: QEMU process terminated unexpectedly after start. Exit code: {self.proc.returncode}\n")
                    return False
                info(f"*** [{self.name}] WARNING: QEMU PID file {self.pid_file} not found shortly after start.\n")
        except Exception as e:
            info(f"*** [{self.name}] ERROR starting QEMU: {e}\n")
            return False

        info(f"*** [{self.name}] Waiting for SSH on {self.qemu_ip}:{self.ssh_host_port} (up to 60 seconds)...\n")
        for i in range(30): 
            time.sleep(2)
            try:
                result = subprocess.run(
                    ['sshpass', '-p', '0944', 'ssh', '-o', 'StrictHostKeyChecking=no',
                     '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR',
                     '-o', 'ConnectTimeout=5', '-p', str(self.ssh_host_port), 
                     f'root@{self.qemu_ip}', 'echo SSH_OK'], 
                    capture_output=True, text=True, check=True, timeout=10
                )
                if "SSH_OK" in result.stdout:
                    info(f"*** [{self.name}] SSH connection to {self.qemu_ip}:{self.ssh_host_port} successful!\n")
                    self.booted = True
                    return True
            except subprocess.CalledProcessError as e:
                if not any(err_msg in e.stderr for err_msg in ["Connection refused", "Connection reset by peer", "kex_exchange_identification", "Connection timed out during banner exchange"]):
                    info(f"*** [{self.name}] SSH attempt {i+1}/30 to {self.qemu_ip}:{self.ssh_host_port} failed (CalledProcessError): {e.stderr.strip()}\n")
            except subprocess.TimeoutExpired:
                pass 
            except Exception as e:
                info(f"*** [{self.name}] SSH attempt {i+1}/30 to {self.qemu_ip}:{self.ssh_host_port} failed with unexpected error: {e!r}\n")
                if "Permission denied" in str(e): break

        info(f"*** [{self.name}] FAILED to establish SSH connection to {self.qemu_ip}:{self.ssh_host_port} after multiple attempts.\n")
        # Cleanup QEMU if SSH failed
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f_pid: pid_to_kill = int(f_pid.read().strip())
                info(f"*** [{self.name}] SSH failed, attempting to kill QEMU process {pid_to_kill}\n")
                subprocess.call(['sudo', 'kill', str(pid_to_kill)])
            except Exception as kill_e: info(f"*** [{self.name}] Error killing QEMU process: {kill_e}\n")
        elif self.proc and self.proc.poll() is None:
             info(f"*** [{self.name}] SSH failed, terminating QEMU process via Popen.\n")
             self.proc.terminate(); self.proc.wait(timeout=2) if self.proc.poll() is None else None
        subprocess.call(['sudo', 'ip', 'link', 'set', self.tap, 'down'], stderr=subprocess.DEVNULL)
        subprocess.call(['sudo', 'ip', 'tuntap', 'del', 'dev', self.tap, 'mode', 'tap'], stderr=subprocess.DEVNULL)
        return False

    def cmd(self, *args, want_tuple=False, **kwargs):
        # Build command_str_for_log
        if isinstance(args[0], list):
            command_str_for_log = ' '.join(args[0])
        else:
            command_str_for_log = ' '.join(map(str,args))

        # Case 1: Intercept Mininet's commands on conceptual interfaces (e.g., qX-eth0)
        # These should not appear if we don't use addLink for QemuHost,
        # but let's keep a safety check.
        conceptual_intf_pattern = f"{self.name}-eth"
        if any(cmd_part in command_str_for_log for cmd_part in ["ifconfig", "ethtool", "/sbin/ip addr", "/sbin/ip link set"]) and \
           conceptual_intf_pattern in command_str_for_log:
            if conceptual_intf_pattern in command_str_for_log:
                info(f"*** [{self.name}] QemuHost.cmd: INTERCEPTED Mininet cmd for (non-existent) conceptual intf: '{command_str_for_log}' (Not to VM)\n")
                if want_tuple: return '', '', 0 
                return ''

        # Case 2: Special commands (ping QEMU hostname, cat /etc/hosts)
        command_to_ssh = command_str_for_log 
        if command_str_for_log.startswith('ping q') or \
           (command_str_for_log.startswith('ping -c') and any(p.startswith('q') for p in command_str_for_log.split())):
            parts = command_str_for_log.split(); translated = False
            for i, part in enumerate(parts):
                if part.startswith('q') and any(c.isdigit() for c in part) and '_qemu_hosts' in self.params and any(h.name == part for h in self.params['_qemu_hosts']):
                    ip_mapping = {h.name: h.app_ip for h in self.params['_qemu_hosts'] if hasattr(h, 'app_ip') and h.app_ip}
                    if part in ip_mapping: parts[i] = ip_mapping[part]; command_to_ssh = ' '.join(parts); translated = True; break
            if translated: info(f"*** [{self.name}] QemuHost.cmd: Translated ping '{command_str_for_log}' to '{command_to_ssh}'\n")
        
        # Case 3: Send command to VM via SSH (if booted)
        if self.booted:
            info(f"*** [{self.name}] QemuHost.cmd (to VM via SSH): '{command_to_ssh}'\n")
            ssh_cmd_list = ['sshpass', '-p', '0944', 'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=10', '-p', str(self.ssh_host_port), f'root@{self.qemu_ip}', command_to_ssh]
            try:
                result = subprocess.run(ssh_cmd_list, capture_output=True, text=True, check=False, timeout=kwargs.get('timeout', 30))
                if result.returncode != 0: info(f"*** [{self.name}] SSH CMD='{command_to_ssh}' FAILED. RC={result.returncode}, STDOUT='{result.stdout.strip()}', STDERR='{result.stderr.strip()}'\n")
                if want_tuple: return result.stdout.strip(), result.stderr.strip(), result.returncode
                return result.stdout.strip()
            except subprocess.TimeoutExpired:
                info(f"*** [{self.name}] TIMEOUT executing SSH cmd '{command_to_ssh}'.\n")
                if want_tuple: return '', 'TIMEOUT_QEMU_CMD', 124
                return 'TIMEOUT_QEMU_CMD'
            except Exception as e:
                info(f"*** [{self.name}] UNEXPECTED ERROR SSH cmd '{command_to_ssh}': {e!r}\n")
                if want_tuple: return '', f'EXCEPTION_QEMU_CMD: {str(e)}', 1
                return f'EXCEPTION_QEMU_CMD: {str(e)}'
        
        # Case 4: VM not booted
        else: # self.booted is False
            info(f"*** [{self.name}] VM not booted. Command '{command_str_for_log}' IGNORED.\n")
            if want_tuple: return '', 'VM not booted', 1
            return ''

    def pexec(self, *args, **kwargs): # Usually called by Mininet for background processes
        # For QemuHost, most commands are run via SSH and are blocking.
        # If a true background process in VM is needed, this might need more thought.
        # For now, treat like a blocking cmd.
        cmd_list = []
        if len(args) == 1 and isinstance(args[0], list):
            cmd_list = args[0]
        else:
            cmd_list = list(args)
        
        info(f"*** [{self.name}] QemuHost.pexec: Running as blocking cmd: '{' '.join(cmd_list)}'\n")
        return self.cmd(*cmd_list, want_tuple=True, **kwargs)

    def setIP(self, ip_with_prefix, intf=None, defaultRoute=None):
        if not self.booted:
            info(f"*** [{self.name}] VM not booted, cannot set IP or route for {self.exp_intf_name}.\n")
            return False
        
        target_vm_intf = self.exp_intf_name
        if not target_vm_intf:
            info(f"*** [{self.name}] ERROR: VM's experimental interface name (exp_intf_name) not specified.\n")
            return False

        # This method is primarily for configuring the VM's experimental interface (ens4)
        # Mininet might call it for its conceptual interface (e.g. q1-eth0) via Host.config().
        # We only act if 'intf' is None or matches self.exp_intf_name.
        if isinstance(intf, Intf) and intf.name != target_vm_intf:
            info(f"*** [{self.name}] setIP called by Mininet for conceptual intf {intf.name} with IP {ip_with_prefix}. Storing conceptually.\n")
            intf.ip = ip_with_prefix.split('/')[0]
            if '/' in ip_with_prefix: intf.prefixLen = int(ip_with_prefix.split('/')[1])
            # self.params['ip_conceptual'] = ip_with_prefix # Store on node if needed
            return True

        info(f"*** [{self.name}] Attempting to set IP {ip_with_prefix} on VM interface {target_vm_intf}\n")
        
        check_intf_cmd = f"/sbin/ip link show {target_vm_intf}"
        s_out_chk, s_err_chk, rc_chk = self.cmd(check_intf_cmd, want_tuple=True)
        if rc_chk != 0 or target_vm_intf not in s_out_chk:
            info(f"*** [{self.name}] ERROR: Interface {target_vm_intf} does not exist in VM. RC={rc_chk}, STDOUT='{s_out_chk}', STDERR='{s_err_chk}'\n")
            return False

        commands = [
            (f"/sbin/ip addr flush dev {target_vm_intf}", "FLUSH_IP"),
            (f"/sbin/ip addr add {ip_with_prefix} dev {target_vm_intf}", "ADD_IP"),
            (f"/sbin/ip link set {target_vm_intf} up", "LINK_UP")
        ]
        success_ip_set = False
        for attempt in range(2):
            all_ok = True
            for cmd_str, desc in commands:
                s_out, s_err, rc = self.cmd(cmd_str, want_tuple=True)
                if rc != 0:
                    if desc == "FLUSH_IP" and ("Cannot assign requested address" in s_err or "No such process" in s_err or "Cannot find device" in s_err):
                        info(f"*** [{self.name}] Note: '{desc}' for {target_vm_intf} reported: {s_err} (benign)\n")
                    else:
                        info(f"*** [{self.name}] Attempt {attempt+1}, Step '{desc}' FAILED. RC={rc}, ERR='{s_err}'\n")
                        all_ok = False; break
            if all_ok:
                verify_cmd = f"/sbin/ip -4 addr show {target_vm_intf} | grep 'inet {ip_with_prefix.split('/')[0]}/'"
                s_out_v, _, rc_v = self.cmd(verify_cmd, want_tuple=True)
                if rc_v == 0 and ip_with_prefix.split('/')[0] in s_out_v:
                    info(f"*** [{self.name}] IP {ip_with_prefix} successfully set and verified on {target_vm_intf}.\n")
                    success_ip_set = True; break
                else:
                    info(f"*** [{self.name}] IP verify for {ip_with_prefix} on {target_vm_intf} FAILED. Verify output: '{s_out_v}'\n")
            if not success_ip_set and attempt < 1: time.sleep(1)
        
        if not success_ip_set:
            info(f"*** [{self.name}] FAILED to set IP {ip_with_prefix} on {target_vm_intf}.\n")
            return False

        # Store this IP on the QemuHost params['ip'] for Mininet's Host.IP() to work if needed
        # self.params['ip'] = ip_with_prefix # Full IP with prefix

        if defaultRoute:
            info(f"*** [{self.name}] Setting default gateway to {defaultRoute} on {target_vm_intf}\n")
            self.cmd(f'/sbin/ip route del default || true', want_tuple=True) # Delete any existing default
            s_out_gw, s_err_gw, rc_gw = self.cmd(f'/sbin/ip route add default via {defaultRoute} dev {target_vm_intf}', want_tuple=True)
            if rc_gw == 0:
                info(f"*** [{self.name}] Default GW {defaultRoute} set successfully via {target_vm_intf}.\n")
            else:
                info(f"*** [{self.name}] FAILED to set default GW {defaultRoute} via {target_vm_intf}. RC={rc_gw}, ERR={s_err_gw}\n")
                # Attempt without dev, though less ideal
                s_out_gw2, s_err_gw2, rc_gw2 = self.cmd(f'/sbin/ip route add default via {defaultRoute}', want_tuple=True)
                if rc_gw2 == 0: info(f"*** [{self.name}] Default GW {defaultRoute} set (general attempt).\n")
                else: info(f"*** [{self.name}] FAILED to set default GW {defaultRoute} (general attempt). RC={rc_gw2}, ERR={s_err_gw2}\n"); return False
        return True

    def stopQemu(self, cleanup=True):
        info(f"*** [{self.name}] Stopping QEMU...\n")
        pid_to_kill = None
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f: pid_to_kill = int(f.read().strip())
                info(f"*** [{self.name}] Killing QEMU process {pid_to_kill} from PID file.\n")
                subprocess.call(['sudo', 'kill', str(pid_to_kill)])
                time.sleep(1) # Give a moment for process to die
                if os.path.exists(f"/proc/{pid_to_kill}"): # Check if still running
                    subprocess.call(['sudo', 'kill', '-9', str(pid_to_kill)])
                os.remove(self.pid_file)
            except (FileNotFoundError, ValueError, TypeError) as e:
                info(f"*** [{self.name}] Error with PID file {self.pid_file}: {e}. May be already stopped or PID invalid.\n")
            except Exception as e:
                info(f"*** [{self.name}] Error stopping QEMU with PID {pid_to_kill}: {e!r}\n")
        
        if self.proc and self.proc.poll() is None: # If Popen object exists and process is running
            info(f"*** [{self.name}] Terminating QEMU process via Popen object.\n")
            self.proc.terminate()
            try: self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(timeout=2)
        
        self.proc = None
        self.booted = False

        if cleanup:
            bridge_name = self.params.get('bridge_name', None)
            if bridge_name and self.tap:
                info(f"*** [{self.name}] Cleaning up TAP {self.tap} from bridge {bridge_name}\n")
                subprocess.call(['sudo', 'ovs-vsctl', '--if-exists', 'del-port', bridge_name, self.tap], stderr=subprocess.DEVNULL)
            if self.tap:
                subprocess.call(['sudo', 'ip', 'link', 'set', self.tap, 'down'], stderr=subprocess.DEVNULL)
                subprocess.call(['sudo', 'ip', 'tuntap', 'del', 'dev', self.tap, 'mode', 'tap'], stderr=subprocess.DEVNULL)
            if os.path.exists(self.overlay):
                info(f"*** [{self.name}] Deleting overlay image {self.overlay}\n")
                try: os.remove(self.overlay)
                except OSError as e: info(f"*** [{self.name}] Error deleting overlay {self.overlay}: {e}\n")

    def terminate(self):
        info(f"*** [{self.name}] QemuHost: Terminating...\n")
        self.stopQemu(cleanup=True) # Ensure full cleanup on terminate
        # DelIntf for conceptual Mininet interfaces will be called by Node.terminate()
        super().terminate()

class QemuSwitch(Switch):
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)

    def start(self, controllers):
        info(f"*** [{self.name}] QemuSwitch: Starting OVS bridge {self.name}\n") # Use self.name as bridge name
        # Ensure OVS is running
        try: subprocess.check_output(['sudo', 'ovs-vsctl', 'show'], stderr=subprocess.STDOUT)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise Exception("Open vSwitch is not running or ovs-vsctl not found.")
        
        self.cmd('sudo ovs-vsctl --may-exist add-br', self.name)
        self.cmd('sudo ip link set', self.name, 'up')

        # First, add all TAP interfaces to OVS bridge
        if hasattr(self, 'net') and self.net:
            for host in self.net.hosts:
                if isinstance(host, QemuHost) and host.params.get('bridge_name') == self.name:
                    tap_if_name = host.tap
                    if tap_if_name:
                        info(f"*** [{self.name}] Adding TAP interface {tap_if_name} to OVS bridge {self.name}\n")
                        # First ensure the TAP interface exists and is up
                        self.cmd(f'sudo ip link set {tap_if_name} up')
                        # Then add it to OVS bridge
                        self.cmd(f'sudo ovs-vsctl --may-exist add-port {self.name} {tap_if_name}')
                        # Wait a moment for OVS to process the port
                        time.sleep(1)

        # Then handle any other interfaces (like router links)
        for intf in self.intfList():
            if intf.name != self.name and intf.name != 'lo':
                info(f"*** [{self.name}] QemuSwitch.start: Attaching Mininet interface {intf.name} to bridge.\n")
                self.attach(intf)
                try: # Bring up the host-side of the veth pair
                    subprocess.check_call(['sudo', 'ip', 'link', 'set', intf.name, 'up'])
                except subprocess.CalledProcessError as e:
                    info(f"*** [{self.name}] Warning: could not bring up {intf.name}: {e}\n")
            elif intf.name == 'lo':
                info(f"*** [{self.name}] QemuSwitch.start: Skipping 'lo' interface.\n")

        if controllers:
            pass
        info(f"*** [{self.name}] QemuSwitch: OVS bridge {self.name} started and interfaces processed.\n")

    def stop(self, deleteIntfs=True):
        info(f"*** [{self.name}] QemuSwitch: Stopping OVS bridge {self.name}\n")
        self.cmd('sudo ovs-vsctl --if-exists del-br', self.name)
        super().stop(deleteIntfs)

    def attach(self, intf):
        info(f"*** [{self.name}] QemuSwitch.attach: Attaching {intf.name} to {self.name}\n")
        self.cmd('sudo ovs-vsctl --may-exist add-port', self.name, intf.name)

    def detach(self, intf):
        info(f"*** [{self.name}] QemuSwitch.detach: Detaching {intf.name} from {self.name}\n")
        self.cmd('sudo ovs-vsctl --if-exists del-port', self.name, intf.name)

class LinuxRouter(Node):
    def config(self, **params):
        # IP forwarding is typically enabled by the runner script after interfaces are up.
        # Here, we ensure the basic Node config happens.
        super(LinuxRouter, self).config(**params)
        info(f"*** [{self.name}] LinuxRouter.config called. Enabling IP forwarding.\n")
        self.cmd('sysctl net.ipv4.ip_forward=1')
        # Set any specific sysctls for the router if needed, e.g., for all interfaces
        # self.cmd('sysctl net.ipv4.conf.all.arp_accept=1') # Example

    def terminate(self):
        self.cmd('sysctl net.ipv4.ip_forward=0') # Disable forwarding on stop
        super(LinuxRouter, self).terminate()

# Utility function to create common hosts file
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
            for intf_name, intf_obj in node.nameToIntf.items():
                if getattr(intf_obj, 'ip', None): # Check if Intf object has an IP
                     # Sanitize intf_name for hostname: r0-r0-eth1 -> r0-eth1
                    hostname_for_intf = f"{node.name}-{intf_name.replace(node.name + '-', '')}"
                    hosts_content.append(f"{intf_obj.ip}\t{hostname_for_intf} {node.name}")
    
    hosts_content.append("\n# End of Mininet host entries")
    with open(MININET_HOSTS_FILE, 'w') as f:
        f.write('\n'.join(hosts_content) + '\n')
    os.chmod(MININET_HOSTS_FILE, 0o644)
    info(f"*** Created common hosts file at {MININET_HOSTS_FILE}:\n" + "\n".join(hosts_content) + "\n")
    return MININET_HOSTS_FILE