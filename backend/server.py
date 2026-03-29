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
TRANSITIONS_PATH = ROOT_DIR / "transitions.json"
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


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
            "accepts_runtime_api_settings": True,
            "default_model": DEFAULT_MODEL,
            "available_methods": ["all_methods", *METHOD_MAP.keys()],
            "supports_case_replay": True,
            "supports_doctor_review": True,
            "supports_report_export": True,
            "supports_reasoning_enhancement": True,
            "supports_training_center": True,
        }
    )


@app.post("/api/diagnose")
def diagnose():
    payload = request.get_json(silent=True) or {}
    patient_description = str(payload.get("patient_description", "")).strip()
    model = str(payload.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    method = str(payload.get("method", "all_methods")).strip() or "all_methods"
    api_key = str(payload.get("api_key", "")).strip()
    base_url = str(payload.get("base_url", "")).strip()
    case_id = make_case_id(patient_description) if patient_description else ""
    client_config = {
        "api_key": api_key,
        "base_url": base_url,
    }

    if not patient_description:
        return jsonify({"error": "patient_description 不能为空"}), 400

    if not api_key and not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "未配置 OPENAI_API_KEY。请在网页中填写 API Key，或在服务端 .env 中配置。"}), 400

    if method != "all_methods" and method not in METHOD_MAP:
        return jsonify({"error": f"不支持的方法: {method}"}), 400

    try:
        if method == "all_methods":
            results = run_async(run_all_methods(patient_description, model, client_config=client_config))
        else:
            results = {method: run_async(METHOD_MAP[method](patient_description, model, client_config=client_config))}

        primary_method = "step_by_step" if "step_by_step" in results else next(iter(results.keys()))
        primary_result = results.get("step_by_step") or next(iter(results.values()))
        diagnosis = primary_result.get("diagnosis", "未知")
        intermediate_states = primary_result.get("intermediate_states", {})
        halt_step = primary_result.get("halt_step")
        graph_path = build_graph_path(diagnosis, intermediate_states, halt_step=halt_step)
        patient_case = normalize_patient_input(patient_description)
        case_replay = build_case_replay(patient_description, primary_result, diagnosis, case_id)
        graph_status = get_exported_graph_status(TRANSITIONS_PATH, KNOWLEDGE_GRAPH_DIR)
        reasoning_bundle = build_reasoning_enhancement_bundle(
            patient_case=patient_case,
            diagnosis=diagnosis,
            steps=primary_result.get("steps", []),
            halt_step=halt_step,
        )

        # 自动保存病例到数据库
        try:
            db = get_db()
            case = Case(
                case_id=case_id,
                patient_description=patient_description,
                diagnosis=diagnosis,
                intermediate_states=intermediate_states,
                steps=primary_result.get("steps", []),
                graph_path=graph_path,
                model=model,
                method=method,
                confidence="规则匹配" if diagnosis in ["STEMI", "NSTEMI", "UA", "变异型心绞痛", "其他"] else "需复核",
                status=primary_result.get("status", "completed"),
                halt_step=halt_step,
                halt_reason=primary_result.get("reason", ""),
                missing_items=primary_result.get("missing_items", []),
                recommendation=primary_result.get("recommendation", ""),
                raw_response=primary_result.get("raw_response", ""),
            )
            db.save_case(case)
            case_saved = True
        except Exception as e:
            print(f"保存病例到数据库失败: {e}")
            case_saved = False

        return jsonify(
            {
                "case_id": case_id,
                "patient_description": patient_description,
                "diagnosis": diagnosis,
                "status": primary_result.get("status", "completed"),
                "model": model,
                "method": method,
                "results": results,
                "primary_method": primary_method,
                "graph_path": graph_path,
                "intermediate_states": intermediate_states,
                "steps": primary_result.get("steps", []),
                "halt_step": halt_step,
                "halt_category": primary_result.get("halt_category", ""),
                "reason": primary_result.get("reason", ""),
                "missing_items": primary_result.get("missing_items", []),
                "recommendation": primary_result.get("recommendation", ""),
                "raw_response": primary_result.get("raw_response", ""),
                "case_replay": case_replay,
                "graph_version_info": graph_status.get("version_info", {}),
                "graph_history": graph_status.get("history", []),
                "preprocessed_case": reasoning_bundle["preprocessed_case"],
                "question_gain_analysis": reasoning_bundle["question_gain_analysis"],
                "trajectory_quality": reasoning_bundle["trajectory_quality"],
                "next_question_recommendations": reasoning_bundle["next_question_recommendations"],
                "single_turn_reasoning_samples": reasoning_bundle["single_turn_reasoning_samples"],
                "case_saved": case_saved,
            }
        )
    except Exception as exc:
        return jsonify({"error": f"诊断失败: {exc}"}), 500


@app.get("/api/knowledge-graph/status")
def knowledge_graph_status():
    try:
        status = get_exported_graph_status(TRANSITIONS_PATH, KNOWLEDGE_GRAPH_DIR)
        if status.get("artifacts"):
            status["artifacts"] = {
                key: to_web_path(value) if value else ""
                for key, value in status["artifacts"].items()
            }
        return jsonify({"ok": True, **status})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"知识图谱状态读取失败: {exc}"}), 500


