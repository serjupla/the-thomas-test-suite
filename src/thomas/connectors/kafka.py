"""Kafka connector (via confluent-kafka). See docs/architecture/05-connectors.md
and contracts/kafka-connector.md. Requires the optional extra `thomas[kafka]`.

A fresh, ephemeral `Consumer` is created per `run_validation` call, positioned
by offset-by-timestamp seeking via manual `assign()` (never `subscribe()`), so
no consumer group is ever registered with the broker — see research.md R2.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from thomas.connectors import BaseConnector, ConnectorTechnicalError

_logger = logging.getLogger("thomas.connectors.kafka")

_REQUIRED_CONFIG_FIELDS = ("brokers", "username", "password")
_NOT_FOUND = object()


def _extract_path(document: dict, path: str) -> Any:
    """Walks `document` following the dot-path `path`. Returns the sentinel
    `_NOT_FOUND` if any segment is missing or an intermediate value isn't a
    dict — never raises."""
    current: Any = document
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _NOT_FOUND
        current = current[segment]
    return current


class KafkaConnector(BaseConnector):
    NEVER_SHOW_FIELDS = frozenset()

    def __init__(self, config: dict):
        super().__init__(config)
        try:
            import confluent_kafka
        except ModuleNotFoundError as exc:
            raise ConnectorTechnicalError("Kafka driver not installed. Run: pip install thomas[kafka]") from exc

        for field in _REQUIRED_CONFIG_FIELDS:
            if not config.get(field):
                raise ConnectorTechnicalError(f"Kafka connector config is missing required field: {field}")

        self._confluent_kafka = confluent_kafka
        self.timeout_seconds = config.get("timeout_seconds", 30)

    def _bootstrap_servers(self) -> str:
        return ",".join(self.config["brokers"])

    def connect(self) -> None:
        probe = self._confluent_kafka.Consumer(
            {
                "bootstrap.servers": self._bootstrap_servers(),
                "group.id": f"thomas-probe-{uuid.uuid4()}",
                "enable.auto.commit": False,
            }
        )
        try:
            probe.list_topics(timeout=self.timeout_seconds)
        except Exception as exc:
            _logger.debug("Kafka broker-reachability probe failed", exc_info=True)
            raise ConnectorTechnicalError("failed to reach Kafka broker — check brokers/username/password") from exc
        finally:
            probe.close()

    def run_validation(self, validation: dict, correlation_id: str, request_timestamp: str) -> Any:
        """Positions a fresh, per-call consumer by offset-by-timestamp at
        `request_timestamp` and consumes until a message whose `key_filter`
        path matches `correlation_id` is found. If several messages match,
        the one with the highest Kafka message timestamp (Message.timestamp())
        is selected — most recent by Kafka's own timestamp, not consumption
        order (FR-009)."""
        try:
            parsed_timestamp = datetime.fromisoformat(request_timestamp)
        except (TypeError, ValueError) as exc:
            raise ConnectorTechnicalError(
                f"invalid or missing request_timestamp for Kafka validation: {request_timestamp!r}"
            ) from exc
        timestamp_ms = int(parsed_timestamp.timestamp() * 1000)

        topic = validation["topic"]
        confluent_kafka = self._confluent_kafka
        consumer = confluent_kafka.Consumer(
            {
                "bootstrap.servers": self._bootstrap_servers(),
                "group.id": f"thomas-{uuid.uuid4()}",
                "enable.auto.commit": False,
            }
        )
        try:
            metadata = consumer.list_topics(topic, timeout=self.timeout_seconds)
            partitions = list(metadata.topics[topic].partitions.keys())

            seek_partitions = [
                confluent_kafka.TopicPartition(topic, partition_id, timestamp_ms) for partition_id in partitions
            ]
            resolved_partitions = consumer.offsets_for_times(seek_partitions, timeout=self.timeout_seconds)

            end_offsets = {}
            for topic_partition in resolved_partitions:
                _, high_watermark = consumer.get_watermark_offsets(
                    confluent_kafka.TopicPartition(topic, topic_partition.partition), timeout=self.timeout_seconds
                )
                end_offsets[topic_partition.partition] = high_watermark
                if topic_partition.offset < 0:
                    topic_partition.offset = high_watermark

            consumer.assign(resolved_partitions)

            best_match = None
            best_match_timestamp = None
            reached_end = {
                topic_partition.partition: topic_partition.offset >= end_offsets[topic_partition.partition]
                for topic_partition in resolved_partitions
            }

            while not all(reached_end.values()):
                message = consumer.poll(timeout=self.timeout_seconds)
                if message is None:
                    break
                if message.error():
                    continue

                if message.offset() + 1 >= end_offsets.get(message.partition(), message.offset() + 1):
                    reached_end[message.partition()] = True

                try:
                    body = json.loads(message.value())
                except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                    continue

                key_value = _extract_path(body, validation["key_filter"])
                if key_value != correlation_id:
                    continue

                _, message_timestamp = message.timestamp()
                if best_match_timestamp is None or message_timestamp > best_match_timestamp:
                    best_match = body
                    best_match_timestamp = message_timestamp

            if best_match is None:
                raise ConnectorTechnicalError("no matching message found on the topic within the time limit")

            field_value = _extract_path(best_match, validation["field"])
            if field_value is _NOT_FOUND:
                raise ConnectorTechnicalError(
                    f"field path not found in matching Kafka message: {validation['field']}"
                )
            return field_value
        finally:
            consumer.close()

    def describe_query(self, validation: dict) -> str:
        return f"topic={validation['topic']} key_filter={validation['key_filter']}"

    def disconnect(self) -> None:
        pass
