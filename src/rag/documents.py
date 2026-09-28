"""Ingest and chunk the text knowledge that the RAG can retrieve.

A "chunk" is one retrievable piece of text plus metadata saying where it came
from. Chunk boundaries follow the documents' natural structure:

    codebook      -> one chunk per variable (repeated slots like b2_01..b2_20 merged)
    markdown docs -> one chunk per heading section (long sections split by paragraph)
    outreach KB   -> one chunk per organization (separate collection)

Structured numbers (the 724,115 rows) are deliberately NOT chunked or
embedded: numerical questions go to SQL, not to retrieval.
"""

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field

import pandas as pd

from src.config import CODEBOOK_PATH, DATA_DICTIONARY_MD, DOCUMENTS_DIR, OUTREACH_KB_PATH, ROOT

MAX_CHUNK_CHARS = 1800
MAX_LABELS_SHOWN = 30

# Markdown documents in the "docs" collection: (path, source type shown to users)
MARKDOWN_SOURCES = [
    (DATA_DICTIONARY_MD, "data dictionary"),
    (DOCUMENTS_DIR / "methodology.md", "methodology"),
    (ROOT / "docs" / "final_summary.md", "research notes (Analyses 1-6)"),
    (ROOT / "docs" / "analysis_map.md", "project documentation"),
]


@dataclass
class Chunk:
    id: str
    text: str
    source: str            # e.g. "codebook", "methodology"
    title: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Codebook
# ---------------------------------------------------------------------------
def format_labels(labels_json):
    if not labels_json:
        return "no value labels (the values are numbers or text)"
    labels = json.loads(labels_json)
    items = [f"{code} = {meaning}" for code, meaning in labels.items()]
    shown = "; ".join(items[:MAX_LABELS_SHOWN])
    if len(items) > MAX_LABELS_SHOWN:
        shown += f"; ... ({len(items)} codes in total)"
    return shown


def codebook_chunks(path=CODEBOOK_PATH):
    """One chunk per variable. Variables that repeat with a numeric suffix and
    identical labels (b2_01 ... b2_20 = "year of birth" for child 1..20) become
    one chunk, so retrieval isn't flooded with 20 near-identical results."""
    codebook = pd.read_csv(path, dtype=str, keep_default_na=False)
    groups = defaultdict(list)
    for row in codebook.itertuples():
        match = re.match(r"^(.+?)_(\d{1,2})$", row.variable_name)
        base = match.group(1) if match else row.variable_name
        groups[(base, row.variable_label, row.value_labels)].append(row)

    chunks = []
    for (base, label, labels_json), rows in groups.items():
        names = [r.variable_name for r in rows]
        if len(names) == 1:
            title = f"{names[0]}: {label}"
            name_text = f"Variable {names[0]}"
        else:
            title = f"{names[0]} ... {names[-1]}: {label}"
            name_text = (f"Variables {', '.join(names)} (the same question repeated {len(names)} times, "
                         f"once per slot, e.g. per child or per birth)")
        text = (f"{name_text}. Description (codebook label): {label or '(no label)'}. "
                f"Stata type: {rows[0].stata_type}. Value labels: {format_labels(labels_json)}.")
        chunks.append(Chunk(id=f"codebook:{names[0]}", text=text, source="codebook", title=title,
                            metadata={"variables": names, "label": label, "file": "docs/dhs_codebook.csv"}))
    return chunks


# ---------------------------------------------------------------------------
# Markdown documents
# ---------------------------------------------------------------------------
def split_long(text, limit=MAX_CHUNK_CHARS):
    """Split a long section into pieces at paragraph boundaries."""
    if len(text) <= limit:
        return [text]
    pieces, current = [], ""
    for paragraph in text.split("\n\n"):
        if current and len(current) + len(paragraph) > limit:
            pieces.append(current.strip())
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        pieces.append(current.strip())
    return pieces


def markdown_chunks(path, source):
    """One chunk per heading section. The heading path (e.g. 'Limitations')
    is kept in the chunk text so retrieval can match on it."""
    if not path.exists():
        return []
    text = path.read_text()
    relative = str(path.relative_to(ROOT))
    sections, heading, lines = [], path.stem, []
    for line in text.splitlines():
        if re.match(r"^#{1,4} ", line):
            if "\n".join(lines).strip():
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = line.lstrip("#").strip(), []
        else:
            lines.append(line)
    if "\n".join(lines).strip():
        sections.append((heading, "\n".join(lines).strip()))

    chunks = []
    for number, (heading, body) in enumerate(sections):
        for part_number, part in enumerate(split_long(body)):
            variables = sorted(set(re.findall(r"\b([vs]\d{3}[a-z]?|ssmod|sweight|sdist)\b", heading + " " + part)))
            chunks.append(Chunk(
                id=f"{relative}#{number}.{part_number}",
                text=f"{heading}\n\n{part}",
                source=source, title=f"{path.name} > {heading}",
                metadata={"file": relative, "heading": heading, "variables": variables},
            ))
    return chunks


def documentation_chunks():
    """Everything in the 'docs' collection."""
    chunks = codebook_chunks()
    for path, source in MARKDOWN_SOURCES:
        chunks += markdown_chunks(path, source)
    return chunks


# ---------------------------------------------------------------------------
# Outreach knowledge base (separate collection)
# ---------------------------------------------------------------------------
def load_outreach_kb(path=OUTREACH_KB_PATH):
    return json.loads(path.read_text())


def outreach_chunks(path=OUTREACH_KB_PATH):
    kb = load_outreach_kb(path)
    chunks = []
    for org in kb["organizations"]:
        geography = org["geography"]
        where = "national (all India)" if geography["scope"] == "national" else ", ".join(geography["states"])
        facts = " ".join(f["text"] for f in org["facts"])
        text = (f"{org['name']} ({org['type']}). Geography: {where}. {geography.get('detail', '')} "
                f"Channels: {', '.join(org['channels'])}. Stated work: {facts}")
        chunks.append(Chunk(id=f"outreach:{org['id']}", text=text, source="outreach knowledge base",
                            title=org["name"], metadata={"org_id": org["id"], "accessed": kb["accessed"]}))
    return chunks
