# 训练数据说明

训练数据准备入口为：

- `python -m scripts.prepare_training_data`
- 对应实现：`backend/training_data.py`

## 产物类型

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

### 统计与配方

- `training_data/training_stats.json`
- `training_data/training_manifest.json`
- `training_configs/*.yaml`

## 常用命令

```bash
python -m scripts.prepare_training_data --input generated_data/patients.jsonl --output-dir training_data --review-path results/doctor_reviews.jsonl
```

## 当前建议

- 先保证原始病例、医生复核和流程标签完整
- 先把 SFT 数据做稳，再考虑偏好学习或 RL
- 抽取、节点匹配和最终诊断最好分任务准备数据
