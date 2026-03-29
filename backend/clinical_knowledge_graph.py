"""
临床知识图谱构建与导出模块。

能力：
1. 从 transitions.json 构建临床诊断工作流知识图谱
2. 从 MinerU 输出的 markdown/json 中抽取实体与关系并合并入图谱
3. 导出专有存储格式（.ckg.json）
4. 导出 Mermaid 和 SVG 图片
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


GRAPH_FORMAT_NAME = "clinical-knowledge-graph"
GRAPH_FORMAT_VERSION = "1.0"


ENTITY_TYPE_COLORS = {
    "workflow": "#1d5c63",
    "workflow_node": "#2f6f76",
    "symptom": "#9f2f22",
    "finding": "#d17d48",
    "exam": "#7c4d2b",
    "diagnosis": "#245c3f",
    "document": "#5f4b8b",
    "concept": "#566573",
}


MINERU_TERM_PATTERNS = {
    "diagnosis": [
        "STEMI",
        "NSTEMI",
        "UA",
        "变异性心绞痛",
        "急性ST段抬高心肌梗死",
        "急性非ST段抬高心肌梗死",
        "不稳定型心绞痛",
    ],
    "exam": [
        "心电图",
        "ECG",
        "肌钙蛋白",
        "CK-MB",
        "心肌标志物",
        "超声心动图",
        "冠脉CTA",
        "冠状动脉造影",
    ],
    "symptom": [
        "急性胸痛",
        "胸痛",
        "胸闷",
        "胸骨后压榨性疼痛",
        "大汗",
        "恶心",
        "气短",
        "放射痛",
    ],
    "finding": [
        "ST段抬高",
        "非ST段抬高",
        "心肌损伤标志物升高",
        "心肌损伤标志物未升高",
        "T波倒置",
        "ST段压低",
    ],
}


@dataclass
class GraphEntity:
    id: str
    entity_type: str
    name: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "name": self.name,
            "description": self.description,
            "aliases": self.aliases,
            "properties": self.properties,
            "source_refs": self.source_refs,
        }


@dataclass
class GraphRelation:
    id: str
    source: str
    target: str
    relation_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "label": self.label,
            "properties": self.properties,
            "source_refs": self.source_refs,
        }


class ClinicalKnowledgeGraph:
    def __init__(self, graph_id: str, name: str):
        self.graph_id = graph_id
        self.name = name
        self.entities: dict[str, GraphEntity] = {}
        self.relations: dict[str, GraphRelation] = {}
        self.documents: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {
            "domain": "clinical_diagnosis",
            "supports_incremental_update": True,
            "supports_multi_disease_extension": True,
            "graph_schema_version": GRAPH_FORMAT_VERSION,
        }

    def add_entity(self, entity: GraphEntity) -> None:
        if entity.id in self.entities:
            existing = self.entities[entity.id]
            existing.aliases = sorted(set(existing.aliases + entity.aliases))
            existing.source_refs = sorted(set(existing.source_refs + entity.source_refs))
            existing.properties.update(entity.properties)
            if not existing.description and entity.description:
                existing.description = entity.description
            return
        self.entities[entity.id] = entity

    def add_relation(self, relation: GraphRelation) -> None:
        if relation.id in self.relations:
            existing = self.relations[relation.id]
            existing.source_refs = sorted(set(existing.source_refs + relation.source_refs))
            existing.properties.update(relation.properties)
            return
        self.relations[relation.id] = relation

    def add_document(self, document: dict[str, Any]) -> None:
        self.documents.append(document)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": GRAPH_FORMAT_NAME,
            "version": GRAPH_FORMAT_VERSION,
            "graph_id": self.graph_id,
            "name": self.name,
            "metadata": self.metadata,
            "documents": self.documents,
            "entities": [entity.to_dict() for entity in self.entities.values()],
            "relations": [relation.to_dict() for relation in self.relations.values()],
        }


def slugify(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value.strip())
    return text.strip("_").lower() or "unknown"


def split_node_content(content: str) -> list[str]:
    return [item.strip() for item in content.split(",") if item.strip()]


def infer_entity_type(term: str, node_type: str = "") -> str:
    if "诊断" in term or term in MINERU_TERM_PATTERNS["diagnosis"]:
        return "diagnosis"
    if "检查" in term or term in MINERU_TERM_PATTERNS["exam"]:
        return "exam"
    if "症状" in term or term in MINERU_TERM_PATTERNS["symptom"]:
        return "symptom"
    if "发现" in term or term in MINERU_TERM_PATTERNS["finding"]:
        return "finding"
    if "workflow" in node_type.lower():
        return "workflow"
    return "concept"


def build_graph_from_transitions(transitions_path: str | Path) -> ClinicalKnowledgeGraph:
    transitions_file = Path(transitions_path)
    data = json.loads(transitions_file.read_text(encoding="utf-8"))

    workflow_name = data["workflow_name"]
    graph = ClinicalKnowledgeGraph(
        graph_id=f"kg_{slugify(workflow_name)}",
        name=workflow_name,
    )
    graph.add_entity(
        GraphEntity(
            id="workflow_root",
            entity_type="workflow",
            name=workflow_name,
            description="临床诊断工作流主图谱",
            source_refs=[str(transitions_file.name)],
        )
    )

    for node in data["nodes"]:
        node_id = node["id"]
        node_type = node["type"]
        content = node["content"]
        graph.add_entity(
            GraphEntity(
                id=node_id,
                entity_type="workflow_node",
                name=f"{node_id} {node_type}",
                description=content,
                properties={"node_type": node_type, "content": content},
                source_refs=[str(transitions_file.name)],
            )
        )
        graph.add_relation(
            GraphRelation(
                id=f"rel_workflow_contains_{node_id}",
                source="workflow_root",
                target=node_id,
                relation_type="contains",
                label="包含节点",
                source_refs=[str(transitions_file.name)],
            )
        )

        for term in split_node_content(content):
            term_entity_id = f"term_{slugify(term)}"
            graph.add_entity(
                GraphEntity(
                    id=term_entity_id,
                    entity_type=infer_entity_type(term, node_type=node_type),
                    name=term,
                    description=f"从工作流节点 {node_id} 识别出的临床概念",
                    source_refs=[node_id, str(transitions_file.name)],
                )
            )
            graph.add_relation(
                GraphRelation(
                    id=f"rel_{node_id}_{term_entity_id}",
                    source=node_id,
                    target=term_entity_id,
                    relation_type="mentions",
                    label="关联概念",
                    source_refs=[node_id, str(transitions_file.name)],
                )
            )

    for index, transition in enumerate(data["transitions"], start=1):
        from_id = transition["from"]
        to_id = transition["to"]
        condition = transition.get("condition")
        graph.add_relation(
            GraphRelation(
                id=f"transition_{index}",
                source=from_id,
                target=to_id,
                relation_type="transitions_to",
                label=condition or "继续",
                properties={"condition": condition},
                source_refs=[str(transitions_file.name)],
            )
        )

    return graph


def _extract_text_fragments(payload: Any) -> list[str]:
    fragments: list[str] = []

    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped:
            fragments.append(stripped)
        return fragments

    if isinstance(payload, list):
        for item in payload:
            fragments.extend(_extract_text_fragments(item))
        return fragments

    if isinstance(payload, dict):
        preferred_keys = [
            "text",
            "content",
            "markdown",
            "md",
            "title",
            "full_text",
            "value",
        ]
        for key in preferred_keys:
            if key in payload:
                fragments.extend(_extract_text_fragments(payload[key]))

        for key, value in payload.items():
            if key in preferred_keys:
                continue
            if isinstance(value, (dict, list)):
                fragments.extend(_extract_text_fragments(value))
        return fragments

    return fragments


def extract_entities_from_mineru_payload(
    payload: Any,
    document_id: str = "mineru_document",
    title: str = "MinerU Clinical Document",
) -> dict[str, Any]:
    """
    将 MinerU markdown/json 输出适配成图谱更新载荷。

    说明：
    - MinerU 官方文档说明 markdown 和 json 是默认导出格式
    - 这里兼容 markdown 文本、json 字典与嵌套 block 结构
    """
    fragments = _extract_text_fragments(payload)
    unique_terms: dict[str, set[str]] = {key: set() for key in MINERU_TERM_PATTERNS}

    for fragment in fragments:
        for entity_type, terms in MINERU_TERM_PATTERNS.items():
            for term in terms:
                if term in fragment:
                    unique_terms[entity_type].add(term)

    return {
        "document": {
            "document_id": document_id,
            "title": title,
            "source_format": "mineru",
            "fragment_count": len(fragments),
        },
        "entities": [
            {
                "id": f"{entity_type}_{slugify(term)}",
                "entity_type": entity_type,
                "name": term,
                "description": f"从 MinerU 文档中抽取的 {entity_type} 实体",
            }
            for entity_type, terms in unique_terms.items()
            for term in sorted(terms)
        ],
    }


def merge_mineru_entities_into_graph(graph: ClinicalKnowledgeGraph, mineru_payload: Any, title: str = "MinerU Clinical Document") -> ClinicalKnowledgeGraph:
    extracted = extract_entities_from_mineru_payload(
        mineru_payload,
        document_id=f"doc_{slugify(title)}",
        title=title,
    )
    document_id = extracted["document"]["document_id"]
    graph.add_entity(
        GraphEntity(
            id=document_id,
            entity_type="document",
            name=extracted["document"]["title"],
            description="由 MinerU 解析得到的临床文档",
            properties={"source_format": "mineru", "fragment_count": extracted["document"]["fragment_count"]},
            source_refs=[document_id],
        )
    )
    graph.add_document(extracted["document"])

    for entity in extracted["entities"]:
        graph.add_entity(
            GraphEntity(
                id=entity["id"],
                entity_type=entity["entity_type"],
                name=entity["name"],
                description=entity["description"],
                source_refs=[document_id],
            )
        )
        graph.add_relation(
            GraphRelation(
                id=f"rel_{document_id}_{entity['id']}",
                source=document_id,
                target=entity["id"],
                relation_type="describes",
                label="文档描述",
                source_refs=[document_id],
            )
        )

    return graph


def iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def compute_graph_fingerprint(graph: ClinicalKnowledgeGraph) -> str:
    payload = {
        "graph_id": graph.graph_id,
        "name": graph.name,
        "documents": graph.documents,
        "entities": [entity.to_dict() for entity in sorted(graph.entities.values(), key=lambda item: item.id)],
        "relations": [relation.to_dict() for relation in sorted(graph.relations.values(), key=lambda item: item.id)],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_json_file(path: str | Path) -> Any | None:
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def update_graph_version_metadata(
    graph: ClinicalKnowledgeGraph,
    output_dir: str | Path,
    graph_name: str,
    update_type: str,
    source_title: str,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    graph_json_path = output_root / f"{graph_name}.ckg.json"
    history_path = output_root / f"{graph_name}.history.json"

    previous_payload = load_json_file(graph_json_path) or {}
    previous_metadata = previous_payload.get("metadata", {})
    previous_history = load_json_file(history_path) or {}
    previous_entries = previous_history.get("entries", [])

    previous_version_number = int(previous_metadata.get("graph_version_number", 0) or 0)
    previous_fingerprint = previous_metadata.get("content_fingerprint", "")
    content_fingerprint = compute_graph_fingerprint(graph)
    content_changed = content_fingerprint != previous_fingerprint

    version_number = previous_version_number + 1 if previous_version_number == 0 or content_changed else previous_version_number
    version_label = f"v{version_number}"
    updated_at = iso_timestamp()

    graph.metadata.update(
        {
            "graph_version": version_label,
            "graph_version_number": version_number,
            "updated_at": updated_at,
            "content_fingerprint": content_fingerprint,
            "latest_update_type": update_type,
            "latest_source_title": source_title,
        }
    )

    history_entry = {
        "version": version_label,
        "version_number": version_number,
        "updated_at": updated_at,
        "update_type": update_type,
        "source_title": source_title,
        "entity_count": len(graph.entities),
        "relation_count": len(graph.relations),
        "document_count": len(graph.documents),
        "content_changed": content_changed,
    }

    entries = previous_entries
    if not entries or content_changed:
        entries = [*previous_entries, history_entry]
    else:
        entries = previous_entries[:-1] + [{**previous_entries[-1], **history_entry}]

    history_payload = {
        "graph_id": graph.graph_id,
        "graph_name": graph.name,
        "latest_version": version_label,
        "latest_updated_at": updated_at,
        "entries": entries,
    }
    history_path.write_text(json.dumps(history_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "graph_version": version_label,
        "graph_version_number": version_number,
        "updated_at": updated_at,
        "content_changed": content_changed,
        "history_path": str(history_path),
        "history": entries[-10:],
    }


def export_graph_json(graph: ClinicalKnowledgeGraph, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def export_graph_mermaid(graph: ClinicalKnowledgeGraph, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["flowchart LR"]
    for entity in graph.entities.values():
        label = entity.name.replace('"', "'")
        lines.append(f'  {entity.id}["{label}"]')
    for relation in graph.relations.values():
        label = relation.label.replace('"', "'")
        lines.append(f'  {relation.source} -->|"{label}"| {relation.target}')
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _layout_entities(graph: ClinicalKnowledgeGraph) -> dict[str, tuple[int, int]]:
    columns = {
        "workflow": 0,
        "workflow_node": 1,
        "symptom": 2,
        "finding": 2,
        "exam": 3,
        "diagnosis": 4,
        "document": 0,
        "concept": 3,
    }
    grouped: dict[int, list[GraphEntity]] = {}
    for entity in graph.entities.values():
        column = columns.get(entity.entity_type, 3)
        grouped.setdefault(column, []).append(entity)

    positions: dict[str, tuple[int, int]] = {}
    for column, entities in grouped.items():
        for row, entity in enumerate(sorted(entities, key=lambda item: item.id)):
            positions[entity.id] = (80 + column * 240, 60 + row * 90)
    return positions


def export_graph_svg(graph: ClinicalKnowledgeGraph, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    positions = _layout_entities(graph)

    edge_parts = []
    for relation in graph.relations.values():
        source_pos = positions.get(relation.source)
        target_pos = positions.get(relation.target)
        if not source_pos or not target_pos:
            continue
        x1, y1 = source_pos[0] + 160, source_pos[1] + 28
        x2, y2 = target_pos[0], target_pos[1] + 28
        mx = (x1 + x2) // 2
        path = f"M {x1} {y1} C {mx} {y1}, {mx} {y2}, {x2} {y2}"
        edge_parts.append(
            f'<path d="{path}" fill="none" stroke="#c7b8a6" stroke-width="2"/>'
            f'<text x="{mx}" y="{(y1 + y2) // 2 - 8}" font-size="11" text-anchor="middle" fill="#6b5a4f">{relation.label}</text>'
        )

    node_parts = []
    for entity in graph.entities.values():
        x, y = positions[entity.id]
        color = ENTITY_TYPE_COLORS.get(entity.entity_type, "#566573")
        name = entity.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        entity_type = entity.entity_type.replace("&", "&amp;")
        node_parts.append(
            f'<rect x="{x}" y="{y}" rx="16" ry="16" width="160" height="56" fill="#fffaf2" stroke="{color}" stroke-width="2"/>'
            f'<text x="{x + 12}" y="{y + 22}" font-size="11" fill="{color}">{entity_type}</text>'
            f'<text x="{x + 12}" y="{y + 40}" font-size="14" fill="#2f241d">{name}</text>'
        )

    width = max(x for x, _ in positions.values()) + 260 if positions else 1200
    height = max(y for _, y in positions.values()) + 160 if positions else 800
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#f7f1e8"/>
  <g>{"".join(edge_parts)}</g>
  <g>{"".join(node_parts)}</g>
</svg>
"""
    target.write_text(svg, encoding="utf-8")
    return target


