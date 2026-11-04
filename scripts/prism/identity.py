"""资产归一化与跨工具去重（T-032）。

设计依据（升级方案 §5）：
- 规范化 IP、IDNA 域名、URL、端口，使同一资产在不同工具输出下
  产生相同的**确定性资产键**（asset key）
- 跨工具去重只按确定性规则合并（相同资产键 / 别名归并），合并依据
  必须可解释（merge_reason）
- 名称模糊相似度只用于产生**待审查队列**（review queue），永不静默
  合并：低置信匹配不自动合并是硬红线
- 合并结果确定性：与输入顺序无关（按资产键排序输出）
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

import pydantic
from rapidfuzz import fuzz

# 模糊相似度合并阈值：>= MERGE_SCORE 才允许跨键合并提议，
# [REVIEW_SCORE, MERGE_SCORE) 只进待审查队列，< REVIEW_SCORE 视为无关。
MERGE_SCORE = 88.0
REVIEW_SCORE = 70.0

_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
# host:port[/proto] 形态（服务目标）
_SERVICE_TARGET_RE = re.compile(
    r"^(?P<host>[^:/\s]+):(?P<port>\d{1,5})(?:/(?P<proto>tcp|udp))?$"
)
_ASCII_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class IdentityError(ValueError):
    """目标无法归一化。"""


class Normalized(pydantic.BaseModel):
    """归一化结果：key 是确定性资产键，kind 是形态类别。"""

    key: str
    kind: str  # ip / domain / url
    original: str


class Candidate(pydantic.BaseModel):
    """候选事实（parser 产出，合并后成为 digest 条目）。"""

    kind: str
    target: str
    title: str
    summary: str
    confidence: float = pydantic.Field(default=0.5, ge=0.0, le=1.0)
    source: str = ""
    requires_verification: bool = False
    data: dict[str, str | int | float | bool] = pydantic.Field(default_factory=dict)
    # 合并阶段填充
    sources: list[str] = pydantic.Field(default_factory=list)
    asset_key: str = ""
    merge_reason: str = ""


class ReviewItem(pydantic.BaseModel):
    """待审查条目：相似但未合并的候选对，附可解释评分。"""

    left: str
    right: str
    kind: str
    score: float
    reason: str


def normalize_host(value: str) -> Normalized:
    """归一化单个主机标识（IPv4 / IPv6 / 域名，域名做 IDNA）。"""
    text = value.strip().rstrip(".").lower()
    if not text:
        raise IdentityError(f"空主机名: {value!r}")
    if _IPV4_RE.match(text):
        try:
            ipaddress.IPv4Address(text)
        except ValueError as exc:
            raise IdentityError(f"非法 IPv4: {value!r}") from exc
        return Normalized(key=f"ip:{text}", kind="ip", original=value)
    try:
        ipaddress.ip_address(text)
    except ValueError:
        pass
    else:
        # IPv6 等其余形态：统一为压缩小写形式
        return Normalized(
            key=f"ip:{ipaddress.ip_address(text)}", kind="ip", original=value
        )
    labels = text.split(".")
    kind = "domain" if len(labels) >= 2 else "host"  # 单标签 = 内网主机名
    puny_labels = []
    for label in labels:
        if not label:
            raise IdentityError(f"空域名标签: {value!r}")
        if _ASCII_LABEL_RE.match(label):
            puny_labels.append(label)
        elif all(ord(ch) > 127 for ch in label):
            try:
                puny_labels.append(label.encode("idna").decode("ascii").lower())
            except UnicodeError as exc:
                raise IdentityError(f"IDNA 编码失败: {value!r}") from exc
        else:
            raise IdentityError(f"主机名含非法字符: {value!r}")
    domain = ".".join(puny_labels)
    return Normalized(key=f"{kind}:{domain}", kind=kind, original=value)


def normalize_target(value: str) -> Normalized:
    """归一化 URL（小写 scheme/host，去默认端口、query、fragment）。"""
    text = value.strip()
    if "://" not in text:
        return normalize_host(text)
    parts = urlsplit(text)
    if not parts.scheme or not parts.hostname:
        raise IdentityError(f"非法 URL: {value!r}")
    scheme = parts.scheme.lower()
    host = (
        normalize_host(parts.hostname).key.removeprefix("domain:").removeprefix("ip:")
    )
    port = parts.port
    default = {"http": 80, "https": 443}.get(scheme)
    netloc = host if port in (None, default) else f"{host}:{port}"
    path = parts.path.rstrip("/") if parts.path.rstrip("/") != "/" else ""
    canonical = urlunsplit((scheme, netloc, path, "", ""))
    return Normalized(key=f"url:{canonical}", kind="url", original=value)


def service_key(host: str, port: int, proto: str = "tcp") -> str:
    """服务形态的确定性资产键：service:<host>:<port>/<proto>。"""
    return f"service:{normalize_host(host).key.split(':', 1)[1]}:{port}/{proto.lower()}"


def parse_service_target(value: str) -> tuple[str, int, str] | None:
    """解析 host:port[/proto] 形态，非该形态返回 None。"""
    match = _SERVICE_TARGET_RE.match(value.strip())
    if match is None:
        return None
    port = int(match.group("port"))
    if port > 65535:
        return None
    return match.group("host"), port, match.group("proto") or "tcp"


def _canonical_host(host: str, alias_to_primary: dict[str, str]) -> str:
    canonical = normalize_host(host).key.split(":", 1)[1]
    return alias_to_primary.get(canonical, canonical)


def asset_key(candidate: Candidate, alias_to_primary: dict[str, str]) -> str:
    """计算候选的确定性资产键（先服务形态，再 URL，再主机）。"""
    service = parse_service_target(candidate.target)
    if service is not None:
        host, port, proto = service
        return service_key(_canonical_host(host, alias_to_primary), port, proto)
    if "://" in candidate.target:
        try:
            return normalize_target(candidate.target).key
        except IdentityError:
            pass
    try:
        return normalize_host(candidate.target).key
    except IdentityError as exc:
        raise IdentityError(f"候选目标无法归一化: {candidate.target!r}") from exc


def similarity(title_a: str, title_b: str) -> float:
    """标题模糊相似度（0-100，大小写不敏感，token 排序）。"""
    return fuzz.token_sort_ratio(title_a.casefold(), title_b.casefold())


def _alias_to_primary(aliases: dict[str, list[str]]) -> dict[str, str]:
    """aliases: primary -> [alias...]；反转成 alias -> primary 查找表。"""
    table: dict[str, str] = {}
    for primary, names in aliases.items():
        try:
            canon_primary = normalize_host(primary).key.split(":", 1)[1]
        except IdentityError:
            continue
        for name in names:
            try:
                table[normalize_host(name).key.split(":", 1)[1]] = canon_primary
            except IdentityError:
                continue
    return table


def merge(
    candidates: list[Candidate], aliases: dict[str, list[str]] | None = None
) -> tuple[list[Candidate], list[ReviewItem]]:
    """确定性合并候选。

    - 相同资产键（含别名归并）→ 合并为一个候选，sources 取并集，
      merge_reason 说明依据；键内顺序按首次出现，组间按键排序（确定性）
    - 不同键但标题相似度落在审查带 → 生成 ReviewItem，绝不静默合并
    """
    table = _alias_to_primary(aliases or {})
    keyed: list[tuple[str, Candidate]] = []
    for candidate in candidates:
        keyed.append((asset_key(candidate, table), candidate))

    groups: dict[str, list[Candidate]] = {}
    order: list[str] = []
    for key, candidate in keyed:
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(candidate)

    merged: list[Candidate] = []
    for key in sorted(groups):
        members = groups[key]
        head = members[0].model_copy(deep=True)
        head.asset_key = key
        head.sources = list(dict.fromkeys(m.source for m in members if m.source))
        if len(members) > 1:
            head.confidence = max(m.confidence for m in members)
            head.merge_reason = (
                f"相同资产键 {key}（来源: {', '.join(head.sources)}；"
                f"共 {len(members)} 条候选合并）"
            )
            head.summary = head.summary
        merged.append(head)

    # 跨键相似审查：每组取代表（首个成员），同 kind 才比较，避免 O(n²) 爆炸
    review: list[ReviewItem] = []
    seen_pairs: set[tuple[str, str]] = set()
    for i, key_a in enumerate(order):
        for key_b in order[i + 1 :]:
            rep_a, rep_b = groups[key_a][0], groups[key_b][0]
            if rep_a.kind != rep_b.kind:
                continue
            pair = tuple(sorted((key_a, key_b)))
            if pair in seen_pairs:
                continue
            score = similarity(rep_a.title, rep_b.title)
            if REVIEW_SCORE <= score < MERGE_SCORE:
                seen_pairs.add(pair)
                review.append(
                    ReviewItem(
                        left=key_a,
                        right=key_b,
                        kind=rep_a.kind,
                        score=round(score, 1),
                        reason=(
                            f"标题相似（{score:.0f}）但资产键不同且无别名证据，"
                            f"不自动合并，需人工/Agent 复核"
                        ),
                    )
                )
    review.sort(key=lambda item: (item.kind, -item.score, item.left, item.right))
    return merged, review
