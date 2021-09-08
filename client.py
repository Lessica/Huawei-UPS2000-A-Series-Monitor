#!/usr/bin/env python3
import logging
import subprocess
import time

import coloredlogs
import requests

service_host = "127.0.0.1"
service_port = 8087
service_socket = f"{service_host}:{service_port}"
check_interval = 300


def check_resp(resp):
    if resp.status_code != 200:
        err = resp.json()
        raise AssertionError(f"{err['code']} {err['name']}: {err['description']}")


if __name__ == '__main__':
    coloredlogs.install()

    current_interval = check_interval
    service_url = f"http://{service_socket}"
    logging.warning(f"Begin capturing UPS status from {service_url}...")

    service_info_url = f"{service_url}/info"
    info_resp = requests.get(service_info_url)
    check_resp(info_resp)
    info_obj = info_resp.json()
    logging.info(info_obj)

    service_state_url = f"{service_url}/state"
    service_battery_state_url = f"{service_url}/battery_state"
    while True:
        service_state_resp = requests.get(service_state_url)
        check_resp(service_state_resp)
        service_state_obj = service_state_resp.json()
        logging.info(service_state_obj)
        if service_state_obj['mode'] == 2:
            # normal state
            current_interval = check_interval
            logging.warning(f"Power supply is normal, wait {current_interval} seconds for next trial...")
            time.sleep(current_interval)
            continue

        # special state
        logging.warning(f"Possible power failure detected, confirm battery state...")
        service_battery_state_resp = requests.get(service_battery_state_url)
        check_resp(service_battery_state_resp)
        service_battery_state_obj = service_battery_state_resp.json()
        logging.info(service_battery_state_obj)

        battery_level = float(service_battery_state_obj['battery_left'])
        battery_seconds_left = int(service_battery_state_obj['estimated_time_left'])
        if battery_level < 0.2 or battery_seconds_left < 600:
            # battery drain
            logging.error("Battery drained, system will power off NOW!")

            # shutdown command for macOS
            subprocess.call(['osascript', '-e',
                             'tell app "System Events" to shut down'])

            # another unsafe method
            # osascript -e 'do shell script "shutdown -h now" user name "rachel" password "" with administrator
            # privileges'

            break

        current_interval = 30
        logging.warning(f"Power supply is now battery, wait {current_interval} seconds for next trial...")
        time.sleep(current_interval)
