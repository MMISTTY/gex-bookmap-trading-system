"""Normalized JSONL/CSV event adapters. Native Bookmap .bmf decoding is not claimed."""

import csv
import io
import json
from pathlib import Path
from collections.abc import Iterator
from gexbook.models import Event


def read_events(text: str, file_format="jsonl") -> list[Event]:
    rows = (
        csv.DictReader(io.StringIO(text))
        if file_format == "csv"
        else (json.loads(line) for line in text.splitlines() if line.strip())
    )
    events = []
    try:
        for row in rows:
            d = dict(row)
            raw_seq = d["seq"]
            if isinstance(raw_seq, str):
                if not raw_seq.isdecimal():
                    raise ValueError("seq must be a nonnegative integer")
                d["seq"] = int(raw_seq)
            elif type(raw_seq) is not int:
                raise ValueError("seq must be an integer without coercion")
            for f in ("price", "size"):
                d[f] = float(d.get(f) or 0)
            events.append(Event(**d))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid normalized event near row {len(events) + 1}: {exc}") from exc
    if not events:
        raise ValueError("No events in file")
    return events


class FileTail:
    """Incremental local capture reader; partial final lines are retained, never decoded early."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.offset = 0
        self.buffer = ""
        self.inode = None

    def poll(self) -> Iterator[Event]:
        stat = self.path.stat()
        if self.inode is not None and (stat.st_ino != self.inode or stat.st_size < self.offset):
            raise ValueError("Capture rotated/truncated: restart reader and require reset event")
        self.inode = stat.st_ino
        with self.path.open() as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        data = self.buffer + chunk
        lines = data.split("\n")
        self.buffer = lines.pop()
        for line in lines:
            if line.strip():
                yield Event(**json.loads(line))
