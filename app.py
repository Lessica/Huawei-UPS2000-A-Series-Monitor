import socket

import numpy
from flask import Flask, jsonify

app = Flask(__name__)
addr = "xtzn-raspi.local"  # noqa
host = socket.gethostbyname(addr)
port = 51410


def crc16(data: bytes):
    """
    CRC-16-ModBus Algorithm
    """
    data = bytearray(data)
    poly = 0xA001
    crc = 0xFFFF
    for b in data:
        crc ^= (0xFF & b)
        for _ in range(0, 8):
            if crc & 0x0001:
                crc = ((crc >> 1) & 0xFFFF) ^ poly
            else:
                crc = ((crc >> 1) & 0xFFFF)

    return numpy.uint16(crc)


def recv_and_wait(sock, count) -> bytes:
    data = bytes()
    while len(data) < count:
        part = sock.recv(count)
        assert len(part) > 0, "Connection closed"
        data += part
    return data


def read_device_info() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 查询设备列表命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x2B,  # Type: read info
            0x0E,  # Fixed MEI type
            0x03,  # ReadDevID: 请求获得扩展设备识别码(流访问)
            0x87,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 7, "Request not sent"

        all_bytes = bytearray()

        reply = recv_and_wait(sock, 8)
        all_bytes += reply

        # 查询设备列表命令响应帧格式
        assert reply[:5] == bytearray((0x01, 0x2B, 0x0E, 0x03, 0x03)), "Invalid response"
        object_left = reply[-1]

        device_count = 0
        device_arr = []
        while True:
            if object_left == 0:
                break

            reply = recv_and_wait(sock, 2)
            all_bytes += reply

            object_id = reply[0]
            object_len = reply[1]
            reply = recv_and_wait(sock, object_len)
            all_bytes += reply

            if object_id == 0x87:
                device_count = short_of_bytes(reply)
            else:
                device_str = reply.decode()
                device_dict = {}
                for n in device_str.split(";"):
                    m = n.split("=")
                    device_dict[m[0]] = m[1]
                device_dict["model"] = device_dict.pop("1")
                device_dict["version"] = device_dict.pop("2")
                device_dict["protocol"] = device_dict.pop("3")
                device_dict["esn"] = device_dict.pop("4")
                device_dict["id"] = device_dict.pop("5")
                device_dict["group"] = device_dict.pop("6")
                device_arr.append(device_dict)
            object_left -= 1

        ret["count"] = device_count
        ret["devices"] = device_arr

        reply = recv_and_wait(sock, 2)
        assert reply == crc16(all_bytes).tobytes(), "Invalid checksum"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


def short_of_bytes(buffer: bytes) -> int:
    return int.from_bytes(buffer[:2], byteorder='big', signed=False)


def int_of_bytes(buffer: bytes) -> int:
    return int.from_bytes(buffer[:4], byteorder='big', signed=False)


def bit_of_int_bytes(buffer: bytes, offset: int = 0, base: int = 0, pos: int = 0) -> int:
    return (int.from_bytes(
        buffer[(offset - base) * 2:4], byteorder='big', signed=False
    ) >> (31 - pos)) & 1


def power_on() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 写命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x06,  # Type: read register
            0x2B,  # Fixed begin address
            0x15,
            0x00,  # Data: power on
            0x01,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 8, "Request not sent"

        # 写命令响应帧格式与请求帧格式相同
        reply = recv_and_wait(sock, 8)
        assert reply[:8] == preamble, "Invalid response"

        ret["code"] = 0
        ret["msg"] = "ok"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


def power_off() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 写命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x06,  # Type: read register
            0x2B,  # Fixed begin address
            0x16,
            0x00,  # Data: power off
            0x01,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 8, "Request not sent"

        # 写命令响应帧格式与请求帧格式相同
        reply = recv_and_wait(sock, 8)
        assert reply[:8] == preamble, "Invalid response"

        ret["code"] = 0
        ret["msg"] = "ok"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


