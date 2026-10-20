#!/usr/bin/env python3
"""skill 自身维护后的机械对账——改完 SKILL.md / references 任何一处后跑一次。

存在理由：人工逐项想检查清单，必然漏项（实测教训：一次专名清洗只查了
SKILL.md，漏掉 rules.md 表格里的 3 处残留，安静污染了很久）。机械扫描的
边际成本趋近于零，漏检的代价却是实打实的——所以这里**全文件、无条件扫**。

覆盖（全部可数，输出逐条 ✅/❌，任一失败退出码 1）：
  1. 专名清零——本书 / 测试项目专名不得出现在任何 md
  2. 旧名词退役表——已优化掉的口径 / 术语 / 容器名必须为 0
  3. 规则清单对账——SKILL.md 清单行数 = rules.md `## 4.` 规则条数（防断链）
  4. 硬护栏一致——SKILL.md 尾段子句数 = rules.md 4.10 编号条数
  5. 批尾模板唯一——模板标题只许出现在 checklist.md（单一真相源）
  6. 脚本语法——build-merged.py 可编译

**两类失败分开报**（文案会演化，判据不会）：
  · ❌ 数据失败——内容真有问题（专名残留、对账不等、模板双写）→ 修 skill；
  · ⚠️ 定位失败——锚点串 / 模板标题改了名 → 更新本脚本数据区即可，
    **不报成「skill 坏了」**。判据一律「两边相等」，规则加到多少条都自适应。

用法：python scripts/verify.py
维护约定：
  · 专名表 / 退役表 / 锚点串都在下方数据区——加词改词只动那里，别改逻辑；
  · **换一本书维护 skill 时，先把该书专名追加进 PROPER_NAMES**——
    本表挡「已污染词回潮」，挡不了从未见过的新专名。
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILED = []

# 数据区：换任何一本书、退任何旧词、改任何锚点，只改这一块
PROPER_NAMES = ["林笙", "沈燕", "沉沉", "林盛", "体操社", "安玲", "拉威尔", "召唤梦魇"]
RETIRED_TERMS = ["速查卡", "翻案句", "第五种形态", "≥2＝该动"]
GUARD_ANCHOR = "**硬护栏（不可协商）**："   # SKILL.md 尾部硬护栏段的锚点串
GUARD_RULE = "## 4.10"                    # rules.md 硬护栏条目的锚点
TEMPLATE_TITLE = "第 N 批批尾体检"         # 批尾模板标题
TEMPLATE_FILE = "references/checklist.md"  # 模板唯一合法出处


def check(cond, ok_msg, fail_msg):
    print(("  ✅ " if cond else "  ❌ ") + (ok_msg if cond else fail_msg))
    if not cond:
        FAILED.append(fail_msg)


def anchor_fail(msg):
    """定位失败：锚点文案改了名——该更新脚本数据区，不是 skill 坏了。"""
    print("  ⚠️ " + msg)
    FAILED.append(msg)


def main():
    files = [ROOT / "SKILL.md"] + sorted((ROOT / "references").glob("*.md"))
    texts = {f.relative_to(ROOT).as_posix(): f.read_text(encoding="utf-8") for f in files}
    print(f"verify：{len(texts)} 个文件（SKILL.md + references/*.md）")

    print("[1] 专名清零")
    hits = [(p, n) for p, t in texts.items() for n in PROPER_NAMES if n in t]
    check(not hits, f"{len(PROPER_NAMES)} 项 × {len(texts)} 文件，零命中",
          f"专名残留：{hits}——skill 里不许出现本书专名")

    print("[2] 旧名词退役表")
    hits = [(p, w) for p, t in texts.items() for w in RETIRED_TERMS if w in t]
    check(not hits, f"{len(RETIRED_TERMS)} 个旧词全部退役",
          f"旧词复活：{hits}——已优化掉的口径又出现了")

    print("[3] 规则清单对账（防断链）")
    sk, rl = texts["SKILL.md"], texts["references/rules.md"]
    n_list = len(re.findall(r"(?m)^\| 4\.", sk))
    n_rules = len(re.findall(r"(?m)^## 4\.", rl))
    check(n_list == n_rules, f"清单 {n_list} 行 = rules.md {n_rules} 条",
          f"清单 {n_list} 行 ≠ rules.md {n_rules} 条——有规则只写进了按需层，没进执行链")

    print("[4] 硬护栏一致")
    if GUARD_ANCHOR not in sk:
        anchor_fail(f"定位失败：SKILL.md 找不到锚点「{GUARD_ANCHOR}」——护栏段文案变了，更新数据区 GUARD_ANCHOR")
    elif GUARD_RULE not in rl:
        anchor_fail(f"定位失败：rules.md 找不到「{GUARD_RULE}」——硬护栏条目改名了，更新数据区 GUARD_RULE")
    else:
        seg = sk.split(GUARD_ANCHOR)[-1]
        n_clauses = seg.count("；") + 1
        n_guard = len(re.findall(r"(?m)^\d+\. ", rl.split(GUARD_RULE)[-1]))
        check(n_clauses == n_guard, f"SKILL.md {n_clauses} 条 = rules.md 4.10 {n_guard} 条",
              f"硬护栏不同步：SKILL.md {n_clauses} 条 vs 4.10 {n_guard} 条——抄列必然漂移，补一边就要补另一边")

    print("[5] 批尾模板唯一")
    tpl = [(p, t.count(TEMPLATE_TITLE)) for p, t in texts.items() if TEMPLATE_TITLE in t]
    if not tpl:
        anchor_fail(f"定位失败：任何文件找不到模板标题「{TEMPLATE_TITLE}」——模板改名了，更新数据区 TEMPLATE_TITLE")
    else:
        check(len(tpl) == 1 and tpl[0][0] == TEMPLATE_FILE,
              f"唯一出处：{tpl[0][0]}",
              f"模板出现在 {len(tpl)} 处：{tpl}——单一真相源被破坏，改模板要改两遍")

    print("[6] 脚本语法")
    r = subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROOT / "scripts" / "build-merged.py")],
        capture_output=True,
    )
    check(r.returncode == 0, "build-merged.py 编译通过",
          f"build-merged.py 编译失败：{r.stderr.decode('utf-8', 'replace')[:200]}")

    if FAILED:
        print(f"\n结果：{len(FAILED)} 项未过——逐项修完重跑，全绿才算验收通过。")
        sys.exit(1)
    print("\n结果：全绿。")


if __name__ == "__main__":
    main()
