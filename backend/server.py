"""
Flask 后端：提供静态页面、模型诊断 API、病例回放、医生复核、知识图谱版本管理与诊断报告导出。
"""

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from .clinical_reasoning_enhancer import build_reasoning_enhancement_bundle
from .clinical_knowledge_graph import build_and_export_graph, get_exported_graph_status
from .methods import (
    direct_diagnosis,
    direct_generation_diagnosis,
    full_workflow_diagnosis,
    get_step_contexts,
    intermediate_state_diagnosis,
    normalize_patient_input,
    proactive_diagnosis,
    run_all_methods,
    step_by_step_diagnosis,
)
from .proactive_session import create_session, get_session, delete_session
from .training_data import prepare_training_data as build_training_data
from .database import get_db, Case, DoctorReview
from .kg_enhancement import KGEnhancementManager
from .mineru_client import MinerUError, parse_uploaded_file, parse_url_document

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
KNOWLEDGE_GRAPH_DIR = ROOT_DIR / "knowledge_graph"
RESULTS_DIR = ROOT_DIR / "results"
REPORTS_DIR = RESULTS_DIR / "reports"
REVIEWS_PATH = RESULTS_DIR / "doctor_reviews.jsonl"
TRANSITIONS_PATH = ROOT_DIR / "config" / "transitions.json"
GENERATED_DATA_PATH = ROOT_DIR / "generated_data" / "patients.jsonl"
TRAINING_DATA_DIR = ROOT_DIR / "training_data"
TRAINING_CONFIGS_DIR = ROOT_DIR / "training_configs"
API_KEYS_DIR = RESULTS_DIR / "api_keys"

for directory in (KNOWLEDGE_GRAPH_DIR, RESULTS_DIR, REPORTS_DIR, TRAINING_DATA_DIR, TRAINING_CONFIGS_DIR, API_KEYS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

API_APPLICATIONS_PATH = API_KEYS_DIR / "applications.jsonl"
API_KEYS_PATH = API_KEYS_DIR / "keys.jsonl"

# KG Enhancement manager (lazy initialization)
_KG_ENHANCEMENT_MANAGER: KGEnhancementManager | None = None
_KG_ENHANCEMENT_GRAPH_STAMP: tuple[str, float] | None = None


def get_latest_knowledge_graph_path() -> Path | None:
    kg_files = list(KNOWLEDGE_GRAPH_DIR.glob("*.ckg.json"))
    if not kg_files:
        return None
    return max(kg_files, key=lambda item: item.stat().st_mtime)


def get_kg_enhancement_manager() -> KGEnhancementManager:
    """Get or create the KG enhancement manager."""
    global _KG_ENHANCEMENT_MANAGER
    if _KG_ENHANCEMENT_MANAGER is None:
        _KG_ENHANCEMENT_MANAGER = KGEnhancementManager()
    return _KG_ENHANCEMENT_MANAGER


def get_current_kg_enhancement_manager() -> KGEnhancementManager:
    """Ensure the enhancement manager is aligned with the latest graph file."""
    global _KG_ENHANCEMENT_GRAPH_STAMP

    manager = get_kg_enhancement_manager()
    latest_path = get_latest_knowledge_graph_path()
    if latest_path is None:
        return manager

    stamp = (str(latest_path.resolve()), latest_path.stat().st_mtime)
    if _KG_ENHANCEMENT_GRAPH_STAMP != stamp:
        manager.load_knowledge_graph(latest_path)
        _KG_ENHANCEMENT_GRAPH_STAMP = stamp

    return manager

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

METHOD_MAP = {
    "direct": direct_diagnosis,
    "direct_generation": direct_generation_diagnosis,
    "intermediate_state": intermediate_state_diagnosis,
    "full_workflow": full_workflow_diagnosis,
    "step_by_step": step_by_step_diagnosis,
}

REPLAY_DEFAULT_QUESTIONS = {
    1: "请补充胸痛的部位、性质、持续时间以及是否伴有放射痛、大汗、恶心等症状。",
    2: "请提供心电图结果，尤其是导联范围与 ST-T 改变情况。",
    3: "请提供肌钙蛋白、CK-MB 等心肌标志物检测结果。",
}

REPLAY_FILTER_KEYWORDS = {
    1: ["胸痛", "胸闷", "胸骨后", "压榨", "放射", "左肩", "左臂", "大汗", "恶心", "持续", "小时", "分钟"],
    2: ["心电图", "ECG", "导联", "ST段", "ST 抬高", "ST抬高", "T波", "Q波"],
    3: ["肌钙蛋白", "cTn", "CK-MB", "心肌标志物", "ng/mL", "U/L", "升高", "阳性"],
}


def run_async(coro):
    """
    在 Flask 同步视图中运行异步诊断函数。
    """
    return asyncio.run(coro)


def iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def make_case_id(patient_description: str) -> str:
    digest = hashlib.sha1(patient_description.encode("utf-8")).hexdigest()[:8]
    return f"case_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{digest}"


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path, limit: int = 10) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-limit:]


