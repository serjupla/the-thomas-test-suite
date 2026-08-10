import json
import sys
import types

import pytest

from thomas.connectors import ConnectorTechnicalError

CONFIG = {
    "type": "kafka",
    "brokers": ["broker1:9092", "broker2:9092"],
    "username": "user1",
    "password": "secret-pass",
}

REQUEST_TIMESTAMP = "2026-07-28T09:00:00-03:00"
CORRELATION_ID = "corr-1"


class FakeTopicPartition:
    def __init__(self, topic, partition, offset=0):
        self.topic = topic
        self.partition = partition
        self.offset = offset


class FakeMessage:
    def __init__(self, partition, offset, body, timestamp_ms, malformed=False, err=None):
        self._partition = partition
        self._offset = offset
        self._body = body
        self._timestamp_ms = timestamp_ms
        self._malformed = malformed
        self._err = err

    def error(self):
        return self._err

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def value(self):
        if self._malformed:
            return b"not-json{{{"
        return json.dumps(self._body).encode("utf-8")

    def timestamp(self):
        return (1, self._timestamp_ms)


class _TopicMetadata:
    def __init__(self, partitions):
        self.partitions = {p: object() for p in partitions}


class _ClusterMetadata:
    def __init__(self, topic, partitions):
        self.topics = {topic: _TopicMetadata(partitions)}


def _install_fake_confluent_kafka(
    monkeypatch, *, partitions=(0,), messages=None, list_topics_error=None, poll_error_after=None
):
    """Installs a fake confluent_kafka module at the sys.modules boundary.

    `messages` is a list of FakeMessage instances returned in order by
    poll(), then None forever (simulating the timeout window closing).
    `list_topics_error`, if given, is raised by every Consumer.list_topics
    call (used to simulate an unreachable broker).
    `poll_error_after` is a 0-based index: poll() raises RuntimeError("boom")
    once it's been called that many times (used to test finally/close on an
    unexpected mid-loop exception).
    """
    fake_module = types.ModuleType("confluent_kafka")
    queue = list(messages) if messages is not None else []
    created_consumers = []

    class FakeConsumer:
        def __init__(self, config):
            self.config = config
            self.closed = False
            self.assigned = None
            self.subscribe_called = False
            self.offsets_for_times_calls = []
            self.poll_calls = 0
            created_consumers.append(self)

        def list_topics(self, topic=None, timeout=None):
            if list_topics_error is not None:
                raise list_topics_error
            return _ClusterMetadata(topic, partitions)

        def offsets_for_times(self, partitions_list, timeout=None):
            self.offsets_for_times_calls.append(list(partitions_list))
            return [FakeTopicPartition(tp.topic, tp.partition, offset=0) for tp in partitions_list]

        def get_watermark_offsets(self, tp, timeout=None):
            return (0, len(queue))

        def assign(self, partitions_list):
            self.assigned = list(partitions_list)

        def subscribe(self, topics):
            self.subscribe_called = True

        def poll(self, timeout=None):
            self.poll_calls += 1
            if poll_error_after is not None and self.poll_calls > poll_error_after:
                raise RuntimeError("boom")
            if queue:
                return queue.pop(0)
            return None

        def close(self):
            self.closed = True

    fake_module.Consumer = FakeConsumer
    fake_module.TopicPartition = FakeTopicPartition
    monkeypatch.setitem(sys.modules, "confluent_kafka", fake_module)
    return fake_module, created_consumers


def _make_connector(monkeypatch, **fake_kwargs):
    fake_module, created_consumers = _install_fake_confluent_kafka(monkeypatch, **fake_kwargs)
    from thomas.connectors.kafka import KafkaConnector

    connector = KafkaConnector(dict(CONFIG))
    return connector, fake_module, created_consumers


def _validation(**overrides):
    validation = {
        "id": "v1",
        "connector": "kafka_main",
        "topic": "orders",
        "key_filter": "correlationId",
        "field": "status",
        "operator": "equals",
        "expected_value": "SETTLED",
    }
    validation.update(overrides)
    return validation


# --- US1: matching event returns the extracted field ---


def test_resolve_connector_type_returns_kafka_connector_for_kafka_type(monkeypatch):
    _install_fake_confluent_kafka(monkeypatch)
    from thomas.connectors import resolve_connector_type
    from thomas.connectors.kafka import KafkaConnector

    assert resolve_connector_type("kafka") is KafkaConnector