def power_state() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 读命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x03,  # Type: read register
            0x2B,  # Fixed begin address
            0x14,
            0x00,  # Fixed register count
            0x01,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 8, "Request not sent"

        all_bytes = bytearray()

        reply = recv_and_wait(sock, 3)
        all_bytes += reply

        # 读命令响应帧格式
        assert reply[:3] == bytearray((0x01, 0x03, 0x02)), "Invalid response"
        data_len = reply[-1]

        reply = recv_and_wait(sock, data_len)
        all_bytes += reply

        reply_state = int.from_bytes(reply[:2], byteorder='big', signed=False)
        if reply_state == 3:
            ret["msg"] = "launched"
        elif reply_state == 2:
            ret["msg"] = "launch failed"
        elif reply_state == 1:
            ret["msg"] = "wait for launch"
        elif reply_state == 0:
            ret["msg"] = "ready"
        else:
            ret["msg"] = "unknown"
        ret["code"] = reply_state

        reply = recv_and_wait(sock, 2)
        assert reply == crc16(all_bytes).tobytes(), "Invalid checksum"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


def read_registers() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 读命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x03,  # Type: read register
            0x2A,  # Fixed begin address
            0xF8,
            0x00,  # Fixed register count
            0x2B,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 8, "Request not sent"

        all_bytes = bytearray()

        reply = recv_and_wait(sock, 3)
        all_bytes += reply

        # 读命令响应帧格式
        assert reply[:3] == bytearray((0x01, 0x03, 0x2B * 2)), "Invalid response"
        data_len = reply[-1]

        reply = recv_and_wait(sock, data_len)
        all_bytes += reply

        ret["input_voltage"] = short_of_bytes(reply[0:2]) / 10.0
        ret["input_freq"] = short_of_bytes(reply[6:8]) / 10.0
        ret["bypass_voltage"] = short_of_bytes(reply[8:10]) / 10.0
        ret["bypass_freq"] = short_of_bytes(reply[14:16]) / 10.0
        ret["output_voltage"] = short_of_bytes(reply[16:18]) / 10.0
        ret["output_current"] = short_of_bytes(reply[22:24]) / 10.0
        ret["output_freq"] = short_of_bytes(reply[28:30]) / 10.0
        ret["output_active_power"] = short_of_bytes(reply[30:32]) / 10.0
        ret["output_apparent_power"] = short_of_bytes(reply[36:38]) / 10.0
        ret["load"] = short_of_bytes(reply[42:44]) / 1000.0
        ret["mode"] = short_of_bytes(reply[48:50])
        ret["input_mode"] = short_of_bytes(reply[50:52])
        ret["output_mode"] = short_of_bytes(reply[52:54])
        ret["temp"] = short_of_bytes(reply[54:56]) / 10.0

        ret["battery_test"] = bit_of_int_bytes(reply[86:88], pos=2)
        ret["ups_type"] = bit_of_int_bytes(reply[86:88], pos=3)
        ret["ups_failure"] = bit_of_int_bytes(reply[86:88], pos=4)
        ret["battery_drain"] = bit_of_int_bytes(reply[86:88], pos=6)
        ret["main_supply_abnormal"] = bit_of_int_bytes(reply[86:88], pos=7)

        reply = recv_and_wait(sock, 2)
        assert reply == crc16(all_bytes).tobytes(), "Invalid checksum"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


def read_battery() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 读命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x03,  # Type: read register
            0x2E,  # Fixed begin address
            0xE0,
            0x00,  # Fixed register count
            0x21,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 8, "Request not sent"

        all_bytes = bytearray()

        reply = recv_and_wait(sock, 3)
        all_bytes += reply

        # 读命令响应帧格式
        assert reply[:3] == bytearray((0x01, 0x03, 0x21 * 2)), "Invalid response"
        data_len = reply[-1]

        reply = recv_and_wait(sock, data_len)
        all_bytes += reply

        ret["battery_voltage"] = short_of_bytes(reply[0:2]) / 10.0
        ret["battery_state"] = short_of_bytes(reply[4:6])
        ret["battery_left"] = short_of_bytes(reply[6:8]) / 100.0
        ret["estimated_time_left"] = int_of_bytes(reply[8:12])
        ret["battery_count"] = short_of_bytes(reply[14:16])
        ret["battery_capacity"] = short_of_bytes(reply[66:68])

        reply = recv_and_wait(sock, 2)
        assert reply == crc16(all_bytes).tobytes(), "Invalid checksum"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


