"""Combined eval runner. Prints one summary; exits non-zero on failure.

(a) extraction field-level accuracy vs ground truth (2 OMs + 3 leases)
(b) 6 router tests (2 structured, 2 rag, 2 both)
(c) end-to-end ask tests: structured, tenant-aware lease lookup, RAG,
    OM comparison, multi-lease comparison, unanswerable

Rebuilds docs + index first so the eval is self-contained. Local mode
(PROVIDER unset) is expected to pass near-perfectly; any miss is
reported honestly.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import build_index, generate_docs  # noqa: E402
from entities.store import EntityStore  # noqa: E402
from providers import get_provider  # noqa: E402
from query import router  # noqa: E402
from query.ask import REFUSAL, Asker  # noqa: E402

failures: list[str] = []
checks = {"passed": 0, "failed": 0}


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        checks["passed"] += 1
        print(f"  PASS {name}")
    else:
        checks["failed"] += 1
        failures.append(name)
        print(f"  FAIL {name} {detail}")


def canon(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    if isinstance(v, list):
        return [canon(x) for x in v]
    if isinstance(v, dict):
        return {k: canon(val) for k, val in sorted(v.items())}
    s = str(v).strip().lower().replace("$", "").replace(",", "")
    s = re.sub(r"\s+", " ", s).rstrip(".")
    s = s.replace("%", "").replace("per month", "").strip()
    try:
        return round(float(s), 4)
    except ValueError:
        return s


def eval_extraction(store: EntityStore):
    print("\n(a) extraction accuracy vs ground truth")
    for gt_file in ["om_maple_grove.json", "om_harbor_point.json",
                    "lease_bluefin.json", "lease_copperline.json",
                    "lease_glakes.json"]:
        gt = json.loads((ROOT / "data" / "ground_truth" / gt_file).read_text())
        doc_type = gt["doc_type"]
        recs = [r for r in store.get_extractions(doc_type=doc_type)
                if r["source_file"] == gt["source_file"]]
        check(f"{gt_file}: extraction stored", bool(recs))
        if not recs:
            continue
        fields = recs[0]["fields"]
        total, matched = 0, 0
        for name, exp in gt["fields"].items():
            total += 1
            rec = fields.get(name, {})
            got = canon(rec.get("value"))
            want = canon(exp["value"])
            if got == want and rec.get("status") == "ok":
                matched += 1
            else:
                print(f"    miss {name}: got={rec.get('value')!r} "
                      f"(status={rec.get('status')}) want={exp['value']!r}")
                if rec.get("page") != exp.get("page"):
                    print(f"      page got={rec.get('page')} want={exp.get('page')}")
        acc = matched / total if total else 0
        print(f"    {gt_file}: {matched}/{total} = {acc:.1%}")
        check(f"{gt_file}: field accuracy >= 95%", acc >= 0.95,
              f"({matched}/{total})")


def eval_router(store: EntityStore):
    print("\n(b) router tests")
    cases = [
        ("When does the Bluefin Coffee lease expire?", "structured"),
        ("What is the asking price of Maple Grove Apartments?", "structured"),
        ("Summarize the management notes for Maple Grove.", "rag"),
        ("What did the corpus say about parking?", "rag"),
        ("Tell me about Harbor Point and its coffee tenant.", "both"),
        ("Compare Maple Grove and Ironworks on asking price.", "both"),
    ]
    for question, expected in cases:
        r = router.route(question, store)
        check(f"router {expected}: {question[:50]}",
              r["route"] == expected, f"got route={r['route']}")


def eval_ask(store: EntityStore):
    print("\n(c) end-to-end ask tests")
    asker = Asker(store, ROOT / "data", get_provider())

    r = asker.ask("When does the Bluefin Coffee lease expire?")
    check("ask structured: route", r["route"] == "structured",
          f"got {r['route']}")
    check("ask structured: answer has date", "2029-05-31" in r["answer"])
    check("ask structured: citations", bool(r["citations"]))
    check("ask structured: knew", r["knew"] is True)

    # tenant-aware: same property, different tenant -> different answer
    r = asker.ask("When does the Copperline Fitness lease expire?")
    check("ask tenant-aware: route", r["route"] == "structured",
          f"got {r['route']}")
    check("ask tenant-aware: copperline date", "2027-11-30" in r["answer"],
          f"got: {r['answer'][:120]}")
    check("ask tenant-aware: not bluefin's date",
          "2029-05-31" not in r["answer"],
          f"got: {r['answer'][:120]}")

    r = asker.ask("What year was Maple Grove Apartments renovated?")
    check("ask rag: knew", r["knew"] is True)
    check("ask rag: answer has 2019", "2019" in r["answer"])

    r = asker.ask("Compare the asking price and cap rate across properties")
    check("ask compare: route", r["route"] in ("structured", "both"),
          f"got {r['route']}")
    check("ask compare: table present",
          "table" in r and bool(r["table"].get("rows")),
          f"keys={list(r.keys())}")
    check("ask compare: knew", r["knew"] is True)
    check("ask compare: two OM rows",
          len(r["table"]["rows"]) == 2, f"rows={r['table']['rows']}")

    r = asker.ask("Compare base rent across leases")
    check("ask lease compare: route", r["route"] in ("structured", "both"),
          f"got {r['route']}")
    check("ask lease compare: three lease rows",
          "table" in r and len(r["table"].get("rows", [])) == 3,
          f"keys={list(r.keys())}")

    r = asker.ask("What is the CEO's favorite color?")
    check("ask unanswerable: refuses", r["knew"] is False
          and r["answer"] == REFUSAL, f"got: {r['answer'][:80]}")


def main() -> int:
    print("== deal-copilot eval ==")
    print("rebuilding docs + index...")
    generate_docs.main()
    build_index.main()
    store = EntityStore(str(ROOT / "data" / "entities.db"))
    eval_extraction(store)
    eval_router(store)
    eval_ask(store)
    print(f"\n== {checks['passed']} passed, {checks['failed']} failed ==")
    if failures:
        print("failures:", failures)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
