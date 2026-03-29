"""
主动问诊会话管理模块。

管理多轮主动问诊过程中的会话状态，包括对话历史、已收集事实、
中间诊断状态和 think block 推理记录。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

_SESSION_STORE: dict[str, ProactiveSession] = {}
_MAX_AGE_MINUTES = 60


@dataclass
class ProactiveSession:
    """单次主动问诊的完整会话状态。"""

    session_id: str
    patient_input: str
    model: str
    client_config: dict[str, Any]
    current_step: int = 1
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    collected_facts: dict[str, Any] = field(default_factory=dict)
    intermediate_states: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    think_blocks: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    max_turns: int = 6
    status: str = "questioning"  # questioning | completed | max_turns_reached
    diagnosis: str | None = None
    diagnosis_detail: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    # ---------- 便捷方法 ----------

    def append_doctor_turn(self, question: str, think_block: dict[str, Any] | None = None, sig_score: float = 0.0) -> None:
        """记录一轮医生追问。"""
        self.conversation_history.append({"role": "doctor", "content": question})
        self.think_blocks.append(
            {
                "turn": self.turn_count,
                "think_block": think_block or {},
                "sig_score": sig_score,
            }
        )

    def append_patient_turn(self, answer: str) -> None:
        """记录一轮患者回复。"""
        self.conversation_history.append({"role": "patient", "content": answer})
        self.turn_count += 1

    def build_accumulated_text(self) -> str:
        """将原始输入与所有患者回复拼接成完整病历文本。"""
        parts = [self.patient_input]
        for entry in self.conversation_history:
            if entry["role"] == "patient":
                parts.append(entry["content"])
        return "\n".join(part for part in parts if part)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 安全的字典。"""
        return {
            "session_id": self.session_id,
            "patient_input": self.patient_input,
            "model": self.model,
            "current_step": self.current_step,
            "conversation_history": self.conversation_history,
            "collected_facts": self.collected_facts,
            "intermediate_states": self.intermediate_states,
            "steps": self.steps,
            "think_blocks": self.think_blocks,
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
            "status": self.status,
            "diagnosis": self.diagnosis,
            "diagnosis_detail": self.diagnosis_detail,
            "created_at": self.created_at.isoformat(),
        }


# ---------- CRUD 操作 ----------


def create_session(
    patient_input: str,
    model: str,
    client_config: dict[str, Any] | None = None,
    max_turns: int = 6,
) -> ProactiveSession:
    """创建新的主动问诊会话。"""
    cleanup_stale_sessions()
    session_id = f"ps_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    session = ProactiveSession(
        session_id=session_id,
        patient_input=patient_input,
        model=model,
        client_config=client_config or {},
        max_turns=max_turns,
    )
    _SESSION_STORE[session_id] = session
    return session


def get_session(session_id: str) -> ProactiveSession | None:
    """根据 ID 获取会话。"""
    return _SESSION_STORE.get(session_id)


def update_session(session_id: str, **kwargs: Any) -> None:
    """更新会话字段。"""
    session = _SESSION_STORE.get(session_id)
    if session is None:
        return
    for key, value in kwargs.items():
        if hasattr(session, key):
            setattr(session, key, value)


def delete_session(session_id: str) -> None:
    """删除会话。"""
    _SESSION_STORE.pop(session_id, None)


def cleanup_stale_sessions(max_age_minutes: int = _MAX_AGE_MINUTES) -> int:
    """清理超时会话，返回清理数量。"""
    cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
    stale_ids = [sid for sid, sess in _SESSION_STORE.items() if sess.created_at < cutoff]
    for sid in stale_ids:
        del _SESSION_STORE[sid]
    return len(stale_ids)
