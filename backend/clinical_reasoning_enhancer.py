"""
临床推理增强模块。

本模块将 Note2Chat 与 ProMed 的部分思想轻量迁移到当前项目：
1. Note2Chat 风格的病例预处理：把互动式病例拆成 note-style sections 与结构化事实。
2. 单轮推理样本化：把多轮问诊拆成 single-turn reasoning samples。
3. ProMed 风格的信息增益评分：为每轮问题计算 SIG-lite 分数，并给出下一问建议。
4. 轨迹质量评估：评估问诊是否按步骤推进、覆盖关键证据、减少冗余。
"""

from __future__ import annotations

import re
from typing import Any


STAGE_LABELS = {
    1: "症状与病史",
    2: "心电图",
    3: "心肌标志物",
}


FACT_DEFINITIONS = [
    {
        "id": "pain_site",
        "label": "胸痛部位",
        "stage": 1,
        "weight": 1.0,
        "keywords": ["胸骨后", "心前区", "胸部", "前胸", "胸口"],
    },
    {
        "id": "pain_quality",
        "label": "胸痛性质",
        "stage": 1,
        "weight": 1.1,
        "keywords": ["压榨", "压榨性", "紧缩", "闷痛", "胸闷", "窒息", "刺痛", "锐痛", "烧灼"],
    },
    {
        "id": "pain_duration",
        "label": "持续时间",
        "stage": 1,
        "weight": 1.0,
        "keywords": ["分钟", "小时", "天", "持续", "发作", "突发"],
        "patterns": [r"\d+(?:\.\d+)?\s*(分钟|小时|天)"],
    },
    {
        "id": "radiation",
        "label": "放射痛",
        "stage": 1,
        "weight": 1.2,
        "keywords": ["放射", "左肩", "左臂", "背部", "后背", "颈部", "下颌"],
    },
    {
        "id": "autonomic_symptoms",
        "label": "自主神经症状",
        "stage": 1,
        "weight": 1.1,
        "keywords": ["大汗", "出汗", "恶心", "呕吐", "气短"],
    },
    {
        "id": "risk_factors",
        "label": "冠心病危险因素",
        "stage": 1,
        "weight": 0.8,
        "keywords": ["高血压", "糖尿病", "吸烟", "高脂血症", "冠心病家族史", "冠心病", "动脉粥样硬化"],
    },
    {
        "id": "ecg_present",
        "label": "已提供心电图",
        "stage": 2,
        "weight": 1.0,
        "keywords": ["心电图", "ECG", "导联"],
    },
    {
        "id": "ecg_leads",
        "label": "导联信息",
        "stage": 2,
        "weight": 1.0,
        "keywords": ["V1", "V2", "V3", "V4", "V5", "V6", "II", "III", "aVF", "I导联", "胸前导联"],
        "patterns": [r"(V[1-6](?:-V[1-6])?导联)", r"(II、III、aVF导联)", r"(I、aVL导联)"],
    },
    {
        "id": "st_elevation",
        "label": "ST段抬高",
        "stage": 2,
        "weight": 1.4,
        "keywords": ["ST段抬高", "ST抬高"],
        "patterns": [r"ST段抬高\s*\d+(?:\.\d+)?mV"],
    },
    {
        "id": "st_depression_or_twave",
        "label": "ST压低/T波改变",
        "stage": 2,
        "weight": 1.1,
        "keywords": ["ST段压低", "ST压低", "T波倒置", "T波改变"],
    },
    {
        "id": "troponin_value",
        "label": "肌钙蛋白结果",
        "stage": 3,
        "weight": 1.4,
        "keywords": ["肌钙蛋白", "cTnI", "cTnT", "TnI", "TnT"],
        "patterns": [r"(肌钙蛋白[IT]?[^\d]{0,8}\d+(?:\.\d+)?\s*ng/mL)"],
    },
    {
        "id": "ckmb_value",
        "label": "CK-MB结果",
        "stage": 3,
        "weight": 1.2,
        "keywords": ["CK-MB"],
        "patterns": [r"(CK-MB[^\d]{0,8}\d+(?:\.\d+)?\s*U/L)"],
    },
    {
        "id": "biomarker_elevated",
        "label": "心肌标志物升高",
        "stage": 3,
        "weight": 1.5,
        "keywords": ["升高", "增高", "阳性", "超过正常", "高于正常"],
    },
]


