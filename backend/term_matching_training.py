from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .kg_enhancement import TermExtractor

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE_GRAPH_DIR = ROOT_DIR / "knowledge_graph"
DEFAULT_CASE_DIR = ROOT_DIR / "data"
DEFAULT_STATE_PATH = ROOT_DIR / "results" / "kg_enhancement_state.json"
DEFAULT_TRAIN_OUTPUT = ROOT_DIR / "training_data" / "sft_term_matching_train.jsonl"
DEFAULT_VAL_OUTPUT = ROOT_DIR / "training_data" / "sft_term_matching_val.jsonl"
DEFAULT_STATS_OUTPUT = ROOT_DIR / "training_data" / "term_matching_stats.json"
ALLOWED_ENTITY_TYPES = {"symptom", "finding", "exam", "diagnosis"}
NO_MATCH_ID = "NO_MATCH"
NO_MATCH_NAME = "无合适实体"
GROUP_CATEGORY_HINTS = {
    "ischemic_chest_pain": "symptom",
    "non_ischemic_chest_pain": "symptom",
    "st_elevation": "finding",
    "troponin_elevated": "finding",
    "troponin_normal": "finding",
    "ck_mb_elevated": "finding",
}
GROUP_ENTITY_NAME_HINTS = {
    "ischemic_chest_pain": ["缺血性胸痛"],
    "non_ischemic_chest_pain": ["非缺血性胸痛"],
    "st_elevation": ["ST段抬高"],
    "troponin_elevated": ["心肌损伤标志物升高"],
    "troponin_normal": ["心肌损伤标志物未升高"],
    "ck_mb_elevated": ["心肌损伤标志物升高"],
}
GENERIC_SURFACE_FORMS = {
    "症状",
    "临床发现",
    "检查",
    "诊断",
    "最终诊断",
    "概念",
    "其他",
}
SYSTEM_PROMPT = (
    "你是一名临床术语匹配助手。"
    "请根据待匹配术语、类别、上下文和候选实体，选择最匹配的知识图谱实体。"
    "如果候选列表里都不合适，就输出 NO_MATCH。"
    "只输出 JSON，字段固定为 match_decision、matched_entity_id、matched_entity_name、confidence、reason。"
)


@dataclass(frozen=True)
class MatchingEntity:
    entity_id: str
    entity_type: str
    name: str
    description: str
    aliases: tuple[str, ...]
    surface_forms: tuple[str, ...]


@dataclass(frozen=True)
class MatchingExample:
    example_id: str
    term: str
    category: str
    context: str
    label_entity_id: str
    label_entity_name: str
    label_source: str
    candidates: tuple[MatchingEntity, ...]

    def to_jsonl_record(self) -> dict[str, Any]:
        user_content = build_user_prompt(
            term=self.term,
            category=self.category,
            context=self.context,
            candidates=self.candidates,
        )
        assistant_payload = {
            "match_decision": "no_match" if self.label_entity_id == NO_MATCH_ID else "match",
            "matched_entity_id": self.label_entity_id,
            "matched_entity_name": self.label_entity_name,
            "confidence": 0.25 if self.label_entity_id == NO_MATCH_ID else 0.93,
            "reason": (
                "候选实体都不能完整覆盖该术语含义，当前知识图谱中暂无合适匹配。"
                if self.label_entity_id == NO_MATCH_ID
                else "该术语与候选实体在类别、表述和语义上最接近，且上下文支持这一匹配。"
            ),
        }
        return {
            "id": self.example_id,
            "task_type": "term_matching",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": json.dumps(assistant_payload, ensure_ascii=False, indent=2)},
            ],
            "metadata": {
                "term": self.term,
                "category": self.category,
                "label_entity_id": self.label_entity_id,
                "label_entity_name": self.label_entity_name,
                "label_source": self.label_source,
                "candidate_ids": [candidate.entity_id for candidate in self.candidates],
            },
        }


