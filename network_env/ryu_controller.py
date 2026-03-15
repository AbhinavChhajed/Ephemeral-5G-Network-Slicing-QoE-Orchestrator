"""
Ryu SDN Controller for 5G Network Slicing
============================================
Implements a Layer 2 learning switch with OpenFlow 1.3 support.
Provides mechanisms for:
- Dynamic flow rule modification
- Meter-based bandwidth limiting
- Queue prioritization
- Network telemetry collection
"""

from ryu.base import app_manager
from ryu.controller import ofp_event, dpset
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3, ofproto_v1_3_parser
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, udp, icmp
from ryu.lib.packet.packet_base import packet as packet_base
from ryu.lib import mac as mac_lib, ip as ip_lib
from ryu.lib.hub import spawn, sleep
from ryu.app.wsgi import WSGIApplication
from ryu.controller import handler

import logging
import json
from datetime import datetime
from collections import defaultdict
import time


LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class SliceConfig:
    """Configuration container for a network slice."""
    
    def __init__(self, slice_id, slice_name, priority, bandwidth_mbps, delay_ms, loss_percent):
        self.slice_id = slice_id
        self.slice_name = slice_name
        self.priority = priority
        self.bandwidth_mbps = bandwidth_mbps
        self.delay_ms = delay_ms
        self.loss_percent = loss_percent
        self.created_at = datetime.now()
        self.is_active = True


class PacketCounter:
    """Tracks packet and byte statistics per flow."""
    
    def __init__(self):
        self.packet_count = 0
        self.byte_count = 0
        self.last_update = time.time()