QUESTION_LIBRARY = {
    1: [
        {
            "question": "请补充胸痛的部位、性质和持续时间。",
            "target_facts": ["pain_site", "pain_quality", "pain_duration"],
        },
        {
            "question": "胸痛是否向左肩、左臂、背部或下颌放射？",
            "target_facts": ["radiation"],
        },
        {
            "question": "发作时是否伴有大汗、恶心、呕吐或气短？",
            "target_facts": ["autonomic_symptoms"],
        },
        {
            "question": "既往是否有高血压、糖尿病、吸烟等危险因素？",
            "target_facts": ["risk_factors"],
        },
    ],
    2: [
        {
            "question": "请提供心电图结果，尤其是导联分布和 ST-T 改变。",
            "target_facts": ["ecg_present", "ecg_leads", "st_elevation", "st_depression_or_twave"],
        },
        {
            "question": "是否有相邻导联 ST 段抬高，幅度大约多少？",
            "target_facts": ["st_elevation", "ecg_leads"],
        },
        {
            "question": "心电图是否提示 ST 压低或 T 波倒置？",
            "target_facts": ["st_depression_or_twave"],
        },
    ],
    3: [
        {
            "question": "请提供肌钙蛋白和 CK-MB 的检测结果。",
            "target_facts": ["troponin_value", "ckmb_value"],
        },
        {
            "question": "心肌标志物是否升高，是否超过正常参考范围？",
            "target_facts": ["biomarker_elevated", "troponin_value", "ckmb_value"],
        },
    ],
}


QUESTION_STAGE_HINTS = {
    1: ["胸痛", "放射", "大汗", "恶心", "病史", "危险因素", "持续时间"],
    2: ["心电图", "ECG", "导联", "ST", "T波"],
    3: ["肌钙蛋白", "CK-MB", "标志物", "化验", "检测结果"],
}

