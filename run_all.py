#!/usr/bin/env python3
import argparse
import signal
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Meshtastic collector and persistence writer together."
    )
    parser.add_argument("--port", default="/dev/ttyACM0", help="Meshtastic serial port")
    parser.add_argument("--aq1", default="0x84f3f1a7", help="AQ1 node id")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--topic-prefix", default="meshair")
    parser.add_argument("--jsonl", default="data/airquality.jsonl")
    parser.add_argument("--db", default="data/meshair.db")
    parser.add_argument("--web", action="store_true", help="Start the local web UI too")
    parser.add_argument("--web-host", default="0.0.0.0")
    parser.add_argument("--web-port", type=int, default=8055)
    return parser.parse_args()


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    args = parse_args()
    python = sys.executable

    collector_cmd = [
        python,
        "collector.py",
        "--port",
        args.port,
        "--aq1",
        args.aq1,
        "--mqtt-host",
        args.mqtt_host,
        "--mqtt-port",
        str(args.mqtt_port),
        "--topic-prefix",
        args.topic_prefix,
    ]
    writer_cmd = [
        python,
        "writer.py",
        "--mqtt-host",
        args.mqtt_host,
        "--mqtt-port",
        str(args.mqtt_port),
        "--topic",
        f"{args.topic_prefix}/airquality/+",
        "--jsonl",
        args.jsonl,
        "--db",
        args.db,
    ]
    web_cmd = [
        python,
        "web.py",
        "--host",
        args.web_host,
        "--port",
        str(args.web_port),
        "--db",
        args.db,
    ]

    processes: list[subprocess.Popen] = []

    def shutdown(signum, frame):
        for process in reversed(processes):
            stop_process(process)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("starting writer", flush=True)
    processes.append(subprocess.Popen(writer_cmd))

    print("starting collector", flush=True)
    processes.append(subprocess.Popen(collector_cmd))

    if args.web:
        print("starting web UI", flush=True)
        processes.append(subprocess.Popen(web_cmd))

    while True:
        for process in processes:
            return_code = process.poll()
            if return_code is not None:
                for other in processes:
                    if other is not process:
                        stop_process(other)
                return return_code

        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
