import re
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class WlanInfo:
    """Dataclass containing WLAN connection information"""

    interface: str
    ssid: str
    signal: str
    bitrate: str

    def __str__(self) -> str:
        if self.ssid == "Not connected":
            return f"not connected"
        return f"ssid={self.ssid}, signal={self.signal}, bitrate={self.bitrate}"


def get_wlan_info(interface: str = "wlan0") -> Optional[WlanInfo]:
    """
    Get WLAN connection information using iwconfig.

    Args:
        interface: Wireless interface name (e.g., 'wlan0').
                  If None, will auto-detect the interface.

    Returns:
        WlanInfo object containing connection details, or None if failed

    Raises:
        subprocess.CalledProcessError: If iwconfig command fails
        FileNotFoundError: If iwconfig is not installed
    """
    try:

        # Get information using iwconfig
        result = subprocess.run(
            ["iwconfig", interface], capture_output=True, text=True, check=True
        )

        output = result.stdout

        # Parse SSID
        ssid_match = re.search(r'ESSID:"([^"]*)"', output)
        ssid = ssid_match.group(1) if ssid_match else "Not connected"

        # Parse Signal Level
        signal_match = re.search(r"Signal level=(-?\d+)\s*dBm", output)
        if not signal_match:
            signal_match = re.search(r"Signal level=(\d+)/(\d+)", output)
            if signal_match:
                signal = f"{signal_match.group(1)}/{signal_match.group(2)}"
            else:
                signal = "N/A"
        else:
            signal = f"{signal_match.group(1)} dBm"

        # Parse Bit Rate
        bitrate_match = re.search(r"Bit Rate[=:](\d+\.?\d*)\s*([MGK]b/s)", output)
        bitrate = (
            f"{bitrate_match.group(1)} {bitrate_match.group(2)}"
            if bitrate_match
            else "N/A"
        )

        return WlanInfo(interface=interface, ssid=ssid, signal=signal, bitrate=bitrate)

    except Exception:
        return None
