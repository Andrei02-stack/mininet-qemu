#!/usr/bin/env python3

from mininet.cli import CLI
from mininet.log import info, debug, error

class QemuCLI(CLI):
    """Custom CLI for QEMU hosts that doesn't substitute node names with IP addresses
    for QemuHost nodes, allowing hostname resolution to occur inside the QEMU VMs."""

    def default(self, line):
        """Override default method to ensure commands for QemuHost nodes are
           executed via node.pexec(), which should handle SSH to the VM."""
        
        first, args, _line = self.parseline(line)

        if not first: # No command entered
            return

        if first in self.mn:
            node = self.mn[first]
            cmd_for_node = args

            # Crucially, call the node's pexec method
            # This allows QemuHost.pexec to take over and use SSH
            # The pexec method in QemuHost is expected to return (stdout, stderr, exit_code)
            output, err, exitcode = node.pexec(cmd_for_node) # pexec expects a string command

            if output:
                # Mininet's CLI typically prints stdout directly.
                # We need to ensure it's stripped of trailing newlines that pexec might add.
                print(output.strip())
            
            if err:
                # Use self.mn.error for Mininet-style error reporting,
                # which usually prints to stderr.
                # Check if err is not empty and not just whitespace before printing
                err_stripped = err.strip()
                if err_stripped:
                    self.mn.error(err_stripped + '\\n')

            return # Command handled
        
        # If not a node command (e.g., "help", "exit", "py ..."), fall back to MininetCLI's default
        # info(f"QemuCLI: Command '{line}' not for a node, calling super().default()\\n") # Original debug
        return super().default(line)