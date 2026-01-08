"""Quick script to add a table from snapshot file, avoiding path conversion issues."""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from extraction_models import add_table_from_snapshot

if len(sys.argv) < 3:
    print("Usage: python add_table.py <snapshot_file> <table_name>")
    sys.exit(1)

snapshot_file = sys.argv[1]
table_name = sys.argv[2]

with open(snapshot_file, 'r', encoding='utf-8') as f:
    snapshot = f.read()

result = add_table_from_snapshot(snapshot, table_name)
print(result)
