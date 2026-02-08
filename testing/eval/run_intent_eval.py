#!/usr/bin/env python3
"""Run fixed intent/entity evaluation corpus for PixelLink."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pylink"))

from core.context.session import SessionContext
from core.nlu.hybrid_parser import HybridIntentParser


def _normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _entity_scores(expected: dict, predicted: dict) -> tuple[int, int, int]:
    exp_items = {(k, _normalize(v)) for k, v in (expected or {}).items()}
    pred_items = {(k, _normalize(v)) for k, v in (predicted or {}).items()}
    tp = len(exp_items & pred_items)
    fp = len(pred_items - exp_items)
    fn = len(exp_items - pred_items)
    return tp, fp, fn


def main() -> int:
    corpus = ROOT / "testing" / "eval" / "intent_eval_cases.jsonl"
    if not corpus.exists():
        print(f"Corpus not found: {corpus}")
        return 1

    parser = HybridIntentParser()
    session = SessionContext()

    total = 0
    intent_correct = 0
    tp_total = 0
    fp_total = 0
    fn_total = 0
    mismatches: list[str] = []

    with corpus.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            total += 1
            case = json.loads(line)
            text = case["text"]
            expected_intent = case["intent"]
            expected_entities = case.get("entities", {})

            result = parser.parse(text, session, source="text")
            predicted = result.intent

            if predicted.name == expected_intent:
                intent_correct += 1
            elif len(mismatches) < 20:
                mismatches.append(
                    f"line {line_no}: text={text!r} expected={expected_intent} predicted={predicted.name}"
                )

            tp, fp, fn = _entity_scores(expected_entities, predicted.entities)
            tp_total += tp
            fp_total += fp
            fn_total += fn

    intent_acc = (intent_correct / total) if total else 0.0
    precision = tp_total / (tp_total + fp_total) if (tp_total + fp_total) else 0.0
    recall = tp_total / (tp_total + fn_total) if (tp_total + fn_total) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    print("Intent Eval Results")
    print("-" * 60)
    print(f"Corpus: {corpus}")
    print(f"Samples: {total}")
    print(f"Intent exact-match: {intent_acc:.4f} ({intent_correct}/{total})")
    print(f"Entity precision: {precision:.4f}")
    print(f"Entity recall: {recall:.4f}")
    print(f"Entity F1: {f1:.4f}")

    if mismatches:
        print("\nSample mismatches:")
        for item in mismatches:
            print(f"  - {item}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
