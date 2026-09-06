import os
import re
import json
import hashlib
import datetime
import pymupdf4llm
from dotenv import load_dotenv

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from fastembed import TextEmbedding


class FastEmbedEmbeddings:
    """Minimal shim to avoid pydantic validation issues with langchain-community."""
    def __init__(self, model_name):
        self._m = TextEmbedding(model_name)

    def embed_documents(self, texts):
        return list(self._m.embed(texts, batch_size=16))

    def embed_query(self, text):
        return list(self._m.embed([text]))[0]


load_dotenv()

CORPUS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Corpus'))
CHROMA_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chroma_db'))
REGISTRY_PATH = os.path.join(os.path.dirname(__file__), 'registry.json')

# Embedding model is env-configurable. Changing this requires a full re-ingestion
# because vector dimensions differ between models.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)

national_collection = Chroma(
    collection_name="ip_sakti_national",
    embedding_function=embeddings,
    persist_directory=CHROMA_DB_DIR,
)

international_collection = Chroma(
    collection_name="ip_sakti_international",
    embedding_function=embeddings,
    persist_directory=CHROMA_DB_DIR,
)

text_splitter = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", " "],
    chunk_size=1000,
    chunk_overlap=150,
    length_function=len,
)

# ── Pre-processing ──────────────────────────────────────────────────────────────

# Regex patterns for HTML-like artifacts emitted by pymupdf4llm
_MARK_TAG_RE = re.compile(r'</?mark[^>]*>', re.IGNORECASE)
# Collapse sequences of more than 2 blank lines that pymupdf4llm sometimes emits
_EXCESS_BLANK_RE = re.compile(r'\n{3,}')


def _clean_markdown(text: str) -> str:
    """
    Strip pymupdf4llm markup artifacts before chunking:
      - <mark> / </mark> tags (pollute embeddings and confuse section regex)
      - Other stray HTML tags that shouldn't be in legal text
      - Excessive blank lines

    This must run on the raw per-page text BEFORE the text is appended to
    full_text and BEFORE the section splitter runs.
    """
    text = _MARK_TAG_RE.sub('', text)
    # Strip any other HTML-like tags defensively
    text = re.sub(r'<[^>]{1,60}>', '', text)
    text = _EXCESS_BLANK_RE.sub('\n\n', text)
    return text


# ── Section-boundary-first chunking ────────────────────────────────────────────

# Matches common legal document header patterns:
#   Chapter 3, Section 100, Article IV, Rule 12, Regulation 5, Schedule II
# Anchored to the start of a line (after optional heading hashes).
_SECTION_HEADER_RE = re.compile(
    r'(?i)^(?:#+\s*)?(C?hapter|S?ection|A?rticle|R?ule|R?egulation|S?chedule|P?art)\s+'
    r'([0-9a-zA-Z\(\)\.\-]+(?:\s+[A-Z][a-z]+)?)',
    re.MULTILINE,
)

# Amendment extraction pattern (e.g. "31. For section 39 of the principal Act...")
_AMENDMENT_TARGET_RE = re.compile(
    r'(?i)(?:for|of)\s+(?:section|article|rule)\s+([0-9a-zA-Z\(\)\.\-]+)\s+of\s+the\s+principal\s+act',
    re.MULTILINE,
)


def extract_sections(markdown_text: str, is_amendment: bool = False):
    """
    Slice the document by section headers first, THEN sub-chunk within each section.

    Strategy
    --------
    1. Find every section-header position in the full document.
    2. Slice into (label, text) segments at those boundaries.
    """
    if is_amendment:
        matches = list(_AMENDMENT_TARGET_RE.finditer(markdown_text))
    else:
        matches = list(_SECTION_HEADER_RE.finditer(markdown_text))

    if not matches:
        # No structural headers found — yield the whole document as one segment
        yield "Unknown", markdown_text
        return

    # Yield preamble text before the first header (if any)
    if matches[0].start() > 0:
        preamble = markdown_text[: matches[0].start()].strip()
        if preamble:
            yield "Preamble/Intro", preamble

    for i, match in enumerate(matches):
        if is_amendment:
            # "Amendment Target: Section 39"
            section_label = f"Amendment Target: Section {match.group(1).strip().upper()}"
        else:
            # Build section label and fix drop-caps
            type_str = match.group(1).title()
            if type_str.endswith("hapter"): type_str = "Chapter"
            elif type_str.endswith("ection"): type_str = "Section"
            elif type_str.endswith("rticle"): type_str = "Article"
            elif type_str.endswith("ule"): type_str = "Rule"
            elif type_str.endswith("egulation"): type_str = "Regulation"
            elif type_str.endswith("chedule"): type_str = "Schedule"
            elif type_str.endswith("art"): type_str = "Part"
            
            section_label = f"{type_str} {match.group(2).strip()}"

        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        section_text = markdown_text[start_idx:end_idx].strip()

        if not section_text:
            continue

        yield section_label, section_text


