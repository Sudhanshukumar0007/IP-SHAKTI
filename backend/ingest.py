import os
import re
import json
import hashlib
import datetime
import pymupdf4llm
from dotenv import load_dotenv

from langchain_chroma import Chroma
from langchain_chroma import Chroma
from langchain_community.embeddings import FastEmbedEmbeddings  # still usable via langchain-community but will migrate
# NOTE: using fastembed directly via LangChain wrapper to avoid pydantic validation issue
# in newer langchain-community versions that removed FastEmbedEmbeddings from the
# langchain_community.embeddings.fastembed sub-module.
from fastembed import TextEmbedding

class FastEmbedEmbeddings:  # minimal shim
    def __init__(self, model_name): self._m = TextEmbedding(model_name)
    def embed_documents(self, texts): return list(self._m.embed(texts, batch_size=16))
    def embed_query(self, text): return list(self._m.embed([text]))[0]
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

load_dotenv()

CORPUS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Corpus'))
CHROMA_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chroma_db'))
REGISTRY_PATH = os.path.join(os.path.dirname(__file__), 'registry.json')

# Embedding model is env-configurable so switching between e.g. multilingual-e5-small
# and BGE-M3 doesn't require a code change. Changing this requires a full re-ingestion
# because vector dimensions differ between models.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)

national_collection = Chroma(
    collection_name="ip_sakti_national",
    embedding_function=embeddings,
    persist_directory=CHROMA_DB_DIR
)

international_collection = Chroma(
    collection_name="ip_sakti_international",
    embedding_function=embeddings,
    persist_directory=CHROMA_DB_DIR
)

text_splitter = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", " "],
    chunk_size=1000,
    chunk_overlap=150,
    length_function=len
)

def get_file_hash(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def extract_sections(markdown_text: str):
    # Expanded regex to catch Chapter, Section, Article, Rule, Regulation, Schedule
    header_regex = re.compile(
        r'(?i)^(?:#+\s*)?(Chapter|Section|Article|Rule|Regulation|Schedule)\s+([0-9a-zA-Z\(\)\.\-]+)',
        re.MULTILINE
    )

    matches = list(header_regex.finditer(markdown_text))

    if not matches:
        yield "Unknown", markdown_text
        return

    if matches[0].start() > 0:
        preamble = markdown_text[0:matches[0].start()].strip()
        if preamble:
            yield "Preamble/Intro", preamble

    for i, match in enumerate(matches):
        section_label = f"{match.group(1)} {match.group(2)}".title()
        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)

        section_text = markdown_text[start_idx:end_idx].strip()
        if section_text:
            yield section_label, section_text

def get_page_range(chunk_text: str, full_text: str, page_spans: list) -> tuple:
    """Return the (first_page, last_page) range that a chunk spans.

    Uses strip-normalised search so that whitespace trimming by the text splitter
    doesn't cause silent (1, 1) fallbacks.
    """
    needle = chunk_text.strip()
    start_idx = full_text.find(needle)
    if start_idx == -1:
        return (1, 1)  # Fallback — should be rare after normalisation

    end_idx = start_idx + len(needle)

    overlapping_pages = []
    for p_start, p_end, p_num in page_spans:
        if max(start_idx, p_start) < min(end_idx, p_end):
            overlapping_pages.append(p_num)

    if not overlapping_pages:
        return (1, 1)

    return (min(overlapping_pages), max(overlapping_pages))

