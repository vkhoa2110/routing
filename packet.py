import copy


class Packet:
    """
    Lớp Packet mô tả packet được client và router gửi trong mạng mô phỏng.

    Tham số
    -------
    kind
        Một trong hai giá trị `Packet.TRACEROUTE` hoặc `Packet.ROUTING`. Khi tự
        tạo packet trong thuật toán định tuyến, hãy dùng `Packet.ROUTING`.
    src_addr
        Địa chỉ nguồn của packet.
    dst_addr
        Địa chỉ đích của packet.
    content
        Nội dung packet. Nếu có nội dung thì bắt buộc phải là chuỗi.
    """

    TRACEROUTE = 1
    ROUTING = 2

    def __init__(self, kind, src_addr, dst_addr, content=None):
        self.kind = kind
        self.src_addr = src_addr
        self.dst_addr = dst_addr
        self.content = content
        self.route = [src_addr]

    def copy(self):
        """Tạo bản sao sâu của packet.

        Hàm này được gọi tự động khi gửi packet để tránh lỗi nhiều nơi cùng giữ
        tham chiếu tới một object packet.
        """
        content = copy.deepcopy(self.content)
        p = Packet(self.kind, self.src_addr, self.dst_addr, content=content)
        p.route = list(self.route)
        return p

    @property
    def is_traceroute(self):
        """Trả về True nếu packet là packet traceroute."""
        return self.kind == Packet.TRACEROUTE

    @property
    def is_routing(self):
        """Trả về True nếu packet là packet định tuyến."""
        return self.kind == Packet.ROUTING

    def add_to_route(self, addr):
        """KHÔNG gọi hàm này từ DVrouter hoặc LSrouter."""
        self.route.append(addr)

    def animate_send(self, src, dst, latency):
        """KHÔNG gọi hàm này từ DVrouter hoặc LSrouter."""
        if hasattr(Packet, "animate"):
            Packet.animate(self, src, dst, latency)