def test_run_validation_returns_matching_field_value(monkeypatch):
    message = FakeMessage(
        partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=1000
    )
    connector, _, _ = _make_connector(monkeypatch, messages=[message])

    result = connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert result == "SETTLED"


def test_run_validation_uses_offset_for_times_not_beginning(monkeypatch):
    message = FakeMessage(
        partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=1000
    )
    connector, _, created_consumers = _make_connector(monkeypatch, messages=[message])

    connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    consumer = created_consumers[-1]
    assert consumer.subscribe_called is False
    assert len(consumer.offsets_for_times_calls) == 1
    from datetime import datetime

    expected_ms = int(datetime.fromisoformat(REQUEST_TIMESTAMP).timestamp() * 1000)
    seek_partitions = consumer.offsets_for_times_calls[0]
    assert all(tp.offset == expected_ms for tp in seek_partitions)
    assert consumer.assigned is not None


def test_run_validation_reads_key_filter_from_json_body_not_kafka_key(monkeypatch):
    non_matching_by_body = FakeMessage(
        partition=0,
        offset=0,
        body={"correlationId": "some-other-id", "status": "PENDING"},
        timestamp_ms=1000,
    )
    matching_by_body = FakeMessage(
        partition=0, offset=1, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=2000
    )
    connector, _, _ = _make_connector(monkeypatch, messages=[non_matching_by_body, matching_by_body])

    result = connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert result == "SETTLED"


# --- US2: bounded timeout / curated errors / no credential leakage ---


def test_run_validation_raises_technical_error_on_timeout_with_no_match(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, messages=[])

    with pytest.raises(ConnectorTechnicalError, match="no matching message found on the topic within the time limit"):
        connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)


def test_connect_raises_technical_error_when_broker_unreachable(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, list_topics_error=Exception("SASL auth failed for secret-pass"))

    with pytest.raises(ConnectorTechnicalError) as exc_info:
        connector.connect()

    assert "secret-pass" not in str(exc_info.value)
    assert "SASL" not in str(exc_info.value)


def test_connect_and_run_validation_never_log_credentials_at_debug_level(monkeypatch, caplog):
    connector, _, _ = _make_connector(monkeypatch, list_topics_error=Exception("boom"))

    with caplog.at_level("DEBUG", logger="thomas.connectors.kafka"), pytest.raises(ConnectorTechnicalError):
        connector.connect()

    assert CONFIG["username"] not in caplog.text
    assert CONFIG["password"] not in caplog.text


def test_run_validation_raises_technical_error_when_request_timestamp_missing_or_unparseable(monkeypatch):
    connector, _, created_consumers = _make_connector(monkeypatch, messages=[])

    with pytest.raises(ConnectorTechnicalError):
        connector.run_validation(_validation(), CORRELATION_ID, "")

    with pytest.raises(ConnectorTechnicalError):
        connector.run_validation(_validation(), CORRELATION_ID, "not-a-timestamp")

    assert created_consumers == []


@pytest.mark.parametrize("missing_field", ["brokers", "username", "password"])
def test_missing_config_fields_raise_technical_error_before_any_connection(monkeypatch, missing_field):
    _install_fake_confluent_kafka(monkeypatch)
    bad_config = dict(CONFIG)
    bad_config[missing_field] = "" if missing_field != "brokers" else []

    from thomas.connectors.kafka import KafkaConnector

    with pytest.raises(ConnectorTechnicalError, match=missing_field):
        KafkaConnector(bad_config)


# --- US3: duplicate resolution by most recent Kafka message timestamp ---


def test_run_validation_selects_most_recent_message_on_duplicate_match(monkeypatch):
    older = FakeMessage(
        partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "PENDING"}, timestamp_ms=1000
    )
    newer = FakeMessage(
        partition=0, offset=1, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=5000
    )
    # queued out of timestamp order to prove selection isn't by consumption order
    connector, _, _ = _make_connector(monkeypatch, messages=[newer, older])

    result = connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert result == "SETTLED"


# --- US4: driver-not-installed guidance (real absence, no mocking) ---


