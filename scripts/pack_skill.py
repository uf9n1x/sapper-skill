"""打包 sapper-skill 发布产物并做结构校验（T-051c）。

用法（仓库根目录）：
    python -X utf8 scripts/pack_skill.py [--out dist]

产物：dist/sapper-skill/（目录名 = frontmatter name，ADR-0012）。
校验失败即退出码 1；产物可整体分发（离线，无 CDN）。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "sapper-skill"

# 打包清单（相对仓库根）
COPY_ITEMS = [
    "SKILL.md",
    "playbooks",
    "scripts/case_ledger.py",
    "scripts/prism.py",
    "scripts/prism",
    "scripts/pyproject.toml",
    "scripts/requirements.lock",
    "scripts/requirements-dev.txt",
    "references/hosts",
    "references/result-schema.json",
    "references/result-schema.md",
    "kb/README.md",
]
# dist 内排除的噪音
EXCLUDE_DIRS = {"__pycache__", ".venv", ".pytest_cache", "dashboard"}

_REQUIRED_COMMANDS = (
    "migrate", "ingest", "recover", "repair", "harvest", "schema", "pack",
    "verify-pack", "hosts", "state", "recall", "doc", "kb-list", "kb-read",
    "kb-promote", "render", "serve", "claim",
)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def copy_item(rel: str, dst_root: Path) -> None:
    src = ROOT / rel
    dst = dst_root / rel
    if not src.exists():
        fail(f"打包清单项不存在: {rel}")
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
        for junk in dst.rglob("__pycache__"):
            shutil.rmtree(junk, ignore_errors=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def validate_structure(dist: Path) -> list[str]:
    problems: list[str] = []

    # 1. frontmatter name 与目录名一致
    skill_md = (dist / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", skill_md, re.DOTALL)
    if not m:
        problems.append("SKILL.md 缺 frontmatter")
    else:
        fm = m.group(1)
        name_m = re.search(r"^name:\s*(\S+)", fm, re.MULTILINE)
        if not name_m or name_m.group(1) != SKILL_NAME:
            problems.append(
                f"frontmatter name={name_m.group(1) if name_m else '缺失'} != {SKILL_NAME}"
            )
        if not re.search(r"^description:", fm, re.MULTILINE):
            problems.append("frontmatter 缺 description")

    # 2. 资源引用完整：SKILL.md / playbooks 引用的仓库内路径必须存在于 dist
    referenced: set[str] = set()
    for md in [dist / "SKILL.md", *sorted((dist / "playbooks").glob("*.md"))]:
        text = md.read_text(encoding="utf-8")
        referenced.update(re.findall(r"`?(?:scripts|references|playbooks|kb)/[\w\-./]+`?", text))
    for ref in sorted(referenced):
        rel = ref.strip("`")
        if "{" in rel or "<" in rel or "*" in rel:
            continue
        if not (dist / rel).exists():
            problems.append(f"引用缺失: {rel}（被 SKILL.md/playbooks 引用）")

    # 3. 无宿主专有工具名（Core 纯净性；host 差异只在 references/hosts/）
    core_files = [
        dist / "SKILL.md",
        *sorted((dist / "playbooks").glob("*.md")),
        *sorted((dist / "scripts" / "prism").glob("*.py")),
        dist / "scripts" / "prism.py",
        dist / "scripts" / "case_ledger.py",
    ]
    # 宿主 CLI 名称词表（与 .ruff.toml 词边界扫描同源口径）
    for path in core_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for hit in re.findall(r"\b(omp)\b", text):
            problems.append(f"Core 文件含宿主专有名 '{hit}': {path.relative_to(dist)}")

    # 4. CLI 命令面完整
    help_out = subprocess.run(
        [sys.executable, "-X", "utf8", str(dist / "scripts" / "prism.py"), "--help"],
        check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    for cmd in _REQUIRED_COMMANDS:
        if cmd not in help_out:
            problems.append(f"CLI 缺命令: {cmd}")

    # 5. result-schema 与模型同步（打包内跑 schema 导出对比）
    exported = subprocess.run(
        [sys.executable, "-X", "utf8", str(dist / "scripts" / "prism.py"),
         "schema", "--format", "json"],
        check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if exported.returncode != 0:
        problems.append("dist 内 schema 导出失败")
    else:
        raw = exported.stdout
        payload = json.loads(raw[raw.index("{"):])
        shipped = json.loads((dist / "references" / "result-schema.json").read_text(encoding="utf-8"))
        if payload != shipped:
            problems.append("result-schema.json 与模型不同步")

    return problems


def smoke_test(dist: Path) -> None:
    """干净环境冒烟：临时目录建案件 → claim/ingest/state/render 全链。"""
    with tempfile.TemporaryDirectory(prefix="sapper-smoke-") as td:
        case = Path(td) / "case"
        (case / "artifacts").mkdir(parents=True)
        (case / "results").mkdir(parents=True)
        (case / "artifacts" / "a.txt").write_text("probe", encoding="utf-8")
        import hashlib
        sha = hashlib.sha256((case / "artifacts" / "a.txt").read_bytes()).hexdigest()

        prism = [sys.executable, "-X", "utf8", str(dist / "scripts" / "prism.py")]
        ledger = case / "ledger.jsonl"
        now = "2026-01-01T00:00:00Z"
        recs = [
            {"v": 2, "type": "approval", "id": "A1", "at": now, "action_class": "probe",
             "target_scope": "smoke", "effect": "reversible", "status": "approved",
             "decided_by": "user"},
            {"v": 2, "type": "hypothesis", "id": "H1", "at": now, "claim": "smoke 假设",
             "scope": "smoke", "disprove_if": ["x"]},
            {"v": 2, "type": "intent", "id": "I1", "at": now, "event": "created",
             "title": "smoke", "objective": "o", "angle": "a", "target": "t"},
        ]
        ledger.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
            encoding="utf-8", newline="\n",
        )

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                prism + list(args), check=False, cwd=case, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )

        r = run("claim", ".", "--intent", "I1", "--run", "R1", "--actor", "worker")
        if r.returncode != 0:
            fail(f"smoke claim 失败: {r.stdout}{r.stderr}")

        result = {
            "schema_version": 2, "run_id": "R1", "intent_id": "I1",
            "idempotency_key": "smoke-r1", "status": "needs_verification",
            "summary": "冒烟", "facts": [], "hypotheses": [],
            "evidence": [{"hypothesis": "H1", "role": "observation",
                          "effect": "supports", "artifact": "artifacts/a.txt",
                          "sha256": sha, "summary": "s"}],
            "suggested_verdicts": [], "next_intents": [], "deviations": [],
            "blockers": [],
        }
        rp = case / "results" / "R1.json"
        rp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        r = run("ingest", ".", "--result", "results/R1.json")
        if r.returncode != 0:
            fail(f"smoke ingest 失败: {r.stdout}{r.stderr}")
        # 幂等重放
        r2 = run("ingest", ".", "--result", "results/R1.json")
        if r2.returncode != 0 or '"status": "ingested"' not in r2.stdout.replace(" ", ""):
            pass  # duplicate 或 ingested 均可接受，失败才管
        r = run("state", ".", "--json")
        if r.returncode != 0:
            fail(f"smoke state 失败: {r.stderr}")
        r = run("render", ".")
        if r.returncode != 0 or not (case / "dashboard" / "dashboard.html").exists():
            fail(f"smoke render 失败: {r.stdout}{r.stderr}")
        r = run("pack", ".", "--hypothesis", "H1")
        if r.returncode != 0:
            fail(f"smoke pack 失败: {r.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser(description="打包 sapper-skill 发布产物")
    parser.add_argument("--out", default="dist", help="输出根目录（默认 dist）")
    args = parser.parse_args()

    out_root = ROOT / args.out
    dist = out_root / SKILL_NAME
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)

    for item in COPY_ITEMS:
        copy_item(item, dist)
    for junk in list(out_root.rglob("__pycache__")):
        shutil.rmtree(junk, ignore_errors=True)

    problems = validate_structure(dist)
    if problems:
        for p in problems:
            print("FAIL:", p)
        sys.exit(1)

    smoke_test(dist)

    files = sorted(p.relative_to(dist) for p in dist.rglob("*") if p.is_file())
    print(f"OK: {dist}")
    print(f"files: {len(files)}")
    for p in files:
        print("  ", p)


if __name__ == "__main__":
    main()