@app.get("/api/knowledge-graph/build")
def build_knowledge_graph():
    try:
        graph_payload = normalize_graph_response(
            build_and_export_graph(
                transitions_path=TRANSITIONS_PATH,
                output_dir=KNOWLEDGE_GRAPH_DIR,
            )
        )
        return jsonify(
            {
                "ok": True,
                "message": "已根据当前临床流程生成基础知识图谱。",
                **graph_payload,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"知识图谱生成失败: {exc}"}), 500


@app.post("/api/knowledge-graph/mineru-ingest")
def ingest_mineru_knowledge_graph():
    payload = request.get_json(silent=True) or {}
    mineru_payload = payload.get("mineru_payload")
    title = str(payload.get("title", "MinerU Clinical Document")).strip() or "MinerU Clinical Document"

    if mineru_payload is None:
        return jsonify({"ok": False, "error": "mineru_payload 不能为空"}), 400

    try:
        graph_payload = normalize_graph_response(
            build_and_export_graph(
                transitions_path=TRANSITIONS_PATH,
                output_dir=KNOWLEDGE_GRAPH_DIR,
                mineru_payload=mineru_payload,
                mineru_title=title,
            )
        )
        return jsonify(
            {
                "ok": True,
                "message": "已将 MinerU 文档解析结果合并进知识图谱。",
                **graph_payload,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU 图谱更新失败: {exc}"}), 500


@app.post("/api/review")
def save_review():
    payload = request.get_json(silent=True) or {}
    case_id = str(payload.get("case_id", "")).strip()
    reviewer_name = str(payload.get("reviewer_name", "")).strip() or "未署名医生"
    review_action = str(payload.get("review_action", "")).strip() or "confirm"
    reviewed_diagnosis = str(payload.get("reviewed_diagnosis", "")).strip()

    if not case_id:
        return jsonify({"ok": False, "error": "case_id 不能为空"}), 400
    if not reviewed_diagnosis:
        return jsonify({"ok": False, "error": "reviewed_diagnosis 不能为空"}), 400

    record = {
        "case_id": case_id,
        "reviewer_name": reviewer_name,
        "review_action": review_action,
        "reviewed_diagnosis": reviewed_diagnosis,
        "comment": str(payload.get("comment", "")).strip(),
        "ai_diagnosis": str(payload.get("ai_diagnosis", "")).strip(),
        "patient_description": str(payload.get("patient_description", "")).strip(),
        "graph_version": str(payload.get("graph_version", "")).strip(),
        "reviewed_at": iso_timestamp(),
    }
    append_jsonl(REVIEWS_PATH, record)

    # 同时保存到数据库
    db_saved = False
    db_error = None
    try:
        db = get_db()
        review = DoctorReview(
            case_id=case_id,
            reviewer_name=reviewer_name,
            review_action=review_action,
            reviewed_diagnosis=reviewed_diagnosis,
            comment=record["comment"],
            ai_diagnosis=record["ai_diagnosis"],
            patient_description=record["patient_description"],
            graph_version=record["graph_version"],
            reviewed_at=record["reviewed_at"],
        )
        db.save_review(review)
        db_saved = True
    except Exception as e:
        print(f"保存复核记录到数据库失败：{e}")
        import traceback
        traceback.print_exc()
        db_error = str(e)

    return jsonify(
        {
            "ok": True,
            "message": "医生复核记录已保存。" + ("" if db_saved else f"（数据库保存失败：{db_error}）"),
            "review": record,
            "recent_reviews": read_jsonl(REVIEWS_PATH, limit=5),
            "db_saved": db_saved,
        }
    )



@app.get("/api/reviews/recent")
def recent_reviews():
    limit = max(1, min(int(request.args.get("limit", 5)), 20))
    return jsonify({"ok": True, "reviews": read_jsonl(REVIEWS_PATH, limit=limit)})


@app.get("/api/training/status")
def training_status():
    try:
        return jsonify({"ok": True, **collect_training_status()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"训练中心状态读取失败: {exc}"}), 500


@app.post("/api/training/prepare")
def prepare_training():
    try:
        result = build_training_data(
            input_path=GENERATED_DATA_PATH,
            output_dir=TRAINING_DATA_DIR,
            review_path=REVIEWS_PATH,
        )
        status = collect_training_status()
        return jsonify(
            {
                "ok": True,
                "message": "已重新生成 SFT / 偏好学习 / RL 风格训练数据。",
                "prepare_result": result,
                **status,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"训练数据生成失败: {exc}"}), 500


@app.post("/api/report/export")
def export_report():
    payload = request.get_json(silent=True) or {}
    case_id = str(payload.get("case_id", "")).strip()

    if not case_id:
        return jsonify({"ok": False, "error": "case_id 不能为空"}), 400

    report_markdown = build_markdown_report(payload)
    report_path = REPORTS_DIR / f"{case_id}_diagnosis_report.md"
    report_path.write_text(report_markdown, encoding="utf-8")

    return jsonify(
        {
            "ok": True,
            "message": "诊断报告已导出。",
            "report_path": str(report_path),
            "download_url": to_web_path(report_path),
        }
    )


# ---------------------------------------------------------------------------
# 主动问诊 API 端点
# ---------------------------------------------------------------------------


@app.post("/api/proactive/create")
def create_proactive_session():
    """
    创建主动问诊会话。
    
    接收患者初始主诉，创建会话并返回 session_id。
    """
    payload = request.get_json(silent=True) or {}
    patient_input = str(payload.get("patient_input", "")).strip()
    model = str(payload.get("model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    api_key = str(payload.get("api_key", "")).strip()
    base_url = str(payload.get("base_url", "")).strip()
    max_turns = int(payload.get("max_turns", 6))

    if not patient_input:
        return jsonify({"error": "patient_input 不能为空"}), 400

    if not api_key and not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "未配置 OPENAI_API_KEY。请在网页中填写 API Key，或在服务端 .env 中配置。"}), 400

    client_config = {
        "api_key": api_key,
        "base_url": base_url,
    }

    try:
        session = create_session(
            patient_input=patient_input,
            model=model,
            client_config=client_config,
            max_turns=max_turns,
        )
        return jsonify(
            {
                "ok": True,
                "session_id": session.session_id,
                "message": "主动问诊会话已创建。",
                "max_turns": session.max_turns,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"创建会话失败：{exc}"}), 500


@app.post("/api/proactive/question")
def get_proactive_question():
    """
    获取主动问诊问题。
    
    根据 session_id 获取当前会话状态，生成主动追问问题。
    """
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id", "")).strip()

    if not session_id:
        return jsonify({"error": "session_id 不能为空"}), 400

    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "会话不存在或已过期"}), 404

    try:
        # 运行主动诊断，获取问题
        result = run_async(
            proactive_diagnosis(
                patient_input=session.patient_input,
                model=session.model,
                client_config=session.client_config,
                session=session,
            )
        )

        if result.get("status") == "questioning":
            return jsonify(
                {
                    "ok": True,
                    "session_id": session_id,
                    "turn": result.get("turn", 0),
                    "current_step": result.get("current_step", 1),
                    "question": result.get("question", ""),
                    "think_block": result.get("think_block", {}),
                    "sig_score": result.get("sig_score", 0),
                    "sig_components": result.get("sig_components", {}),
                    "collected_facts": result.get("collected_facts", {}),
                    "missing_items": result.get("missing_items", []),
                    "status": "questioning",
                }
            )
        elif result.get("status") == "completed":
            return jsonify(
                {
                    "ok": True,
                    "session_id": session_id,
                    "turn": result.get("turn", 0),
                    "diagnosis": result.get("diagnosis", ""),
                    "steps": result.get("steps", []),
                    "intermediate_states": result.get("intermediate_states", {}),
                    "status": "completed",
                }
            )
        elif result.get("status") == "max_turns_reached":
            return jsonify(
                {
                    "ok": True,
                    "session_id": session_id,
                    "turn": result.get("turn", 0),
                    "current_step": result.get("current_step", 1),
                    "message": result.get("message", ""),
                    "missing_items": result.get("missing_items", []),
                    "steps": result.get("steps", []),
                    "intermediate_states": result.get("intermediate_states", {}),
                    "status": "max_turns_reached",
                }
            )
        else:
            return jsonify(
                {
                    "ok": False,
                    "error": "无法生成问题，请检查输入信息。",
                    "status": result.get("status", "unknown"),
                }
            )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"生成问题失败：{exc}"}), 500


