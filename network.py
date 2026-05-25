import argparse
import sys
import threading
import json
import pickle
import signal
import time
import queue
from collections import defaultdict
from client import Client
from link import Link
from router import Router


def json_load_byteified(file_handle):
    return _byteify(json.load(file_handle, object_hook=_byteify), ignore_dicts=True)


def _byteify(data, ignore_dicts=False):
    # Nếu dữ liệu là chuỗi unicode, trả về dạng bytes UTF-8 của chuỗi đó.
    if isinstance(data, str):
        return data.encode("utf-8")
    # Nếu dữ liệu là list, chuyển từng phần tử trong list.
    if isinstance(data, list):
        return [_byteify(item, ignore_dicts=True) for item in data]
    # Nếu dữ liệu là dict, chuyển cả key và value, nhưng chỉ làm khi dict này
    # chưa từng được chuyển ở bước gọi trước đó.
    if isinstance(data, dict) and not ignore_dicts:
        return {
            _byteify(key, ignore_dicts=True): _byteify(value, ignore_dicts=True)
            for key, value in data.items()
        }
    # Các kiểu dữ liệu khác được giữ nguyên.
    return data


class Network:
    """Lớp Network quản lý toàn bộ client, router, link và cấu hình mô phỏng.

    Tham số
    -------
    net_json_path
        Đường dẫn tới file JSON chứa cấu hình mạng.
    RouterClass
        Lớp router sẽ được dùng: DVrouter, LSrouter hoặc router mặc định.
    visualize
        Có bật giao diện trực quan để quan sát mạng hay không.
    """

    def __init__(self, net_json_path, RouterClass, visualize=False):
        # Đọc các thông số cấu hình chung từ file JSON.
        with open(net_json_path, "r") as f:
            net_json = json.load(f)
        self.latency_multiplier = 100
        self.end_time = net_json["end_time"] * self.latency_multiplier
        self.visualize = visualize
        if visualize:
            self.latency_multiplier *= net_json["visualize"]["time_multiplier"]
        self.client_send_rate = net_json["client_send_rate"] * self.latency_multiplier

        # Tạo các router, client và link theo cấu hình.
        self.routers = self.parse_routers(net_json["routers"], RouterClass)
        self.clients = self.parse_clients(net_json["clients"], self.client_send_rate)
        self.links = self.parse_links(net_json["links"])

        # Đọc lịch thay đổi link nếu file cấu hình có khai báo.
        if "changes" in net_json:
            self.changes = self.parse_changes(net_json["changes"])
        else:
            self.changes = None

        # Đọc route đúng để so sánh và chuẩn bị các biến theo dõi route hiện tại.
        self.correct_routes = self.parse_correct_routes(net_json["correct_routes"])
        self.threads = []
        self.routes = {}
        self.routes_lock = threading.Lock()

    def parse_routers(self, router_params, RouterClass):
        """Tạo các router từ dict `router_params` trong file cấu hình."""
        routers = {}
        for addr in router_params:
            routers[addr] = RouterClass(
                addr, heartbeat_time=self.latency_multiplier * 10
            )
        return routers

    def parse_clients(self, client_params, client_send_rate):
        """Tạo các client từ dict `client_params` trong file cấu hình."""
        clients = {}
        for addr in client_params:
            clients[addr] = Client(
                addr, client_params, client_send_rate, self.update_route
            )
        return clients

    def parse_links(self, link_params):
        """Tạo các link từ danh sách `link_params` trong file cấu hình."""
        links = {}
        for addr1, addr2, p1, p2, c12, c21 in link_params:
            link = Link(addr1, addr2, c12, c21, self.latency_multiplier)
            links[(addr1, addr2)] = (p1, p2, c12, c21, link)
        return links

    def parse_changes(self, changes_params):
        """Tạo hàng đợi ưu tiên cho các sự kiện thay đổi link."""
        changes = queue.PriorityQueue()
        for change in changes_params:
            changes.put(change)
        return changes

    def parse_correct_routes(self, routes_params):
        """Đọc danh sách route đúng từ cấu hình để dùng khi kiểm tra kết quả."""
        correct_routes = defaultdict(list)
        for route in routes_params:
            src, dst = route[0], route[-1]
            correct_routes[(src, dst)].append(route)
        return correct_routes

    def run(self):
        """Chạy toàn bộ mô phỏng mạng.

        Hàm tạo thread cho từng router và client, tạo thêm thread xử lý thay đổi
        link nếu có. Nếu không chạy giao diện trực quan, simulator chờ tới thời
        điểm kết thúc rồi in các route cuối cùng.
        """
        for router in self.routers.values():
            thread = RouterThread(router)
            thread.start()
            self.threads.append(thread)
        for client in self.clients.values():
            thread = ClientThread(client)
            thread.start()
            self.threads.append(thread)
        self.add_links()
        if self.changes:
            self.handle_changes_thread = HandleChangesThread(self)
            self.handle_changes_thread.start()

        if not self.visualize:
            signal.signal(signal.SIGINT, self.handle_interrupt)
            time.sleep(self.end_time / 1000)
            self.final_routes()
            sys.stdout.write("\n" + self.get_route_string() + "\n")
            self.join_all()

    def add_links(self):
        """Gắn các link đã tạo vào client và router tương ứng."""
        for addr1, addr2 in self.links:
            p1, p2, c12, c21, link = self.links[(addr1, addr2)]
            if addr1 in self.clients:
                self.clients[addr1].change_link(("add", link))
            if addr2 in self.clients:
                self.clients[addr2].change_link(("add", link))
            if addr1 in self.routers:
                self.routers[addr1].change_link(("add", p1, addr2, link, c12))
            if addr2 in self.routers:
                self.routers[addr2].change_link(("add", p2, addr1, link, c21))

    def handle_changes(self):
        """Xử lý các sự kiện thay đổi link theo thời gian.

        Phương thức này chạy trong thread riêng. Priority queue giúp lấy sự kiện
        có thời điểm xảy ra sớm nhất trước, nhờ vậy simulator có thể thêm/gỡ link
        đúng lịch đã khai báo trong file JSON.
        """
        start_time = time.time() * 1000
        while not self.changes.empty():
            change_time, target, change = self.changes.get()
            current_time = time.time() * 1000
            wait_time = (
                change_time * self.latency_multiplier + start_time
            ) - current_time
            if wait_time > 0:
                time.sleep(wait_time / 1000)

            # Thêm hoặc gỡ link theo loại sự kiện.
            if change == "up":
                addr1, addr2, p1, p2, c12, c21 = target
                link = Link(addr1, addr2, c12, c21, self.latency_multiplier)
                self.links[(addr1, addr2)] = (p1, p2, c12, c21, link)
                self.routers[addr1].change_link(("add", p1, addr2, link, c12))
                self.routers[addr2].change_link(("add", p2, addr1, link, c21))
            elif change == "down":
                addr1, addr2 = target
                p1, p2, _, _, link = self.links[(addr1, addr2)]
                self.routers[addr1].change_link(("remove", p1))
                self.routers[addr2].change_link(("remove", p2))

            # Nếu đang chạy giao diện trực quan, cập nhật hình vẽ của link.
            if hasattr(Network, "visualize_changes_callback"):
                Network.visualize_changes_callback(change, target)

    def update_route(self, src, dst, route):
        """
        Hàm gọi lại để client cập nhật route hiện tại mà packet traceroute đã đi qua.

        Network lưu route mới nhất cho từng cặp nguồn-đích, đồng thời đánh dấu
        route đó có nằm trong danh sách route đúng của cấu hình hay không.
        """
        self.routes_lock.acquire()
        time_ms = int(round(time.time() * 1000))
        is_good = route in self.correct_routes[(src, dst)]
        try:
            _, _, current_time = self.routes[(src, dst)]
            if time_ms > current_time:
                self.routes[(src, dst)] = (route, is_good, time_ms)
        except KeyError:
            self.routes[(src, dst)] = (route, is_good, time_ms)
        finally:
            self.routes_lock.release()

    def get_route_string(self, label_incorrect=True):
        """
        Tạo chuỗi mô tả các route hiện tại tìm được bằng packet traceroute.

        Nếu `label_incorrect` là True, các route sai sẽ được gắn nhãn để dễ nhìn
        khi in ra terminal. Dòng cuối cùng cho biết toàn bộ route đã đúng hay chưa.
        """
        self.routes_lock.acquire()
        route_strings = []
        all_correcct = True
        for src, dst in self.routes:
            route, is_good, _ = self.routes[(src, dst)]
            info = "" if (is_good or not label_incorrect) else "Incorrect Route"
            route_strings.append(f"{src} -> {dst}: {route} {info}")
            if not is_good:
                all_correcct = False
        route_strings.sort()
        if all_correcct and len(self.routes) > 0:
            route_strings.append("\nSUCCESS: All Routes correct!")
        else:
            route_strings.append("\nFAILURE: Not all routes are correct")
        route_string = "\n".join(route_strings)
        self.routes_lock.release()
        return route_string

    def get_route_pickle(self):
        """Tạo dữ liệu pickle chứa các route hiện tại của packet traceroute."""
        self.routes_lock.acquire()
        route_pickle = pickle.dumps(self.routes)
        self.routes_lock.release()
        return route_pickle

    def reset_routes(self):
        """Xóa các route traceroute đang được lưu."""
        self.routes_lock.acquire()
        self.routes = {}
        self.routes_lock.release()

    def final_routes(self):
        """Yêu cầu client gửi một lượt traceroute cuối để lấy kết quả sau cùng."""
        self.reset_routes()
        for client in self.clients.values():
            client.last_send()
        time.sleep(4 * self.client_send_rate / 1000)

    def join_all(self):
        if self.changes:
            self.handle_changes_thread.join()
        for thread in self.threads:
            thread.join()

    def handle_interrupt(self, signum, frame):
        self.join_all()
        print("")
        quit()


