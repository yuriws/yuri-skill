#!/usr/bin/env python3
"""两个用途，二选一：

1) python build-merged.py
   把 text/ 下的单章正文拼接成**整合稿** text/merged-*.md（生成物，.gitignore 已排除）。

2) python build-merged.py --archive
   **归档模式**：把 text/ 下的单章按卷追加进 text/vol-00N.md（每 100 章一卷）。

约定（重要）：
    · merged-*.md 是**生成物**，改文不要改它，重跑脚本即重建。
    · vol-*.md 是**正文的真相源**，归档后可直接编辑（改文改卷文件，不必再建单章）。
    · 归档采用**追加 + 按章节标题去重**：重复执行不会把同一章写两遍。

安全顺序（写死在流程里，不要跳步）：
    commit → push → 确认远程同步 → 才跑 --archive → 确认卷文件完整 → 才删单章 → 再提交。
    归档后单章会被删除，恢复靠 Git 历史；**未推送的历史只在本机，丢了就没了**。
"""

import argparse
import pathlib
import re

base = pathlib.Path(__file__).resolve().parent
text = base / "text"

CHAPTERS_PER_VOL = 100


def list_chapters():
    """列出 text/ 下的单章正文，按章号数字排序。"""
    chapters = [
        p
        for p in text.glob("[0-9]*.md")
        if not p.name.startswith("merged") and not p.name.startswith("vol-")
    ]
    return sorted(chapters, key=lambda p: int(p.stem))


def build_merged(chapters):
    """正文来源优先级：卷文件 vol-*.md > 单章 00X.md。

    第 10 章之后单章会被归档删除，text/ 下只剩卷文件 —— 整合稿必须能从卷文件生成。
    """
    # ⚠️ 只认纯卷文件 vol-NNN.md —— 摘录文件（vol-002-ch021-030.md）也匹配 vol-*.md，
    # 不排除会把 021–030 再拼一遍（实测章节数虚报 40 而非 30，正文重复）。
    vols = sorted(
        p for p in text.glob("vol-*.md") if re.fullmatch(r"vol-\d{3}", p.stem)
    )
    sources = vols if vols else chapters

    parts = [p.read_text(encoding="utf-8").strip() for p in sources]
    # 章标题格式以 init.md 规定为准：## 第NN章《标题》（本正则只提取章号数字）
    numbers = [
        m.group(1)
        for p in sources
        for m in re.finditer(r"^## 第(\d+)章", p.read_text(encoding="utf-8"), re.M)
    ]
    first, last = (numbers[0], numbers[-1]) if numbers else ("???", "???")
    out = text / f"merged-{first}-{last}.md"

    header = (
        "> **本文件是生成物**，由 `text/` 下的正文顺序拼接而成，**请勿直接编辑**。\n"
        "> 改文请改真相源（单章或卷文件），然后重跑 `python build-merged.py` 重建。\n"
        f"> 共 {len(numbers)} 章（{first} → {last}）\n"
    )
    body = "\n\n\n".join(parts)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{header}\n---\n\n{body}\n")

    print(f"已生成 {out.name}")
    print(f"  章节数：{len(numbers)}（{first} → {last}）｜来源：{'卷文件' if vols else '单章'}")
    print(f"  正文字数：{sum(len(p) for p in parts)} 字符")


def archive(chapters):
    vols = {}
    for p in chapters:
        vol_no = (int(p.stem) - 1) // CHAPTERS_PER_VOL + 1
        vols.setdefault(vol_no, []).append(p)

    for vol_no in sorted(vols):
        vol_path = text / f"vol-{vol_no:03d}.md"
        existing = vol_path.read_text(encoding="utf-8") if vol_path.exists() else ""

        blocks = []
        if not existing:
            blocks.append(f"# 卷 {vol_no:03d} · 正文（真相源，可直接编辑）")

        added = 0
        for p in vols[vol_no]:
            body = p.read_text(encoding="utf-8").strip()
            title = body.splitlines()[0].strip()
            if title and title in existing:
                print(f"  = 跳过（已归档）{p.name}")
                continue
            blocks.append(body)
            added += 1
            print(f"  + {p.name}")

        if not added:
            print(f"卷 {vol_no:03d}：无新增章节")
            continue

        with open(vol_path, "a", encoding="utf-8", newline="\n") as f:
            if existing:
                f.write("\n\n")
            f.write("\n\n\n".join(blocks) + "\n")

        print(f"已追加进 {vol_path.name}（本次 {added} 章）")


def main():
    ap = argparse.ArgumentParser(description="整合稿生成 / 分卷归档")
    ap.add_argument(
        "--archive",
        action="store_true",
        help="归档模式：把单章追加进 text/vol-00N.md（每 100 章一卷）",
    )
    args = ap.parse_args()

    chapters = list_chapters()

    if args.archive:
        if not chapters:
            raise SystemExit("text/ 下没有找到可归档的单章（可能都已归档进卷文件）")
        archive(chapters)
        return

    if not chapters and not sorted(text.glob("vol-*.md")):
        raise SystemExit("text/ 下既没有单章也没有卷文件，无法生成整合稿")
    build_merged(chapters)


if __name__ == "__main__":
    main()
