from pathlib import Path

from flask import Blueprint, jsonify, request

from ..server import (
    DEFAULT_WORKFLOW_ID,
    KNOWLEDGE_GRAPH_DIR,
    ROOT_DIR,
    _collect_mineru_options,
    _resolve_mineru_token,
    build_and_export_graph,
    get_exported_graph_status,
    get_workflow_definition,
    normalize_graph_response,
    parse_uploaded_file,
    parse_url_document,
    to_web_path,
    MinerUError,
)

bp = Blueprint("knowledge_graph_routes", __name__)


def serialize_workflow_definition(definition):
    config_path = Path(definition["config_path"])
    return {
        "workflow_id": definition["workflow_id"],
        "name": definition["name"],
        "specialty": definition.get("specialty", ""),
        "status": definition.get("status", "draft"),
        "relative_config_path": definition.get("relative_config_path", str(config_path)),
    }


def resolve_workflow_definition(payload=None):
    workflow_id = None
    if isinstance(payload, dict):
        workflow_id = payload.get("workflow_id")
    workflow_id = workflow_id or request.args.get("workflow_id") or request.form.get("workflow_id")
    try:
        return get_workflow_definition(workflow_id)
    except KeyError as exc:
        raise ValueError(f"未知 workflow_id: {workflow_id or DEFAULT_WORKFLOW_ID}") from exc


def with_workflow_metadata(response_payload, workflow):
    return {**response_payload, "workflow": serialize_workflow_definition(workflow)}


def build_graph_payload(workflow, mineru_payload=None, mineru_title="MinerU Clinical Document"):
    return normalize_graph_response(
        build_and_export_graph(
            transitions_path=workflow["config_path"],
            output_dir=KNOWLEDGE_GRAPH_DIR,
            mineru_payload=mineru_payload,
            mineru_title=mineru_title,
        )
    )


@bp.get("/api/knowledge-graph/status")
def knowledge_graph_status():
    try:
        workflow = resolve_workflow_definition()
        status = get_exported_graph_status(workflow["config_path"], KNOWLEDGE_GRAPH_DIR)
        if status.get("artifacts"):
            status["artifacts"] = {
                key: to_web_path(value) if value else ""
                for key, value in status["artifacts"].items()
            }
        return jsonify(with_workflow_metadata({"ok": True, **status}, workflow))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"知识图谱状态读取失败: {exc}"}), 500


@bp.get("/api/knowledge-graph/build")
def build_knowledge_graph():
    try:
        workflow = resolve_workflow_definition()
        graph_payload = build_graph_payload(workflow)
        return jsonify(with_workflow_metadata({
            "ok": True,
            "message": f"已根据 {workflow['name']} 生成基础知识图谱。",
            **graph_payload,
        }, workflow))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"知识图谱生成失败: {exc}"}), 500


@bp.post("/api/knowledge-graph/mineru-ingest")
def ingest_mineru_knowledge_graph():
    payload = request.get_json(silent=True) or {}
    mineru_payload = payload.get("mineru_payload")
    title = str(payload.get("title", "MinerU Clinical Document")).strip() or "MinerU Clinical Document"

    if mineru_payload is None:
        return jsonify({"ok": False, "error": "mineru_payload 不能为空"}), 400

    try:
        workflow = resolve_workflow_definition(payload)
        graph_payload = build_graph_payload(workflow, mineru_payload=mineru_payload, mineru_title=title)
        return jsonify(with_workflow_metadata({
            "ok": True,
            "message": f"已将 MinerU 结果合并到 {workflow['name']} 知识图谱。",
            **graph_payload,
        }, workflow))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU 图谱更新失败: {exc}"}), 500


@bp.post("/api/knowledge-graph/mineru-url")
@bp.post("/api/knowledge-graph/mineru-agent-url")
def ingest_mineru_url():
    payload = request.get_json(silent=True) or {}
    source_url = str(payload.get("url", "")).strip()
    title = str(payload.get("title", "")).strip() or "MinerU URL Document"
    token = _resolve_mineru_token(payload.get("token"))

    if not source_url:
        return jsonify({"ok": False, "error": "url 不能为空"}), 400
    if not token:
        return jsonify({"ok": False, "error": "未提供 MinerU token，且服务端未配置 MINERU_API_TOKEN"}), 400

    try:
        workflow = resolve_workflow_definition(payload)
        import_result = parse_url_document(
            token,
            source_url,
            options=_collect_mineru_options(payload),
        )
        graph_payload = build_graph_payload(workflow, mineru_payload=import_result["payload"], mineru_title=title)
        return jsonify(with_workflow_metadata({
            "ok": True,
            "message": f"已按 MinerU v4 远程文档解析并更新 {workflow['name']} 图谱。",
            "mineru_job": {
                "mode": "url",
                "task_id": import_result["task_id"],
                "state": import_result["task_result"].get("state"),
                "source_url": source_url,
                "full_zip_url": import_result["full_zip_url"],
            },
            "mineru_payload_summary": import_result["payload_summary"],
            **graph_payload,
        }, workflow))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except MinerUError as exc:
        return jsonify({"ok": False, "error": f"MinerU URL 解析失败: {exc}"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU URL 图谱更新失败: {exc}"}), 500


@bp.post("/api/knowledge-graph/mineru-file")
@bp.post("/api/knowledge-graph/mineru-agent-file")
def ingest_mineru_file():
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
        workflow = resolve_workflow_definition(payload)
        import_result = parse_uploaded_file(
            token,
            file_name,
            file_bytes,
            options=_collect_mineru_options(payload),
        )
        graph_payload = build_graph_payload(workflow, mineru_payload=import_result["payload"], mineru_title=title)
        return jsonify(with_workflow_metadata({
            "ok": True,
            "message": f"已按 MinerU v4 上传文档并更新 {workflow['name']} 图谱。",
            "mineru_job": {
                "mode": "file",
                "batch_id": import_result["batch_id"],
                "state": import_result["task_result"].get("state"),
                "file_name": file_name,
                "full_zip_url": import_result["full_zip_url"],
            },
            "mineru_payload_summary": import_result["payload_summary"],
            **graph_payload,
        }, workflow))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except MinerUError as exc:
        return jsonify({"ok": False, "error": f"MinerU 文件解析失败: {exc}"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": f"MinerU 文件图谱更新失败: {exc}"}), 500
