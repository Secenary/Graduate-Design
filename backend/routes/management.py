import json
import secrets
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from ..server import (
    API_APPLICATIONS_PATH,
    API_KEYS_PATH,
    DEFAULT_MODEL,
    DEFAULT_WORKFLOW_ID,
    FRONTEND_DIR,
    REPORTS_DIR,
    ROOT_DIR,
    TRAINING_DATA_DIR,
    get_workflow_definition,
    list_workflow_definitions,
    append_jsonl,
    generate_api_key,
    get_api_docs,
    get_db,
    iso_timestamp,
    make_case_id,
    read_jsonl,
    to_web_path,
    Case,
)

bp = Blueprint("management_routes", __name__)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


@bp.get("/api/docs")
def get_api_documentation():
    return jsonify(get_api_docs())


@bp.post("/api/keys/apply")
def apply_for_api_key():
    payload = request.get_json(silent=True) or {}
    applicant_name = str(payload.get("applicant_name", "")).strip()
    applicant_email = str(payload.get("applicant_email", "")).strip()
    organization = str(payload.get("organization", "")).strip()

    if not applicant_name:
        return jsonify({"ok": False, "error": "applicant_name 不能为空"}), 400
    if not applicant_email:
        return jsonify({"ok": False, "error": "applicant_email 不能为空"}), 400
    if not organization:
        return jsonify({"ok": False, "error": "organization 不能为空"}), 400

    application = {
        "application_id": f"app_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}",
        "applicant_name": applicant_name,
        "applicant_email": applicant_email,
        "organization": organization,
        "purpose": str(payload.get("purpose", "")).strip(),
        "phone": str(payload.get("phone", "")).strip(),
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
        "message": "API Key 申请已提交。",
        "application_id": application["application_id"],
        "application": application,
    })


@bp.get("/api/keys/applications")
def list_api_applications():
    applications = read_jsonl(API_APPLICATIONS_PATH, limit=1000)
    return jsonify({"ok": True, "applications": applications, "total": len(applications)})


@bp.post("/api/keys/review")
def review_api_application():
    payload = request.get_json(silent=True) or {}
    application_id = str(payload.get("application_id", "")).strip()
    action = str(payload.get("action", "")).strip()
    reviewer = str(payload.get("reviewer", "admin")).strip() or "admin"
    comment = str(payload.get("comment", "")).strip()

    if not application_id:
        return jsonify({"ok": False, "error": "application_id 不能为空"}), 400
    if action not in {"approve", "reject"}:
        return jsonify({"ok": False, "error": "action 必须是 approve 或 reject"}), 400

    applications = read_jsonl(API_APPLICATIONS_PATH, limit=1000)
    match_index = next((index for index, item in enumerate(applications) if item.get("application_id") == application_id), None)
    if match_index is None:
        return jsonify({"ok": False, "error": "application 不存在"}), 404

    application = applications[match_index]
    if application.get("status") != "pending":
        return jsonify({"ok": False, "error": f"application 当前状态为 {application.get('status')}，不可重复处理"}), 400

    application["reviewed_at"] = iso_timestamp()
    application["reviewer"] = reviewer
    application["review_comment"] = comment

    if action == "approve":
        api_key = generate_api_key()
        application["status"] = "approved"
        application["api_key"] = api_key
        append_jsonl(API_KEYS_PATH, {
            "api_key": api_key,
            "application_id": application_id,
            "applicant_name": application.get("applicant_name", ""),
            "applicant_email": application.get("applicant_email", ""),
            "organization": application.get("organization", ""),
            "created_at": iso_timestamp(),
            "status": "active",
            "usage_count": 0,
        })
    else:
        application["status"] = "rejected"

    applications[match_index] = application
    write_jsonl(API_APPLICATIONS_PATH, applications)
    return jsonify({"ok": True, "message": f"application 已{ '批准' if action == 'approve' else '拒绝' }。", "application": application})


@bp.get("/api/keys/status/<application_id>")
def check_application_status(application_id: str):
    applications = read_jsonl(API_APPLICATIONS_PATH, limit=1000)
    application = next((item for item in applications if item.get("application_id") == application_id), None)
    if application is None:
        return jsonify({"ok": False, "error": "application 不存在"}), 404
    return jsonify({
        "ok": True,
        "application": {
            "application_id": application.get("application_id"),
            "status": application.get("status"),
            "applied_at": application.get("applied_at"),
            "reviewed_at": application.get("reviewed_at"),
            "api_key": application.get("api_key") if application.get("status") == "approved" else None,
        },
    })


@bp.get("/api/keys/list")
def list_api_keys():
    keys = read_jsonl(API_KEYS_PATH, limit=1000)
    return jsonify({"ok": True, "keys": keys, "total": len(keys)})


@bp.post("/api/cases")
def create_case():
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
        record_id = db.save_case(case)
        return jsonify({"ok": True, "message": "病例已保存。", "case_id": case.case_id, "id": record_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存病例失败: {exc}"}), 500


@bp.get("/api/cases")
def list_cases():
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
        result = []
        for item in cases:
            case_dict = item.to_dict()
            case_dict["tags"] = db.get_tags(item.case_id)
            case_dict["reviews"] = [review.to_dict() for review in db.get_reviews(item.case_id)]
            result.append(case_dict)
        return jsonify({"ok": True, "cases": result, "total": total, "limit": limit, "offset": offset})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"查询病例失败: {exc}"}), 500