def build_and_export_graph(
    transitions_path: str | Path,
    output_dir: str | Path,
    mineru_payload: Any | None = None,
    mineru_title: str = "MinerU Clinical Document",
) -> dict[str, Any]:
    output_root = Path(output_dir)
    graph = build_graph_from_transitions(transitions_path)
    if mineru_payload is not None:
        graph = merge_mineru_entities_into_graph(graph, mineru_payload, title=mineru_title)

    graph_name = slugify(graph.name)
    update_type = "mineru_ingest" if mineru_payload is not None else "base_build"
    source_title = mineru_title if mineru_payload is not None else Path(transitions_path).name
    version_info = update_graph_version_metadata(
        graph=graph,
        output_dir=output_root,
        graph_name=graph_name,
        update_type=update_type,
        source_title=source_title,
    )
    ckg_path = export_graph_json(graph, output_root / f"{graph_name}.ckg.json")
    mermaid_path = export_graph_mermaid(graph, output_root / f"{graph_name}.mmd")
    svg_path = export_graph_svg(graph, output_root / f"{graph_name}.svg")

    return {
        "graph_json": str(ckg_path),
        "mermaid": str(mermaid_path),
        "svg": str(svg_path),
        "history": version_info["history_path"],
        "version_info": version_info,
    }