def get_file_hash(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()


def get_page_range(chunk_text: str, full_text: str, page_spans: list) -> tuple:
    """Return the (first_page, last_page) range that a chunk spans.

    Uses strip-normalised search so that whitespace trimming by the text
    splitter doesn't cause silent (1, 1) fallbacks.
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


def _make_chunk_id(document_id: str, section_label: str, chunk_text: str) -> str:
    """
    Deterministic, content-based chunk ID.

    Hash = SHA-256( document_id + section_label + first-200-chars-of-chunk ).
    Using content rather than a sequential index means re-ingesting the same
    PDF without any changes produces identical chunk IDs, so Chroma's
    upsert-by-id is idempotent and a full wipe is not required.
    """
    fingerprint = f"{document_id}|{section_label}|{chunk_text[:200]}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()


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
            act_docs_added = 0

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

                # Stable document ID — keyed on (jurisdiction, act_folder, filename, version)
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

                # ── Build full_text: clean each page before concatenation ────
                # _clean_markdown() must run HERE — before full_text is assembled
                # and before extract_sections() runs — so <mark> tags don't
                # reach the section regex or the embeddings.
                full_text = ""
                page_spans = []
                for p in pages:
                    p_text = _clean_markdown(p['text'])
                    p_num = p['metadata'].get('page', 1)
                    start_idx = len(full_text)
                    full_text += p_text + "\n"
                    end_idx = len(full_text)
                    page_spans.append((start_idx, end_idx, p_num))

                source_pdf_path = os.path.join(
                    "Corpus", jurisdiction, act_folder, filename
                ).replace('\\', '/')

                docs = []
                ids = []

                # ── Section-boundary-first chunking ────────────────────────
                # extract_sections() yields (authoritative_label, section_text).
                # The label is derived from the header that precedes the text,
                # so it is always correct — never re-derived after chunking.
                is_amendment = doc_type == "amendment"
                for section_label, section_text in extract_sections(full_text, is_amendment=is_amendment):
                    chunks = text_splitter.split_text(section_text)

                    for chunk in chunks:
                        # Content-based deterministic ID — see _make_chunk_id()
                        chunk_id = _make_chunk_id(document_id, section_label, chunk)

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
                            "source_pdf_path": source_pdf_path,
                            # Deserialize on retrieval side with json.loads()
                            "related_refs": json.dumps([]),
                        }

                        doc = Document(page_content=chunk, metadata=metadata)
                        docs.append(doc)
                        ids.append(chunk_id)

                if docs:
                    # Deduplicate by chunk_id before upsert.
                    # OCR'd PDFs can produce empty/near-identical short pages
                    # whose first-200-char hash collides. Same ID = same content
                    # = same vector, so keeping the first occurrence is safe.
                    seen_ids: set = set()
                    deduped_docs = []
                    deduped_ids = []
                    for doc, cid in zip(docs, ids):
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            deduped_docs.append(doc)
                            deduped_ids.append(cid)
                    dropped = len(docs) - len(deduped_docs)
                    if dropped:
                        print(f"  [dedup] dropped {dropped} duplicate chunks", flush=True)

                    BATCH_SIZE = 16
                    for i in range(0, len(deduped_docs), BATCH_SIZE):
                        batch_docs = deduped_docs[i:i + BATCH_SIZE]
                        batch_ids = deduped_ids[i:i + BATCH_SIZE]
                        vectorstore.add_documents(documents=batch_docs, ids=batch_ids)
                    total_chunks += len(deduped_docs)
                    print(f"  → {len(deduped_docs)} chunks added", flush=True)

                # Update registry — keyed by document_id (stable hash)
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

    # Final registry flush
    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=4)

    print(
        f"\nIngestion complete. "
        f"Ingested: {total_ingested} PDFs | "
        f"Skipped (unchanged): {total_skipped} | "
        f"Chunks added: {total_chunks}",
        flush=True,
    )


if __name__ == "__main__":
    print(f"Starting ingestion... (embedding model: {EMBEDDING_MODEL})", flush=True)
    ingest_corpus()