def _resolve_mineru_token(raw_token: Any) -> str:
    token = str(raw_token or "").strip()
    return token or str(os.getenv("MINERU_API_TOKEN", "")).strip()


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _collect_mineru_options(payload: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {
        "model_version": str(payload.get("model_version", "vlm")).strip() or "vlm",
        "language": str(payload.get("language", "ch")).strip() or "ch",
        "page_ranges": str(payload.get("page_ranges", "")).strip() or None,
        "data_id": str(payload.get("data_id", "")).strip() or None,
        "enable_formula": _parse_bool(payload.get("enable_formula"), True),
        "enable_table": _parse_bool(payload.get("enable_table"), True),
        "is_ocr": _parse_bool(payload.get("is_ocr"), False),
        "no_cache": _parse_bool(payload.get("no_cache"), False),
    }

    cache_tolerance = str(payload.get("cache_tolerance", "")).strip()
    if cache_tolerance:
        options["cache_tolerance"] = cache_tolerance

    extra_formats = payload.get("extra_formats")
    if extra_formats:
        options["extra_formats"] = extra_formats

    return {key: value for key, value in options.items() if value is not None}


def _merge_mineru_graph_payload(mineru_payload: Any, title: str) -> dict[str, Any]:
    return normalize_graph_response(
        build_and_export_graph(
            transitions_path=TRANSITIONS_PATH,
            output_dir=KNOWLEDGE_GRAPH_DIR,
            mineru_payload=mineru_payload,
            mineru_title=title,
        )
    )


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def split_fragments(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。\n；;]+", text) if item.strip()]


def to_web_path(path: str | Path) -> str:
    target = Path(path)
    try:
        return f"/{target.resolve().relative_to(ROOT_DIR.resolve()).as_posix()}"
    except ValueError:
        return f"/{target.as_posix().lstrip('/')}"


def select_round_answer(patient_case: dict, round_no: int) -> str:
    rounds = patient_case.get("rounds", [])
    if len(rounds) >= round_no:
        return rounds[round_no - 1].get("patient_answer", "").strip()

    if round_no == 1:
        return patient_case.get("initial_presentation", "").strip() or patient_case.get("full_description", "").strip()

    fragments = split_fragments(patient_case.get("full_description", ""))
    filtered = [fragment for fragment in fragments if any(keyword in fragment for keyword in REPLAY_FILTER_KEYWORDS[round_no])]
    if filtered:
        return "；".join(filtered)

    return "当前原始病例中未单独拆出这一轮问答，系统基于整段病历进行了本步分析。"


def build_graph_path(
    diagnosis: str,
    intermediate_states: dict | None = None,
    halt_step: int | None = None,
) -> dict[str, list[str]]:
    """
    根据诊断与中间状态返回前端图谱高亮路径。
    """
    intermediate_states = intermediate_states or {}
    ischemic = intermediate_states.get("ischemic_chest_pain")
    st_elevation = intermediate_states.get("st_elevation")
    biomarker_elevated = intermediate_states.get("biomarker_elevated")

    if diagnosis.startswith("待补充"):
        if halt_step == 1:
            return {
                "nodes": ["start"],
                "edges": [],
            }
        if halt_step == 2:
            return {
                "nodes": ["start", "ischemic_yes"],
                "edges": ["start->ischemic_yes"],
            }
        if halt_step == 3:
            target_node = "st_yes" if st_elevation else "st_no"
            target_edge = "ischemic_yes->st_yes" if st_elevation else "ischemic_yes->st_no"
            return {
                "nodes": ["start", "ischemic_yes", target_node],
                "edges": ["start->ischemic_yes", target_edge],
            }

    if diagnosis == "其他" or ischemic is False:
        return {
            "nodes": ["start", "ischemic_no", "other"],
            "edges": ["start->ischemic_no", "ischemic_no->other"],
        }

    if diagnosis == "STEMI" or (st_elevation is True and biomarker_elevated is True):
        return {
            "nodes": ["start", "ischemic_yes", "st_yes", "stemi"],
            "edges": ["start->ischemic_yes", "ischemic_yes->st_yes", "st_yes->stemi"],
        }

    if diagnosis in {"变异性心绞痛", "变异型心绞痛"} or (st_elevation is True and biomarker_elevated is False):
        return {
            "nodes": ["start", "ischemic_yes", "st_yes", "variant"],
            "edges": ["start->ischemic_yes", "ischemic_yes->st_yes", "st_yes->variant"],
        }

    if diagnosis == "NSTEMI" or (st_elevation is False and biomarker_elevated is True):
        return {
            "nodes": ["start", "ischemic_yes", "st_no", "nstemi"],
            "edges": ["start->ischemic_yes", "ischemic_yes->st_no", "st_no->nstemi"],
        }

    return {
        "nodes": ["start", "ischemic_yes", "st_no", "ua"],
        "edges": ["start->ischemic_yes", "ischemic_yes->st_no", "st_no->ua"],
    }


def build_round_graph_path(
    round_no: int,
    diagnosis: str,
    intermediate_states: dict[str, Any],
    halt_step: int | None = None,
) -> dict[str, list[str]]:
    ischemic = intermediate_states.get("ischemic_chest_pain")
    st_elevation = intermediate_states.get("st_elevation")

    if round_no == 1:
        if ischemic is False:
            return {"nodes": ["start", "ischemic_no", "other"], "edges": ["start->ischemic_no", "ischemic_no->other"]}
        if ischemic is True:
            return {"nodes": ["start", "ischemic_yes"], "edges": ["start->ischemic_yes"]}
        return {"nodes": ["start"], "edges": []}

    if round_no == 2:
        if halt_step == 2 or st_elevation is None:
            return {"nodes": ["start", "ischemic_yes"], "edges": ["start->ischemic_yes"]}
        target_node = "st_yes" if st_elevation else "st_no"
        target_edge = "ischemic_yes->st_yes" if st_elevation else "ischemic_yes->st_no"
        return {"nodes": ["start", "ischemic_yes", target_node], "edges": ["start->ischemic_yes", target_edge]}

    return build_graph_path(diagnosis, intermediate_states, halt_step=halt_step)


def build_case_replay(
    patient_input: Any,
    primary_result: dict[str, Any],
    diagnosis: str,
    case_id: str,
) -> dict[str, Any]:
    patient_case = normalize_patient_input(patient_input)
    steps = primary_result.get("steps", [])
    steps_by_round = {item.get("step"): item for item in steps}
    halt_step = primary_result.get("halt_step")
    intermediate_states = primary_result.get("intermediate_states", {})
    round_count = max(len(steps), halt_step or 0, 1)

    replay_rounds = []
    for round_no in range(1, round_count + 1):
        round_info = patient_case.get("rounds", [])[round_no - 1] if len(patient_case.get("rounds", [])) >= round_no else {}
        step_info = steps_by_round.get(round_no, {})
        replay_rounds.append(
            {
                "round": round_no,
                "stage": f"第 {round_no} 轮",
                "ai_question": round_info.get("doctor_question", "").strip() or REPLAY_DEFAULT_QUESTIONS[round_no],
                "user_answer": select_round_answer(patient_case, round_no),
                "step_question": step_info.get("question", ""),
                "step_result": step_info.get("answer", "信息不足" if halt_step == round_no else "未执行"),
                "graph_path": build_round_graph_path(round_no, diagnosis, intermediate_states, halt_step=halt_step),
                "workflow_target": "ischemic" if round_no == 1 else "st" if round_no == 2 else "biomarker",
                "status": "halted" if halt_step == round_no else "completed",
                "note": primary_result.get("reason", "") if halt_step == round_no else "",
            }
        )

    return {
        "case_id": case_id,
        "initial_presentation": patient_case.get("initial_presentation", ""),
        "rounds": replay_rounds,
        "final_graph_path": build_graph_path(diagnosis, intermediate_states, halt_step=halt_step),
    }


def normalize_graph_response(payload: dict[str, Any]) -> dict[str, Any]:
    version_info = dict(payload.get("version_info") or {})
    history = version_info.pop("history", [])
    history_path = version_info.pop("history_path", "")
    artifacts = {
        "graph_json": to_web_path(payload["graph_json"]) if payload.get("graph_json") else "",
        "mermaid": to_web_path(payload["mermaid"]) if payload.get("mermaid") else "",
        "svg": to_web_path(payload["svg"]) if payload.get("svg") else "",
        "history": to_web_path(payload["history"] or history_path) if payload.get("history") or history_path else "",
    }
    return {
        "artifacts": artifacts,
        "version_info": version_info,
        "history": history,
    }


def collect_training_status() -> dict[str, Any]:
    stats_path = TRAINING_DATA_DIR / "training_stats.json"
    manifest_path = TRAINING_DATA_DIR / "training_manifest.json"
    stats = read_json(stats_path, {})
    manifest = read_json(manifest_path, {})
    datasets_meta = manifest.get("datasets", {})

    datasets = []
    for dataset_name, meta in datasets_meta.items():
        relative_file = str(meta.get("file", "")).strip()
        if not relative_file:
            continue
        dataset_path = TRAINING_DATA_DIR / relative_file
        exists = dataset_path.exists()
        row_count = meta.get("count")
        if row_count is None and exists and dataset_path.suffix == ".jsonl":
            row_count = count_jsonl_rows(dataset_path)
        datasets.append(
            {
                "name": dataset_name,
                "file": relative_file,
                "count": row_count or 0,
                "exists": exists,
                "size_bytes": dataset_path.stat().st_size if exists else 0,
                "download_url": to_web_path(dataset_path) if exists else "",
            }
        )

    if not datasets:
        for dataset_path in sorted(TRAINING_DATA_DIR.glob("*.jsonl")):
            datasets.append(
                {
                    "name": dataset_path.stem,
                    "file": dataset_path.name,
                    "count": count_jsonl_rows(dataset_path),
                    "exists": True,
                    "size_bytes": dataset_path.stat().st_size,
                    "download_url": to_web_path(dataset_path),
                }
            )

    recipes = [
        {
            "name": recipe_path.stem,
            "file": recipe_path.name,
            "download_url": to_web_path(recipe_path),
        }
        for recipe_path in sorted(TRAINING_CONFIGS_DIR.glob("*.yaml"))
    ]

    summary = {
        "generated_patients": count_jsonl_rows(GENERATED_DATA_PATH),
        "doctor_reviews": count_jsonl_rows(REVIEWS_PATH),
        "sft_total": (
            stats.get("sft_fact_extraction", 0)
            + stats.get("sft_single_turn_questioning", 0)
            + stats.get("sft_multi_turn_dialogue", 0)
            + stats.get("sft_stepwise_diagnosis", 0)
        ),
        "preference_total": (
            stats.get("dpo_question_preference", 0) + stats.get("diagnosis_review_preference", 0)
        ),
        "rl_total": stats.get("reward_question_scoring", 0) + stats.get("rl_question_policy", 0),
    }

    return {
        "stats": stats,
        "manifest": manifest,
        "datasets": datasets,
        "recipes": recipes,
        "summary": summary,
        "source_files": {
            "patients_jsonl": to_web_path(GENERATED_DATA_PATH) if GENERATED_DATA_PATH.exists() else "",
            "doctor_reviews_jsonl": to_web_path(REVIEWS_PATH) if REVIEWS_PATH.exists() else "",
        },
    }


def build_markdown_report(payload: dict[str, Any]) -> str:
    doctor_review = payload.get("doctor_review") or {}
    graph_version = payload.get("graph_version_info") or {}
    steps = payload.get("steps") or []
    missing_items = payload.get("missing_items") or []
    replay = payload.get("case_replay") or {}
    preprocessing = payload.get("preprocessed_case") or {}
    question_gain_analysis = payload.get("question_gain_analysis") or {}
    trajectory_quality = payload.get("trajectory_quality") or {}
    next_question_recommendations = payload.get("next_question_recommendations") or []
    single_turn_reasoning_samples = payload.get("single_turn_reasoning_samples") or []

    lines = [
        "# 急性胸痛临床诊断报告",
        "",
        f"- 报告编号：{payload.get('case_id', 'unknown')}",
        f"- 生成时间：{iso_timestamp()}",
        f"- 模型：{payload.get('model', DEFAULT_MODEL)}",
        f"- 主方法：{payload.get('primary_method', payload.get('method', 'step_by_step'))}",
        "",
        "## 患者信息",
        payload.get("patient_description", "未提供"),
        "",
        "## AI 初判结果",
        f"- 诊断结论：{payload.get('diagnosis', '未知')}",
        f"- 当前状态：{payload.get('status', 'completed')}",
        f"- 诊断路径：{payload.get('diagnosis_path', '')}",
    ]

    if payload.get("reason"):
        lines.append(f"- 停止原因：{payload['reason']}")
    if missing_items:
        lines.append(f"- 待补充检查/信息：{'、'.join(missing_items)}")
    if payload.get("recommendation"):
        lines.append(f"- 下一步建议：{payload['recommendation']}")

    lines.extend(["", "## 病例预处理"])
    note_sections = preprocessing.get("note_style_sections") or {}
    if note_sections:
        lines.extend(
            [
                f"- 主诉：{note_sections.get('chief_complaint', '')}",
                f"- 现病史：{note_sections.get('history_of_present_illness', '')}",
                f"- 心电图：{note_sections.get('electrocardiogram', '')}",
                f"- 心肌标志物：{note_sections.get('cardiac_biomarkers', '')}",
            ]
        )
    structured_facts = preprocessing.get("structured_facts") or []
    if structured_facts:
        fact_text = "；".join(f"{item.get('label')}({item.get('evidence')})" for item in structured_facts[:10])
        lines.append(f"- 结构化事实：{fact_text}")
    if preprocessing.get("summary"):
        lines.append(f"- 预处理摘要：{preprocessing['summary']}")

    lines.extend(["", "## 证据链"])
    if steps:
        for step in steps:
            lines.append(f"- 第 {step.get('step')} 步：{step.get('question', '')} -> {step.get('answer', '')}")
    else:
        lines.append("- 当前无可回放步骤。")

    replay_rounds = replay.get("rounds") or []
    lines.extend(["", "## 病例回放"])
    if replay_rounds:
        for round_info in replay_rounds:
            lines.append(f"### 第 {round_info.get('round')} 轮")
            lines.append(f"- AI 提问：{round_info.get('ai_question', '')}")
            lines.append(f"- 患者回答：{round_info.get('user_answer', '')}")
            lines.append(f"- 本轮判定：{round_info.get('step_result', '')}")
            if round_info.get("note"):
                lines.append(f"- 说明：{round_info['note']}")
            lines.append("")
    else:
        lines.append("- 当前无病例回放记录。")

    lines.extend(["", "## 信息增益与单轮推理样本"])
    gain_rounds = question_gain_analysis.get("rounds") or []
    if gain_rounds:
        for gain in gain_rounds:
            lines.append(
                f"- 第 {gain.get('round')} 轮：SIG-lite {gain.get('sig_lite_score', 0)}，"
                f"{gain.get('quality_label', '')}，说明：{gain.get('explanation', '')}"
            )
    if trajectory_quality:
        lines.append(f"- 轨迹质量：{trajectory_quality.get('quality_label', '')}，{trajectory_quality.get('summary', '')}")
    if next_question_recommendations:
        lines.append("- 下一问建议：")
        for item in next_question_recommendations:
            lines.append(
                f"  - {item.get('question', '')}（预估增益 {item.get('estimated_sig_lite_gain', 0)}，"
                f"补向 {'、'.join(fact.get('label', '') for fact in item.get('targeted_facts', []))}）"
            )
    if single_turn_reasoning_samples:
        lines.append(f"- 单轮推理样本数：{len(single_turn_reasoning_samples)}")

    lines.extend(["## 医生复核"])
    if doctor_review:
        lines.extend(
            [
                f"- 复核医生：{doctor_review.get('reviewer_name', '未填写')}",
                f"- 复核动作：{doctor_review.get('review_action', '未填写')}",
                f"- 复核诊断：{doctor_review.get('reviewed_diagnosis', '未填写')}",
                f"- 复核意见：{doctor_review.get('comment', '无')}",
                f"- 复核时间：{doctor_review.get('reviewed_at', '')}",
            ]
        )
    else:
        lines.append("- 当前尚无医生复核记录。")

    lines.extend(["", "## 知识图谱版本"])
    if graph_version:
        lines.extend(
            [
                f"- 图谱版本：{graph_version.get('graph_version', '未生成')}",
                f"- 更新时间：{graph_version.get('updated_at', '')}",
                f"- 最新更新类型：{graph_version.get('latest_update_type', '')}",
                f"- 实体数：{graph_version.get('entity_count', 0)}",
                f"- 关系数：{graph_version.get('relation_count', 0)}",
            ]
        )
    else:
        lines.append("- 当前未读取到知识图谱版本信息。")

    return "\n".join(lines).strip() + "\n"

import secrets
import string
import requests
import time


def generate_api_key(prefix: str = "fw") -> str:
    """生成 API Key，格式：fw_xxxxxxxxxxxxxxxx"""
    chars = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(16))
    return f"{prefix}_{random_part}"


