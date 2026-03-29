# 知识图谱说明

知识图谱相关实现位于：

- `backend/clinical_knowledge_graph.py`

它负责把流程配置与文档抽取结果整理成统一的临床知识图谱，并导出 `.ckg.json`、Mermaid 和 SVG 等产物。

## 数据来源

1. `config/transitions.json`：基础诊断流程配置
2. MinerU 解析出的 markdown / json：补充文档实体与关系

## 主要输出

默认输出到：

```text
knowledge_graph/
```

常见文件包括：

- `*.ckg.json`
- `*.mmd`
- `*.svg`

## 常用接口

- `GET /api/knowledge-graph/status`：查看当前图谱状态
- `GET /api/knowledge-graph/build`：按当前流程配置重建基础图谱
- `POST /api/knowledge-graph/mineru-ingest`：把 MinerU 结果合并进图谱
- `POST /api/knowledge-graph/mineru-url`：按 URL 调 MinerU v4 并合并
- `POST /api/knowledge-graph/mineru-file`：按文件调 MinerU v4 并合并

## 命令行入口

模块本身也支持直接执行：

```bash
python -m backend.clinical_knowledge_graph
```

这会使用 `config/transitions.json` 作为默认流程输入。
