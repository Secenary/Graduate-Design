# 项目说明

本项目面向急性胸痛/急性冠脉综合征场景，包含网页演示、后端诊断接口、知识图谱构建与增强，以及训练数据准备与评估脚本。

## 启动方式

网站启动入口保持不变：

```bash
python server.py
```

默认访问地址：

```text
http://localhost:8000
```

## 目录结构

```text
fuwai/
├─ backend/                 # Flask 后端、诊断逻辑、知识图谱与训练数据处理
├─ frontend/                # 页面资源
├─ scripts/                 # 命令行脚本入口
├─ config/                  # 流程配置
│  ├─ transitions.json
│  └─ transitions.txt
├─ generated_data/          # 生成后的病例数据
├─ knowledge_graph/         # 导出的知识图谱与图形文件
├─ results/                 # 评估结果、复核记录、数据库等输出
├─ training_data/           # SFT / 偏好 / Reward / RL 数据
├─ training_configs/        # 训练配方
├─ docs/                    # 项目文档
├─ .env.example             # 环境变量模板
├─ requirements.txt
└─ server.py                # 启动入口
```

## 命令行脚本

根目录不再保留一层薄包装脚本，统一使用：

```bash
python -m scripts.generate_data
python -m scripts.prepare_training_data
python -m scripts.prepare_term_matching_data
python -m scripts.process_patient_cases
python -m scripts.evals
python -m scripts.eval_cardiovascular
```

常用示例：

```bash
python -m scripts.prepare_training_data --input generated_data/patients.jsonl --output-dir training_data --review-path results/doctor_reviews.jsonl
python -m scripts.prepare_term_matching_data --case-dir data --state-path results/kg_enhancement_state.json
python -m scripts.evals --sample 20 --methods direct,direct_generation,intermediate_state,step_by_step,full_workflow
```

## 微调入口

术语匹配微调默认走 Qwen2.5-14B-Instruct + LLaMA-Factory：

- 数据构造：`python -m scripts.prepare_term_matching_data`
- 数据来源：`data/` 原始病例 + 知识图谱实体/同义词 + 审核状态
- 单卡训练：`bash scripts/run_qwen25_14b_term_matching_single_gpu.sh`
- Slurm 提交：`sbatch scripts/submit_qwen25_14b_term_matching_a100.slurm`
- 训练配置：`training_configs/llamafactory_qwen25_14b_term_matching.yaml`

## 环境变量

`.env.example` 保留在仓库中作为模板，真实配置写入 `.env`。

示例：

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
PORT=8000
```

## 更多文档

- `docs/README.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/WEB_README.md`
- `docs/TRAINING_README.md`
- `docs/KNOWLEDGE_GRAPH_README.md`
- `docs/KG_ENHANCEMENT_README.md`