DEFAULT_STAGE_QUESTIONS = {
    1: "请补充胸痛的部位、性质、持续时间以及伴随症状。",
    2: "请提供心电图结果，尤其是导联范围和 ST-T 改变。",
    3: "请提供肌钙蛋白、CK-MB 等心肌标志物结果。",
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _extract_first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_text(match.group(1) if match.groups() else match.group(0))
    return ""


def extract_demographics(text: str) -> dict[str, str]:
    age_match = re.search(r"(\d{1,3})\s*岁", text)
    gender_match = re.search(r"患者[男女]|[，。；\s]([男女])[，。；\s]", text)

    gender = ""
    if "患者男" in text or re.search(r"[，。\s]男[，。\s]", text):
        gender = "男"
    elif "患者女" in text or re.search(r"[，。\s]女[，。\s]", text):
        gender = "女"
    elif gender_match:
        gender = gender_match.group(0).replace("患者", "").strip("，。； ")

    return {
        "age": age_match.group(1) if age_match else "",
        "gender": gender,
    }


def extract_structured_facts(text: str) -> list[dict[str, Any]]:
    normalized_text = _clean_text(text)
    facts: list[dict[str, Any]] = []

    for definition in FACT_DEFINITIONS:
        match_text = ""
        if any(keyword in normalized_text for keyword in definition.get("keywords", [])):
            match_text = next((keyword for keyword in definition.get("keywords", []) if keyword in normalized_text), "")

        if definition.get("patterns"):
            pattern_match = _extract_first_match(normalized_text, definition["patterns"])
            if pattern_match:
                match_text = pattern_match

        if match_text:
            facts.append(
                {
                    "id": definition["id"],
                    "label": definition["label"],
                    "stage": definition["stage"],
                    "weight": definition["weight"],
                    "evidence": match_text,
                }
            )

    return facts


def group_facts_by_stage(facts: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped = {1: [], 2: [], 3: []}
    for fact in facts:
        grouped.setdefault(fact["stage"], []).append(fact)
    return grouped


def build_note_style_sections(patient_case: dict[str, Any], diagnosis: str) -> dict[str, str]:
    rounds = ensure_reasoning_rounds(patient_case)
    return {
        "chief_complaint": patient_case.get("initial_presentation", ""),
        "history_of_present_illness": rounds[0].get("patient_answer", "") if len(rounds) >= 1 else patient_case.get("full_description", ""),
        "electrocardiogram": rounds[1].get("patient_answer", "") if len(rounds) >= 2 else "",
        "cardiac_biomarkers": rounds[2].get("patient_answer", "") if len(rounds) >= 3 else "",
        "working_diagnosis": diagnosis,
    }


def summarize_stage_coverage(facts: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = group_facts_by_stage(facts)
    coverage = {}

    for stage in (1, 2, 3):
        expected = [item for item in FACT_DEFINITIONS if item["stage"] == stage]
        found_ids = {item["id"] for item in grouped.get(stage, [])}
        coverage[f"step{stage}"] = {
            "label": STAGE_LABELS[stage],
            "identified": grouped.get(stage, []),
            "missing": [
                {
                    "id": item["id"],
                    "label": item["label"],
                    "weight": item["weight"],
                }
                for item in expected
                if item["id"] not in found_ids
            ],
            "completion_ratio": round(len(found_ids) / len(expected), 3) if expected else 1.0,
        }

    return coverage


def infer_question_stage(question: str, round_no: int) -> int:
    normalized = _clean_text(question)
    for stage, hints in QUESTION_STAGE_HINTS.items():
        if any(hint in normalized for hint in hints):
            return stage
    return round_no


def extract_patient_case_snapshot(patient_case: dict[str, Any], round_count: int) -> str:
    parts = [patient_case.get("initial_presentation", "")]
    for round_info in ensure_reasoning_rounds(patient_case)[:round_count]:
        if round_info.get("doctor_question"):
            parts.append(f"医生提问：{round_info['doctor_question']}")
        if round_info.get("patient_answer"):
            parts.append(f"患者回答：{round_info['patient_answer']}")
    return "\n".join([item for item in parts if item]).strip()


def _split_fragments(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。\n；;]+", text) if item.strip()]


def _pick_stage_fragments(text: str, stage: int) -> str:
    fragments = _split_fragments(text)
    hints = QUESTION_STAGE_HINTS.get(stage, [])
    matched = [fragment for fragment in fragments if any(hint in fragment for hint in hints)]
    return "；".join(matched) if matched else ""


def ensure_reasoning_rounds(patient_case: dict[str, Any]) -> list[dict[str, Any]]:
    rounds = patient_case.get("rounds", [])
    if rounds:
        return rounds

    full_description = patient_case.get("full_description", "")
    synthetic_rounds = []
    for stage in (1, 2, 3):
        answer = _pick_stage_fragments(full_description, stage)
        if not answer and stage == 1:
            answer = patient_case.get("initial_presentation", "") or full_description
        synthetic_rounds.append(
            {
                "round": stage,
                "focus": STAGE_LABELS[stage],
                "doctor_question": DEFAULT_STAGE_QUESTIONS[stage],
                "patient_answer": answer,
            }
        )
    return synthetic_rounds


def analyze_question_information_gain(
    patient_case: dict[str, Any],
    steps: list[dict[str, Any]],
    halt_step: int | None = None,
) -> dict[str, Any]:
    rounds = ensure_reasoning_rounds(patient_case)
    analyses = []
    seen_fact_ids: set[str] = set()
    seen_questions: list[str] = []

    for round_no, round_info in enumerate(rounds, start=1):
        question = round_info.get("doctor_question", "").strip()
        answer = round_info.get("patient_answer", "").strip()
        question_stage = infer_question_stage(question, round_no)
        answer_facts = extract_structured_facts(answer)
        answer_fact_ids = {fact["id"] for fact in answer_facts}
        new_facts = [fact for fact in answer_facts if fact["id"] not in seen_fact_ids]
        repeated_fact_count = len(answer_facts) - len(new_facts)

        novelty_score = min(len(new_facts) / 3, 1.0)
        criticality_score = min(sum(fact["weight"] for fact in new_facts) / 4, 1.0)
        step_alignment_score = 1.0 if question_stage == round_no else 0.45
        redundancy_penalty = min(repeated_fact_count * 0.18, 0.45)
        repeated_question_penalty = 0.2 if question and question in seen_questions else 0.0

        total_score = max(
            0.0,
            round((novelty_score * 0.35 + criticality_score * 0.4 + step_alignment_score * 0.25 - redundancy_penalty - repeated_question_penalty) * 10, 2),
        )

        if total_score >= 7.0:
            quality_label = "高价值问题"
        elif total_score >= 4.5:
            quality_label = "中等价值问题"
        else:
            quality_label = "低价值问题"

        analyses.append(
            {
                "round": round_no,
                "stage": STAGE_LABELS.get(round_no, f"第{round_no}轮"),
                "question": question,
                "question_stage": question_stage,
                "quality_label": quality_label,
                "sig_lite_score": total_score,
                "components": {
                    "novelty_score": round(novelty_score, 3),
                    "criticality_score": round(criticality_score, 3),
                    "step_alignment_score": round(step_alignment_score, 3),
                    "redundancy_penalty": round(redundancy_penalty + repeated_question_penalty, 3),
                },
                "new_facts": new_facts,
                "all_answer_facts": answer_facts,
                "step_answer": next((step.get("answer") for step in steps if step.get("step") == round_no), ""),
                "explanation": _build_gain_explanation(new_facts, question_stage, round_no, quality_label),
            }
        )

        seen_fact_ids.update(answer_fact_ids)
        if question:
            seen_questions.append(question)

        if halt_step and round_no >= halt_step:
            break

    avg_score = round(sum(item["sig_lite_score"] for item in analyses) / len(analyses), 2) if analyses else 0.0
    return {
        "rounds": analyses,
        "average_sig_lite_score": avg_score,
        "summary": f"平均 SIG-lite 分数为 {avg_score}，用于衡量每轮提问带来的新增临床信息价值。",
    }


def _build_gain_explanation(
    new_facts: list[dict[str, Any]],
    question_stage: int,
    expected_stage: int,
    quality_label: str,
) -> str:
    if not new_facts:
        return f"该轮未带来新的关键事实，因此被评为{quality_label}。"
    fact_labels = "、".join(fact["label"] for fact in new_facts[:4])
    if question_stage != expected_stage:
        return f"该轮虽补充了{fact_labels}，但提问阶段与当前诊断步骤不完全一致，因此价值被折减。"
    return f"该轮新增了{fact_labels}等关键事实，且与当前步骤匹配，因此被评为{quality_label}。"


def build_next_question_recommendations(
    preprocessed_case: dict[str, Any],
    halt_step: int | None = None,
) -> list[dict[str, Any]]:
    coverage = preprocessed_case["coverage"]
    target_step = halt_step
    if target_step is None:
        for stage in (1, 2, 3):
            if coverage[f"step{stage}"]["missing"]:
                target_step = stage
                break
    target_step = target_step or 3

    missing_items = coverage[f"step{target_step}"]["missing"]
    missing_ids = {item["id"] for item in missing_items}
    recommendations = []

    for candidate in QUESTION_LIBRARY.get(target_step, []):
        targeted = [fact_id for fact_id in candidate["target_facts"] if fact_id in missing_ids]
        if not targeted:
            continue
        targeted_defs = [item for item in missing_items if item["id"] in targeted]
        estimated_gain = round(sum(item["weight"] for item in targeted_defs) * 2.2, 2)
        recommendations.append(
            {
                "stage": target_step,
                "stage_label": STAGE_LABELS[target_step],
                "question": candidate["question"],
                "targeted_facts": targeted_defs,
                "estimated_sig_lite_gain": estimated_gain,
                "rationale": f"该问题直接补向 {', '.join(item['label'] for item in targeted_defs)}，适合当前步骤继续追问。",
            }
        )

    recommendations.sort(key=lambda item: item["estimated_sig_lite_gain"], reverse=True)
    return recommendations[:3]


def evaluate_trajectory_quality(
    question_gain_analysis: dict[str, Any],
    preprocessed_case: dict[str, Any],
) -> dict[str, Any]:
    rounds = question_gain_analysis.get("rounds", [])
    if not rounds:
        return {
            "step_compliance_score": 0.0,
            "coverage_score": 0.0,
            "redundancy_score": 0.0,
            "average_sig_lite_score": 0.0,
            "quality_label": "缺少轨迹数据",
            "summary": "当前无可评估的问诊轨迹。",
        }

    alignment_hits = sum(1 for item in rounds if item["question_stage"] == item["round"])
    step_compliance_score = round(alignment_hits / len(rounds), 3)
    coverage_values = [preprocessed_case["coverage"][f"step{stage}"]["completion_ratio"] for stage in (1, 2, 3)]
    coverage_score = round(sum(coverage_values) / len(coverage_values), 3)
    average_sig_lite_score = round(question_gain_analysis.get("average_sig_lite_score", 0.0) / 10, 3)
    redundancy_score = round(
        1 - min(sum(item["components"]["redundancy_penalty"] for item in rounds) / max(len(rounds), 1), 1.0),
        3,
    )

    composite = round(step_compliance_score * 0.35 + coverage_score * 0.35 + average_sig_lite_score * 0.2 + redundancy_score * 0.1, 3)
    if composite >= 0.8:
        quality_label = "高质量主动问诊轨迹"
    elif composite >= 0.6:
        quality_label = "中等质量主动问诊轨迹"
    else:
        quality_label = "需改进的主动问诊轨迹"

    return {
        "step_compliance_score": step_compliance_score,
        "coverage_score": coverage_score,
        "redundancy_score": redundancy_score,
        "average_sig_lite_score": question_gain_analysis.get("average_sig_lite_score", 0.0),
        "composite_score": composite,
        "quality_label": quality_label,
        "summary": (
            f"轨迹按步骤推进得分 {step_compliance_score}，证据覆盖得分 {coverage_score}，"
            f"平均 SIG-lite 得分 {question_gain_analysis.get('average_sig_lite_score', 0.0)}。"
        ),
    }


def build_single_turn_reasoning_samples(
    patient_case: dict[str, Any],
    question_gain_analysis: dict[str, Any],
    diagnosis: str,
    halt_step: int | None = None,
) -> list[dict[str, Any]]:
    rounds = ensure_reasoning_rounds(patient_case)
    gain_map = {item["round"]: item for item in question_gain_analysis.get("rounds", [])}
    samples = []

    for round_no, round_info in enumerate(rounds, start=1):
        if halt_step and round_no > halt_step:
            break

        visible_context = extract_patient_case_snapshot(patient_case, round_no - 1)
        gain_info = gain_map.get(round_no, {})
        samples.append(
            {
                "sample_id": f"{diagnosis.lower()}_turn_{round_no}",
                "turn": round_no,
                "stage": STAGE_LABELS.get(round_no, f"第{round_no}轮"),
                "visible_context": visible_context,
                "instruction": "基于当前已知信息，提出下一条最有价值且不跳步的临床问题。",
                "target_question": round_info.get("doctor_question", ""),
                "expected_patient_answer": round_info.get("patient_answer", ""),
                "supervision_signal": {
                    "question_value_label": gain_info.get("quality_label", ""),
                    "sig_lite_score": gain_info.get("sig_lite_score", 0.0),
                    "target_new_facts": gain_info.get("new_facts", []),
                },
                "target_diagnosis_state": diagnosis if round_no == 3 else f"推进到第{round_no + 1}步",
            }
        )

    return samples


def build_preprocessed_case(patient_case: dict[str, Any], diagnosis: str) -> dict[str, Any]:
    full_description = patient_case.get("full_description", "")
    demographics = extract_demographics(full_description)
    structured_facts = extract_structured_facts(full_description)
    coverage = summarize_stage_coverage(structured_facts)

    return {
        "note_style_sections": build_note_style_sections(patient_case, diagnosis),
        "demographics": demographics,
        "structured_facts": structured_facts,
        "coverage": coverage,
        "summary": (
            f"共抽取 {len(structured_facts)} 条结构化事实，"
            f"覆盖率分别为 Step1 {coverage['step1']['completion_ratio']}, "
            f"Step2 {coverage['step2']['completion_ratio']}, Step3 {coverage['step3']['completion_ratio']}。"
        ),
    }


def build_reasoning_enhancement_bundle(
    patient_case: dict[str, Any],
    diagnosis: str,
    steps: list[dict[str, Any]] | None = None,
    halt_step: int | None = None,
) -> dict[str, Any]:
    steps = steps or []
    preprocessed_case = build_preprocessed_case(patient_case, diagnosis)
    question_gain_analysis = analyze_question_information_gain(patient_case, steps, halt_step=halt_step)
    trajectory_quality = evaluate_trajectory_quality(question_gain_analysis, preprocessed_case)
    next_question_recommendations = build_next_question_recommendations(preprocessed_case, halt_step=halt_step)
    single_turn_reasoning_samples = build_single_turn_reasoning_samples(
        patient_case,
        question_gain_analysis,
        diagnosis,
        halt_step=halt_step,
    )

    return {
        "preprocessed_case": preprocessed_case,
        "question_gain_analysis": question_gain_analysis,
        "trajectory_quality": trajectory_quality,
        "next_question_recommendations": next_question_recommendations,
        "single_turn_reasoning_samples": single_turn_reasoning_samples,
    }
