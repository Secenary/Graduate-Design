# 项目结构说明

这次结构整理采用了“兼容式重构”的思路：

- 继续保留根目录脚本入口，避免 `python server.py`、`python generate_data.py` 这些旧命令失效。
- 把真正的网页资源放入 `frontend/`，把真正的后端服务与核心逻辑收拢到 `backend/`。
- 数据、图谱、结果、训练配置继续放在稳定的顶层目录，方便实验复现和论文截图。

## 结构设计参考

### 1. 前后端分层

参考高星项目常见做法，将运行时接口与网页资源分离：

- `backend/` 放 API、诊断逻辑、知识图谱、训练数据准备逻辑
- `frontend/` 放静态页面与交互逻辑

### 2. 数据资产独立目录

参考数据科学项目常见布局，把“数据、结果、文档、配置”固定成稳定目录：

- `generated_data/`
- `knowledge_graph/`
- `results/`
- `training_data/`
- `training_configs/`
- `docs/`

### 3. 训练相关资源一等公民化

参考大模型训练项目的组织方式，把训练数据与训练配方显式放在顶层，而不是散落在脚本旁边：

- `training_data/` 保存导出的 SFT / DPO / Reward / RL 数据
- `training_configs/` 保存训练 recipe 模板

## 当前兼容策略

- `server.py` 仍然是可运行入口，但内部转发到 `backend/server.py`
- `methods.py`、`prompts.py`、`prepare_training_data.py` 等根目录文件保留为兼容导入层
- 网页服务优先从 `frontend/` 提供静态资源
- 根目录 `index.html` 仅保留为跳转入口

## 这样做的好处

- 继续兼容你现在的运行方式，不影响答辩前稳定性
- 目录层次更清晰，论文中可以直接画成系统结构图
- 后续如果要继续拆成 FastAPI / Vue / React 或接训练框架，也更容易演进
