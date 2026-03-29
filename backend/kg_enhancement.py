"""
Knowledge Graph Enhancement Module.

This module extracts diagnostic term variations from patient cases
and provides semantic matching for doctor review to enhance the knowledge graph.

Features:
1. Extract diagnostic terms and their variations from patient case files
2. Semantic matching against existing knowledge graph entities
3. Group similar terms for doctor review
4. Merge approved terms into the knowledge graph
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from collections import defaultdict

from .clinical_knowledge_graph import ClinicalKnowledgeGraph, GraphEntity, GraphRelation


def workflow_node_sort_key(node_id: str) -> tuple[int, str]:
    """Provide a stable sort key for workflow node identifiers."""
    match = re.search(r"node_(\d+)", str(node_id or ""))
    return (int(match.group(1)) if match else 10**9, str(node_id or ""))


@dataclass
class ExtractedTerm:
    """Represents a term extracted from patient cases."""
    term: str
    category: str  # symptom, finding, exam, diagnosis
    source_file: str
    context: str = ""
    frequency: int = 1
    aliases: list[str] = field(default_factory=list)
    matched_entity_id: str | None = None
    match_confidence: float = 0.0
    review_status: str = "pending"  # pending, approved, rejected
    review_comment: str = ""
    reviewer_name: str = ""
    review_date: str = ""
    manual_workflow_node_ids: list[str] = field(default_factory=list)
    manual_match_reviewer_name: str = ""
    manual_match_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "category": self.category,
            "source_file": self.source_file,
            "context": self.context,
            "frequency": self.frequency,
            "aliases": self.aliases,
            "matched_entity_id": self.matched_entity_id,
            "match_confidence": self.match_confidence,
            "review_status": self.review_status,
            "review_comment": self.review_comment,
            "reviewer_name": self.reviewer_name,
            "review_date": self.review_date,
            "manual_workflow_node_ids": self.manual_workflow_node_ids,
            "manual_match_reviewer_name": self.manual_match_reviewer_name,
            "manual_match_date": self.manual_match_date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedTerm:
        return cls(
            term=data["term"],
            category=data["category"],
            source_file=data["source_file"],
            context=data.get("context", ""),
            frequency=data.get("frequency", 1),
            aliases=data.get("aliases", []),
            matched_entity_id=data.get("matched_entity_id"),
            match_confidence=data.get("match_confidence", 0.0),
            review_status=data.get("review_status", "pending"),
            review_comment=data.get("review_comment", ""),
            reviewer_name=data.get("reviewer_name", ""),
            review_date=data.get("review_date", ""),
            manual_workflow_node_ids=data.get("manual_workflow_node_ids", []),
            manual_match_reviewer_name=data.get("manual_match_reviewer_name", ""),
            manual_match_date=data.get("manual_match_date", ""),
        )


class TermExtractor:
    """Extract clinical terms from patient case files."""

    # Patterns for different term categories
    TERM_PATTERNS = {
        "symptom": [
            # Chest pain related
            r"(?:缺血性 | 非缺血性 | 变异型)?胸痛",
            r"胸闷",
            r"胸骨后 (?:压榨性 | 紧缩性 | 烧灼样)?(?:疼痛 | 不适)",
            r"心悸",
            r"气促",
            r"呼吸困难",
            r"大汗 (?:淋漓)?",
            r"恶心 (?:呕吐)?",
            r"放射痛",
            r"左肩 (?:背部)? 放射",
            r"下颌 (?:部)? 疼痛",
            r"上腹部 (?:疼痛 | 不适)",
            r"濒死感",
            r"乏力",
            r"头晕",
            r"晕厥",
            r"紫绀",
            r"咳嗽",
            r"发热",
        ],
        "finding": [
            # ECG findings
            r"ST 段 (?:抬高 | 压低 | 改变)",
            r"T 波 (?:倒置 | 高尖 | 改变)",
            r"病理性 Q 波",
            r"新发 (?:左 | 右)?束支传导阻滞",
            r"心房 (?:颤动 | 扑动)",
            r"室性 (?:早搏 | 心动过速)",
            r"房室传导阻滞",
            r"窦性 (?:心动过速 | 心动过缓)",
            # Lab findings
            r"肌钙蛋白 (?:I|T)?(?:升高 | 阳性 | 临界)",
            r"cTn(?:I|T)?(?:升高 | 阳性)",
            r"CK-MB(?:升高 | 增高)?",
            r"心肌酶 (?:谱)?(?:升高 | 异常)",
            r"肌红蛋白 (?:升高 | 增高)",
            r"D-二聚体 (?:升高 | 增高)",
            r"BNP(?:升高 | 增高)?",
            r"NT-proBNP(?:升高 | 增高)?",
            r"白细胞 (?:增多 | 升高)",
            r"C 反应蛋白 (?:升高 | 增高)",
            r"血沉 (?:增快 | 升高)",
            # Imaging findings
            r"室壁 (?:运动异常 | 运动减弱 | 无运动)",
            r"射血分数 (?:降低 | 下降)",
            r"冠脉 (?:狭窄 | 闭塞 | 病变)",
            r"血栓 (?:形成)?",
            r"斑块 (?:形成 | 破裂)?",
        ],
        "exam": [
            r"心电图",
            r"ECG",
            r"动态心电图",
            r"Holter",
            r"超声心动图",
            r"心脏彩超",
            r"冠脉 (?:CTA|CT 血管成像)",
            r"冠状动脉造影",
            r"PCI(?:术)?",
            r"CABG(?:术)?",
            r"冠脉搭桥",
            r"心脏核磁",
            r"心脏 CT",
            r"胸部 CT",
            r"CTPA",
            r"肺动脉造影",
            r"下肢血管超声",
            r"颈动脉超声",
        ],
        "diagnosis": [
            # ACS related
            r"急性 ST 段抬高型心肌梗死",
            r"STEMI",
            r"急性非 ST 段抬高型心肌梗死",
            r"NSTEMI",
            r"不稳定型心绞痛",
            r"UA",
            r"变异型心绞痛",
            r" Prinzmetal 心绞痛",
            r"急性冠脉综合征",
            r"ACS",
            r"冠心病",
            r"冠状动脉粥样硬化性心脏病",
            # Other cardiac
            r"心力衰竭",
            r"心功能不全",
            r"心律失常",
            r"心房颤动",
            r"室性心动过速",
            r"心脏骤停",
            r"心源性休克",
            r"心肌病",
            r"心肌炎",
            r"心包 (?:炎 | 积液)",
            r"瓣膜 (?:病 | 狭窄 | 关闭不全)",
            # Vascular
            r"肺栓塞",
            r"PE",
            r"深静脉血栓形成",
            r"DVT",
            r"主动脉夹层",
            r"高血压 (?:病)?",
            r"动脉粥样硬化",
            # Congenital
            r"先天性心脏病",
            r"法洛四联症",
            r"室间隔缺损",
            r"房间隔缺损",
            r"动脉导管未闭",
        ],
    }

    # Synonym mappings for semantic matching
    SYNONYM_GROUPS = {
        "ischemic_chest_pain": [
            "缺血性胸痛",
            "心源性胸痛",
            "心绞痛样胸痛",
            "典型胸痛",
            "冠心病胸痛",
        ],
        "non_ischemic_chest_pain": [
            "非缺血性胸痛",
            "非心源性胸痛",
            "功能性胸痛",
            "神经官能症性胸痛",
        ],
        "st_elevation": [
            "ST 段抬高",
            "ST 抬高",
            "ST 段上抬",
            "ST 段弓背向上抬高",
        ],
        "troponin_elevated": [
            "肌钙蛋白升高",
            "肌钙蛋白阳性",
            "cTn 升高",
            "cTnI 升高",
            "cTnT 升高",
            "心肌损伤标志物升高",
            "心肌酶升高",
        ],
        "troponin_normal": [
            "肌钙蛋白正常",
            "肌钙蛋白阴性",
            "cTn 正常",
            "心肌损伤标志物正常",
            "心肌酶正常",
        ],
        "ck_mb_elevated": [
            "CK-MB 升高",
            "CKMB 升高",
            "肌酸激酶同工酶升高",
            "心肌酶谱升高",
        ],
    }

    def __init__(self):
        self.compiled_patterns = {
            category: [re.compile(p, re.IGNORECASE) for p in patterns]
            for category, patterns in self.TERM_PATTERNS.items()
        }

    def extract_from_text(self, text: str, source_file: str = "") -> list[ExtractedTerm]:
        """Extract clinical terms from text."""
        extracted_terms = []
        term_counts = defaultdict(lambda: {"count": 0, "contexts": []})

        for category, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    term = match.group(0)
                    # Get surrounding context (50 chars before and after)
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].strip()
                    context = re.sub(r"\s+", " ", context)

                    key = f"{category}:{term}"
                    term_counts[key]["count"] += 1
                    if context not in term_counts[key]["contexts"]:
                        term_counts[key]["contexts"].append(context)

        for key, data in term_counts.items():
            category, term = key.split(":", 1)
            extracted_terms.append(ExtractedTerm(
                term=term,
                category=category,
                source_file=source_file,
                context=data["contexts"][0] if data["contexts"] else "",
                frequency=data["count"],
            ))

        return extracted_terms

    def extract_from_markdown_file(self, file_path: Path) -> list[ExtractedTerm]:
        """Extract clinical terms from a markdown file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.extract_from_text(content, source_file=file_path.name)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []

    def extract_from_directory(self, dir_path: Path) -> list[ExtractedTerm]:
        """Extract clinical terms from all markdown files in a directory."""
        all_terms = []
        term_aggregation = defaultdict(lambda: {
            "frequency": 0,
            "sources": [],
            "contexts": [],
        })

        md_files = list(dir_path.glob("*.md"))

        for md_file in md_files:
            terms = self.extract_from_markdown_file(md_file)
            for term in terms:
                key = f"{term.category}:{term.term}"
                term_aggregation[key]["frequency"] += term.frequency
                if term.source_file not in term_aggregation[key]["sources"]:
                    term_aggregation[key]["sources"].append(term.source_file)
                if term.context and term.context not in term_aggregation[key]["contexts"]:
                    term_aggregation[key]["contexts"].append(term.context)

        for key, data in term_aggregation.items():
            category, term = key.split(":", 1)
            all_terms.append(ExtractedTerm(
                term=term,
                category=category,
                source_file="; ".join(data["sources"][:5]),  # Limit to 5 sources
                context=data["contexts"][0] if data["contexts"] else "",
                frequency=data["frequency"],
            ))

        # Sort by frequency
        all_terms.sort(key=lambda x: x.frequency, reverse=True)
        return all_terms


