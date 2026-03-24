# 急性胸痛临床决策支持系统

这是一个面向毕设展示与实验扩展的急性胸痛辅助诊断项目。系统将胸痛分诊规则、三轮互动式问诊、知识图谱高亮、医生复核闭环，以及 SFT / 偏好学习 / RL 风格训练数据准备统一到同一套网页与 Python 后端中。

## 当前能力

- 三步诊断链：症状学 -> 心电图 -> 心肌标志物
- 证据不足时严格停诊，明确提示缺失检查
- 知识图谱路径高亮与病例逐轮回放
- 医生确认 / 修正闭环
- MinerU 文档结果接入与图谱版本管理
- Note2Chat 风格病例预处理与单轮推理样本构造
- ProMed 风格 SIG-lite 信息增益评分与下一问推荐
- 训练中心：网页直接查看 SFT / DPO / Reward / RL 数据准备结果

## 项目结构

```text
fuwai/
├─ backend/                 # Python 后端与核心临床逻辑
│  ├─ server.py             # Flask API 与网页服务入口
│  ├─ methods.py            # 分步诊断与多方法推理
│  ├─ prompts.py            # 提示词模板
│  ├─ clinical_reasoning_enhancer.py
│  ├─ clinical_knowledge_graph.py
│  └─ training_data.py      # 训练数据准备逻辑
├─ frontend/                # 网页静态资源
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
├─ docs/                    # 扩展文档
├─ generated_data/          # 互动式病例数据
├─ knowledge_graph/         # 图谱存储、Mermaid、SVG 产物
├─ results/                 # 评估、医生复核、报告导出
├─ training_configs/        # SFT / DPO / RL 配方示例
├─ training_data/           # 训练样本导出目录
├─ server.py                # 兼容入口，保持 python server.py 不变
├─ generate_data.py         # 兼容脚本入口
├─ prepare_training_data.py # 兼容脚本入口
└─ evals.py                 # 评估脚本
```

## 快速运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env`：

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
PORT=8000
```

### 3. 启动网页

```bash
python server.py
```

浏览器打开：

```text
http://localhost:8000
```

## 数据与训练

生成互动式病例：

```bash
python generate_data.py --count 20 --concurrent 5
```

准备训练数据：

```bash
python prepare_training_data.py \
  --input generated_data/patients.jsonl \
  --output-dir training_data \
  --review-path results/doctor_reviews.jsonl
```

运行评估：

```bash
python evals.py --sample 20 --methods direct,direct_generation,intermediate_state,step_by_step,full_workflow
```

## 网页演示建议

1. 先载入示例病例并执行诊断
2. 展示知识图谱高亮路径
3. 展示病例逐轮回放与医生复核
4. 切换到训练中心，展示 SFT / 偏好学习 / RL 数据规模
5. 导出诊断报告，形成完整闭环

更多说明见：

- `WEB_README.md`
- `TRAINING_README.md`
- `docs/PROJECT_STRUCTURE.md`
