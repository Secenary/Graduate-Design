# 项目结构

当前这轮整理遵循两个原则：

- 网站启动方式保持 `python server.py` 不变
- 先按职责收口结构，不额外改页面行为和接口语义

## 当前布局

```text
fuwai/
├─ backend/                 # Flask 后端、诊断逻辑、知识图谱与训练数据处理
│  ├─ server.py             # 后端 app 与共享能力
│  ├─ routes/               # 路由分拆后的接口模块
│  ├─ methods.py            # 诊断方法与模型调用
│  ├─ training_data.py      # 训练数据整理
│  └─ ...
├─ frontend/                # 网页资源
├─ scripts/                 # 命令行脚本入口
├─ config/                  # 流程配置文件
├─ generated_data/          # 生成后的病例数据
├─ knowledge_graph/         # 导出的图谱与图形文件
├─ results/                 # 结果、复核记录、数据库等输出
├─ training_data/           # SFT / 偏好 / Reward / RL 数据
├─ training_configs/        # 训练配方
├─ docs/                    # 项目文档
├─ .env.example             # 环境变量模板
├─ requirements.txt
└─ server.py                # 统一启动入口
```

## 已完成的整理

### 1. 路由拆分

- 原来集中在 `backend/server.py` 里的路由已按职责拆到 `backend/routes/`
- 当前主要包括临床诊断、知识图谱、主动问诊、管理接口和图谱增强接口
- `backend/server.py` 保留 app、共享常量与统一注册逻辑

### 2. CLI 收口

- 根目录不再保留一层薄包装脚本
- 统一使用 `python -m scripts.<name>` 运行数据生成、训练准备与评估任务

### 3. 配置收口

- 流程配置从根目录移到 `config/`
- 当前使用的文件为 `config/transitions.json` 与 `config/transitions.txt`

### 4. 文档归档

- 文档集中放在 `docs/`
- 不再参与运行的旧前端副本放在 `docs/archive/legacy-frontend/`

## 现在怎么启动

网站仍然使用：

```bash
python server.py
```

脚本统一使用：

```bash
python -m scripts.generate_data
python -m scripts.prepare_training_data
python -m scripts.process_patient_cases
python -m scripts.evals
python -m scripts.eval_cardiovascular
```

## 后续整理建议

如果继续做第二阶段重构，建议优先拆业务层，而不是再新增一个泛化的 `utils/` 目录。
