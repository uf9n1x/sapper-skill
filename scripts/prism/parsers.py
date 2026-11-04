"""工具输出解析为候选事实与证据引用（T-032）。

设计依据（升级方案 §5）：
- 首批 parser：Nmap XML、Masscan JSON、httpx JSONL、Nuclei JSONL、
  通用 JSON；registry 可扩展（BloodHound 等大数据后续独立 parser）
- parser 是**纯文本解析**：不执行原始输出中包含的任何指令，
  非结构化内容（如 XML 注释）不进入 digest
- 原始输出中的秘密默认脱敏（password/token/api_key/Bearer/sk- 等）
- 扫描器告警（Nuclei 等）只能是 vulnerability_lead 候选，
  requires_verification=True 且 confidence 上限受限——永远不自动成为
  confirmed Finding
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable

import pydantic

from prism import identity

# 扫描器告警的置信度上限（无论告警自称多严重）
MAX_SCANNER_CONFIDENCE = 0.5
# 单次解析产出候选上限（防止超大扫描拖垮控制面）
MAX_TOTAL_CANDIDATES = 2000

_NUCLEI_SEVERITY_CONFIDENCE = {
    "critical": 0.50,
    "high": 0.45,
    "medium": 0.40,
    "low": 0.35,
    "info": 0.30,
}

# 秘密脱敏：键值形态（password=xxx / token: xxx 等）与常见令牌前缀
_SECRET_KV_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|api[_-]?key|secret|authorization)"
    r"(\s*[:=]\s*)([^\s;,&\"'<>]{4,})"
)
_SECRET_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._-]{8,}")
_SECRET_PREFIX_RE = re.compile(r"(?i)\b(sk|pk|ghp|gho|xoxb|xoxp|akia)-?[a-z0-9]{10,}")
_REDACTED = "[REDACTED]"


class ParseError(ValueError):
    """解析失败或未知格式。"""


class ParseOutput(pydantic.BaseModel):
    """单次解析产物：候选事实 + 别名表 + 备注（不含原始日志）。"""

    tool: str
    format: str
    candidates: list[identity.Candidate] = pydantic.Field(default_factory=list)
    aliases: dict[str, list[str]] = pydantic.Field(default_factory=dict)
    notes: list[str] = pydantic.Field(default_factory=list)


def redact(text: str) -> str:
    """对字符串做秘密脱敏（键值、Bearer、常见令牌前缀）。"""
    text = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", text)
    text = _SECRET_BEARER_RE.sub(_REDACTED, text)
    text = _SECRET_PREFIX_RE.sub(_REDACTED, text)
    return text


def _clean(candidate: identity.Candidate) -> identity.Candidate:
    """对候选的全部字符串字段做脱敏与长度裁剪。"""
    for field in ("target", "title", "summary"):
        setattr(candidate, field, redact(getattr(candidate, field))[:500])
    candidate.data = {
        str(redact(str(k))[:80]): redact(str(v))[:300] if isinstance(v, str) else v
        for k, v in candidate.data.items()
    }
    return candidate


def _parse_nmap_xml(raw: str) -> ParseOutput:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ParseError(f"Nmap XML 解析失败: {exc}") from exc
    candidates: list[identity.Candidate] = []
    aliases: dict[str, list[str]] = {}
    notes: list[str] = []
    first_ip: str | None = None
    for host in root.iter("host"):
        address = host.find("address")
        if address is None or address.get("addrtype") != "ipv4":
            continue
        ip = address.get("addr", "")
        if first_ip is None:
            first_ip = ip
        osmatch = host.find("./os/osmatch")
        os_name = osmatch.get("name") if osmatch is not None else None
        data: dict[str, str | int | float | bool] = {}
        if os_name:
            data["os"] = os_name
        names = [
            h.get("name", "")
            for h in host.findall("./hostnames/hostname")
            if h.get("name")
        ]
        if names:
            aliases.setdefault(ip, []).extend(names)
            data["hostname"] = names[0]
        candidates.append(
            _clean(
                identity.Candidate(
                    kind="asset",
                    target=ip,
                    title=f"主机 {ip}",
                    summary=f"存活主机 {ip}" + (f"，OS: {os_name}" if os_name else ""),
                    confidence=0.9,
                    source="nmap-xml",
                    data=data,
                )
            )
        )
        for port in host.findall("./ports/port"):
            state_el = port.find("state")
            if state_el is None or state_el.get("state") != "open":
                continue
            service = port.find("service")
            port_id = port.get("portid", "")
            proto = port.get("protocol", "tcp")
            name = (service.get("name") if service is not None else "") or "unknown"
            product = (service.get("product") if service is not None else "") or ""
            version = (service.get("version") if service is not None else "") or ""
            extra = (service.get("extrainfo") if service is not None else "") or ""
            title = " ".join(part for part in (name, product, version) if part)
            data_sv: dict[str, str | int | float | bool] = {"port": int(port_id)}
            if product:
                data_sv["product"] = product
            if version:
                data_sv["version"] = version
            if extra:
                data_sv["extrainfo"] = extra
            candidates.append(
                _clean(
                    identity.Candidate(
                        kind="service",
                        target=f"{ip}:{port_id}/{proto}",
                        title=title or f"{name} 服务",
                        summary=f"{ip} {proto}/{port_id} 开放：{title}",
                        confidence=0.85,
                        source="nmap-xml",
                        data=data_sv,
                    )
                )
            )
    # run 级 hostname（样例/简化输出）：挂到首个已知主机
    for hostname in root.iter("hostname"):
        name = hostname.get("name", "")
        if name and first_ip:
            known = aliases.setdefault(first_ip, [])
            if name not in known:
                known.append(name)
    runstats = root.find("./runstats")
    if runstats is not None:
        notes.append(
            f"nmap 汇总: up={runstats.get('up', '?')} total={runstats.get('total', '?')}"
        )
    return ParseOutput(
        tool=root.get("scanner", "nmap"),
        format="nmap-xml",
        candidates=candidates,
        aliases=aliases,
        notes=notes,
    )


def _parse_masscan_json(raw: str) -> ParseOutput:
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Masscan JSON 解析失败: {exc}") from exc
    if not isinstance(records, list):
        raise ParseError("Masscan JSON 顶层必须是数组")
    candidates: list[identity.Candidate] = []
    for record in records:
        ip = str(record.get("ip", ""))
        if not ip:
            continue
        for port in record.get("ports", []):
            port_num = port.get("port")
            proto = port.get("proto", "tcp")
            candidates.append(
                _clean(
                    identity.Candidate(
                        kind="service",
                        target=f"{ip}:{port_num}/{proto}",
                        title=f"{proto} 端口开放",
                        summary=f"masscan 发现 {ip}:{port_num}/{proto} 开放",
                        confidence=0.8,
                        source="masscan-json",
                        data={"port": port_num},
                    )
                )
            )
    return ParseOutput(tool="masscan", format="masscan-json", candidates=candidates)


def _iter_jsonl(raw: str) -> list[dict]:
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParseError(f"JSONL 行解析失败: {exc}") from exc
        if not isinstance(entry, dict):
            raise ParseError("JSONL 每行必须是 JSON 对象")
        entries.append(entry)
    return entries


def _parse_httpx_jsonl(raw: str) -> ParseOutput:
    candidates: list[identity.Candidate] = []
    for entry in _iter_jsonl(raw):
        url = str(entry.get("url", "")).strip()
        host = str(entry.get("host", "")).strip()
        target = url or host
        if not target:
            continue
        status = entry.get("status_code")
        webserver = str(entry.get("webserver", "") or "")
        tech = entry.get("tech") or []
        title_page = str(entry.get("title", "") or "")
        parts = [f"HTTP {status}" if status is not None else ""]
        if webserver:
            parts.append(f"server: {webserver}")
        if tech:
            parts.append("tech: " + ",".join(str(t) for t in tech))
        summary = " ".join(part for part in parts if part) or "httpx 探测存活"
        candidates.append(
            _clean(
                identity.Candidate(
                    kind="application",
                    target=target,
                    title=title_page or host or target,
                    summary=summary,
                    confidence=0.8,
                    source="httpx-jsonl",
                    data={
                        key: value
                        for key, value in {
                            "status": status if isinstance(status, int) else None,
                            "webserver": webserver,
                            "tech": ",".join(str(t) for t in tech),
                        }.items()
                        if value not in (None, "")
                    },
                )
            )
        )
    return ParseOutput(tool="httpx", format="httpx-jsonl", candidates=candidates)


def _parse_nuclei_jsonl(raw: str) -> ParseOutput:
    candidates: list[identity.Candidate] = []
    for entry in _iter_jsonl(raw):
        info = entry.get("info") or {}
        severity = str(info.get("severity", "info")).lower()
        name = str(info.get("name", "") or "未命名模板")
        template_id = str(entry.get("template-id", "") or "")
        host = str(entry.get("host", "") or entry.get("matched-at", ""))
        if not host:
            continue
        candidates.append(
            _clean(
                identity.Candidate(
                    kind="vulnerability_lead",
                    target=host,
                    title=name,
                    summary=f"nuclei [{severity}] {template_id}: {name}（扫描器告警，需验证）",
                    confidence=_NUCLEI_SEVERITY_CONFIDENCE.get(
                        severity, MAX_SCANNER_CONFIDENCE
                    ),
                    source="nuclei-jsonl",
                    requires_verification=True,  # 硬红线：告警不是 confirmed
                    data={"template_id": template_id, "severity": severity},
                )
            )
        )
    return ParseOutput(tool="nuclei", format="nuclei-jsonl", candidates=candidates)


def _walk_json(value, depth: int = 0) -> list[dict]:
    """递归收集含 host/ip 键的对象（浅层启发，最大深度 6）。"""
    found: list[dict] = []
    if depth > 6:
        return found
    if isinstance(value, dict):
        host = value.get("host") or value.get("ip") or value.get("hostname")
        if isinstance(host, str) and host.strip():
            found.append(value)
        for child in value.values():
            found.extend(_walk_json(child, depth + 1))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_json(child, depth + 1))
    return found


def _parse_generic_json(raw: str) -> ParseOutput:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"通用 JSON 解析失败: {exc}") from exc
    candidates: list[identity.Candidate] = []
    for entry in _walk_json(data):
        host = str(entry.get("host") or entry.get("ip") or entry.get("hostname"))
        role = str(entry.get("role", "") or "")
        port = entry.get("port")
        summary = f"通用 JSON 资产: {host}"
        if role:
            summary += f"（role: {role}）"
        data_out: dict[str, str | int | float | bool] = {}
        if isinstance(port, int):
            data_out["port"] = port
        candidates.append(
            _clean(
                identity.Candidate(
                    kind="asset",
                    target=host,
                    title=role or host,
                    summary=summary,
                    confidence=0.6,  # 启发式解析，置信度低于专用 parser
                    source="generic-json",
                    data=data_out,
                )
            )
        )
    return ParseOutput(tool="generic", format="generic-json", candidates=candidates)


PARSERS: dict[str, Callable[[str], ParseOutput]] = {
    "nmap-xml": _parse_nmap_xml,
    "masscan-json": _parse_masscan_json,
    "httpx-jsonl": _parse_httpx_jsonl,
    "nuclei-jsonl": _parse_nuclei_jsonl,
    "generic-json": _parse_generic_json,
}


def parse(format: str, raw: str) -> ParseOutput:
    """按 registry 解析工具输出；超限候选截断并记入 notes。"""
    parser = PARSERS.get(format)
    if parser is None:
        raise ParseError(
            f"unknown format: {format}（可用: {', '.join(sorted(PARSERS))}）"
        )
    result = parser(raw)
    if len(result.candidates) > MAX_TOTAL_CANDIDATES:
        omitted = len(result.candidates) - MAX_TOTAL_CANDIDATES
        result.candidates = result.candidates[:MAX_TOTAL_CANDIDATES]
        result.notes.append(
            f"候选超上限，已截断 {omitted} 条（上限 {MAX_TOTAL_CANDIDATES}）"
        )
    return result
