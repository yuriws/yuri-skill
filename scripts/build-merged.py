#!/usr/bin/env python3
"""从项目根目录的 text/ 生成整合稿，或用 --archive 分卷归档（每卷 100 章）。

本脚本复制到项目根目录使用。正文标题：## 第NN章《标题》。
无参数只接受一种来源：纯卷文件 vol-NNN.md 或纯数字单章 NNN.md；摘录不参与。
归档先验证整批，再逐文件原子替换；同章同内容跳过，同章改稿报冲突。
单章输入始终保留，后续由用户核验、备份后自行清理。不会自动删除任何正文。
这是机械结构检查，不验证正文语义；跨文件写入不是文件系统事务。
"""

import argparse
from dataclasses import dataclass
import os
import pathlib
import re
import tempfile

base = pathlib.Path(__file__).resolve().parent
text = base / "text"
CHAPTERS_PER_VOL = 100
HEADING = re.compile(r"^##[ \t]+第([0-9]+)章《([^\n》]+)》[ \t]*$", re.M)


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    body: str
    block: str


def list_chapters():
    return sorted((p for p in text.glob("*.md") if re.fullmatch(r"[0-9]+", p.stem)),
                  key=lambda p: int(p.stem))


def list_volumes():
    return sorted(p for p in text.glob("*.md") if re.fullmatch(r"vol-[0-9]{3}", p.stem))


def consecutive(chapters, label):
    numbers = [c.number for c in chapters]
    if len(numbers) != len(set(numbers)):
        raise ValueError(f"{label}：章号重复 {numbers}")
    if any(right != left + 1 for left, right in zip(numbers, numbers[1:])):
        raise ValueError(f"{label}：章号乱序或断章 {numbers}")


def read_source(path, volume=None):
    content = path.read_text(encoding="utf-8-sig")
    matches = list(HEADING.finditer(content))
    if not matches:
        raise ValueError(f"{path.name}：没有合法章标题（## 第NN章《标题》）")
    # A malformed chapter heading must not disappear into the preceding body.
    candidates = re.findall(r"^##[ \t]+第[^\n]*章[^\n]*$", content, re.M)
    if len(candidates) != len(matches):
        raise ValueError(f"{path.name}：章标题格式不合法")
    chapters = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        number = int(match[1])
        if number < 1:
            raise ValueError(f"{path.name}：章号必须为正数")
        if volume is not None and (number - 1) // CHAPTERS_PER_VOL + 1 != volume:
            raise ValueError(f"{path.name}：第 {number} 章不属于该卷")
        chapters.append(Chapter(number, match[2], content[match.end():end].strip(),
                                content[match.start():end].strip()))
    if volume is None:
        if len(chapters) != 1 or chapters[0].number != int(path.stem):
            raise ValueError(f"{path.name}：单章文件名与唯一章号不符")
        if content[:matches[0].start()].strip():
            raise ValueError(f"{path.name}：单章标题前有额外内容")
    consecutive(chapters, path.name)
    return content, chapters


def atomic_write(path, content):
    """临时文件与目标同目录；失败时清理临时文件，替换是单文件原子的。"""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".novel-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def build_merged(chapters):
    volumes = list_volumes()
    if volumes and chapters:
        raise ValueError("text/ 同时有卷文件和单章：请先核对并归档，不能静默忽略单章")
    sources = volumes or chapters
    if not sources:
        raise ValueError("text/ 下既没有纯数字单章也没有纯卷文件，无法生成整合稿")
    parts, all_chapters = [], []
    for path in sources:
        content, parsed = read_source(path, int(path.stem[4:]) if volumes else None)
        parts.append(content.strip())
        all_chapters.extend(parsed)
    consecutive(all_chapters, "整合稿来源")
    first, last = all_chapters[0].number, all_chapters[-1].number
    out = text / f"merged-{first}-{last}.md"
    header = (
        "> **本文件是生成物**，由 `text/` 下的正文顺序拼接而成，**请勿直接编辑**。\n"
        "> 改文请改真相源（单章或卷文件），然后重跑 `python build-merged.py` 重建。\n"
        f"> 共 {len(all_chapters)} 章（{first} → {last}）\n"
    )
    atomic_write(out, header + "\n---\n\n" + "\n\n\n".join(parts) + "\n")
    print(f"已生成 {out.name}：{len(all_chapters)} 章（{first} → {last}）")


def archive(chapters):
    # Read and validate every existing volume and every loose source before writing.
    contents, existing = {}, {}
    ordered = []
    for path in list_volumes():
        volume = int(path.stem[4:])
        content, parsed = read_source(path, volume)
        contents[volume] = content
        ordered.extend(parsed)
        for chapter in parsed:
            if chapter.number in existing:
                raise ValueError(f"重复章号：{chapter.number}")
            existing[chapter.number] = chapter
    consecutive(ordered, "已有卷文件")
    additions = {}
    seen_loose = set()
    last_existing = ordered[-1].number if ordered else 0
    for path in chapters:
        _, parsed = read_source(path)
        chapter = parsed[0]
        if chapter.number in seen_loose:
            raise ValueError(f"单章章号重复：{chapter.number}")
        seen_loose.add(chapter.number)
        old = existing.get(chapter.number)
        if old is not None:
            if (old.title, old.body) != (chapter.title, chapter.body):
                raise ValueError(f"{path.name}：同章号标题或正文冲突，请人工核对")
            continue
        if chapter.number <= last_existing:
            raise ValueError(f"{path.name}：不可将回填章节追加到已有正文之后")
        volume = (chapter.number - 1) // CHAPTERS_PER_VOL + 1
        additions.setdefault(volume, []).append(chapter)
        ordered.append(chapter)
    consecutive(ordered, "归档后的完整章序")

    planned = []
    for volume, added in sorted(additions.items()):
        existing_content = contents.get(volume, "").rstrip()
        prefix = existing_content or f"# 卷 {volume:03d} · 正文（真相源，可直接编辑）"
        planned.append((text / f"vol-{volume:03d}.md",
                        prefix + "\n\n\n" + "\n\n\n".join(c.block for c in added) + "\n"))
    for path, content in planned:
        atomic_write(path, content)
        print(f"已归档进 {path.name}")
    if not planned:
        print("全部单章已归档且标题、正文相同，无需写入")
    print("单章源文件已保留；请核验、备份后自行决定是否清理")


def main():
    parser = argparse.ArgumentParser(description="整合稿生成 / 分卷归档")
    parser.add_argument("--archive", action="store_true",
                        help="归档单章到 text/vol-NNN.md（每 100 章一卷，保留源文件）")
    args = parser.parse_args()
    try:
        chapters = list_chapters()
        if args.archive:
            if not chapters:
                raise ValueError("text/ 下没有找到可归档的纯数字单章")
            archive(chapters)
        else:
            build_merged(chapters)
    except (ValueError, OSError, UnicodeError) as error:
        raise SystemExit(f"未完成：{error}") from None


if __name__ == "__main__":
    main()