def read_warnings() -> dict:
    ret = {}
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.settimeout(2)

    try:
        # 读命令请求帧格式
        preamble = bytearray((
            0x01,  # Fixed idx
            0x03,  # Type: read register
            0xA0,  # Fixed begin address (41180)
            0xDC,
            0x00,  # Fixed register count
            0x1A,
        ))

        preamble += crc16(preamble).tobytes()
        assert sock.send(preamble) == 8, "Request not sent"

        all_bytes = bytearray()

        reply = recv_and_wait(sock, 3)
        all_bytes += reply

        # 读命令响应帧格式
        assert reply[:3] == bytearray((0x01, 0x03, 0x1A * 2)), "Invalid response"
        data_len = reply[-1]

        reply = recv_and_wait(sock, data_len)
        all_bytes += reply

        all_warnings = {
            "0030,1": bit_of_int_bytes(reply, 40156, base=40156, pos=3),
            "0010,1": bit_of_int_bytes(reply, 40161, base=40156, pos=1),
            "0010,2": bit_of_int_bytes(reply, 40161, base=40156, pos=2),
            "0025,1": bit_of_int_bytes(reply, 40163, base=40156, pos=3),
            "0029,1": bit_of_int_bytes(reply, 40164, base=40156, pos=1),
            "0026,1": bit_of_int_bytes(reply, 40164, base=40156, pos=3),
            "0022,1": bit_of_int_bytes(reply, 40170, base=40156, pos=4),
            "0066,1": bit_of_int_bytes(reply, 40173, base=40156, pos=5),
            "0014,1": bit_of_int_bytes(reply, 40174, base=40156, pos=0),
            "0066,2": bit_of_int_bytes(reply, 40174, base=40156, pos=3),
            "0042,15": bit_of_int_bytes(reply, 40179, base=40156, pos=14),
            "0042,17": bit_of_int_bytes(reply, 40179, base=40156, pos=15),
            "0042,18": bit_of_int_bytes(reply, 40180, base=40156, pos=1),
            "0042,24": bit_of_int_bytes(reply, 40180, base=40156, pos=5),
            "0042,27": bit_of_int_bytes(reply, 40180, base=40156, pos=6),
            "0042,28": bit_of_int_bytes(reply, 40180, base=40156, pos=7),
            "0042,31": bit_of_int_bytes(reply, 40180, base=40156, pos=10),
            "0042,32": bit_of_int_bytes(reply, 40180, base=40156, pos=11),
            "0042,36": bit_of_int_bytes(reply, 40180, base=40156, pos=13),
            "0042,42": bit_of_int_bytes(reply, 40182, base=40156, pos=4),
            "0066,3": bit_of_int_bytes(reply, 40182, base=40156, pos=13),
            "0066,4": bit_of_int_bytes(reply, 40182, base=40156, pos=14),
        }

        error_dicts = []
        for warning in all_warnings:
            if all_warnings[warning] > 0:
                warning_arr = warning.split(",")
                error_dicts.append({
                    "warning_id": warning_arr[0],
                    "reason_id": int(warning_arr[1]),
                })
        ret["warnings"] = error_dicts

        reply = recv_and_wait(sock, 2)
        assert reply == crc16(all_bytes).tobytes(), "Invalid checksum"

    except AssertionError as e:
        ret.clear()
        ret["error"] = str(e)

    sock.close()
    return ret


@app.route('/info')
def info():
    return jsonify(read_device_info())


@app.route('/power')
def power():
    return jsonify(power_state())


@app.route('/poweron', methods=["POST"])
def poweron():
    return jsonify(power_on())


@app.route('/poweroff', methods=["POST"])
def poweroff():
    return jsonify(power_off())


@app.route('/state')
def state():
    return jsonify(read_registers())


@app.route('/battery_state')
def battery_state():
    return jsonify(read_battery())


@app.route('/warnings')
def warnings():
    return jsonify(read_warnings())


if __name__ == '__main__':
    app.run()
