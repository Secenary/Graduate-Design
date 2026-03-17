# 急性胸痛临床决策支持系统

基于大语言模型的急性胸痛临床评估与诊断决策支持项目。

## 项目概述

本项目实现了五种基于 LLM 的临床诊断方法，用于急性胸痛患者的诊断流程：

1. **直接诊断法 (Direct Diagnosis)** - 提供诊断选项，模型从中选择
2. **直接生成法 (Direct Generation)** - 模型自由生成诊断结果
3. **中间状态法 (Intermediate State)** - 先生成中间状态再判断诊断
4. **多轮引导法 (Step-by-Step)** - 逐步引导模型判断每个临床节点
5. **全流程法 (Full Workflow)** - 提供完整工作流说明后诊断

## 诊断流程

```
急性胸痛
    ↓
缺血性胸痛判断
    ↓
ST段是否抬高 ──是──→ STEMI
    │
    否
    ↓
心肌标志物是否升高 ──是──→ NSTEMI
    │
    否
    ↓
UA / 变异性心绞痛 / 其他
```

## 项目结构

```
├── transitions.json      # 临床工作流状态机定义
├── transitions.txt       # 工作流文字说明
├── prompts.py            # 提示词模板
├── methods.py            # 五种诊断方法实现
├── generate_data.py      # 患者数据生成脚本
├── evals.py              # 评估模块
├── requirements.txt      # 依赖管理
├── generated_data/       # 生成的患者数据
│   └── patients.jsonl
└── results/              # 评估结果
    └── evaluation_results.json
```

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 设置环境变量

```bash
export OPENAI_API_KEY=your_api_key
# 可选：自定义 API 端点
export OPENAI_BASE_URL=your_api_base_url
```

### 2. 生成患者数据

```bash
# 生成 100 条患者数据（默认）
python generate_data.py

# 指定数量和并发数
python generate_data.py --count 50 --concurrent 5
```

### 3. 运行评估

```bash
# 评估所有方法
python evals.py

# 使用 LLM-as-Judge 评估（更智能）
python evals.py --judge

# 指定方法采样评估
python evals.py --methods direct,full_workflow --sample 20

# 使用 LLM-as-Judge 评估（更智能地判断语义等效的诊断）
python evals.py --judge

# 指定 Judge 使用的模型
python evals.py --judge --judge-model gpt-4o

# 指定并发数
python evals.py --sample 20 --concurrent 5

# 组合使用
python evals.py --methods direct,direct_generation --sample 20 --judge --judge-model gpt-4o
```


## 诊断方法对比

| 方法 | 提供选项 | LLM调用次数 | 特点 |
|------|---------|------------|------|
| direct | 是 | 1 | 简单直接 |
| direct_generation | 否 | 1 | 模型自由生成 |
| intermediate_state | 否 | 1 | 先生成中间状态 |
| step_by_step | 否 | 1-3 | 逐步引导判断 |
| full_workflow | 是 | 1 | 完整流程说明 |

## 评估指标

- 准确率 (Accuracy)
- 精确率 (Precision)
- 召回率 (Recall)
- F1 分数

## 许可证

MIT License