"""Generate canonical submission.jsonl from expanded/test_pairs.json."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.arbitration import arbitrate
from app.composer import MessageComposer
from app.evidence import extract_evidence
from app.storage import Storage

def main():
    root = Path(__file__).resolve().parent.parent
    expanded_dir = root / "dataset" / "expanded"
    test_pairs_file = expanded_dir / "test_pairs.json"
    submission_file = root / "submission.jsonl"

    if not test_pairs_file.exists():
        raise FileNotFoundError(f"Missing {test_pairs_file}. Run generate_dataset.py first.")

    with open(test_pairs_file, "r", encoding="utf-8") as f:
        test_pairs = json.load(f)["pairs"]

    composer = MessageComposer()
    storage = Storage(db_path=":memory:")

    categories = {}
    for f in (expanded_dir / "categories").glob("*.json"):
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            categories[data["slug"]] = data

    lines = []
    print(f"Generating submission for {len(test_pairs)} canonical test pairs...")

    for pair in test_pairs:
        test_id = pair["test_id"]
        t_id = pair["trigger_id"]
        m_id = pair["merchant_id"]
        c_id = pair.get("customer_id")

        with open(expanded_dir / "triggers" / f"{t_id}.json", "r", encoding="utf-8") as fp:
            trigger_data = json.load(fp)

        with open(expanded_dir / "merchants" / f"{m_id}.json", "r", encoding="utf-8") as fp:
            merchant_data = json.load(fp)

        customer_data = None
        if c_id:
            c_file = expanded_dir / "customers" / f"{c_id}.json"
            if c_file.exists():
                with open(c_file, "r", encoding="utf-8") as fp:
                    customer_data = json.load(fp)

        cat_slug = merchant_data.get("category_slug", "dentists")
        category_data = categories.get(cat_slug)

        evidence = extract_evidence(category_data, merchant_data, trigger_data, customer_data)
        decision = arbitrate(evidence, storage)

        body, template_params, cta = composer.compose_proactive(evidence, decision)
        send_as = "merchant_on_behalf" if (c_id or trigger_data.get("scope") == "customer") else "vera"

        entry = {
            "test_id": test_id,
            "conversation_id": f"conv_{m_id}_{t_id}",
            "merchant_id": m_id,
            "customer_id": c_id,
            "send_as": send_as,
            "trigger_id": t_id,
            "template_name": decision.template_name or "vera_generic_v1",
            "template_params": template_params,
            "body": body,
            "cta": cta,
            "suppression_key": trigger_data.get("suppression_key") or f"{evidence.trigger_kind}:{m_id}",
            "rationale": decision.rationale,
        }
        lines.append(json.dumps(entry, ensure_ascii=False))

    with open(submission_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Successfully generated {len(lines)} lines in {submission_file}")

if __name__ == "__main__":
    main()
