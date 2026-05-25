import _thread
import sys
import queue
import time


class Link:
    """
    Lớp Link đại diện cho một đường nối giữa hai router/client.

    Link dùng hai hàng đợi an toàn với thread để mô phỏng việc gửi và nhận
    packet theo hai chiều. Khi gửi packet, link sẽ chờ đúng độ trễ của chiều đó
    rồi mới đưa packet vào hàng đợi nhận ở đầu còn lại.

    Tham số
    -------
    e1, e2
        Địa chỉ của hai đầu kết nối.
    l12, l21
        Độ trễ tính bằng mili-giây cho hai chiều e1->e2 và e2->e1.
    """

    def __init__(self, e1, e2, l12, l21, latency):
        self.q12 = queue.Queue()
        self.q21 = queue.Queue()
        self.l12 = l12 * latency
        self.l21 = l21 * latency
        self.latency_multiplier = latency
        self.e1 = e1
        self.e2 = e2

    def _send_helper(self, packet, src):
        """
        Chạy trong thread riêng để gửi packet từ `src`.

        Hàm này thêm node đích vào đường đi của packet, kích hoạt animation nếu
        đang chạy giao diện, chờ theo độ trễ của link rồi đưa packet vào hàng đợi
        nhận của đầu bên kia.
        """
        if src == self.e1:
            packet.add_to_route(self.e2)
            packet.animate_send(self.e1, self.e2, self.l12)
            time.sleep(self.l12 / 1000)
            self.q12.put(packet)
        elif src == self.e2:
            packet.add_to_route(self.e1)
            packet.animate_send(self.e2, self.e1, self.l21)
            time.sleep(self.l21 / 1000)
            self.q21.put(packet)
        sys.stdout.flush()

    def send(self, packet, src):
        """
        Gửi packet trên link từ đầu `src`.

        Nội dung packet, nếu có, bắt buộc phải là chuỗi. Hàm tạo một bản sao của
        packet rồi mở thread mới để mô phỏng quá trình truyền có độ trễ. `src`
        phải là một trong hai đầu của link: `self.e1` hoặc `self.e2`.
        """
        if packet.content:
            assert isinstance(packet.content, str), "Packet content must be a string"
        p = packet.copy()
        _thread.start_new_thread(self._send_helper, (p, src))

    def recv(self, dst, timeout=None):
        """
        Kiểm tra xem đã có packet tới đầu `dst` của link hay chưa.

        `dst` phải là `self.e1` hoặc `self.e2`. Nếu hàng đợi tương ứng đã có
        packet thì trả về packet đó; nếu chưa có packet sẵn sàng thì trả về
        `None` để vòng lặp mô phỏng tiếp tục chạy.
        """
        if dst == self.e1:
            try:
                packet = self.q21.get_nowait()
                return packet
            except queue.Empty:
                return None
        elif dst == self.e2:
            try:
                packet = self.q12.get_nowait()
                return packet
            except queue.Empty:
                return None

    def change_latency(self, src, c):
        """
        Cập nhật độ trễ của chiều gửi bắt đầu từ `src`.
        """
        if src == self.e1:
            self.l12 = c * self.latency_multiplier
        elif src == self.e2:
            self.l21 = c * self.latency_multiplier
