#!/usr/bin/env python
"""How many real shopper sentences does the instant path understand?

    python eval/kirana_corpus.py <path to shabda_kirana_sft.jsonl>

Uses the labelled shopper sentences from the Shabda Kirana training data
("rendu biyyam", "teen nei", "one పాలు"…). For every sentence labelled as a
single add_item(product, qty), it checks that app/agent/fast_path.py
understands it with NO model call — same product (via the 10-language
vocabulary) and the same quantity. Sentences it doesn't understand are not
errors (the model handles them); WRONG answers are what matter.
"""

import collections
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agent.fast_path import parse  # noqa: E402
from app.i18n.grocery_terms import expand_query  # noqa: E402

BRANDS = {"amul", "tata", "maggi", "aashirvaad", "nestle", "parle", "parle-g", "britannia", "fortune", "coca-cola"}


def main(path: str) -> int:
    total = understood = right = 0
    wrong: list[tuple[str, str]] = []
    missed = collections.Counter()
    for line in open(path, encoding="utf-8"):
        msgs = json.loads(line)["messages"]
        for i, m in enumerate(msgs):
            if m["role"] != "user" or i + 1 >= len(msgs) or msgs[i + 1]["role"] != "assistant":
                continue
            try:
                label = json.loads(msgs[i + 1]["content"])
            except ValueError:
                continue
            calls = label.get("calls") or []
            if len(calls) != 1 or calls[0].get("tool") != "add_item":
                continue
            want_tags = expand_query(calls[0]["args"]["product"])[1:]
            want_qty = int(calls[0]["args"].get("qty") or 1)
            if not want_tags:
                continue  # a product Gnani Shop doesn't stock
            total += 1
            plan = parse(m["content"], BRANDS)
            if not plan:
                missed[m["content"]] += 1
                continue
            understood += 1
            got = (plan[0].tag, plan[0].quantity or 1)
            if len(plan) == 1 and got[0] in want_tags and got[1] == want_qty:
                right += 1
            else:
                wrong.append((m["content"], f"got {got} want {want_tags[0]}×{want_qty}"))
    print(f"single-item add sentences: {total}")
    print(f"understood instantly     : {understood} ({understood / max(total, 1):.0%})")
    print(f"  of which correct        : {right}  ·  WRONG: {len(wrong)}")
    for s, why in wrong[:25]:
        print(f"   WRONG  {s!r}: {why}")
    print("examples handed to the model instead:")
    for s, _ in missed.most_common(15):
        print(f"   {s!r}")
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
