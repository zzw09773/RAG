import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from rag_system.config import RAGConfig
from rag_system.rag_service import RAGService

def main():
    # Load config
    load_dotenv(override=True)
    try:
        config = RAGConfig.from_env()
        config.validate()
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)

    print("Initializing RAG Service (ParentDocumentRetriever)...")
    
    # Initialize unified service
    rag_service = RAGService(config)

    # Define data directory
    data_dir = repo_root / "data/converted_md"
    
    if not data_dir.exists():
        print(f"Error: Data directory not found at {data_dir}")
        sys.exit(1)

    print(f"Scanning for Markdown files in {data_dir}...")
    
    # Clear existing index (Optional - uncomment if you want a fresh start)
    # rag_service.clear_index()
    
    # Index directory
    results = rag_service.index_directory(data_dir, pattern="*.md")
    
    print("\nIndexing Summary:")
    print(f"  Success: {results['success']}")
    print(f"  Failed:  {results['failed']}")

if __name__ == "__main__":
    main()