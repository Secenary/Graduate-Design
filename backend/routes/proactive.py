import os

from flask import Blueprint, jsonify, request

from ..server import (
    DEFAULT_MODEL,
    create_session,
    delete_session,
    get_session,
    proactive_diagnosis,
    run_async,
)

bp = Blueprint("proactive_routes", __name__)

@bp.post("/api/proactive/create")
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


@bp.post("/api/proactive/question")
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


@bp.post("/api/proactive/answer")
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


@bp.get("/api/proactive/session/<session_id>")
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


@bp.delete("/api/proactive/session/<session_id>")
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