@bp.get("/api/cases/<case_id>")
def get_case_detail(case_id: str):
    try:
        db = get_db()
        case = db.get_case(case_id)
        if not case:
            return jsonify({"ok": False, "error": "病例不存在"}), 404
        case_dict = case.to_dict()
        case_dict["tags"] = db.get_tags(case_id)
        case_dict["reviews"] = [review.to_dict() for review in db.get_reviews(case_id)]
        return jsonify({"ok": True, "case": case_dict})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取病例失败: {exc}"}), 500


@bp.delete("/api/cases/<case_id>")
def delete_case(case_id: str):
    try:
        db = get_db()
        if not db.delete_case(case_id):
            return jsonify({"ok": False, "error": "病例不存在"}), 404
        return jsonify({"ok": True, "message": "病例已删除。"})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"删除病例失败: {exc}"}), 500


@bp.post("/api/cases/<case_id>/tags")
def add_case_tag(case_id: str):
    payload = request.get_json(silent=True) or {}
    tag = str(payload.get("tag", "")).strip()
    if not tag:
        return jsonify({"ok": False, "error": "tag 不能为空"}), 400
    try:
        db = get_db()
        if not db.add_tag(case_id, tag):
            return jsonify({"ok": False, "error": "标签已存在"}), 400
        return jsonify({"ok": True, "message": "标签已添加。", "tag": tag})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"添加标签失败: {exc}"}), 500


@bp.delete("/api/cases/<case_id>/tags/<tag>")
def remove_case_tag(case_id: str, tag: str):
    try:
        db = get_db()
        if not db.remove_tag(case_id, tag):
            return jsonify({"ok": False, "error": "标签不存在"}), 404
        return jsonify({"ok": True, "message": "标签已移除。"})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"移除标签失败: {exc}"}), 500


@bp.get("/api/cases/tags")
def list_all_tags():
    try:
        return jsonify({"ok": True, "tags": get_db().get_all_tags()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取标签失败: {exc}"}), 500


@bp.get("/api/cases/statistics")
def get_cases_statistics():
    try:
        return jsonify({"ok": True, "statistics": get_db().get_statistics()})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取统计失败: {exc}"}), 500


@bp.post("/api/cases/export-training")
def export_training_data():
    payload = request.get_json(silent=True) or {}
    export_name = str(payload.get("export_name", f"training_data_{iso_timestamp()}"))
    output_path = TRAINING_DATA_DIR / f"{export_name}.jsonl"
    try:
        result = get_db().export_training_data(
            output_path=output_path,
            diagnosis=payload.get("diagnosis"),
            has_review=payload.get("has_review"),
            tags=payload.get("tags") or None,
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


@bp.get("/api/cases/<case_id>/reviews")
def get_case_reviews(case_id: str):
    try:
        reviews = get_db().get_reviews(case_id)
        return jsonify({"ok": True, "reviews": [review.to_dict() for review in reviews]})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"获取复核记录失败: {exc}"}), 500


def serialize_workflow_definition(definition):
    config_path = Path(definition["config_path"])
    return {
        "workflow_id": definition["workflow_id"],
        "name": definition["name"],
        "specialty": definition.get("specialty", ""),
        "status": definition.get("status", "draft"),
        "relative_config_path": definition.get("relative_config_path", str(config_path)),
        "config_exists": config_path.exists(),
    }


@bp.get("/api/workflow/configs")
def list_workflow_configs():
    workflows = [serialize_workflow_definition(item) for item in list_workflow_definitions()]
    return jsonify({
        "ok": True,
        "default_workflow_id": DEFAULT_WORKFLOW_ID,
        "workflows": workflows,
    })


@bp.get("/api/workflow/config")
def get_workflow_config():
    workflow_id = request.args.get("workflow_id")
    try:
        workflow = get_workflow_definition(workflow_id)
        config_path = Path(workflow["config_path"])
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        return jsonify({
            "ok": True,
            "workflow": serialize_workflow_definition(workflow),
            "config": config,
        })
    except KeyError:
        return jsonify({"ok": False, "error": f"未知 workflow_id: {workflow_id or DEFAULT_WORKFLOW_ID}"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"读取流程配置失败: {exc}"}), 500


@bp.post("/api/workflow/config")
def save_workflow_config():
    payload = request.get_json(silent=True) or {}
    config = payload.get("config")
    workflow_id = payload.get("workflow_id")
    if not isinstance(config, dict):
        return jsonify({"ok": False, "error": "config 必须是 JSON 对象"}), 400
    try:
        workflow = get_workflow_definition(workflow_id)
        config_path = Path(workflow["config_path"])
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({
            "ok": True,
            "message": f"流程配置已保存到 {workflow['relative_config_path']}",
            "workflow": serialize_workflow_definition(workflow),
            "config": config,
        })
    except KeyError:
        return jsonify({"ok": False, "error": f"未知 workflow_id: {workflow_id or DEFAULT_WORKFLOW_ID}"}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"保存流程配置失败: {exc}"}), 500


@bp.get("/<path:path>")
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
