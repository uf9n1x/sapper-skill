"""离线 KB、信任级别与经验晋升（T-040）。

设计依据（升级方案 §8）：
- KB = 带元数据的本地 Markdown（python-frontmatter）：记录来源
  （source）、信任级别（trust: official/community/unverified）、
  适用版本（applies_to）与最后验证时间（last_verified）
- 冲突或过期知识必须展示警告（默认 180 天未验证 = EXPIRED）
- 晋升门禁：只有 latest verdict = confirmed 的假设才能晋升为 KB；
  晋升文本经过**去目标化硬校验**（含案件内任何原始目标串即拒绝），
  原始目标输出不得自动污染 KB
- 新晋升条目固定 trust: unverified——信任由后续验证提升，不虚标
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

import frontmatter

from prism import state

TRUST_LEVELS = ("official", "community", "unverified")
KB_PREFIX = "kb-"
DEFAULT_MAX_AGE_DAYS = 180

# 原始目标串抽取：IPv4 / 域名 / 主机名 / CIDR（用于去目标化校验）
_TARGET_TOKEN_RE = re.compile(
    r"\b(?:\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?"
    r"|[a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+)\b",
    re.IGNORECASE,
)


class KBError(ValueError):
    """KB 操作失败（无效 trust / 晋升门禁不通过等）。"""


def _today() -> _dt.date:
    return _dt.date.today()


def load_kb(kb_dir: Path) -> list[dict]:
    """加载全部 KB 条目（按 id 排序）；无效 trust 直接报错。"""
    entries: list[dict] = []
    if not kb_dir.is_dir():
        return entries
    for path in sorted(kb_dir.glob("*.md")):
        if not path.name.startswith(KB_PREFIX):
            continue
        post = frontmatter.load(str(path))
        meta = post.metadata
        trust = str(meta.get("trust", ""))
        if trust not in TRUST_LEVELS:
            raise KBError(
                f"invalid trust: {trust!r}（{path.name}，可选: {'/'.join(TRUST_LEVELS)}）"
            )
        entries.append(
            {
                "id": path.stem,
                "path": path,
                "meta": meta,
                "body": post.content,
            }
        )
    return entries


def is_expired(entry: dict, today: _dt.date | None = None) -> bool:
    """last_verified 距今超过 max_age 天视为过期（缺失日期视为过期）。"""
    today = today or _today()
    raw = str(entry["meta"].get("last_verified", ""))
    try:
        verified = _dt.date.fromisoformat(raw.strip())
    except ValueError:
        return True
    return (today - verified).days > DEFAULT_MAX_AGE_DAYS


def promote(
    case: Path,
    hypothesis_id: str,
    text_file: Path,
    kb_dir: Path,
    source_note: str = "",
    today: _dt.date | None = None,
) -> Path:
    """把已验证且去目标化的经验晋升为 KB 条目（unverified 起步）。

    门禁：latest verdict 必须 confirmed；文本（含 title/source）出现
    案件内任何原始目标串即拒绝。
    """
    today = today or _today()
    derived = state.replay(Path(case))
    verdict = derived.verdicts.get(hypothesis_id)
    if verdict is None or verdict.get("status") != "confirmed":
        status = (verdict or {}).get("status", "open")
        raise KBError(
            f"hypothesis {hypothesis_id} 不是 confirmed（当前 {status}），禁止晋升为 KB"
        )
    hyp = derived.hypotheses[hypothesis_id]

    text = text_file.read_text(encoding="utf-8")
    source_note = source_note or "engagement finding（已验证，已去目标化）"
    blob = f"{text}\n{source_note}"

    # 去目标化硬校验：案件内全部原始目标串（fact target / hypothesis scope /
    # intent target；产品标题不算目标，避免误伤 applies_to 文本）
    leak_tokens: set[str] = set()
    for record in derived.facts.values():
        leak_tokens.update(_target_tokens(str(record.get("target", ""))))
    for record in derived.hypotheses.values():
        leak_tokens.update(_target_tokens(str(record.get("scope", ""))))
    leak_tokens.discard("")
    leaks = sorted(token for token in leak_tokens if token in blob)
    if leaks:
        raise KBError(f"晋升文本泄漏原始目标，必须先去目标化: {', '.join(leaks[:5])}")

    # applies_to：取与假设 claim 有交集的服务/应用 fact 标题（如产品版本）
    applies_to = ""
    claim = str(hyp.get("claim", ""))
    for record in derived.facts.values():
        if record.get("kind") in ("service", "application"):
            title = str(record.get("title", ""))
            if title and any(
                token in claim.casefold() for token in _ascii_tokens(title)
            ):
                applies_to = title
                break

    title = claim
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    title = _detarget_default(title, leak_tokens, claim)

    slug = re.sub(r"[^a-z0-9-]", "-", hypothesis_id.lower()).strip("-") or "entry"
    base_name = f"{KB_PREFIX}{slug}-{today.strftime('%Y%m%d')}"
    path = kb_dir / f"{base_name}.md"
    counter = 2
    while path.exists():
        path = kb_dir / f"{base_name}-{counter}.md"
        counter += 1

    kb_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "title": title,
        "source": source_note,
        "trust": "unverified",  # 新晋升不虚标信任
        "applies_to": applies_to,
        "last_verified": today.isoformat(),
        "promoted_from": hypothesis_id,
        "tags": ["promoted"],
    }
    post = frontmatter.Post(text.strip() + "\n", metadata=metadata)
    path.write_text(frontmatter.dumps(post), encoding="utf-8", newline="\n")
    return path


def render_entry_text(entry: dict, today: _dt.date | None = None) -> str:
    """条目全文 + 强制警告（过期 / 未验证）。"""
    meta = entry["meta"]
    lines = [
        f"# {meta.get('title', entry['id'])}",
        f"- id: {entry['id']}",
        f"- source: {meta.get('source', '')}",
        f"- trust: {meta.get('trust', '')}",
        f"- applies_to: {meta.get('applies_to', '')}",
        f"- last_verified: {meta.get('last_verified', '')}",
    ]
    if is_expired(entry, today=today):
        lines.append(
            f"- WARNING: EXPIRED——最后验证已超过 {DEFAULT_MAX_AGE_DAYS} 天，"
            "使用前必须复核"
        )
    if meta.get("trust") == "unverified":
        lines.append("- WARNING: trust=unverified，未经独立验证，仅作线索")
    lines.append("")
    lines.append(entry["body"].strip())
    return "\n".join(lines) + "\n"


def _target_tokens(value: str) -> list[str]:
    """从目标字段抽取待检测串：主机/IP/CIDR 形态且长度 >= 4。"""
    return [
        token.lower() for token in _TARGET_TOKEN_RE.findall(value) if len(token) >= 4
    ]


def _ascii_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9.-]*", value.casefold())
        if len(token) >= 3
    ]


def _detarget_default(title: str, leak_tokens: set[str], fallback: str) -> str:
    """标题若含目标串则退回 claim（claim 本身也须过门禁）。"""
    if any(token in title for token in leak_tokens):
        return fallback
    return title