class Ryu5GController(app_manager.RyuApp):
    """
    Main Ryu SDN controller application.
    Handles OpenFlow events and slice orchestration.
    """
    
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Ryu5GController, self).__init__(*args, **kwargs)
        
        # MAC address table: {dpid -> {mac -> port}}
        self.mac_to_port = defaultdict(lambda: defaultdict(int))
        
        # Flow statistics: {(dpid, eth_src, eth_dst) -> PacketCounter}
        self.flow_stats = defaultdict(PacketCounter)
        
        # Slice configurations: {slice_id -> SliceConfig}
        self.slices = {}
        
        # Port statistics: {(dpid, port_no) -> stats}
        self.port_stats = defaultdict(dict)
        
        # Flow to slice mapping: {(dpid, match_hash) -> slice_id}
        self.flow_to_slice = {}
        
        # Meter IDs: {slice_id -> meter_id}
        self.slice_meters = {}
        
        # Queue configurations
        self.slice_queues = {}
        
        # Data switch reference
        self.datapaths = {}
        
        # Statistics collection interval (seconds)
        self.stats_interval = 10

    @set_ev_cls(ofp_event.EventOFPStateChange, CONFIG_DISPATCHER)
    def _state_change_handler(self, ev):
        """
        Handle datapath state changes (connection/disconnection).
        Configures the switch on first connection.
        """
        datapath = ev.datapath
        
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                LOG.info(f"*** Datapath {hex(datapath.id)} connected ***")
                self.datapaths[datapath.id] = datapath
                self._setup_initial_table_miss(datapath)
        elif ev.state == CONFIG_DISPATCHER:
            if datapath.id in self.datapaths:
                LOG.info(f"*** Datapath {hex(datapath.id)} disconnected ***")
                del self.datapaths[datapath.id]

    def _setup_initial_table_miss(self, datapath):
        """
        Setup initial table miss flow rule.
        All packets not matching any rule are sent to the controller.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Create a table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, 0, match, actions, idle_timeout=0, hard_timeout=0)
        
        LOG.info(f"*** Installed table-miss flow rule on {hex(datapath.id)} ***")

    def _add_flow(self, datapath, priority, match, actions, idle_timeout=300, hard_timeout=0):
        """
        Add a flow rule to the datapath.
        
        Args:
            datapath: OpenFlow datapath
            priority: Flow rule priority (higher = better)
            match: OFPMatch object
            actions: List of OFPAction objects
            idle_timeout: Flow idle timeout in seconds
            hard_timeout: Flow hard timeout in seconds
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            flags=ofproto.OFPFF_SEND_FLOW_REM
        )
        
        try:
            datapath.send_msg(mod)
            LOG.debug(f"Flow rule added to {hex(datapath.id)}: priority={priority}")
        except Exception as e:
            LOG.error(f"Error adding flow rule: {str(e)}")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        Handle incoming packets (table miss).
        Implements learning switch behavior with slice awareness.
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        if eth.dst == mac_lib.BROADCAST_STR or eth.src == mac_lib.BROADCAST_STR:
            return
        
        # Learn MAC address
        self.mac_to_port[datapath.id][eth.src] = in_port
        
        # Lookup destination port
        if eth.dst in self.mac_to_port[datapath.id]:
            out_port = self.mac_to_port[datapath.id][eth.dst]
        else:
            out_port = ofproto.OFPP_FLOOD
        
        # Build match and actions
        match = parser.OFPMatch(in_port=in_port, eth_src=eth.src, eth_dst=eth.dst)
        actions = [parser.OFPActionOutput(out_port)]
        
        # Determine slice priority based on packet characteristics
        priority = self._get_priority_for_packet(pkt)
        
        # Add flow rule (if not flooding)
        if out_port != ofproto.OFPP_FLOOD:
            self._add_flow(datapath, priority, match, actions)
            LOG.debug(f"Learned route: {eth.src} -> {eth.dst} (port {out_port}, priority {priority})")
        
        # Send packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def _get_priority_for_packet(self, pkt):
        """
        Determine flow priority based on packet characteristics.
        Returns higher priority for latency-sensitive protocols (e.g., UDP gaming).
        """
        # Check packet type
        if pkt.get_protocol(udp.udp):
            # UDP: likely gaming or VoIP
            return 20
        elif pkt.get_protocol(tcp.tcp):
            # TCP: could be video streaming or web
            return 15
        else:
            # Default: best effort IoT
            return 10

    def add_meter(self, datapath_id, slice_config, meter_id):
        """
        Add a meter to enforce bandwidth limits on a slice.
        
        Args:
            datapath_id: OpenFlow datapath ID
            slice_config: SliceConfig object
            meter_id: Meter ID (1-255)
        """
        if datapath_id not in self.datapaths:
            LOG.error(f"Datapath {datapath_id} not found")
            return False
        
        datapath = self.datapaths[datapath_id]
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Create meter bands
        rate = slice_config.bandwidth_mbps * 1024  # Convert to Kbps
        bands = [
            parser.OFPMeterBandDrop(
                type_=ofproto.OFPMBT_DROP,
                rate=rate,
                burst_size=burst
            )
        ]
        
        # Create meter command
        cmd = ofproto.OFPMC_ADD
        flags = ofproto.OFPMF_KBPS
        
        meter_mod = parser.OFPMeterMod(
            datapath=datapath,
            command=cmd,
            flags=flags,
            meter_id=meter_id,
            bands=bands
        )
        
        try:
            datapath.send_msg(meter_mod)
            self.slice_meters[slice_config.slice_id] = meter_id
            LOG.info(f"Installed meter {meter_id} for slice {slice_config.slice_name}: {slice_config.bandwidth_mbps} Mbps")
            return True
        except Exception as e:
            LOG.error(f"Error adding meter: {str(e)}")
            return False

    def modify_meter(self, datapath_id, meter_id, new_bandwidth_mbps):
        """
        Modify an existing meter's bandwidth.
        
        Args:
            datapath_id: OpenFlow datapath ID
            meter_id: Meter ID to modify
            new_bandwidth_mbps: New bandwidth in Mbps
        """
        if datapath_id not in self.datapaths:
            LOG.error(f"Datapath {datapath_id} not found")
            return False
        
        datapath = self.datapaths[datapath_id]
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        rate = new_bandwidth_mbps * 1024  # Convert to Kbps
        bands = [
            parser.OFPMeterBandDrop(
                type_=ofproto.OFPMBT_DROP,
                rate=rate,
                burst_size=32000
            )
        ]
        
        meter_mod = parser.OFPMeterMod(
            datapath=datapath,
            command=ofproto.OFPMC_MODIFY,
            flags=ofproto.OFPMF_KBPS,
            meter_id=meter_id,
            bands=bands
        )
        
        try:
            datapath.send_msg(meter_mod)
            LOG.info(f"Modified meter {meter_id}: new bandwidth {new_bandwidth_mbps} Mbps")
            return True
        except Exception as e:
            LOG.error(f"Error modifying meter: {str(e)}")
            return False

    def delete_meter(self, datapath_id, meter_id):
        """
        Delete a meter from the datapath.
        
        Args:
            datapath_id: OpenFlow datapath ID
            meter_id: Meter ID to delete
        """
        if datapath_id not in self.datapaths:
            LOG.error(f"Datapath {datapath_id} not found")
            return False
        
        datapath = self.datapaths[datapath_id]
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        meter_mod = parser.OFPMeterMod(
            datapath=datapath,
            command=ofproto.OFPMC_DELETE,
            meter_id=meter_id
        )
        
        try:
            datapath.send_msg(meter_mod)
            LOG.info(f"Deleted meter {meter_id}")
            return True
        except Exception as e:
            LOG.error(f"Error deleting meter: {str(e)}")
            return False

    def create_slice(self, slice_id, slice_name, priority, bandwidth_mbps, delay_ms, loss_percent):
        """
        Create a new network slice with QoS parameters.
        
        Args:
            slice_id: Unique slice identifier
            slice_name: Human-readable slice name
            priority: QoS priority level
            bandwidth_mbps: Bandwidth allocation in Mbps
            delay_ms: Maximum allowed delay in milliseconds
            loss_percent: Maximum allowed packet loss percentage
        """
        slice_config = SliceConfig(
            slice_id=slice_id,
            slice_name=slice_name,
            priority=priority,
            bandwidth_mbps=bandwidth_mbps,
            delay_ms=delay_ms,
            loss_percent=loss_percent
        )
        
        self.slices[slice_id] = slice_config
        
        # Add meter for the first available datapath
        if self.datapaths:
            datapath_id = list(self.datapaths.keys())[0]
            # Use slice_id as meter_id (limit to valid range 1-255)
            meter_id = (slice_id % 254) + 1
            self.add_meter(datapath_id, slice_config, meter_id)
        
        LOG.info(f"Created slice: {slice_name} (ID: {slice_id}, Priority: {priority}, BW: {bandwidth_mbps} Mbps)")
        return slice_config

    def delete_slice(self, slice_id):
        """
        Delete a network slice.
        
        Args:
            slice_id: ID of the slice to delete
        """
        if slice_id not in self.slices:
            LOG.warning(f"Slice {slice_id} not found")
            return False
        
        slice_config = self.slices[slice_id]
        meter_id = self.slice_meters.get(slice_id)
        
        # Delete meter from all datapaths
        if meter_id:
            for datapath_id in self.datapaths.keys():
                self.delete_meter(datapath_id, meter_id)
        
        # Mark as inactive
        slice_config.is_active = False
        
        LOG.info(f"Deleted slice: {slice_config.slice_name}")
        return True

    def get_slice_status(self, slice_id=None):
        """
        Get status of one or all slices.
        
        Args:
            slice_id: Optional specific slice ID
            
        Returns:
            Dictionary with slice status information
        """
        if slice_id:
            if slice_id not in self.slices:
                return {"error": f"Slice {slice_id} not found"}
            
            sc = self.slices[slice_id]
            return {
                "slice_id": sc.slice_id,
                "slice_name": sc.slice_name,
                "priority": sc.priority,
                "bandwidth_mbps": sc.bandwidth_mbps,
                "delay_ms": sc.delay_ms,
                "loss_percent": sc.loss_percent,
                "is_active": sc.is_active,
                "created_at": sc.created_at.isoformat()
            }
        else:
            return {
                "total_slices": len(self.slices),
                "slices": [
                    {
                        "slice_id": sc.slice_id,
                        "slice_name": sc.slice_name,
                        "is_active": sc.is_active
                    }
                    for sc in self.slices.values()
                ]
            }

    def get_flow_stats(self, datapath_id=None):
        """
        Get current flow statistics.
        
        Args:
            datapath_id: Optional specific datapath ID
            
        Returns:
            Dictionary with flow statistics
        """
        stats = {}
        for (dpid, eth_src, eth_dst), counter in self.flow_stats.items():
            if datapath_id is None or dpid == datapath_id:
                flow_key = f"{eth_src} -> {eth_dst}"
                stats[flow_key] = {
                    "packets": counter.packet_count,
                    "bytes": counter.byte_count,
                    "dpid": hex(dpid)
                }
        return stats

    def get_controller_info(self):
        """
        Get general controller information.
        """
        return {
            "controller": "Ryu 5G Slice Controller",
            "version": "1.0",
            "connected_datapaths": len(self.datapaths),
            "total_slices": len(self.slices),
            "total_flows": len(self.flow_stats),
            "datapaths": [hex(dpid) for dpid in self.datapaths.keys()]
        }


def main():
    """
    Main entry point for the Ryu controller.
    Run with: ryu-manager ryu_controller.py
    """
    LOG.info("Starting Ryu 5G Network Slicing Controller...")


if __name__ == '__main__':
    main()