def normalize_text(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[\s\-_()（）:：/]+", "", text)
    return text


def similarity(a: str, b: str) -> float:
    na = normalize_text(a)
    nb = normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def find_latest_kg_path(knowledge_graph_dir: Path) -> Path:
    candidates = sorted(knowledge_graph_dir.glob("*.ckg.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"未找到知识图谱文件: {knowledge_graph_dir}")
    return candidates[0]


def expand_surface_forms(entity_name: str, aliases: list[str]) -> list[str]:
    forms: set[str] = set()

    def add_form(value: str) -> None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return
        forms.add(cleaned)

        simplified = re.sub(r"^(最终诊断[:：]\s*)", "", cleaned).strip()
        if simplified:
            forms.add(simplified)

        for chunk in re.split(r"[:：/]", simplified):
            chunk = chunk.strip()
            if len(chunk) <= 1 or chunk in GENERIC_SURFACE_FORMS:
                continue
            forms.add(chunk)

        no_suffix = re.sub(r"(?:/)?(症状|临床发现|检查|诊断)$", "", simplified).strip()
        if no_suffix and no_suffix not in GENERIC_SURFACE_FORMS and len(no_suffix) > 1:
            forms.add(no_suffix)

    add_form(entity_name)
    for alias in aliases:
        add_form(alias)

    return sorted(forms, key=lambda item: (len(normalize_text(item)), item))


def load_entities(kg_path: Path) -> list[MatchingEntity]:
    payload = json.loads(kg_path.read_text(encoding="utf-8"))
    entities: list[MatchingEntity] = []

    for entity_data in payload.get("entities", []):
        entity_type = entity_data.get("entity_type")
        if entity_type not in ALLOWED_ENTITY_TYPES:
            continue

        aliases = [alias for alias in entity_data.get("aliases", []) if str(alias or "").strip()]
        surface_forms = expand_surface_forms(entity_data.get("name", ""), aliases)
        entities.append(
            MatchingEntity(
                entity_id=entity_data["id"],
                entity_type=entity_type,
                name=entity_data.get("name", ""),
                description=entity_data.get("description", ""),
                aliases=tuple(aliases),
                surface_forms=tuple(surface_forms),
            )
        )

    enrich_entities_with_synonyms(entities)
    return entities


def enrich_entities_with_synonyms(entities: list[MatchingEntity]) -> None:
    for index, entity in enumerate(entities):
        matched_synonyms: set[str] = set(entity.surface_forms)
        for group_name, synonyms in TermExtractor.SYNONYM_GROUPS.items():
            group_category = GROUP_CATEGORY_HINTS.get(group_name)
            if group_category and group_category != entity.entity_type:
                continue

            name_hints = GROUP_ENTITY_NAME_HINTS.get(group_name, [])
            entity_texts = [entity.name, *entity.surface_forms]
            if name_hints and not any(any(hint in text for hint in name_hints) for text in entity_texts):
                continue

            matched_synonyms.update(str(synonym).strip() for synonym in synonyms if str(synonym).strip())

        entities[index] = MatchingEntity(
            entity_id=entity.entity_id,
            entity_type=entity.entity_type,
            name=entity.name,
            description=entity.description,
            aliases=entity.aliases,
            surface_forms=tuple(sorted(matched_synonyms, key=lambda item: (len(normalize_text(item)), item))),
        )


def build_entity_index(entities: list[MatchingEntity]) -> dict[str, MatchingEntity]:
    return {entity.entity_id: entity for entity in entities}


def best_entity_score(term: str, entity: MatchingEntity) -> float:
    return max((similarity(term, surface) for surface in entity.surface_forms), default=0.0)


def shortlist_candidates(
    term: str,
    category: str,
    entities: list[MatchingEntity],
    max_candidates: int,
    gold_entity_id: str | None = None,
) -> list[MatchingEntity]:
    pool = [entity for entity in entities if entity.entity_type == category]
    if not pool:
        pool = entities[:]

    ranked = sorted(
        pool,
        key=lambda entity: (best_entity_score(term, entity), entity.name),
        reverse=True,
    )

    selected: list[MatchingEntity] = []
    seen: set[str] = set()
    if gold_entity_id and gold_entity_id != NO_MATCH_ID:
        gold_entity = next((entity for entity in pool if entity.entity_id == gold_entity_id), None)
        if gold_entity is not None:
            selected.append(gold_entity)
            seen.add(gold_entity.entity_id)

    for entity in ranked:
        if entity.entity_id in seen:
            continue
        selected.append(entity)
        seen.add(entity.entity_id)
        if len(selected) >= max_candidates:
            break

    return selected[:max_candidates]


def build_user_prompt(term: str, category: str, context: str, candidates: tuple[MatchingEntity, ...]) -> str:
    lines = [
        f"待匹配术语：{term}",
        f"类别：{category}",
        f"上下文：{context or '无'}",
        "候选实体：",
    ]
    for index, candidate in enumerate(candidates, start=1):
        alias_text = "；".join(candidate.aliases[:5]) if candidate.aliases else "无"
        surface_text = "；".join(candidate.surface_forms[:6]) if candidate.surface_forms else candidate.name
        description = candidate.description or "无"
        lines.append(
            f"{index}. id={candidate.entity_id} | 名称={candidate.name} | 类别={candidate.entity_type} | 表达={surface_text} | 别名={alias_text} | 说明={description}"
        )
    lines.append("请从候选实体中选择最匹配的一项；如果都不合适，请输出 NO_MATCH。")
    return "\n".join(lines)


def load_review_examples(state_path: Path) -> list[dict[str, Any]]:
    if not state_path.exists():
        return []
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return payload.get("extracted_terms", [])


def iter_case_files(case_dir: Path) -> list[Path]:
    return sorted(case_dir.rglob("*.md"))


def read_case_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def is_ascii_token(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.+-]+", text or ""))


def find_surface_matches(text: str, surface: str, max_matches: int = 2) -> list[tuple[int, int, str]]:
    if not surface:
        return []

    if is_ascii_token(surface):
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(surface)}(?![A-Za-z0-9])", re.IGNORECASE)
        matches = []
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), match.group(0)))
            if len(matches) >= max_matches:
                break
        return matches

    matches = []
    start = 0
    while True:
        index = text.find(surface, start)
        if index == -1:
            break
        matches.append((index, index + len(surface), surface))
        if len(matches) >= max_matches:
            break
        start = index + len(surface)
    return matches


