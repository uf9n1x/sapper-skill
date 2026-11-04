"""混合可解释召回（T-040）。

设计依据（升级方案 §8）：
- 混合召回：BM25（rank-bm25，jieba 分词处理中文）+ RapidFuzz 模糊
  匹配（产品别名/近似指纹）+ 结构化加权 + 一跳图扩展（限量）
- 可解释：每条命中返回 score breakdown 与命中原因
- 同时召回成功路径与失败路径（killed 假设 / blocked Intent 标注
  path=failure），避免不同 Worker 重复走死路
- Top-N 只给短摘要与 has_doc，详情按需 `prism.py doc <id>`
- 索引为每次调用内存重建（案件规模可控）；SQLite 物化缓存仍是
  可选优化，接口不变（ADR-0008 延迟决策继续有效）
"""

from __future__ import annotations

import re

import jieba
import pydantic
from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz

from prism import state

# 打分权重：BM25 为主，模糊匹配次之，结构化加权与图扩展为辅
_WEIGHT_BM25 = 0.6
_WEIGHT_FUZZY = 0.25
_WEIGHT_TARGET = 0.10
_WEIGHT_GRAPH = 0.30
# 低于该总分的命中不返回（噪声过滤）
_MIN_SCORE = 0.05
_SNIPPET_LIMIT = 160
_GRAPH_EXTRA_LIMIT = 5

_ASCII_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.:/_-]*")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# 文本中出现的主机形态（IPv4 / 域名 / 单标签主机名），用于资产族关联
_HOST_RE = re.compile(
    r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|[a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+)\b",
    re.IGNORECASE,
)


class RecallError(ValueError):
    """召回失败（空查询等）。"""


class RecallHit(pydantic.BaseModel):
    """单条召回命中：短摘要 + 可解释打分。"""

    id: str
    type: str
    title: str
    snippet: str
    score: float
    breakdown: dict[str, float]
    reasons: list[str]
    status: str
    path: str  # success / failure / neutral
    has_doc: bool


class _Doc:
    """召回语料条目（内部结构）。"""

    __slots__ = ("hosts", "ref", "target", "text", "title", "tokens", "type")

    def __init__(self, ref: str, type_: str, title: str, text: str, target: str):
        self.ref = ref
        self.type = type_
        self.title = title
        self.text = text
        self.target = target
        self.tokens = tokenize(f"{title} {text} {target}")
        self.hosts = {
            match.group(0).lower() for match in _HOST_RE.finditer(f"{target} {text}")
        }


def tokenize(text: str) -> list[str]:
    """中英文混合分词：ASCII 词元 + jieba 中文词元（去纯标点）。"""
    lowered = text.casefold()
    tokens = _ASCII_TOKEN_RE.findall(lowered)
    for word in jieba.lcut(lowered):
        if _CJK_RE.search(word):
            tokens.append(word)
    return tokens


def _snippet(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:_SNIPPET_LIMIT]


def _family_hosts(doc: _Doc) -> set[str]:
    """资产族键：文档文本中出现的全部主机标识。"""
    return doc.hosts


def _build_docs(derived: state.DerivedState) -> list[_Doc]:
    docs: list[_Doc] = []
    for fact_id in sorted(derived.facts):
        record = derived.facts[fact_id]
        data_values = " ".join(str(v) for v in record.get("data", {}).values())
        docs.append(
            _Doc(
                ref=fact_id,
                type_="fact",
                title=str(record.get("title", "")),
                text=f"{record.get('summary', '')} {data_values}".strip(),
                target=str(record.get("target", "")),
            )
        )
    for hyp_id in sorted(derived.hypotheses):
        record = derived.hypotheses[hyp_id]
        disprove = " ".join(record.get("disprove_if", []))
        docs.append(
            _Doc(
                ref=hyp_id,
                type_="hypothesis",
                title=str(record.get("claim", "")),
                text=f"{record.get('scope', '')} 证伪条件: {disprove}".strip(),
                target=str(record.get("scope", "")),
            )
        )
    for intent_id in sorted(derived.intents):
        entry = derived.intents[intent_id]
        docs.append(
            _Doc(
                ref=intent_id,
                type_="intent",
                title=str(entry.get("title", "")),
                text=f"{entry.get('objective', '')} {entry.get('angle', '')}".strip(),
                target=str(entry.get("target", "")),
            )
        )
    return docs


def _resolve_status_path(
    ref: str, type_: str, derived: state.DerivedState
) -> tuple[str, str]:
    """返回 (status, path)。失败路径 = killed 假设 / blocked Intent。"""
    if type_ == "hypothesis":
        verdict = derived.verdicts.get(ref)
        if verdict is None:
            return "open", "neutral"
        status = str(verdict.get("status", "open"))
        path = (
            "success"
            if status == "confirmed"
            else ("failure" if status == "killed" else "neutral")
        )
        return status, path
    if type_ == "intent":
        entry = derived.intents.get(ref, {})
        status = str(entry.get("status", "created"))
        path = (
            "failure"
            if status in ("blocked", "cancelled")
            else ("success" if status == "completed" else "neutral")
        )
        return status, path
    return "n/a", "neutral"