def get_exported_graph_status(
    transitions_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    graph_name = slugify(build_graph_from_transitions(transitions_path).name)
    output_root = Path(output_dir)
    graph_json_path = output_root / f"{graph_name}.ckg.json"
    mermaid_path = output_root / f"{graph_name}.mmd"
    svg_path = output_root / f"{graph_name}.svg"
    history_path = output_root / f"{graph_name}.history.json"

    if not graph_json_path.exists():
        return {
            "exists": False,
            "artifacts": {},
            "version_info": {},
            "history": [],
        }

    graph_payload = load_json_file(graph_json_path) or {}
    metadata = graph_payload.get("metadata", {})
    history_payload = load_json_file(history_path) or {}

    return {
        "exists": True,
        "artifacts": {
            "graph_json": str(graph_json_path),
            "mermaid": str(mermaid_path) if mermaid_path.exists() else "",
            "svg": str(svg_path) if svg_path.exists() else "",
            "history": str(history_path) if history_path.exists() else "",
        },
        "version_info": {
            "graph_version": metadata.get("graph_version", ""),
            "graph_version_number": metadata.get("graph_version_number", 0),
            "updated_at": metadata.get("updated_at", ""),
            "latest_update_type": metadata.get("latest_update_type", ""),
            "latest_source_title": metadata.get("latest_source_title", ""),
            "entity_count": len(graph_payload.get("entities", [])),
            "relation_count": len(graph_payload.get("relations", [])),
            "document_count": len(graph_payload.get("documents", [])),
        },
        "history": history_payload.get("entries", [])[-10:],
    }


if __name__ == "__main__":
    artifacts = build_and_export_graph(
        transitions_path=Path("config/transitions.json"),
        output_dir=Path("knowledge_graph"),
    )
    print(json.dumps(artifacts, ensure_ascii=False, indent=2))