def extract_context(text: str, start: int, end: int, window: int = 90) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right]
    snippet = re.sub(r"\s+", " ", snippet)
    return snippet.strip(" -\n\r\t")


def use_entity_for_case_supervision(entity: MatchingEntity) -> bool:
    normalized_name = normalize_text(entity.name)
    if normalized_name in {"其他", "最终诊断其他"}:
        return False
    if "询问" in entity.name:
        return False
    return True


def useful_surface_for_case(surface: str) -> bool:
    cleaned = str(surface or "").strip()
    if not cleaned:
        return False
    if cleaned in GENERIC_SURFACE_FORMS:
        return False
    if len(normalize_text(cleaned)) <= 1:
        return False
    return True


def build_examples(
    entities: list[MatchingEntity],
    review_terms: list[dict[str, Any]],
    case_dir: Path | None,
    max_candidates: int,
    auto_negative_limit: int,
    case_negative_limit: int,
    max_case_positive_per_entity: int,
) -> list[MatchingExample]:
    entity_index = build_entity_index(entities)
    examples: list[MatchingExample] = []
    dedupe_keys: set[tuple[str, str, str, str]] = set()

    def append_example(
        *,
        example_id: str,
        term: str,
        category: str,
        context: str,
        label_entity_id: str,
        label_entity_name: str,
        label_source: str,
    ) -> None:
        dedupe_context = ""
        if label_source.startswith("reviewed") or label_source.startswith("case_"):
            dedupe_context = normalize_text(context)[:120]
        dedupe_key = (normalize_text(term), category, label_entity_id, dedupe_context)
        if dedupe_key in dedupe_keys:
            return
        candidates = shortlist_candidates(term, category, entities, max_candidates, label_entity_id)
        if label_entity_id != NO_MATCH_ID and not any(candidate.entity_id == label_entity_id for candidate in candidates):
            return
        if not candidates:
            return
        dedupe_keys.add(dedupe_key)
        examples.append(
            MatchingExample(
                example_id=example_id,
                term=term,
                category=category,
                context=context,
                label_entity_id=label_entity_id,
                label_entity_name=label_entity_name,
                label_source=label_source,
                candidates=tuple(candidates),
            )
        )

    case_positive_counter = 0
    if case_dir and case_dir.exists():
        case_files = iter_case_files(case_dir)
        for entity in entities:
            if not use_entity_for_case_supervision(entity):
                continue
            surfaces = [surface for surface in entity.surface_forms if useful_surface_for_case(surface)]
            surfaces = sorted(set(surfaces), key=lambda item: (-len(normalize_text(item)), item))
            if not surfaces:
                continue

            per_entity_count = 0
            seen_contexts: set[str] = set()
            for path in case_files:
                if per_entity_count >= max_case_positive_per_entity:
                    break
                text = read_case_text(path)
                matched_in_file = False
                for surface in surfaces:
                    for start, end, matched_text in find_surface_matches(text, surface, max_matches=1):
                        context = extract_context(text, start, end)
                        normalized_context = normalize_text(context)[:120]
                        if not context or normalized_context in seen_contexts:
                            continue
                        case_positive_counter += 1
                        per_entity_count += 1
                        seen_contexts.add(normalized_context)
                        append_example(
                            example_id=f"term_match_case_pos_{case_positive_counter:04d}",
                            term=matched_text,
                            category=entity.entity_type,
                            context=context,
                            label_entity_id=entity.entity_id,
                            label_entity_name=entity.name,
                            label_source="case_weak_positive",
                        )
                        matched_in_file = True
                        break
                    if matched_in_file or per_entity_count >= max_case_positive_per_entity:
                        break

    reviewed_counter = 0
    auto_negative_counter = 0
    for item in review_terms:
        term = str(item.get("term", "")).strip()
        category = str(item.get("category", "")).strip()
        if not term or category not in ALLOWED_ENTITY_TYPES:
            continue
        context = str(item.get("context", "")).strip()
        review_status = str(item.get("review_status", "pending")).strip()
        matched_entity_id = item.get("matched_entity_id")

        if review_status in {"approved", "merge"} and matched_entity_id and matched_entity_id in entity_index:
            reviewed_counter += 1
            entity = entity_index[matched_entity_id]
            append_example(
                example_id=f"term_match_review_pos_{reviewed_counter:04d}",
                term=term,
                category=category,
                context=context,
                label_entity_id=entity.entity_id,
                label_entity_name=entity.name,
                label_source="reviewed_positive",
            )
            continue

        if review_status == "rejected":
            reviewed_counter += 1
            append_example(
                example_id=f"term_match_review_neg_{reviewed_counter:04d}",
                term=term,
                category=category,
                context=context,
                label_entity_id=NO_MATCH_ID,
                label_entity_name=NO_MATCH_NAME,
                label_source="reviewed_negative",
            )
            continue

        if auto_negative_counter >= auto_negative_limit:
            continue
        best_score = max((best_entity_score(term, entity) for entity in entities if entity.entity_type == category), default=0.0)
        if best_score <= 0.35:
            auto_negative_counter += 1
            append_example(
                example_id=f"term_match_auto_neg_{auto_negative_counter:04d}",
                term=term,
                category=category,
                context=context,
                label_entity_id=NO_MATCH_ID,
                label_entity_name=NO_MATCH_NAME,
                label_source="review_pending_negative",
            )

    counter = 0
    for entity in entities:
        for surface_form in entity.surface_forms:
            if not useful_surface_for_case(surface_form):
                continue
            counter += 1
            append_example(
                example_id=f"term_match_alias_{counter:04d}",
                term=surface_form,
                category=entity.entity_type,
                context=f"该术语来自知识图谱实体“{entity.name}”的标准表述或别名。",
                label_entity_id=entity.entity_id,
                label_entity_name=entity.name,
                label_source="kg_surface_form",
            )

    case_negative_counter = 0
    if case_dir and case_dir.exists() and case_negative_limit > 0:
        extractor = TermExtractor()
        for md_path in iter_case_files(case_dir):
            if case_negative_counter >= case_negative_limit:
                break
            for extracted in extractor.extract_from_markdown_file(md_path):
                if case_negative_counter >= case_negative_limit:
                    break
                if extracted.category not in ALLOWED_ENTITY_TYPES:
                    continue
                if not useful_surface_for_case(extracted.term):
                    continue
                best_score = max(
                    (best_entity_score(extracted.term, entity) for entity in entities if entity.entity_type == extracted.category),
                    default=0.0,
                )
                if best_score > 0.35:
                    continue
                case_negative_counter += 1
                append_example(
                    example_id=f"term_match_case_neg_{case_negative_counter:04d}",
                    term=extracted.term,
                    category=extracted.category,
                    context=extracted.context,
                    label_entity_id=NO_MATCH_ID,
                    label_entity_name=NO_MATCH_NAME,
                    label_source="case_auto_negative",
                )

    return examples


