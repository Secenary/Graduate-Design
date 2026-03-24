from __future__ import annotations

import argparse
import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from .clinical_reasoning_enhancer import build_reasoning_enhancement_bundle

DEFAULT_RAW_INPUT = Path("generated_data/patients_before_process.jsonl")
DEFAULT_PROCESSED_OUTPUT = Path("generated_data/patients.jsonl")
DEFAULT_PROCESSED_INPUT = Path("generated_data/patients.jsonl")
DEFAULT_TRANSITIONS_PATH = Path("transitions.json")
DEFAULT_KNOWLEDGE_GRAPH_DIR = Path("knowledge_graph")

CATEGORY_LABELS = {
    "symptom": "\u75c7\u72b6\u4e0e\u75c5\u53f2",
    "ecg": "\u5fc3\u7535\u56fe",
    "biomarker": "\u5fc3\u808c\u6807\u5fd7\u7269",
    "generic": "\u8865\u5145\u68c0\u67e5",
}

CATEGORY_QUESTIONS = {
    "symptom": "\u8bf7\u8fdb\u4e00\u6b65\u63cf\u8ff0\u4e3b\u8bc9\u3001\u80f8\u75db\u90e8\u4f4d\u4e0e\u6027\u8d28\u3001\u6301\u7eed\u65f6\u95f4\u3001\u662f\u5426\u6709\u653e\u5c04\u75db\u3001\u4f34\u968f\u75c7\u72b6\uff0c\u4ee5\u53ca\u65e2\u5f80\u5371\u9669\u56e0\u7d20\u3002",
    "ecg": "\u8bf7\u63d0\u4f9b\u5fc3\u7535\u56fe\u68c0\u67e5\u7ed3\u679c\uff0c\u5c24\u5176\u662f\u5bfc\u8054\u8303\u56f4\u4ee5\u53ca ST-T \u6539\u53d8\u60c5\u51b5\u3002",
    "biomarker": "\u8bf7\u63d0\u4f9b\u5fc3\u808c\u6807\u5fd7\u7269\u7ed3\u679c\uff0c\u5305\u62ec\u808c\u9499\u86cb\u767d\u3001CK-MB \u7b49\u662f\u5426\u5347\u9ad8\u3002",
}

CATEGORY_HINTS = {
    "symptom": ["\u80f8\u75db", "\u75c7\u72b6", "\u4e3b\u8bc9", "\u653e\u5c04", "\u5927\u6c57", "\u6076\u5fc3", "\u75c5\u53f2", "\u5371\u9669\u56e0\u7d20", "\u7f3a\u8840\u6027"],
    "ecg": ["\u5fc3\u7535\u56fe", "ECG", "\u5bfc\u8054", "ST", "T\u6ce2", "Q\u6ce2"],
    "biomarker": ["\u808c\u9499\u86cb\u767d", "CK-MB", "\u6807\u5fd7\u7269", "troponin", "\u5fc3\u808c\u635f\u4f24"],
    "diagnosis": ["\u6700\u7ec8\u8bca\u65ad", "STEMI", "NSTEMI", "UA", "\u4e0d\u7a33\u5b9a\u578b\u5fc3\u7ede\u75db", "\u53d8\u5f02\u578b\u5fc3\u7ede\u75db"],
}

RISK_KEYWORDS = ["\u9ad8\u8840\u538b", "\u7cd6\u5c3f\u75c5", "\u5438\u70df", "\u9ad8\u8102\u8840\u75c7", "\u51a0\u5fc3\u75c5", "\u5bb6\u65cf\u53f2", "\u52a8\u8109\u7ca5\u6837\u786c\u5316"]

def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    return [json.loads(line) for line in file_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]

def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

def normalize_text(value: Any) -> str:
    return str(value or "").strip()

def split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\u3002\uff1b;\n]", normalize_text(text)) if item.strip()]

def extract_demographics(*texts: str) -> dict[str, Any]:
    joined = " ".join(normalize_text(text) for text in texts if normalize_text(text))
    patterns = [
        re.compile(r"\u60a3\u8005(?P<name>[\u4e00-\u9fff]{1,4})[\uff0c,\u3001 ]*(?P<sex>\u7537|\u5973)[\uff0c,\u3001 ]*(?P<age>\d{1,3})\u5c81"),
        re.compile(r"(?P<name>[\u4e00-\u9fff]{1,4})[\uff0c,\u3001 ]*(?P<sex>\u7537|\u5973)[\uff0c,\u3001 ]*(?P<age>\d{1,3})\u5c81"),
        re.compile(r"(?P<sex>\u7537|\u5973)[\uff0c,\u3001 ]*(?P<age>\d{1,3})\u5c81"),
    ]
    result: dict[str, Any] = {"name": "", "sex": "", "age": None}
    for pattern in patterns:
        match = pattern.search(joined)
        if not match:
            continue
        groups = match.groupdict()
        if groups.get("name"):
            result["name"] = groups["name"]
        if groups.get("sex"):
            result["sex"] = groups["sex"]
        if groups.get("age"):
            result["age"] = int(groups["age"])
        break
    return result

