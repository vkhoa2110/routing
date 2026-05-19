####################################################
# LSrouter.py
# Name:
# HUID:
#####################################################

import heapq
from json import dumps, loads

from packet import Packet
from router import Router


class LSrouter(Router):
    """Link state routing protocol implementation.

    Add your own class fields and initialization code (e.g. to create forwarding table
    data structures). See the `Router` base class for docstrings of the methods to
    override.
    """

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Initialize base class - DO NOT REMOVE
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.port_to_endpoint = {}
        self.endpoint_to_port = {}
        self.link_costs = {}
        self.sequence_number = 0
        self.link_state_db = {
            self.addr: {"seq": self.sequence_number, "links": {}}
        }
        self.forwarding_table = {}

    def handle_packet(self, port, packet):
        """Process incoming packet."""
        if packet.is_traceroute:
            out_port = self.forwarding_table.get(packet.dst_addr)
            if out_port is not None:
                self.send(out_port, packet)
        else:
            message = self._decode(packet.content)
            if not message or message.get("type") != "LS":
                return

            origin = message.get("origin")
            sequence_number = message.get("seq")
            links = message.get("links")
            if origin is None or sequence_number is None or not isinstance(links, dict):
                return

            old_state = self.link_state_db.get(origin)
            if old_state is None or sequence_number > old_state["seq"]:
                self.link_state_db[origin] = {
                    "seq": sequence_number,
                    "links": dict(links),
                }
                self._recompute_forwarding_table()
                self._broadcast_message(message, exclude_port=port)

    def handle_new_link(self, port, endpoint, cost):
        """Handle new link."""
        self.port_to_endpoint[port] = endpoint
        self.endpoint_to_port[endpoint] = port
        self.link_costs[endpoint] = cost
        self._publish_local_state()

    def handle_remove_link(self, port):
        """Handle removed link."""
        endpoint = self.port_to_endpoint.pop(port, None)
        if endpoint is not None:
            if self.endpoint_to_port.get(endpoint) == port:
                self.endpoint_to_port.pop(endpoint, None)
            self.link_costs.pop(endpoint, None)
            self._publish_local_state()

    def handle_time(self, time_ms):
        """Handle current time."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast_message(self._local_state_message())

    def __repr__(self):
        """Representation for debugging in the network visualizer."""
        return (
            f"LSrouter(addr={self.addr}, "
            f"links={self.link_costs}, forwarding={self.forwarding_table})"
        )

    def _publish_local_state(self):
        self.sequence_number += 1
        self.link_state_db[self.addr] = {
            "seq": self.sequence_number,
            "links": dict(self.link_costs),
        }
        self._recompute_forwarding_table()
        self._broadcast_message(self._local_state_message())

    def _local_state_message(self):
        return {
            "type": "LS",
            "origin": self.addr,
            "seq": self.sequence_number,
            "links": dict(self.link_costs),
        }

    def _broadcast_message(self, message, exclude_port=None):
        content = dumps(message)
        for port, endpoint in list(self.port_to_endpoint.items()):
            if port == exclude_port:
                continue
            packet = Packet(Packet.ROUTING, self.addr, endpoint, content)
            self.send(port, packet)

    def _recompute_forwarding_table(self):
        distances = {self.addr: 0}
        first_hops = {}
        heap = [(0, self.addr, None)]

        while heap:
            distance, node, first_hop = heapq.heappop(heap)
            if distance != distances.get(node):
                continue

            for neighbor, cost in self._neighbors(node).items():
                new_distance = distance + cost
                new_first_hop = neighbor if node == self.addr else first_hop
                old_distance = distances.get(neighbor)
                old_first_hop = first_hops.get(neighbor)
                should_update = old_distance is None or new_distance < old_distance
                if (
                    old_distance is not None
                    and new_distance == old_distance
                    and old_first_hop is not None
                    and new_first_hop is not None
                    and new_first_hop < old_first_hop
                ):
                    should_update = True

                if should_update:
                    distances[neighbor] = new_distance
                    first_hops[neighbor] = new_first_hop
                    heapq.heappush(heap, (new_distance, neighbor, new_first_hop))

        forwarding_table = {}
        for destination, first_hop in first_hops.items():
            if destination == self.addr or first_hop is None:
                continue
            port = self.endpoint_to_port.get(first_hop)
            if port is not None:
                forwarding_table[destination] = port
        self.forwarding_table = forwarding_table

    def _neighbors(self, node):
        state = self.link_state_db.get(node)
        if state is None:
            return {}
        return state["links"]

    def _decode(self, content):
        try:
            return loads(content)
        except (TypeError, ValueError):
            return None
