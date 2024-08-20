import os
import nmap
import time
import socket
import json
from datetime import datetime
from pathlib import Path

from server.telemetry import send_message


# Network to scan (e.g., '192.168.1.0/24')
NETWORK = "192.168.1.0/24"

# Time between scans in minutes
SCAN_INTERVAL = 1


_topic = os.environ["NETWORK_NTFY_TOPIC"]


def get_hostname(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return None


def load_mac_address_to_name():
    config_file = Path(".mac_address_to_name.json")
    if config_file.exists():
        with config_file.open("r") as f:
            return json.load(f)
    return {}


def scan_network():
    nm = nmap.PortScanner()
    nm.scan(hosts=NETWORK, arguments="-sn -R")  # Added -R for DNS resolution
    devices = {}
    for host in nm.all_hosts():
        if "mac" in nm[host]["addresses"]:
            mac = nm[host]["addresses"]["mac"]
            devices[mac] = nm[host]
            if "hostnames" in nm[host] and nm[host]["hostnames"]:
                hostname = nm[host]["hostnames"][0]["name"]
            else:
                hostname = get_hostname(host)
            devices[mac]["hostname"] = hostname if hostname else "Unknown"
            devices[mac]["ip"] = host
    return devices


def save_scan_to_file(devices):
    log_dir = Path("network_log")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = log_dir / f"{timestamp}.json"
    with filename.open("w") as f:
        json.dump(devices, f, indent=4)


def main():
    previous_devices = {}
    mac_to_name = load_mac_address_to_name()

    while True:
        current_devices = scan_network()

        # Save the scan results to a JSON file
        save_scan_to_file(current_devices)

        # Check for new devices
        new_devices = set(current_devices.keys()) - set(previous_devices.keys())
        if new_devices:
            new_device_messages = []
            for mac in new_devices:
                device = current_devices[mac]
                name = mac_to_name.get(mac, device.get("hostname", "Unknown"))
                ip = device["ip"]
                new_device_messages.append(f"{name} ({ip})")
            message = f"New devices connected: {', '.join(new_device_messages)}"
            print(message)
            send_message(f"New Devices: {message}", topic=_topic)

        # Check for devices that left
        left_devices = set(previous_devices.keys()) - set(current_devices.keys())
        if left_devices:
            left_device_messages = []
            for mac in left_devices:
                device = previous_devices[mac]
                name = mac_to_name.get(mac, device.get("hostname", "Unknown"))
                ip = device["ip"]
                left_device_messages.append(f"{name} ({ip})")
            message = f"Devices disconnected: {', '.join(left_device_messages)}"
            print(message)
            send_message(f"Devices Left: {message}", topic=_topic)

        previous_devices = current_devices

        # Wait for the next scan
        time.sleep(SCAN_INTERVAL * 60)


if __name__ == "__main__":
    main()