def ingest_corpus():
    registry = {}

    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
                registry = json.load(f)
        except Exception as e:
            print(f"Warning: could not load registry at {REGISTRY_PATH}: {e}. Starting fresh.")
            registry = {}

    today = datetime.date.today().isoformat()

    total_ingested = 0
    total_skipped = 0
    total_chunks = 0

    for jurisdiction in ["national", "international"]:
        jurisdiction_dir = os.path.join(CORPUS_DIR, jurisdiction)
        if not os.path.exists(jurisdiction_dir):
            continue

        vectorstore = national_collection if jurisdiction == "national" else international_collection

        act_folders = [
            d for d in os.listdir(jurisdiction_dir)
            if os.path.isdir(os.path.join(jurisdiction_dir, d))
        ]

        for act_folder in act_folders:
            act_dir = os.path.join(jurisdiction_dir, act_folder)

            meta_path = os.path.join(act_dir, "meta.json")
            source_type = "statute"
            display_act_name = act_folder.replace('-', ' ').title()

            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        source_type = meta.get('source_type', source_type)
                        display_act_name = meta.get('act_name', display_act_name)
                except Exception as e:
                    print(f"Warning: could not read meta.json at {meta_path}: {e}. Using defaults.")

            pdfs = [fn for fn in os.listdir(act_dir) if fn.endswith('.pdf')]
            act_docs_added = 0  # track docs added this act-folder for registry save

            for filename in pdfs:
                parts = filename.replace('.pdf', '').split('_')
                if len(parts) >= 3:
                    doc_type = parts[0]
                    version = "_".join(parts[1:-1])
                    language = parts[-1]
                elif len(parts) == 2:
                    doc_type = parts[0]
                    version = "unknown"
                    language = parts[-1]
                    print(f"Warning: filename '{filename}' has only 2 parts; version set to 'unknown'.", flush=True)
                else:
                    doc_type = "base"
                    version = "unknown"
                    language = "en"
                    print(f"Warning: filename '{filename}' could not be parsed; using defaults.", flush=True)

                # Document ID — stable across runs for the same PDF file in the same act
                document_id = hashlib.sha256(
                    f"{jurisdiction}_{act_folder}_{filename}_{version}".encode()
                ).hexdigest()

                file_path = os.path.join(act_dir, filename)
                pdf_hash = get_file_hash(file_path)

                # Idempotency check — skip unchanged PDFs
                if document_id in registry and registry[document_id].get("pdf_hash") == pdf_hash:
                    print(f"Skipping {filename} (already ingested with same hash)", flush=True)
                    total_skipped += 1
                    continue

                print(f"Ingesting {jurisdiction}/{act_folder}/{filename} ...", flush=True)

                try:
                    pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)
                except Exception as e:
                    print(f"Error reading {file_path}: {e}", flush=True)
                    continue

                # Build full text and page spans for page-range attribution
                full_text = ""
                page_spans = []
                for p in pages:
                    p_text = p['text']
                    p_num = p['metadata'].get('page', 1)
                    start_idx = len(full_text)
                    full_text += p_text + "\n"
                    end_idx = len(full_text)
                    page_spans.append((start_idx, end_idx, p_num))

                # Canonical path for the "verify this act" registry and chunk metadata
                source_pdf_path = os.path.join(
                    "Corpus", jurisdiction, act_folder, filename
                ).replace('\\', '/')

                docs = []
                ids = []
                global_chunk_idx = 0

                for section_label, section_text in extract_sections(full_text):
                    chunks = text_splitter.split_text(section_text)

                    for chunk in chunks:
                        chunk_id = hashlib.sha256(
                            f"{document_id}_{global_chunk_idx}".encode()
                        ).hexdigest()
                        global_chunk_idx += 1
                        
                        page_start, page_end = get_page_range(chunk, full_text, page_spans)

                        metadata = {
                            "chunk_id": chunk_id,
                            "document_id": document_id,
                            "jurisdiction": jurisdiction,
                            "act_name": display_act_name,
                            "source_type": source_type,
                            "section_or_article": section_label,
                            "version": version,
                            "language": language,
                            "page_start": page_start,
                            "page_end": page_end,
                            "last_verified_date": today,
                            # Required by storage schema — feeds "verify this act" PDF viewer
                            "source_pdf_path": source_pdf_path,
                            # Cross-jurisdiction links populated as a post-ingestion step.
                            # Stored as a JSON-encoded string because Chroma only accepts
                            # scalar metadata types (str/int/float/bool) — not lists.
                            # Deserialize on the retrieval side with: json.loads(chunk.metadata["related_refs"])
                            "related_refs": json.dumps([]),
                        }

                        doc = Document(page_content=chunk, metadata=metadata)
                        docs.append(doc)
                        ids.append(chunk_id)

                if docs:
                    BATCH_SIZE = 16
                    for i in range(0, len(docs), BATCH_SIZE):
                        batch_docs = docs[i:i+BATCH_SIZE]
                        batch_ids = ids[i:i+BATCH_SIZE]
                        vectorstore.add_documents(documents=batch_docs, ids=batch_ids)
                    total_chunks += len(docs)

                # Update in-memory registry
                registry[document_id] = {
                    "act_name": display_act_name,
                    "jurisdiction": jurisdiction,
                    "source_pdf_path": source_pdf_path,
                    "version": version,
                    "language": language,
                    "pdf_hash": pdf_hash,
                    "ingested_date": today,
                }

                total_ingested += 1
                act_docs_added += 1

            # Save registry once per act-folder (not per PDF) to reduce I/O
            if act_docs_added > 0:
                with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
                    json.dump(registry, f, indent=4)

    # Final registry flush to capture any state not written mid-loop
    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=4)

    print(
        f"\nIngestion complete. "
        f"Ingested: {total_ingested} PDFs | "
        f"Skipped (unchanged): {total_skipped} | "
        f"Chunks added: {total_chunks}",
        flush=True
    )

if __name__ == "__main__":
    print(f"Starting ingestion... (embedding model: {EMBEDDING_MODEL})", flush=True)
    ingest_corpus()
