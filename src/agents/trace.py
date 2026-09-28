"""Traceability: a record of everything that happened while answering a question.

Every tool and agent writes into one Trace. The UI shows it, so a user can
always answer:
    1. What data was used?                      -> calculations[*].population / sql
    2. Which variables?                         -> variables
    3. Which codebook definitions?              -> variables[*].definition / source
    4. What calculations?                       -> calculations
    5. Which external sources?                  -> external_sources
    6/7. Which statements are facts, which are interpretations? -> statements[*].kind
"""

import time
from dataclasses import asdict, dataclass, field

from src.data.variables import DERIVED_BY_NAME

# Statement kinds (shown as labels in the UI)
DATA_FACT = "FACT (dataset)"            # a number computed from the data by SQL/Python
DOC_FACT = "FACT (documentation)"       # stated in the codebook / project documentation
SOURCE_FACT = "FACT (external source)"  # stated by an external source, with a link
INFERENCE = "INFERENCE"                 # a rule-based or model-generated interpretation
CAVEAT = "CAVEAT"                       # a limitation the reader must know


@dataclass
class Statement:
    kind: str
    text: str
    evidence: list = field(default_factory=list)   # ids/urls this statement rests on


@dataclass
class Step:
    agent: str
    action: str           # e.g. "called tool", "decided", "retrieved"
    tool: str = ""
    detail: str = ""
    inputs: dict = field(default_factory=dict)
    seconds: float = 0.0


class Trace:
    def __init__(self, question):
        self.question = question
        self.mode = ""
        self.steps = []
        self.variables = {}          # name -> {"definition", "source"}
        self.calculations = []       # QueryResult / AnalysisResult dicts
        self.documents = []          # retrieved chunks
        self.external_sources = []   # {"title", "url", "via", "accessed"}
        self.statements = []
        self.tables = []             # {"title", "rows", "chart": {"x", "y"} or None}
        self.warnings = []
        self.llm_calls = []
        self._started = time.time()

    # --- recording ---------------------------------------------------------
    def step(self, agent, action, tool="", detail="", inputs=None, seconds=0.0):
        self.steps.append(Step(agent, action, tool, detail, inputs or {}, round(seconds, 2)))

    def add_variable(self, name, definition, source):
        if name and name not in self.variables:
            self.variables[name] = {"definition": definition, "source": source}

    def add_variables_from(self, names, variable_info):
        """Record codebook definitions (or project definitions for derived indicators)."""
        for name in names:
            if name.startswith("w "):
                self.add_variable("w", "survey weight = v005 / 1,000,000", "project methodology")
            elif name in DERIVED_BY_NAME:
                d = DERIVED_BY_NAME[name]
                self.add_variable(name, f"{d.description}: {d.rule} (universe: {d.universe})",
                                  "project definition (src/data/variables.py)")
            elif name in variable_info:
                self.add_variable(name, variable_info[name]["label"], "codebook (Stata file metadata)")

    def add_calculation(self, result_dict, chart=None):
        self.calculations.append(result_dict)
        if result_dict.get("rows"):
            self.tables.append({"title": result_dict["title"], "rows": result_dict["rows"], "chart": chart})

    def add_document(self, retrieved):
        if all(d["chunk_id"] != retrieved.chunk_id for d in self.documents):
            self.documents.append(asdict(retrieved))

    def add_source(self, title, url, via, accessed=None):
        if url and all(s["url"] != url for s in self.external_sources):
            self.external_sources.append({"title": title, "url": url, "via": via, "accessed": accessed})

    def say(self, kind, text, evidence=None):
        self.statements.append(Statement(kind, text, list(evidence or [])))

    def warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    # --- output ------------------------------------------------------------
    def to_dict(self):
        return {
            "question": self.question, "mode": self.mode,
            "seconds": round(time.time() - self._started, 2),
            "steps": [asdict(s) for s in self.steps],
            "variables": self.variables, "calculations": self.calculations,
            "documents": self.documents, "external_sources": self.external_sources,
            "statements": [asdict(s) for s in self.statements],
            "tables": self.tables, "warnings": self.warnings, "llm_calls": self.llm_calls,
        }

    def tools_used(self):
        """Tools that actually ran (not routing decisions or agent hand-offs)."""
        return sorted({s.tool for s in self.steps if s.tool and s.action in ("called tool", "retrieved")})

    def agents_used(self):
        seen = []
        for s in self.steps:
            if s.agent not in seen:
                seen.append(s.agent)
        return seen
