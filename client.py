import time
import queue
from packet import Packet


class Client:
    """
    Lớp Client mô phỏng một máy đầu cuối trong mạng.

    Client định kỳ gửi packet dạng "traceroute" tới các client khác. Khi nhận
    lại packet traceroute, client báo đường đi của packet cho đối tượng Network
    để simulator có thể hiển thị và kiểm tra kết quả định tuyến.
    """

    def __init__(self, addr, all_clients, send_rate, update_fn):
        self.addr = addr
        self.all_clients = all_clients
        self.send_rate = send_rate
        self.last_time = 0
        self.link = None
        self.update_fn = update_fn
        self.sending = True
        self.link_changes = queue.Queue()
        self.keep_running = True

    def change_link(self, change):
        """Thêm link nối client với mạng.

        Tham số `change` là tuple dạng `('add', link)`, trong đó `link` là đối
        tượng Link mà client sẽ dùng để gửi và nhận packet.
        """
        self.link_changes.put(change)

    def handle_packet(self, packet):
        """Xử lý packet mà client nhận được.

        Packet định tuyến bị bỏ qua vì client không tham gia chạy thuật toán
        định tuyến. Nếu là packet traceroute, client cập nhật route hiện tại cho
        Network để phục vụ hiển thị và chấm đúng/sai.
        """
        if packet.kind == Packet.TRACEROUTE:
            self.update_fn(packet.src_addr, packet.dst_addr, packet.route)

    def send_traceroutes(self):
        """Gửi packet traceroute tới mọi client khác trong mạng."""
        for dst_client in self.all_clients:
            packet = Packet(Packet.TRACEROUTE, self.addr, dst_client)
            if self.link:
                self.link.send(packet, self.addr)
            self.update_fn(packet.src_addr, packet.dst_addr, [])

    def handle_time(self, time_ms):
        """Gửi traceroute theo chu kỳ dựa trên thời gian hiện tại."""
        if self.sending and (time_ms - self.last_time > self.send_rate):
            self.send_traceroutes()
            self.last_time = time_ms

    def run(self):
        """Vòng lặp chính của client trong simulator."""
        while self.keep_running:
            time.sleep(0.1)
            time_ms = int(round(time.time() * 1000))
            try:
                change = self.link_changes.get_nowait()
                if change[0] == "add":
                    self.link = change[1]
            except queue.Empty:
                pass
            if self.link:
                packet = self.link.recv(self.addr)
                if packet:
                    self.handle_packet(packet)
            self.handle_time(time_ms)

    def last_send(self):
        """Gửi một lượt traceroute cuối cùng trước khi kết thúc mô phỏng."""
        self.sending = False
        self.send_traceroutes()
