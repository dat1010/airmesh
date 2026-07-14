#!/usr/bin/env python3

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

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


def parse_node_id(value: str) -> int:
    if value.startswith("!"):
        return int(value[1:], 16)
    return int(value, 16) if value.lower().startswith("0x") else int(value)


def packet_node_id(packet: Dict[str, Any]) -> Optional[int]:
    value = packet.get("from")
    return value if isinstance(value, int) else None


def node_allowed(node_id: Optional[int], allowed_nodes: Set[int]) -> bool:
    return node_id is not None and (not allowed_nodes or node_id in allowed_nodes)


def telemetry_kind(metrics: Dict[str, Any]) -> str:
    if any(metrics.get(key) is not None for key in ("pm1_standard", "pm25_standard", "pm10_standard")):
        return "air"
    if any(metrics.get(key) is not None for key in ("temperature_c", "relative_humidity", "barometric_pressure")):
        return "environment"
    if any(metrics.get(key) is not None for key in ("battery_level", "voltage", "uptime_seconds")):
        return "device"
    return "telemetry"


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


def extract_environment(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    decoded = packet.get("decoded", {})
    telemetry = decoded.get("telemetry", {})

    env = (
        telemetry.get("environment_metrics")
        or telemetry.get("environmentMetrics")
        or telemetry.get("environment")
    )

    if not isinstance(env, dict):
        return None

    metrics = {
        "temperature_c": pick(env, "temperature", "temperature_c", "temperatureC"),
        "relative_humidity": pick(env, "relative_humidity", "relativeHumidity", "humidity"),
        "barometric_pressure": pick(env, "barometric_pressure", "barometricPressure", "pressure"),
        "gas_resistance": pick(env, "gas_resistance", "gasResistance"),
        "voltage": pick(env, "voltage"),
        "current": pick(env, "current"),
        "raw_environment": env,
    }

    if all(value is None for key, value in metrics.items() if key != "raw_environment"):
        return None

    return metrics


def extract_device(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    decoded = packet.get("decoded", {})
    telemetry = decoded.get("telemetry", {})

    device = (
        telemetry.get("device_metrics")
        or telemetry.get("deviceMetrics")
        or telemetry.get("device")
    )

    if not isinstance(device, dict):
        return None

    metrics = {
        "battery_level": pick(device, "battery_level", "batteryLevel"),
        "voltage": pick(device, "voltage"),
        "channel_utilization": pick(device, "channel_utilization", "channelUtilization"),
        "air_util_tx": pick(device, "air_util_tx", "airUtilTx"),
        "uptime_seconds": pick(device, "uptime_seconds", "uptimeSeconds"),
        "raw_device": device,
    }

    if all(value is None for key, value in metrics.items() if key != "raw_device"):
        return None

    return metrics


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
    parser.add_argument(
        "--publish-legacy-airquality",
        action="store_true",
        help="Also publish old meshair/airquality/<node> topics.",
    )
    parser.add_argument(
        "--node",
        action="append",
        default=[],
        help="Optional node id allowlist. Repeat for multiple nodes, e.g. --node 0x84f3f1a7",
    )
    parser.add_argument("--aq1", default=None, help="Deprecated alias for --node")
    args = parser.parse_args()
    allowed_nodes = {parse_node_id(node) for node in args.node}
    if args.aq1:
        allowed_nodes.add(parse_node_id(args.aq1))

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

        from_node = packet_node_id(packet)
        if not node_allowed(from_node, allowed_nodes):
            return

        if decoded.get("portnum") == "TELEMETRY_APP":
            publish(f"{args.topic_prefix}/raw/telemetry", {
                **summary,
                "packet": packet,
            })

        aq = extract_air_quality(packet)
        env = extract_environment(packet)
        device = extract_device(packet)
        if aq is None and env is None and device is None:
            return

        metrics = {
            **(aq or {}),
            **(env or {}),
            **(device or {}),
        }

        payload = {
            **summary,
            "source": from_node,
            "source_node_id": packet.get("fromId"),
            "kind": telemetry_kind(metrics),
            "metrics": metrics,
        }

        publish(f"{args.topic_prefix}/nodes/{from_node}/telemetry", payload)
        if args.publish_legacy_airquality:
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