@app.post("/api/proactive/answer")
def submit_proactive_answer():
    """
    提交患者回答。
    
    接收患者对当前问题的回答，更新会话状态并返回下一轮问题或诊断结果。
    """
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id", "")).strip()
    answer = str(payload.get("answer", "")).strip()

    if not session_id:
        return jsonify({"error": "session_id 不能为空"}), 400
    if not answer:
        return jsonify({"error": "answer 不能为空"}), 400

    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "会话不存在或已过期"}), 404

    try:
        # 记录患者回答
        session.append_patient_turn(answer)

        # 运行主动诊断，获取下一轮问题或诊断结果
        result = run_async(
            proactive_diagnosis(
                patient_input=session.patient_input,
                model=session.model,
                client_config=session.client_config,
                session=session,
            )
        )

        if result.get("status") == "questioning":
            return jsonify(
                {
                    "ok": True,
                    "session_id": session_id,
                    "turn": result.get("turn", 0),
                    "current_step": result.get("current_step", 1),
                    "question": result.get("question", ""),
                    "think_block": result.get("think_block", {}),
                    "sig_score": result.get("sig_score", 0),
                    "collected_facts": result.get("collected_facts", {}),
                    "missing_items": result.get("missing_items", []),
                    "status": "questioning",
                }
            )
        elif result.get("status") == "completed":
            return jsonify(
                {
                    "ok": True,
                    "session_id": session_id,
                    "turn": result.get("turn", 0),
                    "diagnosis": result.get("diagnosis", ""),
                    "steps": result.get("steps", []),
                    "intermediate_states": result.get("intermediate_states", {}),
                    "status": "completed",
                }
            )
        elif result.get("status") == "max_turns_reached":
            return jsonify(
                {
                    "ok": True,
                    "session_id": session_id,
                    "turn": result.get("turn", 0),
                    "current_step": result.get("current_step", 1),
                    "message": result.get("message", ""),
                    "missing_items": result.get("missing_items", []),
                    "steps": result.get("steps", []),
                    "intermediate_states": result.get("intermediate_states", {}),
                    "status": "max_turns_reached",
                }
            )
        else:
            return jsonify(
                {
                    "ok": False,
                    "error": "无法继续问诊流程。",
                    "status": result.get("status", "unknown"),
                }
            )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"提交回答失败：{exc}"}), 500


