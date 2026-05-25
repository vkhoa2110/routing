import time
import queue


class Router:
    """
    Lớp Router cơ sở xử lý phần chung của việc gửi/nhận packet và thay đổi link.

    Các lớp con như DVrouter hoặc LSrouter cần override các phương thức dưới đây
    để cài đặt thuật toán định tuyến cụ thể:

    - __init__
    - handle_packet
    - handle_new_link
    - handle_remove_link
    - handle_time
    - __repr__ (optional, for your own debugging)

    Tham số
    -------
    addr
        Địa chỉ của router hiện tại.
    heartbeat_time
        Khoảng thời gian tối đa giữa hai lần gửi thông tin định tuyến, tính bằng
        mili-giây.
    """

    def __init__(self, addr, heartbeat_time=None):
        self.addr = addr
        self.links = {}  # Các link được lưu theo số port
        self.link_changes = queue.Queue()  # Hàng đợi an toàn thread cho thay đổi link
        self.keep_running = True

    def change_link(self, change):
        """Thêm, gỡ hoặc thay đổi chi phí của một link.

        Tham số `change` là tuple có phần tử đầu là `"add"` hoặc `"remove"`.
        Router đưa yêu cầu này vào hàng đợi để vòng lặp chính xử lý tuần tự.
        """
        self.link_changes.put(change)

    def add_link(self, port, endpointAddr, link, cost):
        """Thêm link mới vào router trên một port cụ thể."""
        if port in self.links:
            self.remove_link(port)
        self.links[port] = link
        self.handle_new_link(port, endpointAddr, cost)

    def remove_link(self, port):
        """Gỡ link khỏi router theo số port."""
        self.links = {p: link for p, link in self.links.items() if p != port}
        self.handle_remove_link(port)

    def run(self):
        """Vòng lặp chính của router trong simulator."""
        while self.keep_running:
            time.sleep(0.1)
            time_ms = int(round(time.time() * 1000))
            try:
                change = self.link_changes.get_nowait()
                if change[0] == "add":
                    self.add_link(*change[1:])
                elif change[0] == "remove":
                    self.remove_link(*change[1:])
            except queue.Empty:
                pass
            for port in self.links.keys():
                packet = self.links[port].recv(self.addr)
                if packet:
                    self.handle_packet(port, packet)
            self.handle_time(time_ms)

    def send(self, port, packet):
        """Gửi packet ra ngoài qua port được chỉ định."""
        try:
            self.links[port].send(packet, self.addr)
        except KeyError:
            pass

    def handle_packet(self, port, packet):
        """Xử lý packet đi vào router.

        Lớp con nên override phương thức này. Cài đặt mặc định chỉ gửi packet
        ngược ra đúng port mà packet vừa đi vào, nên không phải là thuật toán
        định tuyến thật sự.

        Phương thức được gọi mỗi khi có packet tới port `port`. Khi cài đặt lớp
        con, cần phân biệt packet traceroute và packet định tuyến để xử lý đúng.
        Các trường và phương thức của packet được định nghĩa trong `packet.py`.

        Tham số
        -------
        port
            Số port mà packet đi vào.
        packet
            Đối tượng packet vừa nhận được.
        """
        self.send(port, packet)

    def handle_new_link(self, port, endpoint, cost):
        """Xử lý khi router có link mới.

        Lớp con nên override phương thức này. Cài đặt mặc định không làm gì.

        Phương thức được gọi khi một link mới được thêm vào port `port`, nối tới
        router hoặc client có địa chỉ `endpoint` với chi phí link là `cost`.
        Lớp con nên lưu các giá trị này vào cấu trúc dữ liệu dùng cho định
        tuyến. Nếu muốn gửi packet qua link này, gọi `self.send(port, packet)`.

        Tham số
        -------
        port
            Số port mà link mới được thêm vào.
        endpoint
            Địa chỉ của đầu bên kia của link.
        cost
            Chi phí của link.
        """
        pass

    def handle_remove_link(self, port):
        """Xử lý khi một link bị gỡ.

        Lớp con nên override phương thức này. Cài đặt mặc định không làm gì.

        Phương thức được gọi khi link đang nằm trên port `port` bị ngắt. Lớp con
        cần cập nhật các cấu trúc dữ liệu định tuyến tương ứng.

        Tham số
        -------
        port
            Số port của link vừa bị gỡ.
        """
        pass

    def handle_time(self, time_ms):
        """Xử lý thời gian hiện tại.

        Lớp con nên override phương thức này. Cài đặt mặc định không làm gì.

        Simulator gọi phương thức này thường xuyên để router có thể gửi packet
        định tuyến theo chu kỳ.
        """
        pass

    def __repr__(self):
        """Chuỗi biểu diễn router để debug trong giao diện mô phỏng.

        Lớp con có thể override phương thức này.

        Giao diện mô phỏng gọi `repr` để in thông tin hiện tại của router. Hãy
        trả về chuỗi nào giúp việc debug dễ hơn. Phương thức này chỉ phục vụ tiện
        ích cá nhân và không được chấm điểm.
        """
        return f"Router(addr={self.addr})"
