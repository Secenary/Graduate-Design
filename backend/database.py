"""
数据库模块：提供病例持久化存储、查询和导出功能。

支持：
1. 病例存储和检索
2. 医生复核记录关联
3. 标签管理
4. 训练数据导出
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from contextlib import contextmanager

DATABASE_PATH = Path(__file__).parent.parent / "results" / "clinical_cases.db"


@dataclass
class Case:
    """病例数据模型"""
    id: Optional[int] = None
    case_id: str = ""
    patient_description: str = ""
    diagnosis: str = ""
    intermediate_states: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    graph_path: dict = field(default_factory=dict)
    model: str = "gpt-4o-mini"
    method: str = "step_by_step"
    confidence: str = ""
    status: str = "completed"  # completed, halted
    halt_step: Optional[int] = None
    halt_reason: str = ""
    missing_items: list = field(default_factory=list)
    recommendation: str = ""
    raw_response: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "patient_description": self.patient_description,
            "diagnosis": self.diagnosis,
            "intermediate_states": self.intermediate_states,
            "steps": self.steps,
            "graph_path": self.graph_path,
            "model": self.model,
            "method": self.method,
            "confidence": self.confidence,
            "status": self.status,
            "halt_step": self.halt_step,
            "halt_reason": self.halt_reason,
            "missing_items": self.missing_items,
            "recommendation": self.recommendation,
            "raw_response": self.raw_response,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DoctorReview:
    """医生复核数据模型"""
    id: Optional[int] = None
    case_id: str = ""
    reviewer_name: str = ""
    review_action: str = ""  # confirm, revise, supplement
    reviewed_diagnosis: str = ""
    comment: str = ""
    ai_diagnosis: str = ""
    patient_description: str = ""
    graph_version: str = ""
    reviewed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "reviewer_name": self.reviewer_name,
            "review_action": self.review_action,
            "reviewed_diagnosis": self.reviewed_diagnosis,
            "comment": self.comment,
            "ai_diagnosis": self.ai_diagnosis,
            "patient_description": self.patient_description,
            "graph_version": self.graph_version,
            "reviewed_at": self.reviewed_at,
        }


@dataclass
class CaseTag:
    """病例标签数据模型"""
    id: Optional[int] = None
    case_id: str = ""
    tag: str = ""
    created_at: Optional[str] = None


class Database:
    """数据库管理类"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 病例表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT UNIQUE NOT NULL,
                    patient_description TEXT NOT NULL,
                    diagnosis TEXT NOT NULL,
                    intermediate_states TEXT DEFAULT '{}',
                    steps TEXT DEFAULT '[]',
                    graph_path TEXT DEFAULT '{}',
                    model TEXT DEFAULT 'gpt-4o-mini',
                    method TEXT DEFAULT 'step_by_step',
                    confidence TEXT DEFAULT '',
                    status TEXT DEFAULT 'completed',
                    halt_step INTEGER,
                    halt_reason TEXT DEFAULT '',
                    missing_items TEXT DEFAULT '[]',
                    recommendation TEXT DEFAULT '',
                    raw_response TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 医生复核表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS doctor_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    reviewer_name TEXT NOT NULL,
                    review_action TEXT NOT NULL,
                    reviewed_diagnosis TEXT NOT NULL,
                    comment TEXT DEFAULT '',
                    ai_diagnosis TEXT DEFAULT '',
                    patient_description TEXT DEFAULT '',
                    graph_version TEXT DEFAULT '',
                    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                )
            """)

            # 病例标签表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
                    UNIQUE(case_id, tag)
                )
            """)

            # 训练数据导出记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS training_exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    export_name TEXT NOT NULL,
                    export_path TEXT NOT NULL,
                    case_count INTEGER DEFAULT 0,
                    filters TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cases_diagnosis ON cases(diagnosis)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_reviews_case_id ON doctor_reviews(case_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tags_case_id ON case_tags(case_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tags_tag ON case_tags(tag)
            """)

    def save_case(self, case: Case) -> int:
        """保存病例，如果已存在则更新"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            now = datetime.now().isoformat()
            case.updated_at = now
            if not case.created_at:
                case.created_at = now

            # 检查是否已存在
            cursor.execute("SELECT id FROM cases WHERE case_id = ?", (case.case_id,))
            existing = cursor.fetchone()

            if existing:
                # 更新
                cursor.execute("""
                    UPDATE cases SET
                        patient_description = ?,
                        diagnosis = ?,
                        intermediate_states = ?,
                        steps = ?,
                        graph_path = ?,
                        model = ?,
                        method = ?,
                        confidence = ?,
                        status = ?,
                        halt_step = ?,
                        halt_reason = ?,
                        missing_items = ?,
                        recommendation = ?,
                        raw_response = ?,
                        updated_at = ?
                    WHERE case_id = ?
                """, (
                    case.patient_description,
                    json.dumps(case.intermediate_states, ensure_ascii=False),
                    json.dumps(case.steps, ensure_ascii=False),
                    json.dumps(case.graph_path, ensure_ascii=False),
                    case.model,
                    case.method,
                    case.confidence,
                    case.status,
                    case.halt_step,
                    case.halt_reason,
                    json.dumps(case.missing_items, ensure_ascii=False),
                    case.recommendation,
                    case.raw_response,
                    now,
                    case.case_id,
                ))
                return existing["id"]
            else:
                # 插入
                cursor.execute("""
                    INSERT INTO cases (
                        case_id, patient_description, diagnosis,
                        intermediate_states, steps, graph_path,
                        model, method, confidence, status,
                        halt_step, halt_reason, missing_items,
                        recommendation, raw_response, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    case.case_id,
                    case.patient_description,
                    case.diagnosis,
                    json.dumps(case.intermediate_states, ensure_ascii=False),
                    json.dumps(case.steps, ensure_ascii=False),
                    json.dumps(case.graph_path, ensure_ascii=False),
                    case.model,
                    case.method,
                    case.confidence,
                    case.status,
                    case.halt_step,
                    case.halt_reason,
                    json.dumps(case.missing_items, ensure_ascii=False),
                    case.recommendation,
                    case.raw_response,
                    case.created_at,
                    case.updated_at,
                ))
                return cursor.lastrowid

    def get_case(self, case_id: str) -> Optional[Case]:
        """根据 case_id 获取病例"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_case(row)

    def get_cases(
        self,
        diagnosis: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[list[str]] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Case], int]:
        """查询病例列表，返回病例列表和总数"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 构建查询条件
            conditions = []
            params = []

            if diagnosis:
                conditions.append("diagnosis = ?")
                params.append(diagnosis)

            if status:
                conditions.append("status = ?")
                params.append(status)

            if search:
                conditions.append("(patient_description LIKE ? OR diagnosis LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])

            if tags:
                # 需要关联标签表
                tag_conditions = " OR ".join(["tag = ?"] * len(tags))
                conditions.append(f"EXISTS (SELECT 1 FROM case_tags WHERE case_id = cases.case_id AND ({tag_conditions}))")
                params.extend(tags)

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # 查询总数
            count_sql = f"SELECT COUNT(*) as total FROM cases {where_clause}"
            cursor.execute(count_sql, params)
            total = cursor.fetchone()["total"]

            # 查询数据
            sql = f"""
                SELECT * FROM cases
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(sql, params + [limit, offset])
            rows = cursor.fetchall()

            cases = [self._row_to_case(row) for row in rows]
            return cases, total

    def delete_case(self, case_id: str) -> bool:
        """删除病例"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
            return cursor.rowcount > 0

    def save_review(self, review: DoctorReview) -> int:
        """保存医生复核记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO doctor_reviews (
                    case_id, reviewer_name, review_action,
                    reviewed_diagnosis, comment, ai_diagnosis,
                    patient_description, graph_version, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review.case_id,
                review.reviewer_name,
                review.review_action,
                review.reviewed_diagnosis,
                review.comment,
                review.ai_diagnosis,
                review.patient_description,
                review.graph_version,
                review.reviewed_at or datetime.now().isoformat(),
            ))
            return cursor.lastrowid

    def get_reviews(self, case_id: str) -> list[DoctorReview]:
        """获取病例的所有复核记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM doctor_reviews
                WHERE case_id = ?
                ORDER BY reviewed_at DESC
            """, (case_id,))
            rows = cursor.fetchall()
            return [self._row_to_review(row) for row in rows]

    def get_recent_reviews(self, limit: int = 10) -> list[DoctorReview]:
        """获取最近的复核记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM doctor_reviews
                ORDER BY reviewed_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [self._row_to_review(row) for row in rows]

    def add_tag(self, case_id: str, tag: str) -> bool:
        """添加病例标签"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO case_tags (case_id, tag)
                    VALUES (?, ?)
                """, (case_id, tag))
                return True
            except sqlite3.IntegrityError:
                return False  # 标签已存在

    def remove_tag(self, case_id: str, tag: str) -> bool:
        """移除病例标签"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM case_tags WHERE case_id = ? AND tag = ?
            """, (case_id, tag))
            return cursor.rowcount > 0

    def get_tags(self, case_id: str) -> list[str]:
        """获取病例的所有标签"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tag FROM case_tags WHERE case_id = ?
            """, (case_id,))
            rows = cursor.fetchall()
            return [row["tag"] for row in rows]

    def get_all_tags(self) -> list[dict]:
        """获取所有标签及其使用次数"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tag, COUNT(*) as count
                FROM case_tags
                GROUP BY tag
                ORDER BY count DESC
            """)
            rows = cursor.fetchall()
            return [{"tag": row["tag"], "count": row["count"]} for row in rows]

    def get_statistics(self) -> dict[str, Any]:
        """获取病例统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 总病例数
            cursor.execute("SELECT COUNT(*) as total FROM cases")
            total_cases = cursor.fetchone()["total"]

            # 各诊断类型数量
            cursor.execute("""
                SELECT diagnosis, COUNT(*) as count
                FROM cases
                GROUP BY diagnosis
                ORDER BY count DESC
            """)
            diagnosis_stats = [{"diagnosis": row["diagnosis"], "count": row["count"]} for row in cursor.fetchall()]

            # 状态统计
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM cases
                GROUP BY status
            """)
            status_stats = {row["status"]: row["count"] for row in cursor.fetchall()}

            # 复核数量
            cursor.execute("SELECT COUNT(*) as total FROM doctor_reviews")
            total_reviews = cursor.fetchone()["total"]

            # 今日新增
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
                SELECT COUNT(*) as count FROM cases
                WHERE date(created_at) = ?
            """, (today,))
            today_cases = cursor.fetchone()["count"]

            return {
                "total_cases": total_cases,
                "total_reviews": total_reviews,
                "today_cases": today_cases,
                "diagnosis_stats": diagnosis_stats,
                "status_stats": status_stats,
            }

    def export_training_data(
        self,
        output_path: Path,
        diagnosis: Optional[str] = None,
        has_review: Optional[bool] = None,
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """导出训练数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 构建查询条件
            conditions = []
            params = []

            if diagnosis:
                conditions.append("c.diagnosis = ?")
                params.append(diagnosis)

            if tags:
                tag_conditions = " OR ".join(["tag = ?"] * len(tags))
                conditions.append(f"EXISTS (SELECT 1 FROM case_tags WHERE case_id = c.case_id AND ({tag_conditions}))")
                params.extend(tags)

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # 查询病例
            sql = f"""
                SELECT c.* FROM cases c
                {where_clause}
                ORDER BY c.created_at DESC
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            training_samples = []
            for row in rows:
                case = self._row_to_case(row)

                # 获取复核记录
                reviews = self.get_reviews(case.case_id)

                # 如果有复核记录，使用复核后的诊断
                if reviews:
                    final_diagnosis = reviews[0].reviewed_diagnosis
                    review_info = {
                        "reviewer": reviews[0].reviewer_name,
                        "action": reviews[0].review_action,
                        "comment": reviews[0].comment,
                    }
                else:
                    final_diagnosis = case.diagnosis
                    review_info = None

                # 构建训练样本
                sample = {
                    "case_id": case.case_id,
                    "patient_description": case.patient_description,
                    "diagnosis": final_diagnosis,
                    "ai_diagnosis": case.diagnosis,
                    "intermediate_states": case.intermediate_states,
                    "steps": case.steps,
                    "review_info": review_info,
                    "created_at": case.created_at,
                }
                training_samples.append(sample)

            # 保存到文件
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                for sample in training_samples:
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")

            return {
                "total": len(training_samples),
                "path": str(output_path),
                "filters": {
                    "diagnosis": diagnosis,
                    "has_review": has_review,
                    "tags": tags,
                },
            }

    def _row_to_case(self, row: sqlite3.Row) -> Case:
        """将数据库行转换为 Case 对象"""
        return Case(
            id=row["id"],
            case_id=row["case_id"],
            patient_description=row["patient_description"],
            diagnosis=row["diagnosis"],
            intermediate_states=json.loads(row["intermediate_states"] or "{}"),
            steps=json.loads(row["steps"] or "[]"),
            graph_path=json.loads(row["graph_path"] or "{}"),
            model=row["model"],
            method=row["method"],
            confidence=row["confidence"],
            status=row["status"],
            halt_step=row["halt_step"],
            halt_reason=row["halt_reason"],
            missing_items=json.loads(row["missing_items"] or "[]"),
            recommendation=row["recommendation"],
            raw_response=row["raw_response"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_review(self, row: sqlite3.Row) -> DoctorReview:
        """将数据库行转换为 DoctorReview 对象"""
        return DoctorReview(
            id=row["id"],
            case_id=row["case_id"],
            reviewer_name=row["reviewer_name"],
            review_action=row["review_action"],
            reviewed_diagnosis=row["reviewed_diagnosis"],
            comment=row["comment"],
            ai_diagnosis=row["ai_diagnosis"],
            patient_description=row["patient_description"],
            graph_version=row["graph_version"],
            reviewed_at=row["reviewed_at"],
        )


# 全局数据库实例
db = Database()


def get_db() -> Database:
    """获取数据库实例"""
    return db