def main():
    parser = argparse.ArgumentParser(description="Run a network simulation.")
    parser.add_argument(
        "net_json_path",
        type=str,
        help="Path to the network simulation configuration file (JSON).",
    )
    parser.add_argument(
        "router",
        type=str,
        choices=["DV", "LS"],
        nargs="?",
        default=None,
        help="DV for DVrouter and LS for LSrouter. If not provided, Router is used.",
    )
    args = parser.parse_args()

    RouterClass = Router
    if args.router == "DV":
        from DVrouter import DVrouter

        RouterClass = DVrouter
    elif args.router == "LS":
        from LSrouter import LSrouter

        RouterClass = LSrouter

    net = Network(args.net_json_path, RouterClass, visualize=False)
    net.run()


class RouterThread(threading.Thread):
    def __init__(self, router):
        threading.Thread.__init__(self)
        self.router = router

    def run(self):
        self.router.run()

    def join(self, timeout=None):
        # Cách dừng thread này không đẹp, nhưng đủ dùng cho simulator nhỏ này.
        self.router.keep_running = False
        super(RouterThread, self).join(timeout)


class ClientThread(threading.Thread):

    def __init__(self, client):
        threading.Thread.__init__(self)
        self.client = client

    def run(self):
        self.client.run()

    def join(self, timeout=None):
        # Cách dừng thread này không đẹp, nhưng đủ dùng cho simulator nhỏ này.
        self.client.keep_running = False
        super(ClientThread, self).join(timeout)


class HandleChangesThread(threading.Thread):

    def __init__(self, network):
        threading.Thread.__init__(self)
        self.network = network

    def run(self):
        self.network.handle_changes()


if __name__ == "__main__":
    main()