def extract_past_history(text: str) -> str:
    matched = [sentence for sentence in split_sentences(text) if any(keyword in sentence for keyword in RISK_KEYWORDS)]
    return "\uff1b".join(matched) if matched else "\u65e2\u5f80\u5371\u9669\u56e0\u7d20\u672a\u5728\u539f\u59cb\u75c5\u5386\u4e2d\u5355\u5217\uff0c\u9700\u7ed3\u5408\u95ee\u8bca\u8fdb\u4e00\u6b65\u660e\u786e\u3002"

def infer_stage_category(text: str, concepts: list[str] | None = None) -> str:
    joined = " ".join([normalize_text(text), *(concepts or [])]).lower()
    if any(keyword.lower() in joined for keyword in CATEGORY_HINTS["diagnosis"]):
        return "diagnosis"
    if any(keyword.lower() in joined for keyword in CATEGORY_HINTS["biomarker"]):
        return "biomarker"
    if any(keyword.lower() in joined for keyword in CATEGORY_HINTS["ecg"]):
        return "ecg"
    if any(keyword.lower() in joined for keyword in CATEGORY_HINTS["symptom"]):
        return "symptom"
    return "generic"

def _latest_ckg_path(knowledge_graph_dir: str | Path) -> Path | None:
    graph_dir = Path(knowledge_graph_dir)
    files = sorted(graph_dir.glob("*.ckg.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None

def build_question_from_stage(stage_key: str, concepts: list[str] | None = None) -> str:
    if stage_key in CATEGORY_QUESTIONS:
        return CATEGORY_QUESTIONS[stage_key]
    concept_text = "\u3001".join((concepts or [])[:4]) or "\u8be5\u9636\u6bb5"
    return f"\u8bf7\u8865\u5145{concept_text}\u76f8\u5173\u68c0\u67e5\u3001\u53d1\u73b0\u6216\u75c5\u53f2\u4fe1\u606f\u3002"

def _normalize_stage_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fallback_order = ["symptom", "ecg", "biomarker"]
    if not plan:
        plan = [{"stage_key": key, "label": CATEGORY_LABELS[key], "concepts": [], "question": CATEGORY_QUESTIONS[key]} for key in fallback_order]
    order = {key: index for index, key in enumerate(fallback_order)}
    sorted_plan = sorted(plan, key=lambda item: order.get(item["stage_key"], 99))
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(sorted_plan, start=1):
        normalized.append({
            "round": index,
            "stage_key": item["stage_key"],
            "label": item.get("label") or CATEGORY_LABELS.get(item["stage_key"], CATEGORY_LABELS["generic"]),
            "concepts": item.get("concepts", []),
            "question": item.get("question") or build_question_from_stage(item["stage_key"], item.get("concepts", [])),
            "source_node": item.get("source_node", ""),
        })
    return normalized

def _build_stage_plan_from_transitions(transitions_path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(transitions_path).read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in data.get("nodes", [])}
    outgoing: dict[str, list[str]] = {}
    incoming_count: dict[str, int] = {node_id: 0 for node_id in nodes}
    for transition in data.get("transitions", []):
        outgoing.setdefault(transition["from"], []).append(transition["to"])
        incoming_count[transition["to"]] = incoming_count.get(transition["to"], 0) + 1
    queue = deque(sorted([node_id for node_id, count in incoming_count.items() if count == 0] or list(nodes.keys())))
    seen_nodes: set[str] = set()
    seen_categories: set[str] = set()
    plan: list[dict[str, Any]] = []
    while queue:
        node_id = queue.popleft()
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)
        content = normalize_text(nodes[node_id].get("content", ""))
        concepts = [item.strip() for item in re.split(r"[,\uff0c]", content) if item.strip()]
        category = infer_stage_category(content, concepts)
        if category != "diagnosis" and category not in seen_categories:
            seen_categories.add(category)
            plan.append({"stage_key": category, "label": CATEGORY_LABELS.get(category, CATEGORY_LABELS["generic"]), "concepts": concepts, "question": build_question_from_stage(category, concepts), "source_node": node_id})
        for target in sorted(outgoing.get(node_id, [])):
            if target not in seen_nodes:
                queue.append(target)
    return _normalize_stage_plan(plan)

def _build_stage_plan_from_ckg(ckg_path: Path) -> list[dict[str, Any]]:
    data = json.loads(ckg_path.read_text(encoding="utf-8"))
    entities = {entity["id"]: entity for entity in data.get("entities", [])}
    workflow_nodes = {entity_id: entity for entity_id, entity in entities.items() if entity.get("entity_type") == "workflow_node"}
    outgoing: dict[str, list[str]] = {}
    incoming_count: dict[str, int] = {node_id: 0 for node_id in workflow_nodes}
    mentions_map: dict[str, list[str]] = {}
    for relation in data.get("relations", []):
        source = relation.get("source")
        target = relation.get("target")
        relation_type = relation.get("relation_type")
        if relation_type == "transitions_to" and source in workflow_nodes and target in workflow_nodes:
            outgoing.setdefault(source, []).append(target)
            incoming_count[target] = incoming_count.get(target, 0) + 1
        if relation_type == "mentions" and source in workflow_nodes and target in entities:
            mentions_map.setdefault(source, []).append(entities[target].get("name", ""))
    queue = deque(sorted([node_id for node_id, count in incoming_count.items() if count == 0] or list(workflow_nodes.keys())))
    seen_nodes: set[str] = set()
    seen_categories: set[str] = set()
    plan: list[dict[str, Any]] = []
    while queue:
        node_id = queue.popleft()
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)
        entity = workflow_nodes[node_id]
        content = normalize_text(entity.get("description") or entity.get("properties", {}).get("content", ""))
        concepts = [concept for concept in mentions_map.get(node_id, []) if concept]
        category = infer_stage_category(content, concepts)
        if category != "diagnosis" and category not in seen_categories:
            seen_categories.add(category)
            plan.append({"stage_key": category, "label": CATEGORY_LABELS.get(category, CATEGORY_LABELS["generic"]), "concepts": concepts, "question": build_question_from_stage(category, concepts), "source_node": node_id})
        for target in sorted(outgoing.get(node_id, [])):
            if target not in seen_nodes:
                queue.append(target)
    return _normalize_stage_plan(plan)

