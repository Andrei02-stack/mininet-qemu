import os
import time
import json
from datetime import datetime
from logging_config import info, debug, error

def run_latency_tests(qemu_hosts):
    info("\n=== Latency Tests (ping) ===")
    results = {}
    for src in qemu_hosts:
        results[src.name] = {}
        for dst in qemu_hosts:
            if src == dst:
                continue
            info(f"Testing latency: {src.name} -> {dst.name}")
            cmd = f"ping -c 5 -W 1 {dst.name}"
            out, err, rc = src.pexec(cmd)
            if rc == 0:
                # Parse min/avg/max/mdev from ping output
                try:
                    lines = out.split('\n')
                    stats_line = [l for l in lines if 'min/avg/max' in l]
                    if stats_line:
                        stats = stats_line[0].split('=')[1].strip().split(' ')[0]
                        min_rtt, avg_rtt, max_rtt, mdev = map(float, stats.split('/'))
                        results[src.name][dst.name] = {
                            'min': min_rtt,
                            'avg': avg_rtt,
                            'max': max_rtt,
                            'mdev': mdev
                        }
                        info(f"  min/avg/max/mdev: {min_rtt:.2f}/{avg_rtt:.2f}/{max_rtt:.2f}/{mdev:.2f} ms")
                    else:
                        results[src.name][dst.name] = {'error': 'No stats line'}
                        error(f"  No stats line in ping output.")
                except Exception as e:
                    results[src.name][dst.name] = {'error': str(e)}
                    error(f"  Failed to parse ping output: {e}")
            else:
                results[src.name][dst.name] = {'error': f'Ping failed (rc={rc})'}
                error(f"  Ping failed (rc={rc})")
    return results

def run_throughput_tests(qemu_hosts):
    info("\n=== Throughput Tests (iperf) ===")
    results = {}
    for src in qemu_hosts:
        results[src.name] = {}
        for dst in qemu_hosts:
            if src == dst:
                continue
            info(f"Testing throughput: {src.name} -> {dst.name}")
            
            # Verify iperf installation on both hosts
            for host in [src, dst]:
                out, err, rc = host.pexec('which iperf')
                if rc != 0:
                    info(f"Installing iperf on {host.name}")
                    host.cmd('apt-get update && apt-get install -y iperf')
                    # Verify installation
                    out, err, rc = host.pexec('which iperf')
                    if rc != 0:
                        error(f"Failed to install iperf on {host.name}")
                        results[src.name][dst.name] = {'error': 'iperf installation failed'}
                        continue

            # Kill any existing iperf processes
            dst.cmd('pkill iperf')
            time.sleep(1)  # Wait for processes to be killed
            
            # Start iperf server with explicit port and interface
            server_cmd = 'iperf -s -D -p 5001'
            dst.cmd(server_cmd)
            time.sleep(2)  # Give server more time to start
            
            # Verify server is running
            out, err, rc = dst.pexec('pgrep iperf')
            if rc != 0:
                error(f"iperf server failed to start on {dst.name}")
                results[src.name][dst.name] = {'error': 'iperf server failed to start'}
                continue

            # Run iperf client without JSON output
            cmd = f"iperf -c {dst.name} -p 5001 -t 5"
            out, err, rc = src.pexec(cmd)
            
            # Cleanup
            dst.cmd('pkill iperf')
            
            if rc == 0 and out.strip():
                try:
                    # Parse the text output to extract bandwidth
                    lines = out.split('\n')
                    for line in lines:
                        if 'bits/sec' in line:
                            # Extract the bandwidth value
                            parts = line.split()
                            bandwidth = float(parts[-2])
                            unit = parts[-1]
                            
                            # Convert to bits per second
                            if 'Kbits' in unit:
                                bps = bandwidth * 1000
                            elif 'Mbits' in unit:
                                bps = bandwidth * 1000000
                            elif 'Gbits' in unit:
                                bps = bandwidth * 1000000000
                            else:
                                bps = bandwidth
                                
                            results[src.name][dst.name] = {'bps': bps}
                            info(f"  Throughput: {bandwidth:.2f} {unit}")
                            break
                    else:
                        error(f"  Could not find bandwidth in output")
                        results[src.name][dst.name] = {'error': 'No bandwidth found in output'}
                except Exception as e:
                    error(f"  Failed to parse iperf output: {e}")
                    error(f"  Raw output: {out}")
                    results[src.name][dst.name] = {'error': str(e)}
            else:
                error(f"  iperf failed (rc={rc})")
                error(f"  Error output: {err}")
                results[src.name][dst.name] = {'error': f'iperf failed (rc={rc})'}
    return results

def run_performance_tests(net, topo_name="Experiment"):
    qemu_hosts = [h for h in net.hosts if hasattr(h, 'booted') and h.booted]
    timestamp = datetime.now().strftime('%d-%m-%Y_%H:%M:%S')
    results = {'timestamp': timestamp, 'topology': topo_name}
    results['latency'] = run_latency_tests(qemu_hosts)
    results['throughput'] = run_throughput_tests(qemu_hosts)
    # Save results
    outdir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(outdir, exist_ok=True)
    outfile = os.path.join(outdir, f'perf_{topo_name}_{timestamp}.json')
    with open(outfile, 'w') as f:
        json.dump(results, f, indent=2)
    info(f"\nPerformance test results saved to {outfile}\n") 