@app.get("/api/proactive/session/<session_id>")
def get_proactive_session_status(session_id: str):
    """
    获取主动问诊会话状态。
    
    返回当前会话的完整状态信息。
    """
    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "会话不存在或已过期"}), 404

    return jsonify(
        {
            "ok": True,
            "session_id": session.session_id,
            "status": session.status,
            "current_step": session.current_step,
            "turn_count": session.turn_count,
            "max_turns": session.max_turns,
            "diagnosis": session.diagnosis,
            "diagnosis_detail": session.diagnosis_detail,
            "conversation_history": session.conversation_history,
            "collected_facts": session.collected_facts,
            "intermediate_states": session.intermediate_states,
            "steps": session.steps,
            "think_blocks": session.think_blocks,
            "created_at": session.created_at.isoformat(),
        }
    )


@app.delete("/api/proactive/session/<session_id>")
def close_proactive_session(session_id: str):
    """
    关闭主动问诊会话。
    
    删除指定会话，释放资源。
    """
    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "会话不存在或已过期"}), 404

    delete_session(session_id)
    return jsonify(
        {
            "ok": True,
            "message": "会话已关闭。",
            "session_id": session_id,
        }
    )


# ---------------------------------------------------------------------------
# API 管理接口
# ---------------------------------------------------------------------------

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


