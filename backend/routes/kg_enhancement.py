from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from ..server import (
    KNOWLEDGE_GRAPH_DIR,
    RESULTS_DIR,
    ROOT_DIR,
    get_current_kg_enhancement_manager,
)

bp = Blueprint("kg_enhancement_routes", __name__)

@bp.get("/api/kg-enhancement/status")
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


@bp.post("/api/kg-enhancement/extract")
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


@bp.get("/api/kg-enhancement/review-items")
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




@bp.get("/api/kg-enhancement/graph-snapshot")
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


@bp.post("/api/kg-enhancement/review")
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


@bp.post("/api/kg-enhancement/workflow-match")
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


@bp.post("/api/kg-enhancement/merge")
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


@bp.post("/api/kg-enhancement/export")
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


@bp.get("/api/kg-enhancement/download/<filename>")
def download_kg_file(filename: str):
    """Download KG file"""
    try:
        file_path = KNOWLEDGE_GRAPH_DIR / filename
        if not file_path.exists():
            return jsonify({"ok": False, "error": "文件不存在"}), 404
        return send_from_directory(KNOWLEDGE_GRAPH_DIR, filename, as_attachment=True)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"下载失败：{exc}"}), 500
