import json
import os
import sys

from db_manager import BookDatabase


def main():
    if len(sys.argv) != 3:
        print("Usage: python export_graph.py <db_dir> <output.json>")
        sys.exit(1)

    db_dir = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.exists(os.path.join(db_dir, "graph.db")):
        print(f"Graph database not found in {db_dir}")
        sys.exit(1)

    db = BookDatabase(db_dir)
    try:
        export = db.export_graph_state()
    finally:
        db.close()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print(f"Exported graph state to {output_path}")


if __name__ == "__main__":
    main()