def get_api_docs() -> dict[str, Any]:
    """返回 API 文档定义"""
    return {
        "title": "急性胸痛临床决策支持 API",
        "version": "1.0.0",
        "description": "提供急性胸痛临床诊断、知识图谱生成、主动问诊等 API 接口，支持医院系统集成。",
        "contact": {
            "name": "API 申请支持",
            "email": "api-support@example.com",
            "url": "https://example.com/api-apply",
        },
        "endpoints": [
            {
                "path": "/api/diagnose",
                "method": "POST",
                "category": "诊断服务",
                "summary": "急性胸痛诊断分析",
                "description": "输入患者病历文本，返回诊断结果、推理路径和知识图谱高亮。",
                "auth_required": True,
                "request_body": {
                    "patient_description": "string - 患者病历文本（必填）",
                    "model": "string - 模型名称，默认 gpt-4o-mini",
                    "method": "string - 诊断方法：all_methods | step_by_step | direct | direct_generation | intermediate_state | full_workflow",
                },
                "response": {
                    "diagnosis": "诊断结论",
                    "graph_path": "知识图谱路径",
                    "steps": "推理步骤",
                    "intermediate_states": "中间状态",
                },
                "example": {
                    "patient_description": "患者男，65岁。胸骨后压榨性胸痛3小时，向左肩放射...",
                    "model": "gpt-4o-mini",
                    "method": "step_by_step",
                },
            },
            {
                "path": "/api/knowledge-graph/build",
                "method": "GET",
                "category": "知识图谱",
                "summary": "生成基础临床知识图谱",
                "description": "根据当前临床流程配置生成基础知识图谱，输出 .ckg.json、.mmd、.svg 文件。",
                "auth_required": True,
                "response": {
                    "ok": "boolean",
                    "message": "结果说明",
                    "artifacts": "图谱产物路径",
                    "version_info": "版本信息",
                },
            },
            {
                "path": "/api/knowledge-graph/mineru-ingest",
                "method": "POST",
                "category": "知识图谱",
                "summary": "合并 MinerU 文档解析结果",
                "description": "将 MinerU 解析的临床文档合并到知识图谱，支持增量更新。",
                "auth_required": True,
                "request_body": {
                    "title": "string - 文档标题",
                    "mineru_payload": "object - MinerU 解析结果（markdown/json）",
                },
            },
            {
                "path": "/api/knowledge-graph/mineru-agent-url",
                "method": "POST",
                "category": "知识图谱",
                "summary": "通过 MinerU Agent URL 解析文档并合并到知识图谱",
                "description": "提交远程文档 URL，通过 MinerU Agent 解析后合并到知识图谱。",
                "auth_required": True,
                "request_body": {
                    "url": "string - 远程文档 URL（必填）",
                    "title": "string - 文档标题",
                    "language": "string - 解析语言，默认 'ch'",
                    "page_range": "string - 页码范围，如 '1-10'"
                },
            },
            {
                "path": "/api/knowledge-graph/mineru-agent-file",
                "method": "POST",
                "category": "知识图谱",
                "summary": "通过 MinerU Agent 文件上传解析文档并合并到知识图谱",
                "description": "上传本地文档，通过 MinerU Agent 解析后合并到知识图谱。",
                "auth_required": True,
                "request_body": {
                    "file_path": "string - 本地文件路径（必填）",
                    "title": "string - 文档标题",
                    "language": "string - 解析语言，默认 'ch'",
                    "page_range": "string - 页码范围，如 '1-10'"
                },
            },
            {
                "path": "/api/knowledge-graph/status",
                "method": "GET",
                "category": "知识图谱",
                "summary": "获取知识图谱状态",
                "description": "返回当前知识图谱版本、产物路径和更新历史。",
                "auth_required": False,
            },
            {
                "path": "/api/proactive/create",
                "method": "POST",
                "category": "主动问诊",
                "summary": "创建主动问诊会话",
                "description": "输入患者主诉，创建多轮问诊会话，AI 将主动追问收集临床信息。",
                "auth_required": True,
                "request_body": {
                    "patient_input": "string - 患者主诉（必填）",
                    "model": "string - 模型名称",
                    "max_turns": "int - 最大问诊轮次，默认 6",
                },
            },
            {
                "path": "/api/proactive/question",
                "method": "POST",
                "category": "主动问诊",
                "summary": "获取主动问诊问题",
                "description": "获取当前会话的 AI 追问问题。",
                "auth_required": True,
                "request_body": {
                    "session_id": "string - 会话 ID（必填）",
                },
            },
            {
                "path": "/api/proactive/answer",
                "method": "POST",
                "category": "主动问诊",
                "summary": "提交患者回答",
                "description": "提交患者对当前问题的回答，获取下一轮问题或诊断结果。",
                "auth_required": True,
                "request_body": {
                    "session_id": "string - 会话 ID（必填）",
                    "answer": "string - 患者回答（必填）",
                },
            },
            {
                "path": "/api/health",
                "method": "GET",
                "category": "系统",
                "summary": "健康检查",
                "description": "返回服务状态和可用功能。",
                "auth_required": False,
            },
        ],
        "categories": [
            {"key": "诊断服务", "description": "急性胸痛临床诊断分析"},
            {"key": "知识图谱", "description": "临床知识图谱生成与管理"},
            {"key": "主动问诊", "description": "AI 驱动的多轮问诊"},
            {"key": "系统", "description": "系统状态与健康检查"},
        ],
        "code_examples": {
            "python": '''import requests

API_BASE = "https://your-domain.com"
API_KEY = "fw_your_api_key"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 诊断接口
response = requests.post(
    f"{API_BASE}/api/diagnose",
    headers=headers,
    json={
        "patient_description": "患者男，65岁。胸骨后压榨性胸痛3小时...",
        "model": "gpt-4o-mini",
        "method": "step_by_step",
        "api_key": API_KEY
    }
)
result = response.json()
print(f"诊断结果: {result['diagnosis']}")
''',
            "curl": '''# 诊断接口
curl -X POST "https://your-domain.com/api/diagnose" \\
  -H "Content-Type: application/json" \\
  -d '{
    "patient_description": "患者男，65岁。胸骨后压榨性胸痛3小时...",
    "model": "gpt-4o-mini",
    "method": "step_by_step",
    "api_key": "fw_your_api_key"
  }'

# 知识图谱状态
curl "https://your-domain.com/api/knowledge-graph/status"
''',
            "javascript": '''const API_BASE = 'https://your-domain.com';
const API_KEY = 'fw_your_api_key';

// 诊断接口
async function diagnose(patientDescription) {
  const response = await fetch(`${API_BASE}/api/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      patient_description: patientDescription,
      model: 'gpt-4o-mini',
      method: 'step_by_step',
      api_key: API_KEY
    })
  });
  return response.json();
}

// 使用示例
const result = await diagnose('患者男，65岁。胸骨后压榨性胸痛3小时...');
console.log('诊断结果:', result.diagnosis);
''',
        },
    }

from .routes import register_routes

register_routes(app)


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
