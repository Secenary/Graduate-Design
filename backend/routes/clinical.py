from flask import Blueprint, jsonify, request, send_from_directory
import os

from ..server import (
    DEFAULT_MODEL,
    FRONTEND_DIR,
    GENERATED_DATA_PATH,
    KNOWLEDGE_GRAPH_DIR,
    METHOD_MAP,
    REPORTS_DIR,
    REVIEWS_PATH,
    TRANSITIONS_PATH,
    TRAINING_DATA_DIR,
    append_jsonl,
    build_case_replay,
    build_graph_path,
    build_markdown_report,
    build_reasoning_enhancement_bundle,
    build_training_data,
    collect_training_status,
    get_db,
    get_exported_graph_status,
    iso_timestamp,
    make_case_id,
    normalize_patient_input,
    read_jsonl,
    run_all_methods,
    run_async,
    to_web_path,
    Case,
    DoctorReview,
)

bp = Blueprint("clinical_routes", __name__)

@bp.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@bp.get("/api/health")
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


@bp.post("/api/diagnose")
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
        message = f"诊断失败: {exc}"
        if method == "all_methods":
            message += "；当前方法 all_methods 会触发多次模型调用，超时时建议改用 step_by_step 或 direct。"
        return jsonify({"error": message}), 500

@bp.post("/api/review")
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



@bp.get("/api/reviews/recent")
def recent_reviews():
    limit = max(1, min(int(request.args.get("limit", 5)), 20))
    return jsonify({"ok": True, "reviews": read_jsonl(REVIEWS_PATH, limit=limit)})


@bp.get("/api/training/status")
def training_status():
    try:
        return jsonify({"ok": True, **collect_training_status()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"训练中心状态读取失败: {exc}"}), 500


@bp.post("/api/training/prepare")
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


@bp.get("/api/report/download/<path:filename>")
def download_report(filename: str):
    return send_from_directory(REPORTS_DIR, filename)


@bp.get("/results/reports/<path:filename>")
def download_report_legacy(filename: str):
    return send_from_directory(REPORTS_DIR, filename)


@bp.post("/api/report/export")
def export_report():
    payload = request.get_json(silent=True) or {}
    case_id = str(payload.get("case_id", "")).strip()

    if not case_id:
        return jsonify({"ok": False, "error": "case_id \u4e0d\u80fd\u4e3a\u7a7a"}), 400

    report_markdown = build_markdown_report(payload)
    report_filename = f"{case_id}_diagnosis_report.md"
    report_path = REPORTS_DIR / report_filename
    report_path.write_text(report_markdown, encoding="utf-8")

    return jsonify(
        {
            "ok": True,
            "message": "\u8bca\u65ad\u62a5\u544a\u5df2\u5bfc\u51fa\u3002",
            "report_path": str(report_path),
            "download_url": f"/api/report/download/{report_filename}",
            "legacy_download_url": to_web_path(report_path),
        }
    )


# ---------------------------------------------------------------------------
# 主动问诊 API 端点
# ---------------------------------------------------------------------------
