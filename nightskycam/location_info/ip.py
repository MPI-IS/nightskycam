"""
Module for getting the IP addresses of the current host.
"""

from typing import List

import netifaces


def get_IP(iface) -> List[str]:
    """
    Return the IPs for the given interface.
    """
    r: List[str] = []
    iface_details = netifaces.ifaddresses(iface)
    if netifaces.AF_INET in iface_details:
        for ip_interfaces in iface_details[netifaces.AF_INET]:
            if "addr" in ip_interfaces:
                r.append(ip_interfaces["addr"])
    return r


def get_IPs() -> List[str]:
    """
    Return the IPs for all interfaces.
    """
    ips: List[str] = []
    for iface in netifaces.interfaces():
        ips.extend(get_IP(iface))
    return ips
