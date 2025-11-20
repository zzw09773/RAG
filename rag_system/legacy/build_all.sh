#!/bin/bash
# This script automates the entire RAG building process.
# 1. Preprocesses all source documents into clean Markdown files.
# 2. Builds a separate, clean database collection for each processed document.
#
# Usage:
#   ./build_all.sh          # Skip existing collections
#   ./build_all.sh --force  # Force rebuild all collections
#   ./build_all.sh --rebuild-only  # Skip preprocessing, only rebuild collections

# Exit immediately if a command fails.
set -e

# Parse command line arguments
FORCE_REBUILD=false
REBUILD_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --force|-f)
      FORCE_REBUILD=true
      shift
      ;;
    --rebuild-only|-r)
      REBUILD_ONLY=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Build RAG collections from source documents."
      echo ""
      echo "Options:"
      echo "  --force, -f         Force rebuild all collections (even if they exist)"
      echo "  --rebuild-only, -r  Skip preprocessing, only rebuild collections"
      echo "  --help, -h          Show this help message"
      echo ""
      echo "Examples:"
      echo "  $0                  # Incremental build (skip existing collections)"
      echo "  $0 --force          # Force rebuild all collections"
      echo "  $0 --rebuild-only   # Skip preprocessing step"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--force] [--rebuild-only] [--help]"
      exit 1
      ;;
  esac
done

echo "--- Starting RAG Build Process ---"
if [ "$FORCE_REBUILD" = true ]; then
  echo "Mode: FORCE REBUILD (all collections will be recreated)"
elif [ "$REBUILD_ONLY" = true ]; then
  echo "Mode: REBUILD ONLY (skip preprocessing)"
else
  echo "Mode: INCREMENTAL (skip existing collections)"
fi
echo ""

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Load environment variables from .env file if it exists
if [ -f .env ]; then
  set -a # automatically export all variables
  source .env
  set +a # stop automatically exporting
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
  source venv/bin/activate
fi

# --- STEP 1: Preprocess all source documents ---
if [ "$REBUILD_ONLY" = false ]; then
  echo ""
  echo "[STEP 1/2] Preprocessing source documents into Markdown..."
  python3 -m rag_system.legacy.build.preprocess --input_dir rag_system/documents --output_dir rag_system/processed_md
else
  echo ""
  echo "[STEP 1/2] Skipping preprocessing (--rebuild-only mode)"
fi

# --- STEP 2: Build a collection for each processed Markdown file ---
echo ""
echo "[STEP 2/2] Building database collections from Markdown files..."

# Automatically discover all .md files in processed_md directory
PROCESSED_MD_DIR="rag_system/processed_md"

if [ ! -d "$PROCESSED_MD_DIR" ]; then
  echo "Error: Processed markdown directory not found: $PROCESSED_MD_DIR"
  exit 1
fi

# Find all .md files (excluding hidden files)
md_file_count=$(find "$PROCESSED_MD_DIR" -maxdepth 1 -type f -name "*.md" ! -name ".*" | wc -l)

if [ "$md_file_count" -eq 0 ]; then
  echo "Warning: No markdown files found in $PROCESSED_MD_DIR"
  echo "Nothing to index."
  exit 0
fi

echo "Found $md_file_count markdown file(s) to process."
echo ""

# Helper function to check if collection exists in database
collection_exists() {
  local collection_name="$1"

  # Find PostgreSQL container (try multiple methods)
  local container_id=$(docker compose ps -q 2>/dev/null | head -1)
  if [ -z "$container_id" ]; then
    # Fallback: search by image
    container_id=$(docker ps --filter "ancestor=pgvector/pgvector:0.8.1-pg17-trixie" --format "{{.ID}}" | head -1)
  fi

  if [ -z "$container_id" ]; then
    # Container not running, assume collection doesn't exist
    return 1
  fi

  # Query database for collection
  local result=$(docker exec "$container_id" \
    psql -U postgres -tAc "SELECT COUNT(*) FROM langchain_pg_collection WHERE name='$collection_name';" 2>/dev/null || echo "0")

  [ "$result" -gt 0 ]
}

# Counters
BUILT_COUNT=0
SKIPPED_COUNT=0

# Process each markdown file
while IFS= read -r -d '' md_file; do
  # Derive collection name from the filename
  collection_name=$(basename "$md_file" .md)

  echo "-----------------------------------------------------"
  echo "Processing: '$collection_name' from $md_file"

  # Check if collection exists (unless force rebuild)
  if [ "$FORCE_REBUILD" = false ] && collection_exists "$collection_name"; then
    echo "⏭️  SKIPPED: Collection '$collection_name' already exists"
    echo "    (Use --force to rebuild)"
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    echo ""
    continue
  fi

  if [ "$FORCE_REBUILD" = true ]; then
    echo "🔄 REBUILDING: Collection '$collection_name'"
  else
    echo "🔨 BUILDING: Collection '$collection_name'"
  fi
  echo "-----------------------------------------------------"

  # Split strategy is now determined automatically by the indexer.
  python3 -m rag_system.legacy.build.indexer \
    --input_file "$md_file" \
    --collection "$collection_name" \
    --reset_collection \
    --embed \
    --no-verify-ssl

  BUILT_COUNT=$((BUILT_COUNT + 1))
  echo ""
done < <(find "$PROCESSED_MD_DIR" -maxdepth 1 -type f -name "*.md" ! -name ".*" -print0 | sort -z)

echo "-----------------------------------------------------"
echo "--- RAG Build Process Complete ---"
echo ""
echo "Summary:"
echo "  • Total files processed: $md_file_count"
echo "  • Collections built: $BUILT_COUNT"
echo "  • Collections skipped: $SKIPPED_COUNT"
echo ""
if [ "$SKIPPED_COUNT" -gt 0 ]; then
  echo "Tip: Use './build_all.sh --force' to rebuild all collections"
fi