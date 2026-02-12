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
        
        # Initialize with defaults so sensors are always created
        data = {
            "uptime": "Unknown",
            "system_image": "Unknown",
            "interfaces": {},
            "errors": 0,
            "cpu": 0.0,
            "memory": 0.0
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
            # Try multiple paths for wrapper
            wrappers = ["/opt/vyatta/bin/vyatta-op-cmd-wrapper", "vbash -c /opt/vyatta/bin/vyatta-op-cmd-wrapper"]
            for wrapper in wrappers:
                stdin, stdout, stderr = client.exec_command(f"{wrapper} show system image")
                out = stdout.read().decode().strip()
                if out and "image" in out.lower(): # Basic validation
                    data["system_image"] = out
                    break
            
            # 3. Memory
            stdin, stdout, stderr = client.exec_command("cat /proc/meminfo")
            data["memory"] = self._parse_memory(stdout.read().decode())

            # 4. Traffic & CPU (Sequential approach for stability)
            # Start Snapshot
            stdin, stdout, stderr = client.exec_command("cat /proc/net/dev")
            dev_start = stdout.read().decode()
            
            stdin, stdout, stderr = client.exec_command("cat /proc/stat")
            stat_start = stdout.read().decode()

            # Wait
            import time
            time.sleep(2)

            # End Snapshot
            stdin, stdout, stderr = client.exec_command("cat /proc/net/dev")
            dev_end = stdout.read().decode()
            
            stdin, stdout, stderr = client.exec_command("cat /proc/stat")
            stat_end = stdout.read().decode()

            if dev_start and dev_end:
                 data["interfaces"] = self._parse_traffic(dev_start, dev_end)
                 if not data["interfaces"] or (len(data["interfaces"]) == 1 and "total" in data["interfaces"]):
                     _LOGGER.warning("Parsed 0 interfaces from /proc/net/dev output!")

            if stat_start and stat_end:
                 data["cpu"] = self._parse_cpu(stat_start, stat_end)

            # 5. Logs
            # Just try broad grep to avoid wrapper issues if possible, or use commonly available log file
            # EdgeOS usually logs to /var/log/messages
            stdin, stdout, stderr = client.exec_command("tail -n 50 /var/log/messages")
            log_raw = stdout.read().decode()
            data["errors"] = self._count_errors(log_raw)

        except Exception as e:
            _LOGGER.error("Error fetching data: %s", e)
            # We return whatever partial data we have, or defaults
            # raise e # Don't raise, just log, so at least Uptime works if CPU fails
        finally:
            client.close()
            
        return data

    def _parse_traffic(self, start_raw, end_raw):
        """Parse the /proc/net/dev snapshots."""
        _LOGGER.debug("Parsing traffic. Start raw length: %d, End raw length: %d", len(start_raw), len(end_raw))
        # _LOGGER.debug("Start Raw: %s", start_raw) # Uncomment if desperate

        def parse_block(block):
            res = {}
            lines = block.splitlines()
            for line in lines:
                if "|" in line: continue # Skip headers
                if ":" not in line: continue # Skip empty/malformed
                
                # Replace : with space to handle "eth0:123" and "eth0: 123"
                clean_line = line.replace(":", " ")
                parts = clean_line.split()
                
                # parts[0] is iface
                # parts[1] is rx_bytes
                # parts[9] is tx_bytes
                if len(parts) >= 10:
                    try:
                        iface = parts[0]
                        rx = int(parts[1])
                        tx = int(parts[9])
                        res[iface] = (rx, tx)
                    except ValueError:
                        _LOGGER.warning("Failed to parse line: %s", line)
                        continue
                else:
                    _LOGGER.debug("Skipping line (not enough parts): %s", line)
                    
            _LOGGER.debug("Parsed block result keys: %s", list(res.keys()))
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
                _LOGGER.debug("Calculated rate for %s: RX %.2f, TX %.2f", iface, rx_mbps, tx_mbps)
            else:
                _LOGGER.warning("Interface %s found in end snapshot but not start", iface)
        
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
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            # parts[1] is user, [2] nice, [3] system, [4] idle
                            # Sum all numeric fields for total
                            values = [int(x) for x in parts[1:]]
                            total = sum(values)
                            idle = int(parts[4])
                            return total, idle
                        except ValueError:
                            continue
            return 0, 0

        total1, idle1 = get_cpu_times(start_raw)
        total2, idle2 = get_cpu_times(end_raw)
        
        if total2 - total1 > 0:
            total_delta = total2 - total1
            idle_delta = idle2 - idle1
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
        
        INTERESTING_KEYS = {"MemTotal", "MemAvailable", "MemFree", "Buffers", "Cached"}

        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 2: continue
            
            # parts[0] is "MemTotal:"
            key = parts[0].strip(":")
            if key not in INTERESTING_KEYS:
                continue

            try:
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
            used = total - available
        else:
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
