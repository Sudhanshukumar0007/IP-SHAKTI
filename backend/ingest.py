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

# Shared normalized embedding shim — L2-normalizes all vectors and asserts norm~1
# at startup. Must be the same class used by retriever.py so query and passage
# vectors live in the same space.
from services.embeddings import FastEmbedEmbeddings


load_dotenv()

CORPUS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Corpus'))
CHROMA_DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'chroma_db'))
REGISTRY_PATH = os.path.join(os.path.dirname(__file__), 'registry.json')

# Embedding model is env-configurable. Changing this requires a full re-ingestion
# because vector dimensions differ between models.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

# Collection suffix — must match COLLECTION_SUFFIX in retriever.py.
# Set to '_v2' (default) or bump to '_v3' when running a clean Phase 3 re-ingest.
COLLECTION_SUFFIX: str = os.getenv("COLLECTION_SUFFIX", "_v3")

embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)


def get_collection(jurisdiction: str, is_current: bool):
    col_name = f"ip_sakti_{jurisdiction}_{'current' if is_current else 'history'}{COLLECTION_SUFFIX}"
    return Chroma(
        collection_name=col_name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_DIR,
        collection_metadata={"hnsw:space": "cosine"}
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
    r'(?i)^'
    r'(?:'
        r'(?:#+\s*)?(?:\*\*_?)?(C?hapter|S?ection|A?rticle|R?ule|R?egulation|S?chedule|P?art)\s+([0-9a-zA-Z\(\)\.\-]+(?:\s+[A-Z][a-z]+)?)(?:_?\*\*)?\s*$'
        r'|'
        # Bare-numbered marginal headings WITH em-dash (can have body text on same line)
        r'(?:#+\s*)?(?:\*\*_?)?([0-9]{1,3}\.)\s+(?!(?:Ins\.|Subs\.|Omitted|Added|Renumbered|Deleted|Rep\.))([^\n*]+?)(?:\*\*\s*)?(?:\.\s*)?(?:\*\*\s*)?(?:—|–|\uFFFD)(?:\*\*)?'
        r'|'
        # Bare-numbered marginal headings ON THEIR OWN LINE (no em-dash needed)
        r'(?:#+\s*)?(?:\*\*_?)?([0-9]{1,3}\.)\s+(?!(?:Ins\.|Subs\.|Omitted|Added|Renumbered|Deleted|Rep\.))([^\n*]+?)(?:_?\*\*)?\s*$'
    r')',
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
    # Strip Table of Contents (ToC) to prevent heading stubs and boundary shifting
    toc_pattern = re.compile(
        r'(?i)(?:^|\n)(?:#\s*)?(?:ARRANGEMENT OF SECTIONS|TABLE OF CONTENTS)[\s\S]{100,}?(?=\n(?:#+\s*)?(?:THE\s+[a-zA-Z]+|CHAPTER I\b|CHAPTER-I\b|Chapter 1\b|PRELIMINARY|ACT NO\.|An Act to\b))'
    )
    toc_match = toc_pattern.search(markdown_text)
    if toc_match:
        markdown_text = markdown_text[:toc_match.start()] + markdown_text[toc_match.end():]

    if is_amendment:
        matches = list(_AMENDMENT_TARGET_RE.finditer(markdown_text))
    else:
        raw_matches = list(_SECTION_HEADER_RE.finditer(markdown_text))
        matches = []
        for m in raw_matches:
            if m.group(3) or m.group(5):
                t = (m.group(4) or m.group(6) or "").lower()
                if (
                    # Amendment citations: "w.e.f. 20-5-2003" or "Act 38 of 2002"
                    "w.e.f." in t
                    or re.search(r'act\s+\d+\s+of\s+\d{4}', t)
                    # Commencement notifications: "1st October, 2003 (Ss. 1, 2...)"
                    or re.search(r'^\d+(st|nd|rd|th)\s+\w+', t)
                    # Cross-section references used as heading text: "Section 1—..."
                    or re.search(r'^section\s+\d', t)
                    # Amendment Act names: "The Patents (Amendment) Act, 2002"
                    or re.search(r'^the\s+\w[^.]+\(amendment\)\s+act', t)
                ):
                    continue
            matches.append(m)

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
            if match.group(1):
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
            elif match.group(3):
                # Bare number marginal heading with em-dash
                num = match.group(3).strip('.')
                title = match.group(4).strip()
                if title.endswith('—') or title.endswith('-') or title.endswith('\uFFFD'): title = title[:-1].strip()
                section_label = f"Section {num}: {title}"
            else:
                # Bare number marginal heading on its own line
                num = match.group(5).strip('.')
                title = match.group(6).strip()
                section_label = f"Section {num}: {title}"

        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        section_text = markdown_text[start_idx:end_idx].strip()

        if not section_text or len(section_text.strip()) < 40:
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


def slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def build_registry_from_files() -> dict:
    """Scan the Corpus directory dynamically and build the extended registry schema."""
    registry = {}
    act_versions = {} # act_id -> list of dicts
    today = datetime.date.today().isoformat()

    import pathlib
    corpus_path = pathlib.Path(CORPUS_DIR)

    for pdf_path in corpus_path.rglob('*.pdf'):
        # Parse path parts relative to Corpus directory
        rel_parts = pdf_path.relative_to(corpus_path).parts
        
        # Skip medicinal folder for now
        if "medicinal" in rel_parts:
            continue
        
        # We need at least jurisdiction/act_id/filename.pdf
        if len(rel_parts) < 3:
            print(f"Skipping {pdf_path}: unexpected path depth")
            continue
            
        jurisdiction = rel_parts[0]
        filename = rel_parts[-1]
        act_id = rel_parts[-2]
        
        # Extract optional domain and category if they exist
        domain = rel_parts[1] if len(rel_parts) >= 5 else "unknown"
        cat_dir = rel_parts[2] if len(rel_parts) >= 5 else (rel_parts[1] if len(rel_parts) == 4 else "unknown")

        # Plural to singular fallback
        category_mapping = {
            "acts": "act",
            "rules": "rule",
            "treaties": "treaty",
            "pharmacopoeias": "pharmacopoeia",
            "regulations": "regulation",
            "guidelines": "guideline"
        }
        category_type = category_mapping.get(cat_dir.lower(), cat_dir.rstrip('s'))
        
        act_dir = pdf_path.parent
        display_act_name = act_id.replace('-', ' ').title()
        
        meta_path = act_dir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    display_act_name = meta.get('act_name', display_act_name)
            except Exception as e:
                print(f"Warning: could not read meta.json at {meta_path}: {e}")

        parts = filename.replace('.pdf', '').split('_')
        if len(parts) >= 3:
            doc_type = parts[0]
            version = "_".join(parts[1:-1])
            language = parts[-1]
        elif len(parts) == 2:
            doc_type = parts[0]
            version = "unknown"
            language = parts[-1]
        else:
            doc_type = "base"
            version = "unknown"
            language = "en"
            
        # Parse effective_date
        version_parts = version.split('_')
        if len(version_parts) >= 2 and version_parts[1].isdigit():
            effective_date = f"{version_parts[0]}-{version_parts[1].zfill(2)}-01"
        else:
            year_match = re.search(r'^(\d{4})', version)
            if year_match:
                effective_date = f"{year_match.group(1)}-01-01"
            else:
                effective_date = "1970-01-01"
                            
        source_pdf_path = pdf_path.as_posix().replace(corpus_path.as_posix(), "Corpus")
        file_path = str(pdf_path)
        pdf_hash = get_file_hash(file_path)

        document_id = hashlib.sha256(
            f"{jurisdiction}_{act_id}_{filename}_{version}".encode()
        ).hexdigest()

        entry = {
                            "document_id": document_id,
                            "act_id": act_id,
                            "act_name": display_act_name,
                            "jurisdiction": jurisdiction,
                            "category_type": category_type,
                            "document_type": doc_type,
                            "source_pdf_path": source_pdf_path,
                            "version": version,
                            "language": language,
                            "pdf_hash": pdf_hash,
                            "effective_date": effective_date,
                            "ingested_date": today,
                            "is_latest_consolidated": False,
                            "supersedes": None,
                            "superseded_by": None,
            "file_path_local": file_path
        }
        
        if act_id not in act_versions:
            act_versions[act_id] = []
        act_versions[act_id].append(entry)

    # Link versions and deduplicate identical hashes within an act
    for a_id, versions in act_versions.items():
        # Sort by effective date
        versions.sort(key=lambda x: x["effective_date"])
        
        seen_hashes = set()
        deduped = []
        for v in versions:
            if v["pdf_hash"] not in seen_hashes:
                seen_hashes.add(v["pdf_hash"])
                deduped.append(v)
            else:
                print(f"Skipping duplicate pdf_hash for {a_id}: {v['source_pdf_path']}")
                
        latest_consolidated_idx = None
        for i in range(len(deduped)):
            if i > 0:
                deduped[i]["supersedes"] = deduped[i-1]["document_id"]
            if i < len(deduped) - 1:
                deduped[i]["superseded_by"] = deduped[i+1]["document_id"]
                
            if deduped[i]["document_type"] == "consolidated" or deduped[i]["document_type"] == "base":
                latest_consolidated_idx = i
                
        if latest_consolidated_idx is not None:
            # Mark the latest base/consolidated AND everything after it (amendments) as current
            for i in range(latest_consolidated_idx, len(deduped)):
                deduped[i]["is_latest_consolidated"] = True
        elif deduped:
            # If no base/consolidated exists, mark the latest document as current
            deduped[-1]["is_latest_consolidated"] = True
            
        for v in deduped:
            registry[v["document_id"]] = v
            
    return registry


def parse_pdf_to_markdown(file_path: str):
    """
    Fast markdown extraction using PyMuPDF RAG.
    If the document has no extractable text (e.g. pure scanned image),
    fall back to pymupdf4llm's OCR layout engine with a live progress bar.
    """
    import pymupdf
    import pymupdf4llm.helpers.pymupdf_rag as rag

    has_text = False
    try:
        with pymupdf.open(file_path) as doc:
            for page in doc[:min(5, len(doc))]:
                if len(page.get_text().strip()) > 30:
                    has_text = True
                    break
    except Exception:
        has_text = False

    if has_text:
        return rag.to_markdown(file_path, page_chunks=True)
    else:
        print("  [scanned document detected - enabling OCR layout parser with progress]", flush=True)
        return pymupdf4llm.to_markdown(file_path, page_chunks=True, show_progress=True)


def ingest_corpus():
    old_registry = {}
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
                old_registry = json.load(f)
        except Exception as e:
            print(f"Warning: could not load registry at {REGISTRY_PATH}: {e}. Starting fresh.")
            
    print("Building registry from files...")
    registry = build_registry_from_files()
    saved_registry = dict(old_registry)

    total_ingested = 0
    total_skipped = 0
    total_chunks = 0

    for document_id, data in registry.items():
        filename = data["source_pdf_path"].split('/')[-1]
        file_path = data.pop("file_path_local") # Remove before saving to JSON

        # Idempotency check — skip unchanged PDFs
        if document_id in old_registry and old_registry[document_id].get("pdf_hash") == data["pdf_hash"] and old_registry[document_id].get("is_latest_consolidated") == data["is_latest_consolidated"]:
            print(f"Skipping {filename} (already ingested with same hash and status)", flush=True)
            total_skipped += 1
            continue

        # If it was in the old registry but we are re-ingesting it (either hash changed or status flipped),
        # we must delete its old chunks from the collection it used to be in to avoid duplicates.
        if document_id in old_registry:
            leaving_is_current = old_registry[document_id].get("is_latest_consolidated")
            old_collection = get_collection(data["jurisdiction"], leaving_is_current)
            print(f"Deleting old chunks for {filename} from {'current' if leaving_is_current else 'history'} collection before re-ingest...", flush=True)
            try:
                old_collection.delete(where={"document_id": document_id})
            except Exception as e:
                print(f"Warning: failed to delete old chunks for {document_id}: {e}")

        print(f"Ingesting {data['source_pdf_path']} (Current: {data['is_latest_consolidated']}) ...", flush=True)

        try:
            pages = parse_pdf_to_markdown(file_path)
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

        docs = []
        ids = []

        # ── Section-boundary-first chunking ────────────────────────
        # extract_sections() yields (authoritative_label, section_text).
        # The label is derived from the header that precedes the text,
        # so it is always correct — never re-derived after chunking.
        is_amendment = data["document_type"] == "amendment"
        for section_label, section_text in extract_sections(full_text, is_amendment=is_amendment):
            chunks = text_splitter.split_text(section_text)

            for chunk in chunks:
                # Content-based deterministic ID — see _make_chunk_id()
                chunk_id = _make_chunk_id(document_id, section_label, chunk)

                page_start, page_end = get_page_range(chunk, full_text, page_spans)

                metadata = {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "act_id": data["act_id"],
                    "jurisdiction": data["jurisdiction"],
                    "act_name": data["act_name"],
                    "category_type": data["category_type"],
                    "section_or_article": section_label,
                    "version": data["version"],
                    "language": data["language"],
                    "page_start": page_start,
                    "page_end": page_end,
                    "last_verified_date": data["ingested_date"],
                    "source_pdf_path": data["source_pdf_path"],
                    "is_latest_consolidated": data["is_latest_consolidated"],
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

            vectorstore = get_collection(data["jurisdiction"], data["is_latest_consolidated"])
            BATCH_SIZE = 16
            total_batches = (len(deduped_docs) + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"  → Embedding {len(deduped_docs)} chunks across {total_batches} batches...", flush=True)
            for i in range(0, len(deduped_docs), BATCH_SIZE):
                batch_docs = deduped_docs[i:i + BATCH_SIZE]
                batch_ids = deduped_ids[i:i + BATCH_SIZE]
                vectorstore.add_documents(documents=batch_docs, ids=batch_ids)
                batch_idx = (i // BATCH_SIZE) + 1
                if batch_idx % 10 == 0 or batch_idx == total_batches:
                    print(f"    [embedded batch {batch_idx}/{total_batches}]", flush=True)
            total_chunks += len(deduped_docs)
            print(f"  ✓ {len(deduped_docs)} chunks added", flush=True)

        saved_registry[document_id] = {k: v for k, v in data.items() if k != "file_path_local"}
        total_ingested += 1

        # Save registry after every document to prevent any progress loss
        with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
            json.dump(saved_registry, f, indent=4)

    # Final registry flush
    with open(REGISTRY_PATH, 'w', encoding='utf-8') as f:
        json.dump(saved_registry, f, indent=4)

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
