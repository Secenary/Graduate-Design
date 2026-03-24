# 训练数据说明

项目当前已经提供一套可直接用于论文与实验展示的训练数据准备流程，核心入口为：

- `prepare_training_data.py`
- 实际实现位于 `backend/training_data.py`

## 可导出的数据类型

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

### 辅助文件

- `training_data/training_stats.json`
- `training_data/training_manifest.json`
- `training_configs/*.yaml`

## 生成方式

```bash
python prepare_training_data.py \
  --input generated_data/patients.jsonl \
  --output-dir training_data \
  --review-path results/doctor_reviews.jsonl
```

## 网页集成

网页中的“训练中心”已经接入训练数据状态展示，可以直接看到：

- 病例总数
- 医生复核总数
- SFT 样本规模
- 偏好学习样本规模
- Reward / RL 样本规模
- 每份 jsonl 数据文件与 yaml 配方文件

## 论文可写方向

- 基于 Note2Chat 思路的病例预处理与单轮推理样本构造
- 基于 ProMed 思路的 SIG-lite 问题价值评分
- 基于医生复核的偏好学习数据构造
- 基于奖励建模的主动问诊策略优化
