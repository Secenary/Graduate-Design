"""
训练数据准备脚本。

目标：
1. 基于当前 generated_data/patients.jsonl 导出 SFT 数据。
2. 基于单轮推理样本与信息增益，导出偏好学习与 RL 风格数据。
3. 可选整合医生复核记录，构造诊断偏好数据。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .clinical_reasoning_enhancer import (
    FACT_DEFINITIONS,
    QUESTION_LIBRARY,
    STAGE_LABELS,
    build_reasoning_enhancement_bundle,
    ensure_reasoning_rounds,
    extract_structured_facts,
    infer_question_stage,
)


DEFAULT_INPUT = Path("generated_data/patients.jsonl")
DEFAULT_OUTPUT_DIR = Path("training_data")
DEFAULT_REVIEW_PATH = Path("results/doctor_reviews.jsonl")


SYSTEM_PROMPTS = {
    "fact_extraction": "你是一位严谨的临床信息抽取助手。请把病历整理成结构化临床事实。",
    "single_turn_questioning": "你是一位严格遵循急性胸痛三步诊断链的心内科医生。请基于当前可见信息，只提出下一条最有价值且不跳步的问题。",
    "multi_turn_dialogue": "你是一位擅长急性胸痛分诊的临床医生。请按照三步流程开展问诊，并在证据充分后给出结论。",
    "stepwise_diagnosis": "你是一位急性胸痛决策支持医生。请严格按症状学、心电图、心肌标志物三步完成诊断。",
}


LOW_GAIN_QUESTIONS = {
    1: "还有哪里不舒服吗？",
    2: "患者最近睡眠怎么样？",
    3: "最近生活压力大吗？",
}


DIAGNOSIS_OPTIONS = ["STEMI", "NSTEMI", "UA", "变异性心绞痛", "其他", "待补充症状学信息", "待补充心电图检查", "待补充心肌标志物检查"]
FACT_WEIGHT_MAP = {item["id"]: item["weight"] for item in FACT_DEFINITIONS}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_sample_case(sample: dict[str, Any]) -> dict[str, Any]:
    interactive_case = sample.get("interactive_case") or {}
    description = str(sample.get("description", "")).strip()
    rounds = interactive_case.get("rounds", []) if interactive_case else []
    full_description = str(sample.get("full_description") or description).strip()
    return {
        "initial_presentation": interactive_case.get("initial_presentation", description).strip() if interactive_case else description,
        "rounds": rounds,
        "full_description": full_description,
    }


def ensure_reasoning_metadata(sample: dict[str, Any]) -> dict[str, Any]:
    required_keys = {
        "preprocessed_case",
        "question_gain_analysis",
        "trajectory_quality",
        "next_question_recommendations",
        "single_turn_reasoning_samples",
    }
    if required_keys.issubset(sample.keys()) and all(sample.get(key) is not None for key in required_keys):
        return sample

    patient_case = normalize_sample_case(sample)
    diagnosis = sample.get("result_state", "未知")
    bundle = build_reasoning_enhancement_bundle(patient_case=patient_case, diagnosis=diagnosis, steps=[], halt_step=None)
    enriched = dict(sample)
    enriched.update(bundle)
    return enriched


def build_fact_extraction_records(sample: dict[str, Any]) -> list[dict[str, Any]]:
    preprocessing = sample["preprocessed_case"]
    sections = preprocessing["note_style_sections"]
    assistant_payload = {
        "chief_complaint": sections.get("chief_complaint", ""),
        "history_of_present_illness": sections.get("history_of_present_illness", ""),
        "electrocardiogram": sections.get("electrocardiogram", ""),
        "cardiac_biomarkers": sections.get("cardiac_biomarkers", ""),
        "structured_facts": preprocessing.get("structured_facts", []),
    }
    return [
        {
            "id": f"{sample['patient_id']}_fact_extraction",
            "task_type": "fact_extraction",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPTS["fact_extraction"]},
                {
                    "role": "user",
                    "content": (
                        "请把以下胸痛病例整理成 note-style sections 和结构化事实 JSON。\n\n"
                        f"{sample['full_description']}"
                    ),
                },
                {"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False, indent=2)},
            ],
            "metadata": {
                "patient_id": sample["patient_id"],
                "diagnosis": sample["result_state"],
            },
        }
    ]


def build_single_turn_sft_records(sample: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for reasoning_sample in sample["single_turn_reasoning_samples"]:
        target_fact_labels = "、".join(item.get("label", "") for item in reasoning_sample["supervision_signal"].get("target_new_facts", []))
        assistant_payload = {
            "next_question": reasoning_sample["target_question"],
            "rationale": (
                f"当前应继续{reasoning_sample['stage']}，优先补充{target_fact_labels or '关键缺失事实'}，"
                "并避免跳步进入后续检查。"
            ),
        }
        records.append(
            {
                "id": f"{sample['patient_id']}_single_turn_{reasoning_sample['turn']}",
                "task_type": "single_turn_questioning",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPTS["single_turn_questioning"]},
                    {
                        "role": "user",
                        "content": (
                            f"当前是{reasoning_sample['stage']}。\n"
                            f"当前可见信息：\n{reasoning_sample['visible_context']}\n\n"
                            "请给出下一条最有价值的问题，只输出 JSON，包含 next_question 和 rationale。"
                        ),
                    },
                    {"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False, indent=2)},
                ],
                "metadata": {
                    "patient_id": sample["patient_id"],
                    "diagnosis": sample["result_state"],
                    "turn": reasoning_sample["turn"],
                    "sig_lite_score": reasoning_sample["supervision_signal"].get("sig_lite_score", 0.0),
                },
            }
        )
    return records


def build_multi_turn_sft_records(sample: dict[str, Any]) -> list[dict[str, Any]]:
    patient_case = normalize_sample_case(sample)
    rounds = ensure_reasoning_rounds(patient_case)
    messages = [{"role": "system", "content": SYSTEM_PROMPTS["multi_turn_dialogue"]}]
    messages.append({"role": "user", "content": patient_case["initial_presentation"]})
    for round_info in rounds:
        messages.append({"role": "assistant", "content": round_info.get("doctor_question", "")})
        messages.append({"role": "user", "content": round_info.get("patient_answer", "")})
    messages.append(
        {
            "role": "assistant",
            "content": (
                "第1步判断："
                + ("是缺血性胸痛" if sample["result_state"] != "其他" else "不是缺血性胸痛")
                + "\n第2步判断：请结合心电图结果。\n第3步判断：请结合心肌标志物结果。\n"
                + f"最终诊断：{sample['result_state']}"
            ),
        }
    )
    return [
        {
            "id": f"{sample['patient_id']}_multiturn_dialogue",
            "task_type": "multi_turn_dialogue",
            "messages": messages,
            "metadata": {
                "patient_id": sample["patient_id"],
                "diagnosis": sample["result_state"],
            },
        }
    ]


def build_stepwise_diagnosis_records(sample: dict[str, Any]) -> list[dict[str, Any]]:
    facts = sample["preprocessed_case"].get("structured_facts", [])
    fact_summary = "；".join(f"{item['label']}:{item['evidence']}" for item in facts[:12])
    assistant_lines = [
        f"结构化证据：{fact_summary}",
        "步骤判断：",
    ]
    for turn_sample in sample["single_turn_reasoning_samples"]:
        assistant_lines.append(
            f"- {turn_sample['stage']}：应提出“{turn_sample['target_question']}”以获取关键信息。"
        )
    assistant_lines.append(f"最终诊断：{sample['result_state']}")

    return [
        {
            "id": f"{sample['patient_id']}_stepwise_diagnosis",
            "task_type": "stepwise_diagnosis",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPTS["stepwise_diagnosis"]},
                {
                    "role": "user",
                    "content": (
                        "请基于以下完整病例，先完成结构化证据归纳，再按三步诊断链给出最后诊断：\n\n"
                        f"{sample['full_description']}"
                    ),
                },
                {"role": "assistant", "content": "\n".join(assistant_lines)},
            ],
            "metadata": {
                "patient_id": sample["patient_id"],
                "diagnosis": sample["result_state"],
            },
        }
    ]


def candidate_target_facts_from_library(question: str, stage: int) -> list[str]:
    for candidate in QUESTION_LIBRARY.get(stage, []):
        if candidate["question"] == question:
            return list(candidate["target_facts"])
    return []


def build_negative_candidates(stage: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    if stage < 3 and QUESTION_LIBRARY.get(stage + 1):
        jump_question = QUESTION_LIBRARY[stage + 1][0]["question"]
        candidates.append(
            {
                "question": jump_question,
                "reason_type": "jump_step",
                "stage": stage + 1,
                "target_facts": QUESTION_LIBRARY[stage + 1][0]["target_facts"],
            }
        )

    candidates.append(
        {
            "question": LOW_GAIN_QUESTIONS[stage],
            "reason_type": "low_gain",
            "stage": stage,
            "target_facts": [],
        }
    )
    return candidates


def score_question_candidate(
    visible_context: str,
    current_stage: int,
    target_facts: list[str],
    question: str,
) -> float:
    covered_facts = {fact["id"] for fact in extract_structured_facts(visible_context)}
    new_facts = [fact_id for fact_id in target_facts if fact_id not in covered_facts]
    reused_facts = [fact_id for fact_id in target_facts if fact_id in covered_facts]
    question_stage = infer_question_stage(question, current_stage)

    fact_gain = sum(FACT_WEIGHT_MAP.get(fact_id, 0.5) for fact_id in new_facts) * 2.0
    if question_stage == current_stage:
        stage_adjustment = 2.0
    elif question_stage > current_stage:
        stage_adjustment = -(4.0 + 1.5 * abs(question_stage - current_stage))
    else:
        stage_adjustment = -(2.5 + 1.0 * abs(question_stage - current_stage))
    redundancy_penalty = len(reused_facts) * 0.7
    generic_penalty = 1.0 if not target_facts else 0.0

    return round(max(fact_gain + stage_adjustment - redundancy_penalty - generic_penalty, 0.0), 2)


def build_question_preference_records(sample: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for reasoning_sample in sample["single_turn_reasoning_samples"]:
        current_stage = reasoning_sample["turn"]
        chosen_question = reasoning_sample["target_question"]
        chosen_target_facts = [fact["id"] for fact in reasoning_sample["supervision_signal"].get("target_new_facts", [])]
        if not chosen_target_facts:
            chosen_target_facts = candidate_target_facts_from_library(chosen_question, current_stage)

        for negative in build_negative_candidates(current_stage):
            rejected_score = score_question_candidate(
                reasoning_sample["visible_context"], current_stage, negative["target_facts"], negative["question"]
            )
            chosen_score = score_question_candidate(
                reasoning_sample["visible_context"], current_stage, chosen_target_facts, chosen_question
            )
            chosen_score = max(
                chosen_score,
                float(reasoning_sample["supervision_signal"].get("sig_lite_score", 0.0)),
                rejected_score + 1.0,
            )
            records.append(
                {
                    "id": f"{sample['patient_id']}_pref_{current_stage}_{negative['reason_type']}",
                    "task_type": "question_preference",
                    "system": SYSTEM_PROMPTS["single_turn_questioning"],
                    "prompt": (
                        f"当前是{reasoning_sample['stage']}。\n"
                        f"当前可见信息：\n{reasoning_sample['visible_context']}\n\n"
                        "请输出下一条问题。"
                    ),
                    "chosen": chosen_question,
                    "rejected": negative["question"],
                    "metadata": {
                        "patient_id": sample["patient_id"],
                        "diagnosis": sample["result_state"],
                        "turn": current_stage,
                        "preference_reason": negative["reason_type"],
                        "chosen_score": round(chosen_score, 2),
                        "rejected_score": round(rejected_score, 2),
                    },
                }
            )
    return records


def build_reward_and_rl_records(sample: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reward_rows: list[dict[str, Any]] = []
    rl_rows: list[dict[str, Any]] = []

    for reasoning_sample in sample["single_turn_reasoning_samples"]:
        current_stage = reasoning_sample["turn"]
        chosen_question = reasoning_sample["target_question"]
        chosen_target_facts = [fact["id"] for fact in reasoning_sample["supervision_signal"].get("target_new_facts", [])]
        if not chosen_target_facts:
            chosen_target_facts = candidate_target_facts_from_library(chosen_question, current_stage)

        candidates = [
            {
                "question": chosen_question,
                "target_facts": chosen_target_facts,
                "candidate_type": "chosen_reference",
            },
            *[
                {
                    "question": negative["question"],
                    "target_facts": negative["target_facts"],
                    "candidate_type": negative["reason_type"],
                }
                for negative in build_negative_candidates(current_stage)
            ],
        ]

        scored_candidates = []
        max_negative_score = 0.0
        raw_scores: list[tuple[dict[str, Any], float]] = []
        for candidate in candidates:
            reward_score = score_question_candidate(
                reasoning_sample["visible_context"],
                current_stage,
                candidate["target_facts"],
                candidate["question"],
            )
            raw_scores.append((candidate, reward_score))
            if candidate["candidate_type"] != "chosen_reference":
                max_negative_score = max(max_negative_score, reward_score)

        for candidate, reward_score in raw_scores:
            if candidate["candidate_type"] == "chosen_reference":
                reward_score = max(
                    reward_score,
                    float(reasoning_sample["supervision_signal"].get("sig_lite_score", 0.0)),
                    max_negative_score + 1.0,
                )
            reward_rows.append(
                {
                    "id": f"{sample['patient_id']}_reward_{current_stage}_{candidate['candidate_type']}",
                    "task_type": "question_reward_scoring",
                    "prompt": reasoning_sample["visible_context"],
                    "question": candidate["question"],
                    "reward_score": reward_score,
                    "metadata": {
                        "patient_id": sample["patient_id"],
                        "diagnosis": sample["result_state"],
                        "turn": current_stage,
                        "candidate_type": candidate["candidate_type"],
                        "target_facts": candidate["target_facts"],
                    },
                }
            )
            scored_candidates.append(
                {
                    "question": candidate["question"],
                    "reward_score": reward_score,
                    "candidate_type": candidate["candidate_type"],
                    "target_facts": candidate["target_facts"],
                }
            )

        rl_rows.append(
            {
                "id": f"{sample['patient_id']}_rl_{current_stage}",
                "task_type": "question_policy_optimization",
                "prompt": (
                    f"当前是{reasoning_sample['stage']}。\n"
                    f"当前可见信息：\n{reasoning_sample['visible_context']}\n\n"
                    "请从候选问题中选择最有价值且不跳步的一项，并只输出问题文本。"
                ),
                "candidates": [item["question"] for item in scored_candidates],
                "reward_spec": {
                    "objective": "maximize_sig_lite_and_step_alignment",
                    "current_stage": current_stage,
                    "target_stage_label": reasoning_sample["stage"],
                    "candidates": scored_candidates,
                },
                "reference_answer": chosen_question,
                "metadata": {
                    "patient_id": sample["patient_id"],
                    "diagnosis": sample["result_state"],
                    "turn": current_stage,
                },
            }
        )

    return reward_rows, rl_rows


def build_diagnosis_review_preferences(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, review in enumerate(reviews, start=1):
        ai_diagnosis = review.get("ai_diagnosis", "").strip()
        reviewed_diagnosis = review.get("reviewed_diagnosis", "").strip()
        if not ai_diagnosis or not reviewed_diagnosis or ai_diagnosis == reviewed_diagnosis:
            continue

        rows.append(
            {
                "id": f"review_pref_{index:04d}",
                "task_type": "diagnosis_preference",
                "system": SYSTEM_PROMPTS["stepwise_diagnosis"],
                "prompt": (
                    "请根据以下病例给出最终诊断：\n\n"
                    f"{review.get('patient_description', '')}"
                ),
                "chosen": reviewed_diagnosis,
                "rejected": ai_diagnosis,
                "metadata": {
                    "reviewer_name": review.get("reviewer_name", ""),
                    "review_action": review.get("review_action", ""),
                    "reviewed_at": review.get("reviewed_at", ""),
                    "graph_version": review.get("graph_version", ""),
                },
            }
        )
    return rows


def build_manifest(stats: dict[str, int], output_dir: Path) -> dict[str, Any]:
    manifest = {
        "datasets": {
            "sft_fact_extraction": {"file": "sft_fact_extraction.jsonl", "count": stats["sft_fact_extraction"]},
            "sft_single_turn_questioning": {"file": "sft_single_turn_questioning.jsonl", "count": stats["sft_single_turn_questioning"]},
            "sft_multi_turn_dialogue": {"file": "sft_multi_turn_dialogue.jsonl", "count": stats["sft_multi_turn_dialogue"]},
            "sft_stepwise_diagnosis": {"file": "sft_stepwise_diagnosis.jsonl", "count": stats["sft_stepwise_diagnosis"]},
            "dpo_question_preference": {"file": "dpo_question_preference.jsonl", "count": stats["dpo_question_preference"]},
            "reward_question_scoring": {"file": "reward_question_scoring.jsonl", "count": stats["reward_question_scoring"]},
            "rl_question_policy": {"file": "rl_question_policy.jsonl", "count": stats["rl_question_policy"]},
            "diagnosis_review_preference": {"file": "diagnosis_review_preference.jsonl", "count": stats["diagnosis_review_preference"]},
        },
        "output_dir": str(output_dir),
    }
    return manifest


def prepare_training_data(input_path: Path, output_dir: Path, review_path: Path) -> dict[str, Any]:
    patients = [ensure_reasoning_metadata(sample) for sample in load_jsonl(input_path)]
    reviews = load_jsonl(review_path)

    sft_fact_extraction: list[dict[str, Any]] = []
    sft_single_turn: list[dict[str, Any]] = []
    sft_multi_turn: list[dict[str, Any]] = []
    sft_stepwise_diagnosis: list[dict[str, Any]] = []
    dpo_question_preference: list[dict[str, Any]] = []
    reward_question_scoring: list[dict[str, Any]] = []
    rl_question_policy: list[dict[str, Any]] = []

    for sample in patients:
        sft_fact_extraction.extend(build_fact_extraction_records(sample))
        sft_single_turn.extend(build_single_turn_sft_records(sample))
        sft_multi_turn.extend(build_multi_turn_sft_records(sample))
        sft_stepwise_diagnosis.extend(build_stepwise_diagnosis_records(sample))
        dpo_question_preference.extend(build_question_preference_records(sample))
        reward_rows, rl_rows = build_reward_and_rl_records(sample)
        reward_question_scoring.extend(reward_rows)
        rl_question_policy.extend(rl_rows)

    diagnosis_review_preference = build_diagnosis_review_preferences(reviews)

    write_jsonl(output_dir / "sft_fact_extraction.jsonl", sft_fact_extraction)
    write_jsonl(output_dir / "sft_single_turn_questioning.jsonl", sft_single_turn)
    write_jsonl(output_dir / "sft_multi_turn_dialogue.jsonl", sft_multi_turn)
    write_jsonl(output_dir / "sft_stepwise_diagnosis.jsonl", sft_stepwise_diagnosis)
    write_jsonl(output_dir / "dpo_question_preference.jsonl", dpo_question_preference)
    write_jsonl(output_dir / "reward_question_scoring.jsonl", reward_question_scoring)
    write_jsonl(output_dir / "rl_question_policy.jsonl", rl_question_policy)
    write_jsonl(output_dir / "diagnosis_review_preference.jsonl", diagnosis_review_preference)

    stats = {
        "patients": len(patients),
        "doctor_reviews": len(reviews),
        "sft_fact_extraction": len(sft_fact_extraction),
        "sft_single_turn_questioning": len(sft_single_turn),
        "sft_multi_turn_dialogue": len(sft_multi_turn),
        "sft_stepwise_diagnosis": len(sft_stepwise_diagnosis),
        "dpo_question_preference": len(dpo_question_preference),
        "reward_question_scoring": len(reward_question_scoring),
        "rl_question_policy": len(rl_question_policy),
        "diagnosis_review_preference": len(diagnosis_review_preference),
    }

    manifest = build_manifest(stats, output_dir)
    (output_dir / "training_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "training_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "stats": stats,
        "manifest": manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从互动式病例中导出 SFT / DPO / RL 风格训练数据。")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="输入病例 jsonl 文件路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    parser.add_argument("--review-path", default=str(DEFAULT_REVIEW_PATH), help="医生复核记录路径")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = prepare_training_data(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        review_path=Path(args.review_path),
    )
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