def split_examples(examples: list[MatchingExample], val_ratio: float, seed: int) -> tuple[list[MatchingExample], list[MatchingExample]]:
    shuffled = examples[:]
    random.Random(seed).shuffle(shuffled)
    if not shuffled:
        return [], []
    val_count = int(len(shuffled) * val_ratio)
    if val_ratio > 0 and len(shuffled) >= 10:
        val_count = max(1, val_count)
    val_count = min(val_count, max(0, len(shuffled) - 1))
    val_examples = shuffled[:val_count]
    train_examples = shuffled[val_count:]
    return train_examples, val_examples


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_term_matching_dataset(
    kg_path: Path | None,
    state_path: Path,
    case_dir: Path,
    train_output: Path,
    val_output: Path,
    stats_output: Path,
    max_candidates: int = 6,
    val_ratio: float = 0.1,
    seed: int = 42,
    auto_negative_limit: int = 24,
    case_negative_limit: int = 80,
    max_case_positive_per_entity: int = 40,
) -> dict[str, Any]:
    if kg_path is None:
        kg_path = find_latest_kg_path(DEFAULT_KNOWLEDGE_GRAPH_DIR)

    entities = load_entities(kg_path)
    review_terms = load_review_examples(state_path)
    examples = build_examples(
        entities,
        review_terms,
        case_dir=case_dir,
        max_candidates=max_candidates,
        auto_negative_limit=auto_negative_limit,
        case_negative_limit=case_negative_limit,
        max_case_positive_per_entity=max_case_positive_per_entity,
    )
    train_examples, val_examples = split_examples(examples, val_ratio=val_ratio, seed=seed)

    train_records = [example.to_jsonl_record() for example in train_examples]
    val_records = [example.to_jsonl_record() for example in val_examples]
    write_jsonl(train_output, train_records)
    write_jsonl(val_output, val_records)

    label_source_counts: dict[str, int] = defaultdict(int)
    for example in examples:
        label_source_counts[example.label_source] += 1

    stats = {
        "kg_path": str(kg_path),
        "state_path": str(state_path),
        "case_dir": str(case_dir),
        "entity_count": len(entities),
        "review_term_count": len(review_terms),
        "example_count": len(examples),
        "train_count": len(train_examples),
        "val_count": len(val_examples),
        "max_candidates": max_candidates,
        "max_case_positive_per_entity": max_case_positive_per_entity,
        "case_negative_limit": case_negative_limit,
        "label_source_counts": dict(sorted(label_source_counts.items())),
        "output_files": {
            "train": str(train_output),
            "val": str(val_output),
        },
    }
    stats_output.parent.mkdir(parents=True, exist_ok=True)
    stats_output.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare term-matching SFT data for KG enhancement review.")
    parser.add_argument("--kg-path", type=Path, default=None, help="知识图谱文件路径；默认使用 knowledge_graph/ 下最新的 .ckg.json")
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH, help="知识图谱增强审核状态文件")
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR, help="原始病例目录，默认使用 data/cardiovascular_files")
    parser.add_argument("--train-output", type=Path, default=DEFAULT_TRAIN_OUTPUT, help="训练集输出路径")
    parser.add_argument("--val-output", type=Path, default=DEFAULT_VAL_OUTPUT, help="验证集输出路径")
    parser.add_argument("--stats-output", type=Path, default=DEFAULT_STATS_OUTPUT, help="统计文件输出路径")
    parser.add_argument("--max-candidates", type=int, default=6, help="每条样本保留的候选实体数量")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="验证集比例")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--auto-negative-limit", type=int, default=24, help="来自审核状态的弱负例上限")
    parser.add_argument("--case-negative-limit", type=int, default=80, help="来自原始病例的 no-match 负例上限")
    parser.add_argument("--max-case-positive-per-entity", type=int, default=40, help="每个实体最多采样多少条病例上下文正例")
    args = parser.parse_args()

    stats = build_term_matching_dataset(
        kg_path=args.kg_path,
        state_path=args.state_path,
        case_dir=args.case_dir,
        train_output=args.train_output,
        val_output=args.val_output,
        stats_output=args.stats_output,
        max_candidates=args.max_candidates,
        val_ratio=args.val_ratio,
        seed=args.seed,
        auto_negative_limit=args.auto_negative_limit,
        case_negative_limit=args.case_negative_limit,
        max_case_positive_per_entity=args.max_case_positive_per_entity,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
