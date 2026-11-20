"""Qualify a Kafka runtime using an isolated Compose project and synthetic data.

No host ports, deployment credentials, existing containers or volumes are used.
Requires Docker Compose; the candidate image must already exist locally.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args, input=None, check=True, timeout=180, env=None):
    result = subprocess.run(args, input=input, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout,
                            cwd=ROOT, env=env)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args!r}\n"
                           f"{result.stdout}\n{result.stderr}")
    return result


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def qualify(image, expected_kafka="4.3.1"):
    project = "nanosamurai-kafka-test-" + uuid.uuid4().hex[:12]
    environment = dict(os.environ)
    for key in ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES",
                "KAFKA_IMAGE", "KAFKA_JAVA_TOOL_OPTIONS"):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix=project) as tmp:
        folder = Path(tmp)
        empty_env = folder / "empty.env"
        empty_env.write_text("", encoding="utf-8")
        source = json.loads(run("docker", "compose", "--env-file", str(empty_env),
            "-f", str(ROOT / "docker-compose.yml"), "config", "--format", "json",
            env=environment).stdout)
        broker_env = dict(source["services"]["broker"]["environment"])
        broker_env.update({
            "KAFKA_LISTENERS": "INTERNAL://0.0.0.0:29092,CONTROLLER://0.0.0.0:9093",
            "KAFKA_ADVERTISED_LISTENERS": "INTERNAL://broker:29092",
            "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT",
            "KAFKA_LOG_DIRS": "/var/lib/kafka/data",
            "KAFKA_HEAP_OPTS": "-Xms256m -Xmx512m",
            # Actual server-start flags are captured, not inferred from a second JVM.
            "KAFKA_JVM_PERFORMANCE_OPTS": "-XX:+PrintFlagsFinal",
            "JAVA_TOOL_OPTIONS": "-Dkafka.runtime.option.preserved=true",
        })
        model = {
            "services": {
                "broker": {"image": image, "environment": broker_env,
                           "volumes": ["data:/var/lib/kafka/data"],
                           "mem_limit": "2g", "cpus": 2, "pids_limit": 256,
                           "cap_drop": ["ALL"],
                           "security_opt": ["no-new-privileges:true"]},
                "kafka_init": {"image": image,
                    "command": source["services"]["kafka_init"]["command"],
                    "environment": {"KAFKA_HEAP_OPTS": "-Xms64m -Xmx256m"},
                    "mem_limit": "768m", "cpus": 1, "pids_limit": 128,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"]},
            },
            "volumes": {"data": {}},
            "networks": {"default": {"internal": True}},
        }
        config = folder / "compose.json"
        config.write_text(json.dumps(model), encoding="utf-8")
        base = ("docker", "compose", "--project-name", project,
                "--env-file", str(empty_env), "--file", str(config))

        def compose(*args, **kwargs):
            return run(*base, *args, env=environment, **kwargs)

        def cli(tool, *args, **kwargs):
            return compose("exec", "-T", "broker", "/opt/kafka/bin/" + tool,
                           "--bootstrap-server", "broker:29092", *args, **kwargs)

        def wait_ready():
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                result = cli("kafka-topics.sh", "--list", check=False, timeout=30)
                if result.returncode == 0:
                    return
                time.sleep(2)
            raise AssertionError("Disposable Kafka failed to become ready")

        try:
            compose("up", "-d", "--no-build", "--pull", "never", "broker")
            wait_ready()
            version = compose("exec", "-T", "broker", "java", "-version").stderr
            require("21.0.13.1+2-LTS" in version, "Unexpected JVM build")
            require(expected_kafka in cli("kafka-topics.sh", "--version").stdout,
                    "Kafka application version changed")
            logs = compose("logs", "--no-color", "broker").stdout
            require(re.search(r"UseBASE64Intrinsics\s*=\s*false", logs),
                    "Broker startup did not report disabled Base64 intrinsics")
            command = compose("exec", "-T", "broker", "cat", "/proc/1/cmdline").stdout
            require("kafka.Kafka" in command and "PrintFlagsFinal" in command,
                    "Flags were not requested on the running broker JVM")
            require("kafka.runtime.option.preserved=true" in logs,
                    "The runtime entrypoint discarded caller JVM options")
            certs = compose("exec", "-T", "broker", "keytool", "-list", "-v",
                            "-cacerts", "-storepass", "changeit").stdout
            require(not re.search(r"Owner: CN=(emSign (ECC Root CA - G3|Root CA - G[12])|AAA Certificate Services),", certs),
                    "Disallowed root remains in Java cacerts")
            require("ISRG Root X1" in certs, "Public CA truststore is missing")
            uid = compose("exec", "-T", "broker", "id", "-u").stdout.strip()
            require(uid != "0", "Broker must run non-root")

            compose("run", "--rm", "--no-deps", "kafka_init", timeout=600)
            cli("kafka-topics.sh", "--create", "--topic", "runtime-check", "--partitions", "2",
                "--replication-factor", "1", "--config", "retention.ms=86400000")
            cli("kafka-configs.sh", "--entity-type", "topics", "--entity-name", "sessions.meta",
                "--alter", "--add-config", "min.insync.replicas=1")
            cli("kafka-console-producer.sh", "--topic", "runtime-check",
                "--producer-property", "acks=all", input="before-restart\n")
            before = cli("kafka-topics.sh", "--describe").stdout
            compose("run", "--rm", "--no-deps", "kafka_init", timeout=600)
            require(sorted(before.splitlines()) == sorted(cli("kafka-topics.sh", "--describe").stdout.splitlines()),
                    "Repeated initialization changed topic identity/configuration")
            compose("stop", "--timeout", "30", "broker")
            compose("up", "-d", "--force-recreate", "--no-build", "--pull", "never", "broker")
            wait_ready()
            require(sorted(before.splitlines()) == sorted(cli("kafka-topics.sh", "--describe").stdout.splitlines()),
                    "Broker replacement changed existing topics")
            cli("kafka-console-producer.sh", "--topic", "runtime-check",
                "--producer-property", "acks=all", input="after-restart\n")
            messages = cli("kafka-console-consumer.sh", "--topic", "runtime-check", "--from-beginning",
                "--max-messages", "2", "--timeout-ms", "30000").stdout.splitlines()
            require(sorted(messages) == ["after-restart", "before-restart"],
                    "Produce/consume or data preservation failed")
            print("Kafka runtime PASS: fixed JRE, effective mitigation, CA policy, non-root, "
                  "topic-init rerun, broker replacement and persisted produce/consume")
        finally:
            # Only this generated project and its synthetic volume are removed.
            compose("down", "--volumes", "--remove-orphans", "--timeout", "30")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--kafka-version", default="4.3.1")
    args = parser.parse_args()
    qualify(args.image, args.kafka_version)
