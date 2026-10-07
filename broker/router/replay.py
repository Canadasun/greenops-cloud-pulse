"""Replay a downloaded dead-letter JSONL file through the authenticated ingestion API.

Usage: INGESTION_TOKEN=... python replay.py file.jsonl http://localhost:7071/api/telemetry
The source file is retained. Replaying it repeatedly is safe for monotonic alert processing.
"""
import json
import os
import sys
from pathlib import Path
from router import HttpAlertEndpoint

if __name__ == '__main__':
    readings = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
    endpoint = HttpAlertEndpoint(sys.argv[2], os.environ['INGESTION_TOKEN'])
    for offset in range(0, len(readings), 50):
        endpoint(readings[offset:offset + 50])
    print(f'Replayed {len(readings)} readings; source retained')
