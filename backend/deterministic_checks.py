import os
import sys
from dotenv import load_dotenv

# Ensure we're running from backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

# CROSS-REFERENCE: The judge-scored semantic evaluation for I1 and I2 (checking how 
# the LLM uses these chunks) lives in test_cases.json under the 'periodic' tier. 
# This script handles ONLY their deterministic metadata/deduplication requirements.

from services.retriever import retrieve

def test_i1_metadata_integrity():
    """
    Test I1 (Metadata Integrity): 
    Query 'Substitute Section 39 of the Patents Act.'
    Check retrieved chunks and assert that there are no 'Unknown' section identifiers in metadata.
    """
    print("\n--- Running Deterministic Test I1 (Metadata Integrity) ---")
    query = "Substitute Section 39 of the Patents Act."
    chunks = retrieve(query, jurisdiction="national", k=10)
    
    if not chunks:
        print("FAIL: No chunks retrieved.")
        return False
        
    failures = []
    for c in chunks:
        meta = c.get("metadata", {})
        section_name = meta.get("section_name", "")
        if "Unknown" in str(section_name) or "Unknown" in str(meta.get("act_name", "")):
            failures.append(c["chunk_id"])
            
    if failures:
        print(f"FAIL: Found {len(failures)} chunks with 'Unknown' in metadata. IDs: {failures}")
        return False
        
    print(f"PASS: {len(chunks)} chunks retrieved, no 'Unknown' sections found.")
    return True

def test_i2_deduplication():
    """
    Test I2 (Deduplication Check):
    Query 'What does the Biological Diversity Act say about equitable benefit sharing?'
    Compare actual text chunk contents and assert no duplicate chunks in the returned set.
    """
    print("\n--- Running Deterministic Test I2 (Deduplication Check) ---")
    query = "What does the Biological Diversity Act say about equitable benefit sharing?"
    chunks = retrieve(query, jurisdiction="national", k=15)
    
    if not chunks:
        print("FAIL: No chunks retrieved.")
        return False
        
    contents = [c.get("content", "").strip() for c in chunks]
    unique_contents = set(contents)
    
    if len(contents) != len(unique_contents):
        duplicates = len(contents) - len(unique_contents)
        print(f"FAIL: Found {duplicates} duplicate chunks based on page content.")
        return False
        
    print(f"PASS: {len(chunks)} chunks retrieved, all are unique.")
    return True

if __name__ == "__main__":
    i1_pass = test_i1_metadata_integrity()
    i2_pass = test_i2_deduplication()
    
    if i1_pass and i2_pass:
        print("\nAll deterministic checks PASSED.")
        sys.exit(0)
    else:
        print("\nOne or more deterministic checks FAILED.")
        sys.exit(1)