@app.post("/api/knowledge-graph/mineru-url")
@app.post("/api/knowledge-graph/mineru-agent-url")
def ingest_mineru_url():
    """通过 MinerU v4 URL 解析文档并合并到知识图谱。"""
    payload = request.get_json(silent=True) or {}
    source_url = str(payload.get("url", "")).strip()
    title = str(payload.get("title", "")).strip() or "MinerU URL Document"
    token = _resolve_mineru_token(payload.get("token"))

    if not source_url:
        return jsonify({"ok": False, "error": "url 不能为空"}), 400
    if not token:
        return jsonify({"ok": False, "error": "未提供 MinerU token，且服务端未配置 MINERU_API_TOKEN"}), 400

    try:
        import_result = parse_url_document(
            token,
            source_url,
            options=_collect_mineru_options(payload),
        )
        graph_payload = _merge_mineru_graph_payload(import_result["payload"], title)
        return jsonify(
            {
                "ok": True,
                "message": "已按 MinerU v4 文档解析远程文档并合并到知识图谱。",
                "mineru_job": {
                    "mode": "url",
                    "task_id": import_result["task_id"],
                    "state": import_result["task_result"].get("state"),
                    "source_url": source_url,
                    "full_zip_url": import_result["full_zip_url"],
                },
                "mineru_payload_summary": import_result["payload_summary"],
                **graph_payload,
            }
        )
    except MinerUError as exc:
        return jsonify({"ok": False, "error": f"MinerU URL 解析失败: {exc}"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU URL 图谱更新失败: {exc}"}), 500


@app.post("/api/knowledge-graph/mineru-file")
@app.post("/api/knowledge-graph/mineru-agent-file")
def ingest_mineru_file():
    """通过 MinerU v4 文件上传解析文档并合并到知识图谱。"""
    form_payload = request.form.to_dict() if request.form else {}
    json_payload = request.get_json(silent=True) or {}
    payload = {**json_payload, **form_payload}

    uploaded_file = request.files.get("file")
    file_path = str(payload.get("file_path", "")).strip()
    token = _resolve_mineru_token(payload.get("token"))

    if not token:
        return jsonify({"ok": False, "error": "未提供 MinerU token，且服务端未配置 MINERU_API_TOKEN"}), 400

    file_name = ""
    file_bytes = b""
    if uploaded_file and uploaded_file.filename:
        file_name = uploaded_file.filename
        file_bytes = uploaded_file.read()
    elif file_path:
        local_path = Path(file_path)
        if not local_path.is_absolute():
            local_path = ROOT_DIR / local_path
        if not local_path.exists():
            return jsonify({"ok": False, "error": f"文件不存在: {local_path}"}), 400
        file_name = local_path.name
        file_bytes = local_path.read_bytes()
    else:
        return jsonify({"ok": False, "error": "请上传文件，或提供 file_path"}), 400

    if not file_bytes:
        return jsonify({"ok": False, "error": "文件内容为空"}), 400

    title = str(payload.get("title", "")).strip() or file_name or "MinerU Upload Document"

    try:
        import_result = parse_uploaded_file(
            token,
            file_name,
            file_bytes,
            options=_collect_mineru_options(payload),
        )
        graph_payload = _merge_mineru_graph_payload(import_result["payload"], title)
        return jsonify(
            {
                "ok": True,
                "message": "已按 MinerU v4 文档上传文件、完成解析并合并到知识图谱。",
                "mineru_job": {
                    "mode": "file",
                    "batch_id": import_result["batch_id"],
                    "state": import_result["task_result"].get("state"),
                    "file_name": file_name,
                    "full_zip_url": import_result["full_zip_url"],
                },
                "mineru_payload_summary": import_result["payload_summary"],
                **graph_payload,
            }
        )
    except MinerUError as exc:
        return jsonify({"ok": False, "error": f"MinerU 文件解析失败: {exc}"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU 文件图谱更新失败: {exc}"}), 500


@app.get("/api/docs")
def get_api_documentation():
    """返回 API 文档"""
    return jsonify(get_api_docs())


@app.post("/api/keys/apply")
def apply_for_api_key():
    """
    申请 API Key。

    用户提交申请信息，管理员审核后发放 API Key。
    """
    payload = request.get_json(silent=True) or {}
    applicant_name = str(payload.get("applicant_name", "")).strip()
    applicant_email = str(payload.get("applicant_email", "")).strip()
    organization = str(payload.get("organization", "")).strip()
    purpose = str(payload.get("purpose", "")).strip()
    phone = str(payload.get("phone", "")).strip()

    if not applicant_name:
        return jsonify({"ok": False, "error": "申请人姓名不能为空"}), 400
    if not applicant_email:
        return jsonify({"ok": False, "error": "申请人邮箱不能为空"}), 400
    if not organization:
        return jsonify({"ok": False, "error": "所属机构不能为空"}), 400

    application_id = f"app_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"

    application = {
        "application_id": application_id,
        "applicant_name": applicant_name,
        "applicant_email": applicant_email,
        "organization": organization,
        "purpose": purpose,
        "phone": phone,
        "status": "pending",
        "applied_at": iso_timestamp(),
        "reviewed_at": None,
        "reviewer": None,
        "api_key": None,
        "review_comment": None,
    }

    append_jsonl(API_APPLICATIONS_PATH, application)

    return jsonify({
        "ok": True,
        "message": "API Key 申请已提交，请等待管理员审核。审核结果将通过邮件通知。",
        "application_id": application_id,
        "application": application,
    })


@app.get("/api/keys/applications")
def list_api_applications():
    """列出所有 API Key 申请（管理员接口）"""
    applications = read_jsonl(API_APPLICATIONS_PATH, limit=100)
    return jsonify({
        "ok": True,
        "applications": applications,
        "total": len(applications),
    })


@app.post("/api/keys/review")
def review_api_application():
    """审核 API Key 申请（管理员接口）"""
    payload = request.get_json(silent=True) or {}
    application_id = str(payload.get("application_id", "")).strip()
    action = str(payload.get("action", "")).strip()
    reviewer = str(payload.get("reviewer", "admin")).strip()
    comment = str(payload.get("comment", "")).strip()

    if not application_id:
        return jsonify({"ok": False, "error": "application_id 不能为空"}), 400
    if action not in ("approve", "reject"):
        return jsonify({"ok": False, "error": "action 必须是 approve 或 reject"}), 400

    applications = read_jsonl(API_APPLICATIONS_PATH, limit=1000)
    application = None
    application_index = -1

    for i, app in enumerate(applications):
        if app.get("application_id") == application_id:
            application = app
            application_index = i
            break

    if application is None:
        return jsonify({"ok": False, "error": "申请不存在"}), 404

    if application.get("status") != "pending":
        return jsonify({"ok": False, "error": f"申请已处理，当前状态：{application.get('status')}"}), 400

    if action == "approve":
        api_key = generate_api_key()
        application["status"] = "approved"
        application["api_key"] = api_key
        application["reviewed_at"] = iso_timestamp()
        application["reviewer"] = reviewer
        application["review_comment"] = comment

        key_record = {
            "api_key": api_key,
            "application_id": application_id,
            "applicant_name": application["applicant_name"],
            "applicant_email": application["applicant_email"],
            "organization": application["organization"],
            "created_at": iso_timestamp(),
            "status": "active",
            "usage_count": 0,
        }
        append_jsonl(API_KEYS_PATH, key_record)
    else:
        application["status"] = "rejected"
        application["reviewed_at"] = iso_timestamp()
        application["reviewer"] = reviewer
        application["review_comment"] = comment

    applications[application_index] = application
    API_APPLICATIONS_PATH.write_text(
        "\n".join(json.dumps(app, ensure_ascii=False) for app in applications),
        encoding="utf-8"
    )

    return jsonify({
        "ok": True,
        "message": f"申请已{'批准' if action == 'approve' else '拒绝'}。",
        "application": application,
    })


@app.get("/api/keys/status/<application_id>")
def check_application_status(application_id: str):
    """查询申请状态"""
    applications = read_jsonl(API_APPLICATIONS_PATH, limit=1000)

    for app in applications:
        if app.get("application_id") == application_id:
            return jsonify({
                "ok": True,
                "application": {
                    "application_id": app.get("application_id"),
                    "status": app.get("status"),
                    "applied_at": app.get("applied_at"),
                    "reviewed_at": app.get("reviewed_at"),
                    "api_key": app.get("api_key") if app.get("status") == "approved" else None,
                },
            })

    return jsonify({"ok": False, "error": "申请不存在"}), 404


@app.get("/api/keys/list")
def list_api_keys():
    """列出所有 API Key（管理员接口）"""
    keys = read_jsonl(API_KEYS_PATH, limit=100)
    return jsonify({
        "ok": True,
        "keys": keys,
        "total": len(keys),
    })


# ---------------------------------------------------------------------------
# 病例数据库 API
# ---------------------------------------------------------------------------

@app.post("/api/cases")
def create_case():
    """保存病例到数据库"""
    payload = request.get_json(silent=True) or {}

    case = Case(
        case_id=payload.get("case_id") or make_case_id(payload.get("patient_description", "")),
        patient_description=payload.get("patient_description", ""),
        diagnosis=payload.get("diagnosis", ""),
        intermediate_states=payload.get("intermediate_states", {}),
        steps=payload.get("steps", []),
        graph_path=payload.get("graph_path", {}),
        model=payload.get("model", DEFAULT_MODEL),
        method=payload.get("method", "step_by_step"),
        confidence=payload.get("confidence", ""),
        status=payload.get("status", "completed"),
        halt_step=payload.get("halt_step"),
        halt_reason=payload.get("halt_reason", ""),
        missing_items=payload.get("missing_items", []),
        recommendation=payload.get("recommendation", ""),
        raw_response=payload.get("raw_response", ""),
    )

    try:
        db = get_db()
        case_id = db.save_case(case)
        return jsonify({
            "ok": True,
            "message": "病例已保存到数据库。",
            "case_id": case.case_id,
            "id": case_id,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存病例失败: {exc}"}), 500


@app.get("/api/cases")
def list_cases():
    """查询病例列表"""
    diagnosis = request.args.get("diagnosis")
    status = request.args.get("status")
    search = request.args.get("search")
    tags = request.args.getlist("tag")
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))

    try:
        db = get_db()
        cases, total = db.get_cases(
            diagnosis=diagnosis,
            status=status,
            tags=tags if tags else None,
            search=search,
            limit=limit,
            offset=offset,
        )

        # 获取每个病例的标签和复核记录
        result = []
        for case in cases:
            case_dict = case.to_dict()
            case_dict["tags"] = db.get_tags(case.case_id)
            case_dict["reviews"] = [r.to_dict() for r in db.get_reviews(case.case_id)]
            result.append(case_dict)

        return jsonify({
            "ok": True,
            "cases": result,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"查询病例失败: {exc}"}), 500


@app.get("/api/cases/<case_id>")
def get_case_detail(case_id: str):
    """获取病例详情"""
    try:
        db = get_db()
        case = db.get_case(case_id)
        if not case:
            return jsonify({"ok": False, "error": "病例不存在"}), 404

        case_dict = case.to_dict()
        case_dict["tags"] = db.get_tags(case_id)
        case_dict["reviews"] = [r.to_dict() for r in db.get_reviews(case_id)]

        return jsonify({
            "ok": True,
            "case": case_dict,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取病例失败: {exc}"}), 500


@app.delete("/api/cases/<case_id>")
def delete_case(case_id: str):
    """删除病例"""
    try:
        db = get_db()
        if db.delete_case(case_id):
            return jsonify({
                "ok": True,
                "message": "病例已删除。",
            })
        else:
            return jsonify({"ok": False, "error": "病例不存在"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": f"删除病例失败: {exc}"}), 500


@app.post("/api/cases/<case_id>/tags")
def add_case_tag(case_id: str):
    """添加病例标签"""
    payload = request.get_json(silent=True) or {}
    tag = payload.get("tag", "").strip()

    if not tag:
        return jsonify({"ok": False, "error": "标签不能为空"}), 400

    try:
        db = get_db()
        if db.add_tag(case_id, tag):
            return jsonify({
                "ok": True,
                "message": "标签已添加。",
                "tag": tag,
            })
        else:
            return jsonify({"ok": False, "error": "标签已存在"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"添加标签失败: {exc}"}), 500


@app.delete("/api/cases/<case_id>/tags/<tag>")
def remove_case_tag(case_id: str, tag: str):
    """移除病例标签"""
    try:
        db = get_db()
        if db.remove_tag(case_id, tag):
            return jsonify({
                "ok": True,
                "message": "标签已移除。",
            })
        else:
            return jsonify({"ok": False, "error": "标签不存在"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": f"移除标签失败: {exc}"}), 500


@app.get("/api/cases/tags")
def list_all_tags():
    """获取所有标签"""
    try:
        db = get_db()
        tags = db.get_all_tags()
        return jsonify({
            "ok": True,
            "tags": tags,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取标签失败: {exc}"}), 500


@app.get("/api/cases/statistics")
def get_cases_statistics():
    """获取病例统计信息"""
    try:
        db = get_db()
        stats = db.get_statistics()
        return jsonify({
            "ok": True,
            "statistics": stats,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取统计信息失败: {exc}"}), 500


@app.post("/api/cases/export-training")
def export_training_data():
    """导出训练数据"""
    payload = request.get_json(silent=True) or {}
    diagnosis = payload.get("diagnosis")
    has_review = payload.get("has_review")
    tags = payload.get("tags", [])
    export_name = payload.get("export_name", f"training_data_{iso_timestamp()}")

    output_path = TRAINING_DATA_DIR / f"{export_name}.jsonl"

    try:
        db = get_db()
        result = db.export_training_data(
            output_path=output_path,
            diagnosis=diagnosis,
            has_review=has_review,
            tags=tags if tags else None,
        )

        return jsonify({
            "ok": True,
            "message": "训练数据已导出。",
            "export": {
                "name": export_name,
                "path": str(output_path),
                "download_url": to_web_path(output_path),
                "case_count": result["total"],
                "filters": result["filters"],
            },
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"导出训练数据失败: {exc}"}), 500


@app.get("/api/cases/<case_id>/reviews")
def get_case_reviews(case_id: str):
    """获取病例的复核记录"""
    try:
        db = get_db()
        reviews = db.get_reviews(case_id)
        return jsonify({
            "ok": True,
            "reviews": [r.to_dict() for r in reviews],
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取复核记录失败: {exc}"}), 500


@app.get("/<path:path>")
def static_files(path: str):
    frontend_target = FRONTEND_DIR / path
    root_target = ROOT_DIR / path
    reports_target = REPORTS_DIR / path.removeprefix("results/reports/")
    
    if frontend_target.is_file():
        return send_from_directory(FRONTEND_DIR, path)
    if root_target.is_file():
        return send_from_directory(ROOT_DIR, path)
    if path.startswith("results/reports/") and reports_target.is_file():
        return send_from_directory(REPORTS_DIR, path.removeprefix("results/reports/"))
    return send_from_directory(FRONTEND_DIR, "index.html")


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()


# ==================== KG Enhancement APIs ====================

@app.get("/api/kg-enhancement/status")
def get_kg_enhancement_status():
    """Get KG enhancement module status"""
    try:
        manager = get_current_kg_enhancement_manager()
        review_items = manager.get_review_items() if manager.kg is not None else []
        return jsonify({
            "ok": True,
            "kg_loaded": manager.kg is not None,
            "kg_name": manager.kg.name if manager.kg else None,
            "entity_count": len(manager.kg.entities) if manager.kg else 0,
            "extracted_terms_count": len(manager.extracted_terms),
            "review_records_count": len(manager.review_records),
            "review_items_count": len(review_items),
            "approved_groups_count": len([item for item in review_items if item.get("review_status") == "approved"]),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取状态失败：{exc}"}), 500


@app.post("/api/kg-enhancement/extract")
def extract_terms_from_cases():
    """Extract clinical terms from patient case files"""
    try:
        manager = get_current_kg_enhancement_manager()
        payload = request.get_json(silent=True) or {}
        case_dir_str = payload.get("case_dir")

        if case_dir_str:
            case_dir = Path(case_dir_str)
            if not case_dir.is_absolute():
                case_dir = ROOT_DIR / case_dir
        else:
            case_dir = ROOT_DIR / "data" / "cardiovascular_files"

        if not case_dir.exists():
            return jsonify({"ok": False, "error": f"病例目录不存在：{case_dir}"}), 400

        terms = manager.extract_terms_from_cases(case_dir)
        state_path = RESULTS_DIR / "kg_enhancement_state.json"
        manager.save_review_state(state_path)

        return jsonify({
            "ok": True,
            "message": f"从 {case_dir.name} 提取到 {len(terms)} 个临床术语",
            "terms_count": len(terms),
            "categories": {
                "symptom": len([t for t in terms if t.category == "symptom"]),
                "finding": len([t for t in terms if t.category == "finding"]),
                "exam": len([t for t in terms if t.category == "exam"]),
                "diagnosis": len([t for t in terms if t.category == "diagnosis"]),
            },
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"提取术语失败：{exc}"}), 500


@app.get("/api/kg-enhancement/review-items")
def get_review_items():
    """Get items ready for doctor review"""
    try:
        manager = get_current_kg_enhancement_manager()
        if not manager.extracted_terms:
            state_path = RESULTS_DIR / "kg_enhancement_state.json"
            if state_path.exists():
                manager.load_review_state(state_path)

        review_items = manager.get_review_items()
        return jsonify({"ok": True, "review_items": review_items, "total_count": len(review_items)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取复核项目失败：{exc}"}), 500




@app.get("/api/kg-enhancement/graph-snapshot")
def get_kg_graph_snapshot():
    """Return the current latest knowledge graph for enhancement preview."""
    try:
        manager = get_current_kg_enhancement_manager()
        if manager.kg is None:
            return jsonify({"ok": False, "error": "未加载知识图谱"}), 400

        entities = [entity.to_dict() for entity in manager.kg.entities.values()]
        relations = [relation.to_dict() for relation in manager.kg.relations.values()]

        return jsonify({
            "ok": True,
            "graph": {
                "graph_id": manager.kg.graph_id,
                "name": manager.kg.name,
                "metadata": manager.kg.metadata,
                "entities": entities,
                "relations": relations,
                "entity_count": len(entities),
                "relation_count": len(relations),
            },
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取知识图谱快照失败：{exc}"}), 500


@app.post("/api/kg-enhancement/review")
def submit_kg_review():
    """Submit doctor review for term group"""
    try:
        payload = request.get_json(silent=True) or {}
        group_key = payload.get("group_key")
        action = payload.get("action")
        reviewer_name = payload.get("reviewer_name")
        comment = payload.get("comment", "")
        canonical_term = payload.get("canonical_term")

        if not group_key or not action or not reviewer_name:
            return jsonify({"ok": False, "error": "缺少必要参数：group_key, action, reviewer_name"}), 400

        manager = get_current_kg_enhancement_manager()
        result = manager.submit_review(group_key, action, reviewer_name, comment, canonical_term)
        if not result.get("success"):
            return jsonify({"ok": False, "error": result.get("error", "\u63d0\u4ea4\u5ba1\u6838\u5931\u8d25")}), 400

        state_path = RESULTS_DIR / "kg_enhancement_state.json"
        manager.save_review_state(state_path)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"提交复核失败：{exc}"}), 500


@app.post("/api/kg-enhancement/workflow-match")
def save_kg_workflow_match():
    """Save manual workflow-node mapping for a review item."""
    try:
        payload = request.get_json(silent=True) or {}
        group_key = payload.get("group_key")
        reviewer_name = payload.get("reviewer_name")
        workflow_node_ids = payload.get("workflow_node_ids", [])

        if not group_key or not reviewer_name:
            return jsonify({"ok": False, "error": "\u7f3a\u5c11\u5fc5\u8981\u5b57\u6bb5\uff1agroup_key, reviewer_name"}), 400
        if not isinstance(workflow_node_ids, list):
            return jsonify({"ok": False, "error": "workflow_node_ids \u5fc5\u987b\u662f\u6570\u7ec4"}), 400

        manager = get_current_kg_enhancement_manager()
        result = manager.set_manual_workflow_nodes(group_key, workflow_node_ids, reviewer_name)
        if not result.get("success"):
            return jsonify({"ok": False, "error": result.get("error", "\u4fdd\u5b58\u6d41\u7a0b\u8282\u70b9\u5339\u914d\u5931\u8d25")}), 400

        state_path = RESULTS_DIR / "kg_enhancement_state.json"
        manager.save_review_state(state_path)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"\u4fdd\u5b58\u6d41\u7a0b\u8282\u70b9\u5339\u914d\u5931\u8d25\uff1a{exc}"}), 500


@app.post("/api/kg-enhancement/merge")
def merge_approved_terms():
    """Merge all approved terms into knowledge graph"""
    try:
        manager = get_current_kg_enhancement_manager()
        if manager.kg is None:
            return jsonify({"ok": False, "error": "未加载知识图谱"}), 400

        result = manager.merge_approved_terms()
        if result["success"]:
            output_path = KNOWLEDGE_GRAPH_DIR / f"{manager.kg.graph_id}_enhanced.ckg.json"
            export_result = manager.export_enhanced_kg(output_path)
            state_path = RESULTS_DIR / "kg_enhancement_state.json"
            manager.save_review_state(state_path)
            return jsonify({
                "ok": True,
                "message": "已合并审核通过的术语到知识图谱",
                "stats": result["stats"],
                "export": export_result,
                "download_url": f"/api/kg-enhancement/download/{output_path.name}",
            })
        return jsonify(result), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"合并术语失败：{exc}"}), 500


@app.post("/api/kg-enhancement/export")
def export_enhanced_kg():
    """Export enhanced knowledge graph"""
    try:
        payload = request.get_json(silent=True) or {}
        output_name = payload.get("output_name", "enhanced_knowledge_graph")
        manager = get_current_kg_enhancement_manager()

        if manager.kg is None:
            return jsonify({"ok": False, "error": "未加载知识图谱"}), 400

        output_path = KNOWLEDGE_GRAPH_DIR / f"{output_name}.ckg.json"
        result = manager.export_enhanced_kg(output_path)

        if result["success"]:
            return jsonify({
                "ok": True,
                "message": "知识图谱已导出",
                "output_path": result["output_path"],
                "download_url": f"/api/kg-enhancement/download/{output_name}.ckg.json",
                "entity_count": result["entity_count"],
                "relation_count": result["relation_count"],
            })
        return jsonify(result), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"导出知识图谱失败：{exc}"}), 500


@app.get("/api/kg-enhancement/download/<filename>")
def download_kg_file(filename: str):
    """Download KG file"""
    try:
        file_path = KNOWLEDGE_GRAPH_DIR / filename
        if not file_path.exists():
            return jsonify({"ok": False, "error": "文件不存在"}), 404
        return send_from_directory(KNOWLEDGE_GRAPH_DIR, filename, as_attachment=True)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"下载失败：{exc}"}), 500




