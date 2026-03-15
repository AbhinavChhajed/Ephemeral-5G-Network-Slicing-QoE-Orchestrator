"""
Mininet Topology for 5G Network Slicing Environment
=====================================================
Defines a custom network topology with:
- 1 central OpenFlow-enabled switch (OVS)
- 3 host types (video streaming, gaming, IoT/sensor)
- Simulated network flows with configurable parameters
"""

from mininet.net import Mininet
from mininet.node import OVSSwitch, Controller, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info
import subprocess
import time
from threading import Thread
import os


class CustomTCLink(TCLink):
    """
    Custom link with refined traffic control parameters.
    Allows dynamic bandwidth, latency, and loss configurations.
    """
    def config(self, bw=10, delay='5ms', loss=0.1, **params):
        super().config(bw=bw, delay=delay, loss=loss, **params)


class Network5GSlicing:
    """
    5G Network Slicing Topology Manager.
    Orchestrates the creation and management of a Mininet network
    with slice-aware configuration.
    """

    def __init__(self, controller_ip='127.0.0.1', controller_port=6633):
        """
        Initialize the network topology.
        
        Args:
            controller_ip (str): IP address of the Ryu controller
            controller_port (int): Port of the Ryu controller
        """
        self.controller_ip = controller_ip
        self.controller_port = controller_port
        self.net = None
        self.traffic_processes = []
        self.slice_hosts = {}

    def create_topology(self):
        """
        Create the Mininet topology with:
        - Central OVS switch (DPID: 0x00000000000000001)
        - 3 hosts representing different device types
        - Links with traffic control
        """
        info("*** Creating Mininet Network Topology ***\n")

        # Initialize Mininet with a RemoteController (Ryu)
        self.net = Mininet(
            switch=OVSSwitch,
            controller=RemoteController,
            link=CustomTCLink,
            autoSetMacs=True
        )

        # Create the controller (Ryu)
        info("*** Adding Remote Controller (Ryu) ***\n")
        c0 = self.net.addController(
            'c0',
            controller=RemoteController,
            ip=self.controller_ip,
            port=self.controller_port,
            protocols='OpenFlow13'
        )

        # Create central switch
        info("*** Adding Central OpenFlow Switch ***\n")
        s1 = self.net.addSwitch('s1', dpid='0x0000000000000001', cls=OVSSwitch)

        # Create hosts for different device types
        info("*** Adding Hosts (Device Types) ***\n")
        
        # Video Streaming Host (High bandwidth, moderate latency sensitivity)
        h1 = self.net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        self.slice_hosts['video'] = h1

        # Gaming Host (Low latency critical, moderate bandwidth)
        h2 = self.net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        self.slice_hosts['gaming'] = h2

        # IoT/Sensor Host (Low bandwidth, best effort)
        h3 = self.net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        self.slice_hosts['iot'] = h3

        # Connect hosts to central switch with different link characteristics
        info("*** Adding Links (Host <-> Switch) ***\n")
        
        # Video slice: 100 Mbps, 10ms latency, 0.1% loss
        self.net.addLink(h1, s1, cls=CustomTCLink,
                         bw=100, delay='10ms', loss=0.1, 
                         use_htb=True, max_queue_size=1024)

        # Gaming slice: 50 Mbps, 5ms latency, 0.05% loss
        self.net.addLink(h2, s1, cls=CustomTCLink,
                         bw=50, delay='5ms', loss=0.05,
                         use_htb=True, max_queue_size=512)

        # IoT slice: 10 Mbps, 50ms latency, 0.2% loss
        self.net.addLink(h3, s1, cls=CustomTCLink,
                         bw=10, delay='50ms', loss=0.2,
                         use_htb=True, max_queue_size=256)

        info("*** Starting Network ***\n")
        self.net.start()
        
        # Allow time for controller connection
        time.sleep(2)
        
        info("*** Network Started Successfully ***\n")
        info(f"Controller connected at {self.controller_ip}:{self.controller_port}\n")

        return self.net

    def start_traffic(self, duration=None):
        """
        Start continuous network flows between hosts.
        Simulates realistic traffic patterns.
        
        Args:
            duration (int): Duration of traffic simulation in seconds (None = indefinite)
        """
        info("*** Starting Traffic Simulation ***\n")

        # Helper function to run iperf
        def run_iperf_server(host, port):
            """Start iperf server on a host."""
            info(f"Starting iperf server on {host.name}:{port}\n")
            host.popen(f'iperf3 -s -p {port} -D')

        def run_iperf_client(src_host, dst_ip, port, duration=60, bitrate='10M', proto='tcp'):
            """Start iperf client from source to destination."""
            if proto.lower() == 'udp':
                cmd = f'iperf3 -c {dst_ip} -p {port} -u -b {bitrate} -t {duration} &'
            else:
                cmd = f'iperf3 -c {dst_ip} -p {port} -b {bitrate} -t {duration} &'
            
            info(f"Starting traffic: {src_host.name} -> {dst_ip}:{port} ({bitrate}, {duration}s)\n")
            src_host.popen(cmd)

        try:
            # Start iperf servers on all hosts
            run_iperf_server(self.slice_hosts['video'], 5201)
            run_iperf_server(self.slice_hosts['gaming'], 5202)
            run_iperf_server(self.slice_hosts['iot'], 5203)

            # Allow servers to start
            time.sleep(1)

            # Start traffic flows
            # Video streaming: h1 <-> h2 (100 Mbps)
            run_iperf_client(
                self.slice_hosts['video'],
                '10.0.0.2',
                5202,
                duration=duration or 3600,
                bitrate='50M',
                proto='tcp'
            )

            # Gaming: h2 <-> h3 (low latency, 20 Mbps)
            run_iperf_client(
                self.slice_hosts['gaming'],
                '10.0.0.3',
                5203,
                duration=duration or 3600,
                bitrate='15M',
                proto='udp'
            )

            # IoT: h3 <-> h1 (best effort, 5 Mbps)
            run_iperf_client(
                self.slice_hosts['iot'],
                '10.0.0.1',
                5201,
                duration=duration or 3600,
                bitrate='5M',
                proto='tcp'
            )

            info("*** Traffic Flows Started ***\n")

        except Exception as e:
            info(f"Error starting traffic: {str(e)}\n")

    def stop_traffic(self):
        """Stop all running iperf processes."""
        info("*** Stopping Traffic Simulation ***\n")
        for host in self.slice_hosts.values():
            host.popen('pkill -f iperf3')
        time.sleep(1)
        info("*** Traffic Stopped ***\n")

    def get_switch_stats(self):
        """
        Retrieve current switch statistics via OpenFlow.
        Returns port stats, flow stats, etc.
        """
        try:
            s1 = self.net.get('s1')
            # Get flow table stats
            info(f"*** Switch {s1.name} Stats ***\n")
            # This would require interaction with the controller
            # for detailed OpenFlow statistics
            return {"status": "running", "switch": "s1"}
        except Exception as e:
            info(f"Error getting switch stats: {str(e)}\n")
            return {"error": str(e)}

    def add_traffic_control_rule(self, host_name, bandwidth_mbps, delay_ms, loss_percent):
        """
        Dynamically modify traffic control rules on a host's link.
        
        Args:
            host_name (str): Name of the host (e.g., 'h1')
            bandwidth_mbps (int): Bandwidth in Mbps
            delay_ms (int): Delay in milliseconds
            loss_percent (float): Packet loss percentage
        """
        try:
            host = self.net.get(host_name)
            if host:
                # Get the interface connected to the switch
                intf = host.intfs[0]
                
                # Apply tc (traffic control) commands
                cmd = (
                    f'tc qdisc replace dev {intf.name} root tbf '
                    f'rate {bandwidth_mbps}mbit burst 32kbit latency {delay_ms}ms'
                )
                host.popen(cmd)
                info(f"Applied TC rule to {host_name}: {bandwidth_mbps}Mbps, {delay_ms}ms, {loss_percent}% loss\n")
        except Exception as e:
            info(f"Error applying TC rule: {str(e)}\n")

    def cli(self):
        """Enter interactive CLI mode."""
        if self.net:
            CLI(self.net)

    def stop(self):
        """Stop and cleanup the network."""
        info("*** Stopping Network ***\n")
        self.stop_traffic()
        if self.net:
            self.net.stop()
        info("*** Network Stopped ***\n")


def main():
    """
    Main execution function.
    Demonstrates network creation, traffic simulation, and monitoring.
    """
    setLogLevel('info')

    # Create network topology
    network = Network5GSlicing(
        controller_ip='127.0.0.1',
        controller_port=6633
    )

    try:
        # Create and start the topology
        network.create_topology()

        # Start traffic simulation
        network.start_traffic(duration=3600)

        # Keep network running
        info("*** Network is running. Press Ctrl+C to stop. ***\n")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        info("\n*** Shutting down network ***\n")
    finally:
        network.stop()


if __name__ == '__main__':
    main()
