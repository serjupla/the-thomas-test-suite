"""JSON encoding for the execution record. See docs/architecture/03-data-schemas.md §4."""

from __future__ import annotations

import datetime
import json


class ExecutionRecordEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super().default(obj)