def recall(case: str | state.DerivedState, query: str, top: int = 5) -> dict:
    """混合召回：BM25 + 模糊 + 结构化加权 + 一跳图扩展。"""
    derived = case if isinstance(case, state.DerivedState) else state.replay(case)
    query = (query or "").strip()
    if not query:
        raise RecallError("query 不能为空")
    q_tokens = tokenize(query)
    if not q_tokens:
        raise RecallError(f"query 无法分词: {query!r}")

    docs = _build_docs(derived)
    if not docs:
        return {"query": query, "hits": []}

    corpus = [doc.tokens for doc in docs]
    bm25 = BM25Okapi(corpus)
    bm_scores = bm25.get_scores(q_tokens)
    max_bm = max(bm_scores) if max(bm_scores) > 0 else 1.0
    q_lower = query.casefold()

    scored: list[tuple[float, dict[str, float], list[str], _Doc]] = []
    for doc, bm_raw in zip(docs, bm_scores):
        breakdown: dict[str, float] = {}
        reasons: list[str] = []
        bm_norm = bm_raw / max_bm
        if bm_norm > 0.01:
            breakdown["bm25"] = round(_WEIGHT_BM25 * bm_norm, 4)
            reasons.append(f"BM25 命中（归一化 {bm_norm:.2f}）")
        fuzzy = (
            max(
                fuzz.partial_ratio(q_lower, doc.title.casefold()),
                fuzz.partial_ratio(q_lower, doc.text.casefold()),
            )
            / 100.0
        )
        if fuzzy >= 0.5:
            breakdown["fuzzy"] = round(_WEIGHT_FUZZY * fuzzy, 4)
            reasons.append(f"模糊匹配标题/摘要（{fuzzy:.2f}）")
        target_blob = f"{doc.target} {doc.text}".casefold()
        target_boost = sum(_WEIGHT_TARGET for token in q_tokens if token in target_blob)
        if target_boost:
            breakdown["target"] = round(min(target_boost, _WEIGHT_TARGET * 2), 4)
            reasons.append("结构化加权：target/产品字段命中")
        score = sum(breakdown.values())
        scored.append((score, breakdown, reasons, doc))

    scored.sort(key=lambda item: (-item[0], item[3].ref))
    selected = [
        (score, breakdown, reasons, doc)
        for score, breakdown, reasons, doc in scored[:top]
        if score >= _MIN_SCORE
    ]
    selected_refs = {doc.ref for _, _, _, doc in selected}

    # 一跳图扩展：与命中共享资产族的邻居（限量，标注原因）
    family_hosts: set[str] = set()
    for _, _, _, doc in selected:
        family_hosts |= _family_hosts(doc)
    graph_added = 0
    for score, breakdown, reasons, doc in scored:
        if graph_added >= _GRAPH_EXTRA_LIMIT:
            break
        if doc.ref in selected_refs:
            continue
        if _family_hosts(doc) & family_hosts:
            hit_breakdown = dict(breakdown)
            hit_breakdown["graph"] = _WEIGHT_GRAPH
            selected.append(
                (
                    score + _WEIGHT_GRAPH,
                    hit_breakdown,
                    [
                        *reasons,
                        f"图扩展：与命中记录共享资产族（一跳，上限 {_GRAPH_EXTRA_LIMIT}）",
                    ],
                    doc,
                )
            )
            selected_refs.add(doc.ref)
            graph_added += 1

    hits = []
    for total, breakdown, reasons, doc in selected:
        status, path = _resolve_status_path(doc.ref, doc.type, derived)
        has_doc = False
        if doc.type == "fact":
            has_doc = bool(derived.facts[doc.ref].get("doc_path"))
        hits.append(
            RecallHit(
                id=doc.ref,
                type=doc.type,
                title=doc.title,
                snippet=_snippet(doc.text),
                score=round(total, 4),
                breakdown=breakdown,
                reasons=reasons,
                status=status,
                path=path,
                has_doc=has_doc,
            )
        )
    hits.sort(key=lambda hit: (-hit.score, hit.id))
    return {"query": query, "hits": [hit.model_dump() for hit in hits]}


def doc_detail(case, record_id: str) -> str:
    """按需读取详情：有 doc_path/artifact 则返回文件内容，否则记录 JSON。"""
    import json as _json

    derived = case if isinstance(case, state.DerivedState) else state.replay(case)
    if record_id in derived.facts:
        record = derived.facts[record_id]
        doc_path = record.get("doc_path")
        if doc_path:
            return _read_case_file(case, str(doc_path))
        return _json.dumps(record, ensure_ascii=False, indent=2)
    if record_id in derived.hypotheses:
        record = dict(derived.hypotheses[record_id])
        verdict = derived.verdicts.get(record_id)
        if verdict:
            record["latest_verdict"] = verdict
        return _json.dumps(record, ensure_ascii=False, indent=2)
    if record_id in derived.intents:
        return _json.dumps(derived.intents[record_id], ensure_ascii=False, indent=2)
    if record_id in derived.evidence_by_id:
        record = derived.evidence_by_id[record_id]
        artifact = getattr(record, "artifact", None)
        if artifact:
            return _read_case_file(case, artifact)
        return _json.dumps(record.model_dump(), ensure_ascii=False, indent=2)
    raise RecallError(f"未知记录 ID: {record_id}")


def _read_case_file(case, relative: str) -> str:
    from pathlib import Path as _Path

    base = case if isinstance(case, _Path) else _Path(case)
    normalized = relative.replace("\\", "/")
    if normalized.startswith("/") or any(
        part == ".." for part in normalized.split("/")
    ):
        raise RecallError(f"路径必须为 case 内相对路径: {relative}")
    path = base / normalized
    if not path.is_file():
        raise RecallError(f"文件不存在: {relative}")
    return path.read_text(encoding="utf-8")
