"""
Flask 后端：提供静态页面与模型诊断 API。
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from clinical_knowledge_graph import build_and_export_graph
from methods import (
    direct_diagnosis,
    direct_generation_diagnosis,
    intermediate_state_diagnosis,
    full_workflow_diagnosis,
    run_all_methods,
    step_by_step_diagnosis,
)

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

app = Flask(__name__, static_folder=str(ROOT_DIR), static_url_path="")
KNOWLEDGE_GRAPH_DIR = ROOT_DIR / "knowledge_graph"

METHOD_MAP = {
    "direct": direct_diagnosis,
    "direct_generation": direct_generation_diagnosis,
    "intermediate_state": intermediate_state_diagnosis,
    "full_workflow": full_workflow_diagnosis,
    "step_by_step": step_by_step_diagnosis,
}


def build_graph_path(
    diagnosis: str,
    intermediate_states: dict | None = None,
    halt_step: int | None = None
) -> dict:
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

    if diagnosis == "变异性心绞痛" or (st_elevation is True and biomarker_elevated is False):
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


def run_async(coro):
    """
    在 Flask 同步视图中运行异步诊断函数。
    """
    return asyncio.run(coro)


@app.get("/")
def index():
    return send_from_directory(ROOT_DIR, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
            "accepts_runtime_api_settings": True,
            "default_model": DEFAULT_MODEL,
            "available_methods": ["all_methods", *METHOD_MAP.keys()],
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

        primary_result = results.get("step_by_step") or next(iter(results.values()))
        diagnosis = primary_result.get("diagnosis", "未知")
        intermediate_states = primary_result.get("intermediate_states", {})
        halt_step = primary_result.get("halt_step")

        return jsonify(
            {
                "diagnosis": diagnosis,
                "status": primary_result.get("status", "completed"),
                "model": model,
                "method": method,
                "results": results,
                "primary_method": "step_by_step" if "step_by_step" in results else next(iter(results.keys())),
                "graph_path": build_graph_path(diagnosis, intermediate_states, halt_step=halt_step),
                "intermediate_states": intermediate_states,
                "steps": primary_result.get("steps", []),
                "halt_step": halt_step,
                "halt_category": primary_result.get("halt_category", ""),
                "reason": primary_result.get("reason", ""),
                "missing_items": primary_result.get("missing_items", []),
                "recommendation": primary_result.get("recommendation", ""),
                "raw_response": primary_result.get("raw_response", ""),
            }
        )
    except Exception as exc:
        return jsonify({"error": f"诊断失败: {exc}"}), 500


@app.get("/api/knowledge-graph/build")
def build_knowledge_graph():
    try:
        artifacts = build_and_export_graph(
            transitions_path=ROOT_DIR / "transitions.json",
            output_dir=KNOWLEDGE_GRAPH_DIR,
        )
        return jsonify(
            {
                "ok": True,
                "message": "已根据当前临床流程生成基础知识图谱。",
                "artifacts": artifacts,
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
        artifacts = build_and_export_graph(
            transitions_path=ROOT_DIR / "transitions.json",
            output_dir=KNOWLEDGE_GRAPH_DIR,
            mineru_payload=mineru_payload,
            mineru_title=title,
        )
        return jsonify(
            {
                "ok": True,
                "message": "已将 MinerU 文档解析结果合并进知识图谱。",
                "artifacts": artifacts,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU 图谱更新失败: {exc}"}), 500


@app.get("/<path:path>")
def static_files(path: str):
    target = ROOT_DIR / path
    if target.is_file():
        return send_from_directory(ROOT_DIR, path)
    return send_from_directory(ROOT_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