def test_init_raises_technical_error_with_install_guidance_when_driver_not_installed(monkeypatch):
    monkeypatch.delitem(sys.modules, "confluent_kafka", raising=False)

    from thomas.connectors.kafka import KafkaConnector

    with pytest.raises(ConnectorTechnicalError, match=r"^Kafka driver not installed\. Run: pip install thomas\[kafka\]$"):
        KafkaConnector(dict(CONFIG))


# --- US5: never orphan a consumer group ---


def test_run_validation_uses_assign_never_subscribe(monkeypatch):
    message = FakeMessage(
        partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=1000
    )
    connector, _, created_consumers = _make_connector(monkeypatch, messages=[message])

    connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    consumer = created_consumers[-1]
    assert consumer.assigned is not None
    assert consumer.subscribe_called is False


def test_consumer_close_called_on_successful_match(monkeypatch):
    message = FakeMessage(
        partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=1000
    )
    connector, _, created_consumers = _make_connector(monkeypatch, messages=[message])

    connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert created_consumers[-1].closed is True


def test_consumer_close_called_on_timeout(monkeypatch):
    connector, _, created_consumers = _make_connector(monkeypatch, messages=[])

    with pytest.raises(ConnectorTechnicalError):
        connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert created_consumers[-1].closed is True


def test_consumer_close_called_on_unexpected_exception_during_consumption(monkeypatch):
    message = FakeMessage(
        partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=1000
    )
    connector, _, created_consumers = _make_connector(monkeypatch, messages=[message], poll_error_after=0)

    with pytest.raises(RuntimeError, match="boom"):
        connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert created_consumers[-1].closed is True


def test_group_id_is_uuid_derived_and_unique_per_call(monkeypatch):
    def _message():
        return FakeMessage(
            partition=0, offset=0, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=1000
        )

    from thomas.connectors.kafka import KafkaConnector

    _, created_consumers_1 = _install_fake_confluent_kafka(monkeypatch, messages=[_message()])
    connector_1 = KafkaConnector(dict(CONFIG))
    connector_1.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    _, created_consumers_2 = _install_fake_confluent_kafka(monkeypatch, messages=[_message()])
    connector_2 = KafkaConnector(dict(CONFIG))
    connector_2.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    group_id_1 = created_consumers_1[0].config["group.id"]
    group_id_2 = created_consumers_2[0].config["group.id"]
    assert group_id_1 != group_id_2


# --- US6: password rendered masked/revealable, not permanently hidden ---


def test_never_show_fields_is_empty_frozenset():
    from thomas.connectors.kafka import KafkaConnector

    assert KafkaConnector.NEVER_SHOW_FIELDS == frozenset()


# --- Polish: describe_query, edge cases, disconnect ---


def test_describe_query_returns_topic_and_key_filter(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, messages=[])

    description = connector.describe_query(_validation())

    assert description == "topic=orders key_filter=correlationId"


def test_run_validation_skips_message_with_malformed_json_body(monkeypatch):
    malformed = FakeMessage(partition=0, offset=0, body=None, timestamp_ms=1000, malformed=True)
    matching = FakeMessage(
        partition=0, offset=1, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=2000
    )
    connector, _, _ = _make_connector(monkeypatch, messages=[malformed, matching])

    result = connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert result == "SETTLED"


def test_run_validation_treats_missing_key_filter_path_as_non_matching(monkeypatch):
    no_key_filter = FakeMessage(partition=0, offset=0, body={"status": "SETTLED"}, timestamp_ms=1000)
    matching = FakeMessage(
        partition=0, offset=1, body={"correlationId": CORRELATION_ID, "status": "SETTLED"}, timestamp_ms=2000
    )
    connector, _, _ = _make_connector(monkeypatch, messages=[no_key_filter, matching])

    result = connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)

    assert result == "SETTLED"


def test_run_validation_raises_technical_error_when_field_path_missing_on_selected_match(monkeypatch):
    message = FakeMessage(partition=0, offset=0, body={"correlationId": CORRELATION_ID}, timestamp_ms=1000)
    connector, _, _ = _make_connector(monkeypatch, messages=[message])

    with pytest.raises(ConnectorTechnicalError, match="status"):
        connector.run_validation(_validation(), CORRELATION_ID, REQUEST_TIMESTAMP)


def test_disconnect_is_safe_to_call_without_prior_connect(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, messages=[])

    connector.disconnect()
