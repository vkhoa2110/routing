####################################################
# LSrouter.py
# Tên:
# Mã sinh viên:
#####################################################

import heapq
from json import dumps, loads

from packet import Packet
from router import Router


class LSrouter(Router):
    """Cài đặt giao thức định tuyến Link State.

    Mỗi router công bố trạng thái các link trực tiếp của mình kèm số thứ tự.
    Router nhận thông tin này từ mạng, lưu vào cơ sở dữ liệu link-state, rồi chạy
    Dijkstra để tạo forwarding table tới các đích có thể tới được.
    """

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Khởi tạo lớp cha - KHÔNG XÓA
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
        """Xử lý packet đi vào router.

        Packet traceroute được chuyển tiếp theo forwarding table. Packet định
        tuyến LS được kiểm tra số thứ tự; chỉ thông tin mới hơn mới được lưu,
        lan truyền tiếp và dùng để tính lại đường đi ngắn nhất.
        """
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
        """Xử lý khi router có thêm link mới tới `endpoint`."""
        self.port_to_endpoint[port] = endpoint
        self.endpoint_to_port[endpoint] = port
        self.link_costs[endpoint] = cost
        self._publish_local_state()
        self._send_known_link_states(port, exclude_origin=self.addr)

    def handle_remove_link(self, port):
        """Xử lý khi link trên `port` bị gỡ khỏi router."""
        endpoint = self.port_to_endpoint.pop(port, None)
        if endpoint is not None:
            if self.endpoint_to_port.get(endpoint) == port:
                self.endpoint_to_port.pop(endpoint, None)
            self.link_costs.pop(endpoint, None)
            self._publish_local_state()

    def handle_time(self, time_ms):
        """Gửi lại trạng thái link cục bộ theo chu kỳ heartbeat."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast_message(self._local_state_message())

    def __repr__(self):
        """Chuỗi dùng để debug khi bấm vào router trong giao diện mô phỏng."""
        return (
            f"LSrouter(addr={self.addr}, "
            f"links={self.link_costs}, forwarding={self.forwarding_table})"
        )

    def _publish_local_state(self):
        """Tăng số thứ tự, lưu trạng thái link cục bộ và phát cho láng giềng."""
        self.sequence_number += 1
        self.link_state_db[self.addr] = {
            "seq": self.sequence_number,
            "links": dict(self.link_costs),
        }
        self._recompute_forwarding_table()
        self._broadcast_message(self._local_state_message())

    def _local_state_message(self):
        """Tạo gói thông tin link-state đại diện cho router hiện tại."""
        return {
            "type": "LS",
            "origin": self.addr,
            "seq": self.sequence_number,
            "links": dict(self.link_costs),
        }

    def _broadcast_message(self, message, exclude_port=None):
        """Gửi một thông điệp link-state tới mọi láng giềng, trừ cổng cần bỏ qua."""
        for port, endpoint in list(self.port_to_endpoint.items()):
            if port == exclude_port:
                continue
            self._send_message(port, endpoint, message)

    def _send_known_link_states(self, port, exclude_origin=None):
        """Gửi toàn bộ trạng thái link đã biết qua một cổng mới.

        Khi link mới xuất hiện, láng giềng ở đầu kia cần nhanh chóng nhận được
        cơ sở dữ liệu link-state hiện tại để bắt kịp phần còn lại của mạng.
        """
        endpoint = self.port_to_endpoint.get(port)
        if endpoint is None:
            return
        for origin, state in list(self.link_state_db.items()):
            if origin == exclude_origin:
                continue
            message = {
                "type": "LS",
                "origin": origin,
                "seq": state["seq"],
                "links": dict(state["links"]),
            }
            self._send_message(port, endpoint, message)

    def _send_message(self, port, endpoint, message):
        """Đóng gói thông điệp link-state thành packet định tuyến và gửi đi."""
        packet = Packet(Packet.ROUTING, self.addr, endpoint, dumps(message))
        self.send(port, packet)

    def _recompute_forwarding_table(self):
        """Chạy Dijkstra trên cơ sở dữ liệu link-state để tạo forwarding table."""
        distances = {self.addr: 0}
        first_hops = {}
        heap = [(0, self.addr, None)]

        while heap:
            distance, node, first_hop = heapq.heappop(heap)
            if distance != distances.get(node):
                continue

            # Duyệt các cạnh đi ra từ node đang xét. `first_hop` luôn giữ láng
            # giềng đầu tiên trên đường đi từ router hiện tại tới node đó.
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

        # Chuyển first hop thành cổng vật lý để simulator biết packet phải đi ra
        # link nào.
        forwarding_table = {}
        for destination, first_hop in first_hops.items():
            if destination == self.addr or first_hop is None:
                continue
            port = self.endpoint_to_port.get(first_hop)
            if port is not None:
                forwarding_table[destination] = port
        self.forwarding_table = forwarding_table

    def _neighbors(self, node):
        """Trả về các láng giềng mà `node` đã công bố trong cơ sở dữ liệu LS."""
        state = self.link_state_db.get(node)
        if state is None:
            return {}
        return state["links"]

    def _decode(self, content):
        """Giải mã nội dung JSON của packet định tuyến, lỗi thì trả về None."""
        try:
            return loads(content)
        except (TypeError, ValueError):
            return None
