"""Output models of the tools: each becomes a tool's output schema, and every field is described there."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["certified", "not_certified", "no_verdict"]


class Page(BaseModel):
    total: int = Field(description="Matches in all")
    count: int = Field(description="Matches in this page")
    offset: int = Field(description="Index of the first match of this page")
    has_more: bool = Field(description="True when more matches follow")
    next_offset: int | None = Field(default=None, description="Offset of the next page, if any")


class ProblemSummary(BaseModel):
    id: str
    title: str
    family: str = Field(description="constant, ramsey, spherical-code, covering-design, vehicle-routing or "
                                    "constant-weight-code")
    objective: Literal["maximize", "minimize"]
    best_known: str = Field(description="Best value on the source page or table, as printed there")
    verified_in_review: str | None = Field(default=None, description="Best value still in review whose certificate we "
                                                                "replayed, if any")


class ProblemList(Page):
    problems: list[ProblemSummary]
    families: dict[str, int] = Field(description="Problems per family in the whole benchmark")
    data_as_of: str


class ReferenceValue(BaseModel):
    value: str = Field(description="As printed by the source")
    exact: str | None = Field(default=None, description="Exact value (fraction or decimal) when known")
    source: str


class BestKnown(ReferenceValue):
    read: str = Field(description="When it was read: the date the source states, or the page commit it names, and "
                                  "the date of the problem file")


class CheckerInfo(BaseModel):
    program: str
    args: list[str]
    value_kind: str
    exactness: str = Field(description="What kind of number the score is")
    score_meaning: str
    standalone: str = Field(description="How to run the same checker yourself from the public benchmark")
    docs_uri: str
    source_uri: str


class ReferenceCertificate(BaseModel):
    file: str
    uri: str = Field(description="Resource URI of the certificate")
    description: str
    expected: list[str] = Field(description="Verdicts the benchmark's test.sh expects: page best, then verified in "
                                            "review")


class ProblemDetail(BaseModel):
    id: str
    title: str
    family: str
    page: str = Field(description="The source page or table")
    statement: str
    objective: Literal["maximize", "minimize"]
    submission: str = Field(description="The certificate format the checker reads")
    checker: CheckerInfo
    best_known: BestKnown
    verified_in_review: list[ReferenceValue]
    claimed_not_replayed: list[ReferenceValue] = Field(description="Claims nobody has replayed; never compared")
    improvement_rule: str
    reference_certificates: list[ReferenceCertificate]
    instance: dict[str, str] | None = Field(default=None, description="Routing problems: the CVRPLIB instance file the "
                                                                 "checker needs, its SHA-256 and where it was found")
    data_as_of: str


class Comparison(BaseModel):
    reference: Literal["page best", "verified in review"]
    value: str = Field(description="The reference value as printed")
    threshold: str = Field(description="The exact value to beat (fraction p/q or integer)")
    source: str
    improves: bool


class CheckerRun(BaseModel):
    program: str
    exit_code: int | None
    seconds: float
    peak_memory_mb: float | None = Field(default=None, description="Largest memory sample seen")
    output_tail: str = Field(description="The checker's last lines, local paths removed")


class LimitsInfo(BaseModel):
    timeout_s: int
    memory_mb: int
    memory_cap: str = Field(description="How the memory cap is enforced on this platform")
    max_bytes: int


class CheckResult(BaseModel):
    problem_id: str
    verdict: Verdict = Field(description="certified: the checker proved the value; not_certified: the certificate is "
                                         "invalid; no_verdict: a limit stopped the check, nothing was proved")
    reason: str | None = Field(default=None, description="Why it is not certified, or which limit stopped it")
    value: str | None = Field(default=None, description="The exact score (fraction p/q or integer)")
    value_decimal: str | None = Field(default=None, description="The score truncated to 20 decimals, for reading")
    exactness: str
    score_meaning: str
    objective: Literal["maximize", "minimize"]
    improves_page_best: bool | None = None
    improves_verified_in_review: bool | None = Field(default=None, description="Beats every verified value still in "
                                                                          "review (None when there is none)")
    comparisons: list[Comparison]
    certificate_sha256: str
    certificate_bytes: int
    checker: CheckerRun
    limits: LimitsInfo
    reproduce: str = Field(description="Commands that re-run this check with the public benchmark")
    data_as_of: str


class CompareResult(BaseModel):
    problem_id: str
    objective: Literal["maximize", "minimize"]
    value: str = Field(description="The value read exactly")
    value_decimal: str
    improves_page_best: bool
    improves_verified_in_review: bool | None
    comparisons: list[Comparison]
    claimed_not_replayed: list[ReferenceValue]
    best_known_read: str
    note: str
    data_as_of: str


class SearchHit(BaseModel):
    area: str
    name: str
    ours: str | None
    previous: str | None = Field(default=None, description="The best known value before ours")
    status: str = Field(description="listed (in the table), sent (to its keeper) or queued (next batch)")
    status_date: str | None
    found: str | None = Field(default=None, description="Date the result was found")
    venue: str = Field(description="The table that keeps the problem")
    venue_url: str | None
    data_url: str | None = Field(default=None, description="Where the certificate or object is")
    slug: str = Field(description="Use with cite(target='result', id=slug)")


class CoveringArrayEntry(BaseModel):
    t: int
    k: int
    v: int
    N: int = Field(description="Rows of our covering array, the smallest known size")
    previous_N: int = Field(description="The table's best size without our rows")
    family_rows_k: int = Field(description="Columns of our listed family row that gives this entry")
    source: str


class SearchResult(Page):
    interpreted_as: str = Field(description="How the query was read")
    results: list[SearchHit]
    covering_array_entries: list[CoveringArrayEntry]
    citation: str
    data_as_of: str


class ReplayMatch(BaseModel):
    heading: str
    date: str | None
    constants: list[str]
    readme_url: str
    folder_urls: list[str]
    summary: str
    rows: list[str] = Field(description="Table rows of the replay that match the query")
    checks: list[str] = Field(description="Our checking programs")
    results: list[str] = Field(description="Output files of the replay")
    rederive: list[str] = Field(description="Shell commands that re-derive the replay from scratch")


class AsteriskRow(BaseModel):
    constant: str
    tag: str
    bound: str
    status_class: str = Field(description="Class in the asterisk index: (a) replay posted, (b) certificate with only "
                                          "the claimant's checks, (c) no machine-checkable certificate, (d) a limit "
                                          "value starred by convention")
    prs: list[int]


class ReplayResult(BaseModel):
    found: bool
    query: str
    matches: list[ReplayMatch]
    asterisk_rows: list[AsteriskRow]
    asterisk_snapshot: str | None
    replays_commit: str
    note: str


class CitationResult(BaseModel):
    target: str
    id: str | None
    bibtex: str | None
    text: str | None
    cff: str | None = Field(default=None, description="CITATION.cff text (benchmark, dataset and server)")


class GymEnvironment(BaseModel):
    id: str
    problem_id: str | None = None
    description: str = ""


class GymEnvironments(BaseModel):
    backend: str
    environments: list[GymEnvironment]


class GymVerdict(BaseModel):
    env_id: str
    verdict: str = Field(description="The gym's exact verdict")
    score: str | None = Field(default=None, description="The exact score, if the object passed")
    details: dict[str, str] = Field(default_factory=dict)
