####################################################
# DVrouter.py
# Tên:
# Mã sinh viên:
#####################################################

from json import dumps, loads

from packet import Packet
from router import Router


class DVrouter(Router):
    """Cài đặt giao thức định tuyến Distance Vector.

    Router lưu chi phí tốt nhất đã biết tới từng đích, cổng cần gửi ra và
    distance vector nhận được từ các router láng giềng. Khi có link mới, link bị
    gỡ, hoặc nhận được vector mới từ láng giềng, router tính lại bảng định tuyến.
    """

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Khởi tạo lớp cha - KHÔNG XÓA
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.infinity = 16
        self.port_to_endpoint = {}
        self.endpoint_to_port = {}
        self.link_costs = {}
        self.neighbor_vectors = {}
        self.distance_vector = {self.addr: 0}
        self.forwarding_table = {}
        self.next_hops = {}

    def handle_packet(self, port, packet):
        """Xử lý packet đi vào router.

        Nếu là packet traceroute thì chuyển tiếp theo forwarding table. Nếu là
        packet định tuyến DV thì đọc vector của láng giềng, lưu lại và tính lại
        distance vector của chính router này.
        """
        if packet.is_traceroute:
            out_port = self.forwarding_table.get(packet.dst_addr)
            if out_port is not None:
                self.send(out_port, packet)
        else:
            message = self._decode(packet.content)
            if not message or message.get("type") != "DV":
                return

            neighbor = self.port_to_endpoint.get(port)
            vector = message.get("vector")
            if neighbor is None or not isinstance(vector, dict):
                return

            try:
                normalized_vector = {
                    destination: min(self.infinity, int(cost))
                    for destination, cost in vector.items()
                }
            except (TypeError, ValueError):
                return
            if self.neighbor_vectors.get(neighbor) != normalized_vector:
                self.neighbor_vectors[neighbor] = normalized_vector
                if self._recompute_distance_vector():
                    self._broadcast_distance_vector()

    def handle_new_link(self, port, endpoint, cost):
        """Xử lý khi router có thêm link mới tới `endpoint`."""
        self.port_to_endpoint[port] = endpoint
        self.endpoint_to_port[endpoint] = port
        self.link_costs[endpoint] = cost
        self._recompute_distance_vector()
        self._broadcast_distance_vector()

    def handle_remove_link(self, port):
        """Xử lý khi link trên `port` bị gỡ khỏi router."""
        endpoint = self.port_to_endpoint.pop(port, None)
        if endpoint is not None:
            if self.endpoint_to_port.get(endpoint) == port:
                self.endpoint_to_port.pop(endpoint, None)
            self.link_costs.pop(endpoint, None)
            self.neighbor_vectors.pop(endpoint, None)
            self._recompute_distance_vector()
            self._broadcast_distance_vector()

    def handle_time(self, time_ms):
        """Gửi định kỳ distance vector để các router khác luôn có thông tin mới."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast_distance_vector()

    def __repr__(self):
        """Chuỗi dùng để debug khi bấm vào router trong giao diện mô phỏng."""
        return (
            f"DVrouter(addr={self.addr}, "
            f"vector={self.distance_vector}, forwarding={self.forwarding_table})"
        )

    def _recompute_distance_vector(self):
        """Tính lại vector khoảng cách và forwarding table từ dữ liệu hiện có."""
        # Tập đích cần xét gồm chính router, các láng giềng trực tiếp và mọi đích
        # từng xuất hiện trong vector nhận được từ láng giềng.
        destinations = set(self.distance_vector)
        destinations.add(self.addr)
        destinations.update(self.link_costs)
        for vector in self.neighbor_vectors.values():
            destinations.update(vector)

        # Ban đầu coi mọi đích là không tới được, sau đó cập nhật bằng chi phí tốt
        # nhất tìm được theo công thức Bellman-Ford.
        new_vector = {destination: self.infinity for destination in destinations}
        new_vector[self.addr] = 0
        new_next_hops = {}

        # Các láng giềng trực tiếp luôn là ứng viên đường đi đầu tiên.
        for destination, cost in self.link_costs.items():
            bounded_cost = min(self.infinity, cost)
            if bounded_cost < new_vector[destination]:
                new_vector[destination] = bounded_cost
                new_next_hops[destination] = destination

        # Thử đi tới từng đích thông qua từng láng giềng, lấy tổng chi phí nhỏ
        # nhất. Khi hòa chi phí, chọn next hop có tên nhỏ hơn để kết quả ổn định.
        for neighbor, vector in self.neighbor_vectors.items():
            if neighbor not in self.link_costs:
                continue
            link_cost = self.link_costs[neighbor]
            for destination, neighbor_cost in vector.items():
                if destination == self.addr:
                    continue
                total_cost = min(self.infinity, link_cost + neighbor_cost)
                current_next_hop = new_next_hops.get(destination)
                should_update = total_cost < new_vector.get(
                    destination, self.infinity
                )
                if (
                    total_cost == new_vector.get(destination, self.infinity)
                    and total_cost < self.infinity
                    and current_next_hop is not None
                    and neighbor < current_next_hop
                ):
                    should_update = True

                if should_update:
                    new_vector[destination] = total_cost
                    new_next_hops[destination] = neighbor

        # Chỉ đưa vào forwarding table những đích thật sự tới được và có cổng gửi.
        new_forwarding_table = {}
        for destination, next_hop in new_next_hops.items():
            if destination == self.addr:
                continue
            if new_vector.get(destination, self.infinity) >= self.infinity:
                continue
            port = self.endpoint_to_port.get(next_hop)
            if port is not None:
                new_forwarding_table[destination] = port

        changed = (
            new_vector != self.distance_vector
            or new_forwarding_table != self.forwarding_table
        )
        self.distance_vector = new_vector
        self.next_hops = new_next_hops
        self.forwarding_table = new_forwarding_table
        return changed

    def _broadcast_distance_vector(self):
        """Gửi distance vector hiện tại tới tất cả láng giềng trực tiếp."""
        for port, endpoint in list(self.port_to_endpoint.items()):
            vector = self._vector_for_neighbor(endpoint)
            content = dumps({"type": "DV", "vector": vector})
            packet = Packet(Packet.ROUTING, self.addr, endpoint, content)
            self.send(port, packet)

    def _vector_for_neighbor(self, neighbor):
        """Tạo vector gửi riêng cho một láng giềng.

        Nếu đường tới một đích đang đi qua chính láng giềng đó, router quảng bá
        chi phí vô cực cho đích ấy. Đây là kỹ thuật poison reverse để giảm vòng
        lặp định tuyến và hạn chế bài toán count-to-infinity.
        """
        vector = {}
        for destination, cost in self.distance_vector.items():
            advertised_cost = min(self.infinity, cost)
            if self.next_hops.get(destination) == neighbor:
                advertised_cost = self.infinity
            vector[destination] = advertised_cost
        return vector

    def _decode(self, content):
        """Giải mã nội dung JSON của packet định tuyến, lỗi thì trả về None."""
        try:
            return loads(content)
        except (TypeError, ValueError):
            return None
