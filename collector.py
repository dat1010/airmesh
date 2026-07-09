#!/usr/bin/env python3

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import meshtastic.serial_interface
import paho.mqtt.client as mqtt
from pubsub import pub


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def deep_get(d: Dict[str, Any], *keys: str) -> Optional[Any]:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def pick(d: Dict[str, Any], *names: str) -> Optional[Any]:
    for name in names:
        if isinstance(d, dict) and name in d:
            return d[name]
    return None


def extract_air_quality(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    decoded = packet.get("decoded", {})
    telemetry = decoded.get("telemetry", {})

    # Meshtastic Python versions may expose either snake_case or camelCase keys.
    aq = (
        telemetry.get("air_quality_metrics")
        or telemetry.get("airQualityMetrics")
        or telemetry.get("air_quality")
        or telemetry.get("airQuality")
    )

    if not isinstance(aq, dict):
        return None

    pm1_standard = pick(aq, "pm10_standard", "pm10Standard")
    pm25_standard = pick(aq, "pm25_standard", "pm25Standard")
    pm10_standard = pick(aq, "pm100_standard", "pm100Standard")

    pm1_env = pick(aq, "pm10_environmental", "pm10Environmental")
    pm25_env = pick(aq, "pm25_environmental", "pm25Environmental")
    pm10_env = pick(aq, "pm100_environmental", "pm100Environmental")

    # If none of the particulate values exist, it probably is not air quality telemetry.
    if all(v is None for v in [pm1_standard, pm25_standard, pm10_standard, pm1_env, pm25_env, pm10_env]):
        return None

    return {
        "pm1_standard": pm1_standard,
        "pm25_standard": pm25_standard,
        "pm10_standard": pm10_standard,
        "pm1_environmental": pm1_env,
        "pm25_environmental": pm25_env,
        "pm10_environmental": pm10_env,
        "raw_air_quality": aq,
    }


def make_packet_summary(packet: Dict[str, Any]) -> Dict[str, Any]:
    decoded = packet.get("decoded", {})

    return {
        "received_at": utc_now(),
        "from": packet.get("from"),
        "to": packet.get("to"),
        "id": packet.get("id"),
        "rx_snr": packet.get("rxSnr") or packet.get("rx_snr"),
        "rx_rssi": packet.get("rxRssi") or packet.get("rx_rssi"),
        "hop_limit": packet.get("hopLimit") or packet.get("hop_limit"),
        "portnum": decoded.get("portnum"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0", help="Meshtastic serial port")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--topic-prefix", default="meshair")
    parser.add_argument("--aq1", default=None, help="Optional AQ1 node number, e.g. 0x84f3f1a7")
    args = parser.parse_args()

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.connect(args.mqtt_host, args.mqtt_port, 60)
    mqtt_client.loop_start()

    interface_holder = {"interface": None}

    def publish(topic: str, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"), default=str)
        mqtt_client.publish(topic, body)
        print(f"published {topic}: {body}", flush=True)

    def on_receive(packet: Dict[str, Any], interface) -> None:
        summary = make_packet_summary(packet)
        decoded = packet.get("decoded", {})

        # Publish all telemetry raw-ish first, so we can inspect exact packet shape.
        from_node = packet.get("from")

        aq1_matches = True
        if args.aq1:
            aq1_decimal = int(args.aq1, 16) if args.aq1.startswith("0x") else int(args.aq1)
            aq1_matches = from_node == aq1_decimal

        if decoded.get("portnum") == "TELEMETRY_APP" and aq1_matches:
            publish(f"{args.topic_prefix}/raw/telemetry", {
                **summary,
                "packet": packet,
            })
        

        aq = extract_air_quality(packet)
        if aq is None:
            return

        from_node = packet.get("from")
        if args.aq1 and str(from_node).lower() not in {args.aq1.lower(), str(int(args.aq1, 16)) if args.aq1.startswith("0x") else args.aq1}:
            return

        payload = {
            **summary,
            "source": from_node,
            "metrics": aq,
        }

        publish(f"{args.topic_prefix}/airquality/{from_node}", payload)

    def shutdown(signum, frame):
        print("shutting down...", flush=True)
        try:
            if interface_holder["interface"]:
                interface_holder["interface"].close()
        finally:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    pub.subscribe(on_receive, "meshtastic.receive")

    print(f"connecting to Meshtastic device on {args.port}", flush=True)
    interface_holder["interface"] = meshtastic.serial_interface.SerialInterface(args.port)

    print("collector running. waiting for telemetry...", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