class SemanticMatcher:
    """Perform semantic matching between extracted terms and knowledge graph entities."""

    def __init__(self, kg: ClinicalKnowledgeGraph | None = None):
        self.kg = kg
        self._build_synonym_index()

    def _build_synonym_index(self) -> None:
        """Build index for synonym matching."""
        self.synonym_to_group = {}
        for group_name, synonyms in TermExtractor.SYNONYM_GROUPS.items():
            for synonym in synonyms:
                # Index both original and normalized form
                self.synonym_to_group[self._normalize_text(synonym)] = group_name
                self.synonym_to_group[synonym] = group_name

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Remove spaces and special characters
        text = re.sub(r"[\s\-\_\(\)]+", "", text)
        return text.lower()

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity using Levenshtein distance."""
        if len(s1) < len(s2):
            s1, s2 = s2, s1

        if len(s2) == 0:
            return 0.0

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        distance = previous_row[-1]
        max_len = max(len(s1), len(s2))
        return 1 - (distance / max_len)

    def match_term(self, term: ExtractedTerm) -> tuple[str | None, float]:
        """
        Match an extracted term against knowledge graph entities.
        Returns (matched_entity_id, confidence_score).
        """
        if self.kg is None:
            # Try synonym matching only
            return self._match_by_synonym(term)

        best_match_id = None
        best_confidence = 0.0

        normalized_term = self._normalize_text(term.term)

        # Check synonym groups first
        synonym_match, synonym_confidence = self._match_by_synonym(term)
        if synonym_confidence > 0.8:
            best_match_id = synonym_match
            best_confidence = synonym_confidence

        # Then check against KG entities
        for entity_id, entity in self.kg.entities.items():
            # Check entity name
            entity_normalized = self._normalize_text(entity.name)
            similarity = self._string_similarity(normalized_term, entity_normalized)

            # Check entity aliases
            for alias in entity.aliases:
                alias_normalized = self._normalize_text(alias)
                alias_similarity = self._string_similarity(normalized_term, alias_normalized)
                similarity = max(similarity, alias_similarity)

            # Boost confidence if same category
            if self._categories_match(term.category, entity.entity_type):
                similarity = min(1.0, similarity + 0.1)

            if similarity > best_confidence:
                best_confidence = similarity
                best_match_id = entity_id

        # Apply threshold
        if best_confidence < 0.6:
            return None, 0.0

        return best_match_id, best_confidence

    def _match_by_synonym(self, term: ExtractedTerm) -> tuple[str | None, float]:
        """Match term using predefined synonym groups."""
        normalized_term = self._normalize_text(term.term)

        if normalized_term in self.synonym_to_group:
            group_name = self.synonym_to_group[normalized_term]
            return f"synonym_{group_name}", 0.9

        # Check partial matches
        for synonym, group_name in self.synonym_to_group.items():
            if synonym in normalized_term or normalized_term in synonym:
                return f"synonym_{group_name}", 0.7

        return None, 0.0

    def _categories_match(self, term_category: str, entity_type: str) -> bool:
        """Check if term category matches entity type."""
        category_mapping = {
            "symptom": ["symptom"],
            "finding": ["finding"],
            "exam": ["exam"],
            "diagnosis": ["diagnosis"],
        }
        return entity_type in category_mapping.get(term_category, [])

    def find_term_variations(self, terms: list[ExtractedTerm]) -> dict[str, list[ExtractedTerm]]:
        """
        Group terms that are semantic variations of each other.
        Returns dict mapping canonical term to list of variations.
        """
        groups = defaultdict(list)

        for term in terms:
            matched_id, confidence = self.match_term(term)
            term.matched_entity_id = matched_id
            term.match_confidence = confidence

            if matched_id:
                groups[matched_id].append(term)
            else:
                # Create a group for unmatched terms
                groups[f"unmatched_{term.term}"].append(term)

        return dict(groups)


class KGEnhancementManager:
    """Manage the knowledge graph enhancement workflow."""

    def __init__(self, kg_path: Path | None = None):
        self.kg_path = kg_path
        self.kg: ClinicalKnowledgeGraph | None = None
        self.extractor = TermExtractor()
        self.matcher: SemanticMatcher | None = None
        self.extracted_terms: list[ExtractedTerm] = []
        self.term_groups: dict[str, list[ExtractedTerm]] = {}
        self.review_records: list[dict[str, Any]] = []

    def load_knowledge_graph(self, kg_path: Path | None = None) -> None:
        """Load existing knowledge graph."""
        path = kg_path or self.kg_path
        if path is None:
            raise ValueError("No knowledge graph path specified")

        with open(path, "r", encoding="utf-8") as f:
            kg_data = json.load(f)

        self.kg = ClinicalKnowledgeGraph(
            graph_id=kg_data.get("graph_id", "unknown"),
            name=kg_data.get("name", "Unknown Graph"),
        )

        # Load entities
        for entity_data in kg_data.get("entities", []):
            entity = GraphEntity(
                id=entity_data["id"],
                entity_type=entity_data["entity_type"],
                name=entity_data["name"],
                description=entity_data.get("description", ""),
                aliases=entity_data.get("aliases", []),
                properties=entity_data.get("properties", {}),
                source_refs=entity_data.get("source_refs", []),
            )
            self.kg.add_entity(entity)

        # Load relations
        for relation_data in kg_data.get("relations", []):
            from .clinical_knowledge_graph import GraphRelation
            relation = GraphRelation(
                id=relation_data["id"],
                source=relation_data["source"],
                target=relation_data["target"],
                relation_type=relation_data["relation_type"],
                label=relation_data["label"],
                properties=relation_data.get("properties", {}),
                source_refs=relation_data.get("source_refs", []),
            )
            self.kg.add_relation(relation)

        self.matcher = SemanticMatcher(self.kg)

    def extract_terms_from_cases(self, case_dir: Path) -> list[ExtractedTerm]:
        """Extract terms from patient case files."""
        self.extracted_terms = self.extractor.extract_from_directory(case_dir)

        if self.matcher:
            self.term_groups = self.matcher.find_term_variations(self.extracted_terms)
        else:
            # Group by exact term match
            from collections import defaultdict
            groups = defaultdict(list)
            for term in self.extracted_terms:
                groups[term.term].append(term)
            self.term_groups = dict(groups)

        return self.extracted_terms

    def _normalize_workflow_node_ids(self, workflow_node_ids: list[str] | None) -> tuple[list[str], list[str]]:
        """Validate, de-duplicate, and sort workflow node ids."""
        normalized: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()

        for raw_node_id in workflow_node_ids or []:
            node_id = str(raw_node_id or "").strip()
            if not node_id or node_id in seen:
                continue

            if self.kg is not None:
                node = self.kg.entities.get(node_id)
                if node is None or node.entity_type != "workflow_node":
                    invalid.append(node_id)
                    continue

            seen.add(node_id)
            normalized.append(node_id)

        normalized.sort(key=workflow_node_sort_key)
        return normalized, invalid

    def _serialize_workflow_nodes(self, workflow_node_ids: list[str]) -> list[dict[str, Any]]:
        """Return lightweight workflow node summaries for the given ids."""
        if self.kg is None:
            return [{"id": node_id} for node_id in workflow_node_ids]

        workflow_nodes: list[dict[str, Any]] = []
        for node_id in workflow_node_ids:
            node = self.kg.entities.get(node_id)
            if node is None or node.entity_type != "workflow_node":
                continue
            workflow_nodes.append({
                "id": node.id,
                "name": node.name,
                "node_type": node.properties.get("node_type", "workflow_node"),
                "content": node.properties.get("content", node.description),
            })
        return workflow_nodes

    def _find_existing_mentions_relation(self, workflow_node_id: str, entity_id: str) -> GraphRelation | None:
        """Find an existing mentions relation between a workflow node and an entity."""
        if self.kg is None:
            return None

        for relation in self.kg.relations.values():
            if (
                relation.relation_type == "mentions"
                and relation.source == workflow_node_id
                and relation.target == entity_id
            ):
                return relation
        return None

    def _apply_manual_workflow_links(
        self,
        entity: GraphEntity,
        workflow_node_ids: list[str],
        reviewer_name: str,
        review_date: str,
        stats: dict[str, Any],
    ) -> None:
        """Persist manually reviewed workflow-node links onto the KG entity and relations."""
        if self.kg is None or not workflow_node_ids:
            return

        for workflow_node_id in workflow_node_ids:
            if workflow_node_id not in entity.source_refs:
                entity.source_refs.append(workflow_node_id)

            existing_relation = self._find_existing_mentions_relation(workflow_node_id, entity.id)
            if existing_relation is not None:
                existing_relation.label = existing_relation.label or "\u76f8\u5173\u6982\u5ff5"
                existing_relation.properties["manual_review_confirmed"] = True
                existing_relation.properties["manual_review_date"] = review_date
                if reviewer_name:
                    existing_relation.properties["manual_reviewer_name"] = reviewer_name
                if workflow_node_id not in existing_relation.source_refs:
                    existing_relation.source_refs.append(workflow_node_id)
                stats["workflow_links_updated"] += 1
                continue

            relation = GraphRelation(
                id=f"rel_manual_{workflow_node_id}_{entity.id}",
                source=workflow_node_id,
                target=entity.id,
                relation_type="mentions",
                label="\u624b\u52a8\u6d41\u7a0b\u5173\u8054",
                properties={
                    "manual_review_confirmed": True,
                    "manual_review_date": review_date,
                    "manual_reviewer_name": reviewer_name,
                },
                source_refs=[workflow_node_id],
            )
            self.kg.add_relation(relation)
            stats["workflow_links_added"] += 1

        entity.source_refs = sorted(set(entity.source_refs), key=str)

    def get_review_items(self) -> list[dict[str, Any]]:
        """Get items ready for doctor review."""
        review_items = []

        for group_key, terms in self.term_groups.items():
            if not terms:
                continue

            # Get the most frequent term as the representative
            representative = max(terms, key=lambda t: t.frequency)

            # Collect all unique variations
            variations = list(set(t.term for t in terms))
            manual_workflow_node_ids = sorted(
                {node_id for term in terms for node_id in term.manual_workflow_node_ids},
                key=workflow_node_sort_key,
            )

            review_items.append({
                "group_key": group_key,
                "representative_term": representative.term,
                "category": representative.category,
                "variations": variations,
                "total_frequency": sum(t.frequency for t in terms),
                "source_files": list(set(
                    src for t in terms for src in t.source_file.split("; ")
                )),
                "matched_entity_id": representative.matched_entity_id,
                "match_confidence": representative.match_confidence,
                "contexts": [t.context for t in terms[:3] if t.context],
                "review_status": representative.review_status,
                "review_comment": representative.review_comment,
                "reviewer_name": representative.reviewer_name,
                "manual_workflow_node_ids": manual_workflow_node_ids,
                "manual_workflow_nodes": self._serialize_workflow_nodes(manual_workflow_node_ids),
                "manual_match_reviewer_name": representative.manual_match_reviewer_name,
                "manual_match_date": representative.manual_match_date,
            })

        # Sort by frequency
        review_items.sort(key=lambda x: x["total_frequency"], reverse=True)
        return review_items

    def submit_review(
        self,
        group_key: str,
        action: str,
        reviewer_name: str,
        comment: str = "",
        canonical_term: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit doctor review for a term group.

        Args:
            group_key: The group key to review
            action: 'approve', 'reject', or 'merge'
            reviewer_name: Name of the reviewing doctor
            comment: Review comment
            canonical_term: The canonical term to use (for merge action)

        Returns:
            Review result dict
        """
        if group_key not in self.term_groups:
            return {"success": False, "error": "\u672a\u627e\u5230\u672f\u8bed\u7ec4"}

        terms = self.term_groups[group_key]
        review_date = datetime.now().isoformat()

        for term in terms:
            term.review_status = "approved" if action in ["approve", "merge"] else "rejected"
            term.review_comment = comment
            term.reviewer_name = reviewer_name
            term.review_date = review_date

        manual_workflow_node_ids = sorted(
            {node_id for term in terms for node_id in term.manual_workflow_node_ids},
            key=workflow_node_sort_key,
        )

        # Record the review
        review_record = {
            "group_key": group_key,
            "action": action,
            "reviewer_name": reviewer_name,
            "comment": comment,
            "canonical_term": canonical_term,
            "review_date": review_date,
            "terms_affected": len(terms),
            "manual_workflow_node_ids": manual_workflow_node_ids,
        }
        self.review_records.append(review_record)

        return {
            "success": True,
            "review_id": f"review_{len(self.review_records)}",
            "terms_updated": len(terms),
            "manual_workflow_node_ids": manual_workflow_node_ids,
        }

    def set_manual_workflow_nodes(
        self,
        group_key: str,
        workflow_node_ids: list[str] | None,
        reviewer_name: str,
    ) -> dict[str, Any]:
        """Save a doctor's manual mapping between a review item and workflow nodes."""
        if group_key not in self.term_groups:
            return {"success": False, "error": "\u672a\u627e\u5230\u672f\u8bed\u7ec4"}
        if self.kg is None:
            return {"success": False, "error": "\u672a\u52a0\u8f7d\u77e5\u8bc6\u56fe\u8c31"}

        normalized_ids, invalid_ids = self._normalize_workflow_node_ids(workflow_node_ids)
        if invalid_ids:
            invalid_list = ", ".join(invalid_ids[:5])
            return {"success": False, "error": f"\u65e0\u6548\u7684\u6d41\u7a0b\u8282\u70b9\uff1a{invalid_list}"}

        review_date = datetime.now().isoformat()
        terms = self.term_groups[group_key]
        for term in terms:
            term.manual_workflow_node_ids = normalized_ids.copy()
            term.manual_match_reviewer_name = reviewer_name
            term.manual_match_date = review_date

        review_record = {
            "group_key": group_key,
            "action": "manual_match" if normalized_ids else "clear_manual_match",
            "reviewer_name": reviewer_name,
            "workflow_node_ids": normalized_ids,
            "review_date": review_date,
            "terms_affected": len(terms),
        }
        self.review_records.append(review_record)

        return {
            "success": True,
            "group_key": group_key,
            "workflow_node_ids": normalized_ids,
            "workflow_nodes": self._serialize_workflow_nodes(normalized_ids),
            "terms_updated": len(terms),
            "review_id": f"review_{len(self.review_records)}",
        }

    def merge_approved_terms(self) -> dict[str, Any]:
        """
        Merge all approved terms into the knowledge graph.
        Returns statistics about the merge operation.
        """
        if self.kg is None:
            return {"success": False, "error": "\u672a\u52a0\u8f7d\u77e5\u8bc6\u56fe\u8c31"}

        stats = {
            "entities_added": 0,
            "aliases_added": 0,
            "workflow_links_added": 0,
            "workflow_links_updated": 0,
            "errors": [],
        }

        for _group_key, terms in self.term_groups.items():
            approved_terms = [t for t in terms if t.review_status == "approved"]
            if not approved_terms:
                continue

            representative = approved_terms[0]
            entity_id = representative.matched_entity_id
            manual_workflow_node_ids = sorted(
                {node_id for term in approved_terms for node_id in term.manual_workflow_node_ids},
                key=workflow_node_sort_key,
            )

            if entity_id and entity_id in self.kg.entities:
                entity = self.kg.entities[entity_id]
                for term in approved_terms:
                    if term.term not in entity.aliases and term.term != entity.name:
                        entity.aliases.append(term.term)
                        stats["aliases_added"] += 1
            else:
                entity = GraphEntity(
                    id=f"term_{representative.category}_{representative.term}",
                    entity_type=representative.category,
                    name=representative.term,
                    description="\u75c5\u4f8b\u5ba1\u6838\u5bfc\u5165\u4e34\u5e8a\u672f\u8bed",
                    aliases=[t.term for t in approved_terms[1:]],
                    source_refs=list(set(
                        src for t in approved_terms for src in t.source_file.split("; ")
                    )),
                    properties={
                        "extracted_from_cases": True,
                        "total_frequency": sum(t.frequency for t in approved_terms),
                    },
                )
                self.kg.add_entity(entity)
                stats["entities_added"] += 1

            for term in approved_terms:
                term.matched_entity_id = entity.id

            self._apply_manual_workflow_links(
                entity=entity,
                workflow_node_ids=manual_workflow_node_ids,
                reviewer_name=representative.manual_match_reviewer_name or representative.reviewer_name,
                review_date=representative.manual_match_date or representative.review_date or datetime.now().isoformat(),
                stats=stats,
            )

        return {
            "success": True,
            "stats": stats,
        }

    def export_enhanced_kg(self, output_path: Path) -> dict[str, Any]:
        """Export the enhanced knowledge graph."""
        if self.kg is None:
            return {"success": False, "error": "\u672a\u52a0\u8f7d\u77e5\u8bc6\u56fe\u8c31"}

        # Update metadata
        self.kg.metadata["updated_at"] = datetime.now().isoformat()
        self.kg.metadata["graph_version"] = f"v{len(self.review_records) + 1}"
        self.kg.metadata["latest_update_type"] = "case_enhancement"
        self.kg.metadata["latest_source_title"] = "patient_cases"

        kg_data = {
            "format": "clinical-knowledge-graph",
            "version": "1.0",
            "graph_id": self.kg.graph_id,
            "name": self.kg.name,
            "metadata": self.kg.metadata,
            "documents": self.kg.documents,
            "entities": [e.to_dict() for e in self.kg.entities.values()],
            "relations": [r.to_dict() for r in self.kg.relations.values()],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(kg_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "output_path": str(output_path),
            "entity_count": len(self.kg.entities),
            "relation_count": len(self.kg.relations),
        }

    def save_review_state(self, state_path: Path) -> None:
        """Save review state to file."""
        state = {
            "extracted_terms": [t.to_dict() for t in self.extracted_terms],
            "review_records": self.review_records,
            "last_updated": datetime.now().isoformat(),
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def load_review_state(self, state_path: Path) -> None:
        """Load review state from file."""
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        self.extracted_terms = [
            ExtractedTerm.from_dict(t) for t in state.get("extracted_terms", [])
        ]
        self.review_records = state.get("review_records", [])

        # Rebuild term groups
        from collections import defaultdict
        groups = defaultdict(list)
        for term in self.extracted_terms:
            key = term.matched_entity_id or f"unmatched_{term.term}"
            groups[key].append(term)
        self.term_groups = dict(groups)