def build_stage_plan(transitions_path: str | Path = DEFAULT_TRANSITIONS_PATH, knowledge_graph_dir: str | Path = DEFAULT_KNOWLEDGE_GRAPH_DIR) -> list[dict[str, Any]]:
    latest_ckg = _latest_ckg_path(knowledge_graph_dir)
    if latest_ckg is not None:
        try:
            plan = _build_stage_plan_from_ckg(latest_ckg)
            if plan:
                return plan
        except Exception:
            pass
    return _build_stage_plan_from_transitions(transitions_path)

def build_answer_from_stage(raw_case_record: dict[str, Any], stage: dict[str, Any]) -> str:
    raw_case = raw_case_record.get("raw_case", {})
    stage_key = stage.get("stage_key")
    if stage_key == "symptom":
        parts = [raw_case.get("history_of_present_illness", ""), raw_case.get("past_history", ""), raw_case.get("risk_factors", "")]
        answer = "\uff1b".join(normalize_text(part) for part in parts if normalize_text(part))
        return answer or normalize_text(raw_case.get("chief_complaint")) or "\u539f\u59cb\u75c5\u5386\u4e2d\u672a\u8bb0\u5f55\u8db3\u591f\u7684\u75c7\u72b6\u5b66\u4fe1\u606f\u3002"
    if stage_key == "ecg":
        return normalize_text(raw_case.get("electrocardiogram")) or "\u539f\u59cb\u75c5\u5386\u4e2d\u5c1a\u672a\u63d0\u4f9b\u5fc3\u7535\u56fe\u7ed3\u679c\u3002"
    if stage_key == "biomarker":
        return normalize_text(raw_case.get("cardiac_biomarkers")) or "\u539f\u59cb\u75c5\u5386\u4e2d\u5c1a\u672a\u63d0\u4f9b\u5fc3\u808c\u6807\u5fd7\u7269\u7ed3\u679c\u3002"
    supplemental = raw_case.get("supplemental_sections") or {}
    concepts = stage.get("concepts") or []
    for section_name, section_text in supplemental.items():
        joined = normalize_text(section_name) + " " + normalize_text(section_text)
        if any(concept and concept in joined for concept in concepts):
            return normalize_text(section_text)
    note_text = raw_case_record.get("clinical_note", "")
    matched = [sentence for sentence in split_sentences(note_text) if any(concept and concept in sentence for concept in concepts)]
    if matched:
        return "\uff1b".join(matched[:3])
    return "\u539f\u59cb\u75c5\u5386\u4e2d\u6682\u672a\u63d0\u4f9b\u4e0e\u8be5\u9636\u6bb5\u76f4\u63a5\u5bf9\u5e94\u7684\u68c0\u67e5\u4fe1\u606f\u3002"

