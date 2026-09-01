# IP-SHAKTI Corpus Structure

This document outlines the file layout for the `Corpus` directory to be used by the Retrieval-Augmented Generation (RAG) system. The structure is designed to match the Architecture MVP, enabling seamless metadata injection and hierarchical versioning of legal texts.

## Folder Layout

The `Corpus` is organized by:
`Jurisdiction` -> `Act Name` -> `Files`

```text
Corpus/
├── national/
│   ├── patents-act-1970/
│   │   ├── base_1970_en.pdf              (Original 1970 English)
│   │   ├── base_1970_hi.pdf              (Original 1970 Hindi)
│   │   ├── amendment_1999_en.pdf         (1999 Amendment)
│   │   ├── amendment_2002_en.pdf         (2002 Amendment - 38 of 2002)
│   │   ├── amendment_2002_06_en.pdf      (2002 Amendment - June 25)
│   │   ├── amendment_2005_en.pdf         (2005 Amendment)
│   │   ├── consolidated_2015_en.pdf      (Incorporating amendments till 2015)
│   │   └── consolidated_2024_en.pdf      (Incorporating amendments till 2024)
│   │
│   ├── jan-vishwas-act-2023/
│   │   ├── amendment_2023_en.pdf         
│   │   └── amendment_2023_v0_en.pdf      
│   │
│   └── tribunals-reforms-act-2021/
│       └── base_2021_en.pdf              
│
└── international/
    (Empty, ready for future treaties like TRIPS or Nagoya Protocol)
```

## File Naming Convention

Files are named using the following schema to simplify programmatic parsing:
`[document_type]_[year]_[language].pdf`

- **document_type**: `base`, `amendment`, or `consolidated`
- **year**: 4-digit year (e.g. `1970`, `2024`), can optionally include month suffix (e.g., `2002_06`) if multiple amendments happen in a year.
- **language**: 2-letter code (`en` for English, `hi` for Hindi)

## Metadata Extraction for Embeddings

When ingestion pipelines (e.g., LangGraph/LlamaIndex) load documents, they should automatically attach metadata by splitting the filename and extracting the parent folder names.

Example metadata extraction for `Corpus/national/patents-act-1970/amendment_2005_en.pdf`:

```json
{
  "jurisdiction": "national",
  "act_name": "patents-act-1970",
  "document_type": "amendment",
  "version_year": "2005",
  "language": "en"
}
```
