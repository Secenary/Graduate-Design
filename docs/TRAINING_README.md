# 训练数据说明

训练数据准备入口包括：

- `python -m scripts.prepare_training_data`
- `python -m scripts.prepare_term_matching_data`
- 对应实现：`backend/training_data.py`、`backend/term_matching_training.py`

## 通用训练数据

### SFT

- `training_data/sft_fact_extraction.jsonl`
- `training_data/sft_single_turn_questioning.jsonl`
- `training_data/sft_multi_turn_dialogue.jsonl`
- `training_data/sft_stepwise_diagnosis.jsonl`

### 偏好学习

- `training_data/dpo_question_preference.jsonl`
- `training_data/diagnosis_review_preference.jsonl`

### Reward / RL

- `training_data/reward_question_scoring.jsonl`
- `training_data/rl_question_policy.jsonl`

## 术语匹配微调数据

术语审核匹配度优化使用：

- `training_data/sft_term_matching_train.jsonl`
- `training_data/sft_term_matching_val.jsonl`
- `training_data/term_matching_stats.json`

这组数据现在不再只依赖少量审核记录，而是主要来自：

- `data/` 中 207 份原始病例 markdown
- 知识图谱实体名、别名和规范表述
- `TermExtractor.SYNONYM_GROUPS` 中的同义表达
- `results/kg_enhancement_state.json` 中已有的审核记录
- 从病例中自动挖出的 `NO_MATCH` 负例

当前数据构造方式会：

- 从原始病例里抓取术语在正文中的真实上下文，形成弱监督正例
- 从病例抽取结果里筛出图谱中没有合适实体的术语，形成 `NO_MATCH` 负例
- 继续保留少量知识图谱标准表述样本，帮助模型稳住输出格式

生成命令：

```bash
python -m scripts.prepare_term_matching_data --case-dir data --state-path results/kg_enhancement_state.json
```

## LLaMA-Factory 配方

- `training_configs/llamafactory_qwen25_14b_term_matching.yaml`
- `training_configs/sft_term_matching_recipe.yaml`

A100 单卡常用命令：

```bash
bash scripts/run_qwen25_14b_term_matching_single_gpu.sh
```

Slurm 提交：

```bash
sbatch scripts/submit_qwen25_14b_term_matching_a100.slurm
```

## 当前建议

- 第一阶段仍然限定在“候选实体选择 + no-match 判断”
- 先用这版病例弱监督数据把匹配器训起来
- 再继续累积医生审核数据，做第二轮更强监督微调
