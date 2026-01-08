"""Process a snapshot file and add table to database.
Called with: python process_snapshot.py <table_name>
Reads snapshot from temp_snapshot.txt in the same directory.
"""
import sys
from pathlib import Path

# Ensure we can import from this directory
sys.path.insert(0, str(Path(__file__).parent))

from extraction_models import add_table_from_snapshot, ExtractionDB

def main():
    if len(sys.argv) < 2:
        print("Usage: python process_snapshot.py <table_name>")
        sys.exit(1)

    table_name = sys.argv[1]
    snapshot_file = Path(__file__).parent / "temp_snapshot.txt"

    if not snapshot_file.exists():
        print(f"ERROR: Snapshot file not found: {snapshot_file}")
        sys.exit(1)

    with open(snapshot_file, 'r', encoding='utf-8') as f:
        snapshot = f.read()

    result = add_table_from_snapshot(snapshot, table_name)
    print(result)

if __name__ == "__main__":
    main()