def build_full_description(initial_presentation: str, rounds: list[dict[str, Any]]) -> str:
    parts = [f"\u521d\u59cb\u4fe1\u606f\uff1a{normalize_text(initial_presentation)}"]
    for round_info in rounds:
        parts.append(f"\u7b2c{round_info["round"]}\u8f6e\u533b\u751f\u63d0\u95ee\uff1a{normalize_text(round_info["doctor_question"])}")
        parts.append(f"\u7b2c{round_info["round"]}\u8f6e\u60a3\u8005\u56de\u7b54\uff1a{normalize_text(round_info["patient_answer"])}")
    return "\n".join(parts)

def compose_clinical_note(raw_case_record: dict[str, Any]) -> str:
    raw_case = raw_case_record.get("raw_case", {})
    age_text = f"{raw_case.get("age")}\u5c81" if raw_case.get("age") not in (None, "") else "\u5e74\u9f84\u672a\u8be6"
    lines = [
        f"\u59d3\u540d\uff1a{normalize_text(raw_case.get("name")) or "\u672a\u7f72\u540d"}",
        f"\u6027\u522b\uff1a{normalize_text(raw_case.get("sex")) or "\u672a\u8be6"}",
        f"\u5e74\u9f84\uff1a{age_text}",
        f"\u4e3b\u8bc9\uff1a{normalize_text(raw_case.get("chief_complaint"))}",
        f"\u73b0\u75c5\u53f2\uff1a{normalize_text(raw_case.get("history_of_present_illness"))}",
        f"\u65e2\u5f80\u53f2\uff1a{normalize_text(raw_case.get("past_history"))}",
        f"\u5371\u9669\u56e0\u7d20\uff1a{normalize_text(raw_case.get("risk_factors"))}",
        f"\u67e5\u4f53\uff1a{normalize_text(raw_case.get("physical_exam"))}",
        f"\u5fc3\u7535\u56fe\uff1a{normalize_text(raw_case.get("electrocardiogram"))}",
        f"\u5fc3\u808c\u6807\u5fd7\u7269\uff1a{normalize_text(raw_case.get("cardiac_biomarkers"))}",
    ]
    supplemental = raw_case.get("supplemental_sections") or {}
    for key, value in supplemental.items():
        lines.append(f"{normalize_text(key)}\uff1a{normalize_text(value)}")
    if raw_case_record.get("result_state"):
        lines.append(f"\u4e34\u5e8a\u5370\u8c61\uff1a{normalize_text(raw_case_record.get("result_state"))}")
    return "\n".join(lines)

def build_raw_case_from_processed_record(processed_record: dict[str, Any]) -> dict[str, Any]:
    interactive_case = processed_record.get("interactive_case") or {}
    rounds = interactive_case.get("rounds") or []
    round1 = normalize_text(rounds[0].get("patient_answer")) if len(rounds) >= 1 else ""
    round2 = normalize_text(rounds[1].get("patient_answer")) if len(rounds) >= 2 else ""
    round3 = normalize_text(rounds[2].get("patient_answer")) if len(rounds) >= 3 else ""
    description = normalize_text(processed_record.get("description") or interactive_case.get("initial_presentation") or processed_record.get("full_description"))
    demographics = extract_demographics(description, round1)
    past_history = extract_past_history(round1)
    raw_case = {
        "name": demographics.get("name", ""),
        "sex": demographics.get("sex", ""),
        "age": demographics.get("age"),
        "chief_complaint": description,
        "history_of_present_illness": round1 or normalize_text(processed_record.get("full_description")),
        "past_history": past_history,
        "risk_factors": past_history,
        "physical_exam": "\u4e00\u822c\u60c5\u51b5\u4e0e\u751f\u547d\u4f53\u5f81\u5728\u539f\u59cb\u95ee\u7b54\u75c5\u4f8b\u4e2d\u672a\u5355\u5217\uff0c\u5efa\u8bae\u7ed3\u5408\u95e8\u6025\u8bca\u75c5\u5386\u8865\u5168\u3002",
        "electrocardiogram": round2,
        "cardiac_biomarkers": round3,
        "supplemental_sections": {},
    }
    raw_record = {
        "patient_id": processed_record.get("patient_id", ""),
        "raw_case": raw_case,
        "result_state": processed_record.get("result_state", ""),
        "path": processed_record.get("path", []),
    }
    raw_record["clinical_note"] = compose_clinical_note(raw_record)
    return raw_record

