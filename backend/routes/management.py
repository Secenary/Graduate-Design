import json
import secrets
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory

from ..server import (
    API_APPLICATIONS_PATH,
    API_KEYS_PATH,
    DEFAULT_MODEL,
    FRONTEND_DIR,
    REPORTS_DIR,
    ROOT_DIR,
    TRAINING_DATA_DIR,
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

@bp.get("/api/docs")
def get_api_documentation():
    """返回 API 文档"""
    return jsonify(get_api_docs())


@bp.post("/api/keys/apply")
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


@bp.get("/api/keys/applications")
def list_api_applications():
    """列出所有 API Key 申请（管理员接口）"""
    applications = read_jsonl(API_APPLICATIONS_PATH, limit=100)
    return jsonify({
        "ok": True,
        "applications": applications,
        "total": len(applications),
    })


@bp.post("/api/keys/review")
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


@bp.get("/api/keys/status/<application_id>")
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


@bp.get("/api/keys/list")
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

@bp.post("/api/cases")
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


@bp.get("/api/cases")
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


@bp.get("/api/cases/<case_id>")
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


@bp.delete("/api/cases/<case_id>")
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


@bp.post("/api/cases/<case_id>/tags")
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


@bp.delete("/api/cases/<case_id>/tags/<tag>")
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


@bp.get("/api/cases/tags")
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


@bp.get("/api/cases/statistics")
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


@bp.post("/api/cases/export-training")
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


@bp.get("/api/cases/<case_id>/reviews")
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
