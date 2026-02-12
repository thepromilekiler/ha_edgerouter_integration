"""API Client for EdgeRouter."""
import socket
import logging
import asyncio
import paramiko
import re

try:
    from .const import DEFAULT_PORT
except ImportError:
    # If running standalone (e.g. via test script adding this dir to sys.path)
    # we can't do relative import. We can mock it or import from file directly if needed.
    # But simpler: if run via our test script hack, it's NOT a package.
    # So we just define fallback or import absolute if possible.
    DEFAULT_PORT = 22

_LOGGER = logging.getLogger(__name__)

class EdgeRouterAPI:
    """Interface to the EdgeRouter over SSH."""

    def __init__(self, host, username, password, port=DEFAULT_PORT):
        """Initialize."""
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client = None

    def validate_connection(self):
        """Validate connection synchronously (for config flow)."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=5
            )
            client.close()
            return True
        except Exception as e:
            _LOGGER.error("Connection failed: %s", e)
            raise

    async def async_get_data(self):
        """Retrieve data from the router."""
        # Run the blocking SSH call in the executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_data_sync)

    def _get_data_sync(self):
        """Blocking method to connect and fetch all data."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        data = {
            "uptime": "",
            "interfaces": {},
            "errors": 0,
            "system_image": ""
        }

        try:
            client.connect(
                self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10
            )

            # 1. Uptime
            stdin, stdout, stderr = client.exec_command("uptime")
            data["uptime"] = stdout.read().decode().strip()

            # 2. System Image
            # Using vbash wrapper or direct if in path. 
            # We use full path to be safe as per our debug script findings.
            wrapper = "/opt/vyatta/bin/vyatta-op-cmd-wrapper"
            stdin, stdout, stderr = client.exec_command(f"{wrapper} show system image")
            data["system_image"] = stdout.read().decode().strip()

            # 3. Traffic Rates AND CPU - 2s sample
            # We run the command: 
            #   cat /proc/net/dev; cat /proc/stat; sleep 2; cat /proc/net/dev; cat /proc/stat
            # This lets us calculate rates for both.
            cmd = "cat /proc/net/dev; echo '___SPLIT___'; cat /proc/stat; echo '___SPLIT___'; sleep 2; cat /proc/net/dev; echo '___SPLIT___'; cat /proc/stat"
            stdin, stdout, stderr = client.exec_command(cmd)
            perf_raw = stdout.read().decode()
            
            # Split into blocks
            parts = perf_raw.split("___SPLIT___")
            if len(parts) >= 4:
                data["interfaces"] = self._parse_traffic(parts[0], parts[2])
                data["cpu"] = self._parse_cpu(parts[1], parts[3])
            
            # 4. RAM
            stdin, stdout, stderr = client.exec_command("cat /proc/meminfo")
            mem_raw = stdout.read().decode()
            data["memory"] = self._parse_memory(mem_raw)

            # 5. Logs
            stdin, stdout, stderr = client.exec_command(f"{wrapper} show log | tail -n 50")
            log_raw = stdout.read().decode()
            data["errors"] = self._count_errors(log_raw)

        except Exception as e:
            _LOGGER.error("Error fetching data: %s", e)
            # Re-raise or return partial data? Best to throw so the coordinator knows it failed.
            raise e
        finally:
            client.close()
            
        return data

    def _parse_traffic(self, start_raw, end_raw):
        """Parse the /proc/net/dev snapshots."""
        
        def parse_block(block):
            res = {}
            for line in block.splitlines():
                match = re.search(r"^\s*([\w\.\-]+):\s*(\d+)\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)", line)
                if match:
                    res[match.group(1)] = (int(match.group(2)), int(match.group(3)))
            return res

        start = parse_block(start_raw)
        end = parse_block(end_raw)
        
        rates = {}
        for iface, (rx2, tx2) in end.items():
            if iface in start:
                rx1, tx1 = start[iface]
                # Mbps = bytes * 8 / 1024^2 / 2s
                rx_mbps = (rx2 - rx1) * 8 / 1024 / 1024 / 2.0
                tx_mbps = (tx2 - tx1) * 8 / 1024 / 1024 / 2.0
                rates[iface] = {"rx": rx_mbps, "tx": tx_mbps}
        
        # Calculate Total Traffic
        total_rx = sum(r['rx'] for r in rates.values())
        total_tx = sum(r['tx'] for r in rates.values())
        rates['total'] = {'rx': total_rx, 'tx': total_tx}
        
        return rates

    def _parse_cpu(self, start_raw, end_raw):
        """Parse /proc/stat to get CPU usage percentage."""
        def get_cpu_times(raw):
            for line in raw.splitlines():
                if line.startswith("cpu "):
                    # cpu  user nice system idle iowait irq softirq steal guest guest_nice
                    parts = line.split()
                    if len(parts) >= 5:
                        user = int(parts[1])
                        nice = int(parts[2])
                        system = int(parts[3])
                        idle = int(parts[4])
                        # sum all fields for total
                        total = sum(int(x) for x in parts[1:])
                        return total, idle
            return 0, 0

        total1, idle1 = get_cpu_times(start_raw)
        total2, idle2 = get_cpu_times(end_raw)
        
        if total2 - total1 > 0:
            total_delta = total2 - total1
            idle_delta = idle2 - idle1
            # Usage = (Total - Idle) / Total
            usage = (total_delta - idle_delta) / total_delta * 100.0
            return round(usage, 1)
        return 0.0

    def _parse_memory(self, raw):
        """Parse /proc/meminfo to get RAM usage percentage."""
        total = 0
        available = 0
        free = 0
        buffers = 0
        cached = 0
        
        # Keys we care about
        INTERESTING_KEYS = {"MemTotal", "MemAvailable", "MemFree", "Buffers", "Cached"}

        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 2: continue
            
            key = parts[0].strip(":")
            if key not in INTERESTING_KEYS:
                continue

            try:
                # Value is "12345 kB", we just want the number
                val = int(parts[1]) 
            except ValueError:
                continue
            
            if key == "MemTotal": total = val
            elif key == "MemAvailable": available = val
            elif key == "MemFree": free = val
            elif key == "Buffers": buffers = val
            elif key == "Cached": cached = val
            
        if total == 0: return 0.0

        if available > 0:
            # Modern kernels
            used = total - available
        else:
            # Older kernels (EdgeOS older versions might lack MemAvailable)
            used = total - (free + buffers + cached)
            
        return round(used / total * 100.0, 1)

    def _count_errors(self, log_data):
        """Count specific errors in logs."""
        count = 0
        # DHCP Duplicates
        count += len(re.findall(r"uid lease .* is duplicate on", log_data))
        # Kernel Warnings
        count += len(re.findall(r"WARNING: CPU: .*|Call Trace:", log_data))
        # SSH Auth Failures (optional to count, maybe we skip counting 'expected' ones?)
        # Let's count them for now as they are security events.
        count += len(re.findall(r"authentication failure", log_data))
        return count