def convert_raw_case_to_processed_record(raw_case_record: dict[str, Any], stage_plan: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    stages = stage_plan or build_stage_plan()
    raw_case = raw_case_record.get("raw_case", {})
    initial_presentation = normalize_text(raw_case.get("chief_complaint"))
    if not initial_presentation:
        sentences = split_sentences(raw_case_record.get("clinical_note", ""))
        initial_presentation = sentences[0] if sentences else ""
    rounds = []
    for stage in stages:
        rounds.append({
            "round": stage["round"],
            "focus": stage["label"],
            "doctor_question": stage["question"],
            "patient_answer": build_answer_from_stage(raw_case_record, stage),
        })
    interactive_case = {
        "initial_presentation": initial_presentation,
        "rounds": rounds,
        "final_diagnosis": normalize_text(raw_case_record.get("result_state")),
    }
    full_description = build_full_description(initial_presentation, rounds)
    patient_case = {"initial_presentation": initial_presentation, "rounds": rounds, "full_description": full_description}
    bundle = build_reasoning_enhancement_bundle(patient_case=patient_case, diagnosis=normalize_text(raw_case_record.get("result_state")), steps=[], halt_step=None)
    return {
        "patient_id": raw_case_record.get("patient_id", ""),
        "description": initial_presentation,
        "full_description": full_description,
        "interactive_case": interactive_case,
        "result_state": raw_case_record.get("result_state", ""),
        "path": raw_case_record.get("path", []),
        **bundle,
    }

def process_raw_case_records(raw_records: list[dict[str, Any]], transitions_path: str | Path = DEFAULT_TRANSITIONS_PATH, knowledge_graph_dir: str | Path = DEFAULT_KNOWLEDGE_GRAPH_DIR) -> list[dict[str, Any]]:
    stage_plan = build_stage_plan(transitions_path=transitions_path, knowledge_graph_dir=knowledge_graph_dir)
    processed = [convert_raw_case_to_processed_record(record, stage_plan=stage_plan) for record in raw_records]
    processed.sort(key=lambda item: item.get("patient_id", ""))
    return processed

def bootstrap_raw_cases_from_processed(processed_input: str | Path = DEFAULT_PROCESSED_INPUT, raw_output: str | Path = DEFAULT_RAW_INPUT) -> list[dict[str, Any]]:
    processed_records = load_jsonl(processed_input)
    raw_records = [build_raw_case_from_processed_record(record) for record in processed_records]
    write_jsonl(raw_output, raw_records)
    return raw_records

def process_case_file(input_path: str | Path = DEFAULT_RAW_INPUT, output_path: str | Path = DEFAULT_PROCESSED_OUTPUT, transitions_path: str | Path = DEFAULT_TRANSITIONS_PATH, knowledge_graph_dir: str | Path = DEFAULT_KNOWLEDGE_GRAPH_DIR) -> list[dict[str, Any]]:
    raw_records = load_jsonl(input_path)
    processed = process_raw_case_records(raw_records, transitions_path=transitions_path, knowledge_graph_dir=knowledge_graph_dir)
    write_jsonl(output_path, processed)
    return processed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert raw clinical notes into staged dialogue cases.")
    parser.add_argument("--input", default=str(DEFAULT_RAW_INPUT), help="raw case jsonl path")
    parser.add_argument("--output", default=str(DEFAULT_PROCESSED_OUTPUT), help="processed interactive jsonl path")
    parser.add_argument("--transitions", default=str(DEFAULT_TRANSITIONS_PATH), help="workflow transitions path")
    parser.add_argument("--knowledge-graph-dir", default=str(DEFAULT_KNOWLEDGE_GRAPH_DIR), help="knowledge graph directory")
    parser.add_argument("--bootstrap-from-processed", default="", help="bootstrap raw cases from existing processed dataset")
    parser.add_argument("--raw-output", default=str(DEFAULT_RAW_INPUT), help="raw output path for bootstrap mode")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    if args.bootstrap_from_processed:
        raw_records = bootstrap_raw_cases_from_processed(args.bootstrap_from_processed, args.raw_output)
        print(json.dumps({"raw_records": len(raw_records), "raw_output": args.raw_output}, ensure_ascii=False, indent=2))
        return
    processed = process_case_file(input_path=args.input, output_path=args.output, transitions_path=args.transitions, knowledge_graph_dir=args.knowledge_graph_dir)
    print(json.dumps({"processed_records": len(processed), "output": args.output}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
