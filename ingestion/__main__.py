"""Entry point for python -m ingestion."""
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m ingestion <command> [args...]")
        print("Commands: ingest, query")
        sys.exit(1)

    command = sys.argv[1]

    if command == "ingest":
        from ingestion.ingest import main
        sys.argv = sys.argv[1:]
        sys.exit(main())
    elif command == "query":
        from ingestion.query import main
        sys.argv = sys.argv[1:]
        sys.exit(main())
    else:
        print(f"Unknown command: {command}")
        print("Available commands: ingest, query")
        sys.exit(1)
