# 临床知识图谱模块说明

本项目新增了一个可扩展的临床知识图谱模块：

- [clinical_knowledge_graph.py](/F:/fuwai/clinical_knowledge_graph.py)

它用于完成以下工作：

1. 根据当前 `transitions.json` 生成基础临床诊断知识图谱
2. 接收 MinerU 输出的 markdown/json 解析结果并抽取临床实体
3. 生成项目专用知识图谱存储格式 `.ckg.json`
4. 生成 Mermaid 图与 SVG 图片，便于展示和后续扩展

## 专有存储格式

输出文件格式为：

```text
knowledge_graph/*.ckg.json
```

结构包含：

- `format`
- `version`
- `graph_id`
- `metadata`
- `documents`
- `entities`
- `relations`

这套格式已经预留了：

- 增量更新
- 多病种扩展
- 文档来源追踪
- 图谱图片导出

## 当前已生成的产物

当前胸痛流程已经生成：

- [急性胸痛临床评估与诊断流程.ckg.json](/F:/fuwai/knowledge_graph/急性胸痛临床评估与诊断流程.ckg.json)
- [急性胸痛临床评估与诊断流程.mmd](/F:/fuwai/knowledge_graph/急性胸痛临床评估与诊断流程.mmd)
- [急性胸痛临床评估与诊断流程.svg](/F:/fuwai/knowledge_graph/急性胸痛临床评估与诊断流程.svg)

## 后端接口

### 1. 生成基础图谱

```bash
curl http://localhost:8000/api/knowledge-graph/build
```

### 2. 合并 MinerU 文档解析结果

```bash
curl -X POST http://localhost:8000/api/knowledge-graph/mineru-ingest \
  -H "Content-Type: application/json" \
  -d '{
    "title": "急性胸痛临床指南",
    "mineru_payload": {
      "markdown": "# 急性胸痛\n心电图是重要检查。肌钙蛋白升高支持 STEMI 或 NSTEMI。"
    }
  }'
```

## MinerU 接入建议

推荐流程：

1. 用 MinerU 解析临床指南、共识、论文或病种文档
2. 获取其默认导出的 `markdown/json`
3. 将解析结果作为 `mineru_payload` 发给后端接口
4. 后端抽取疾病、症状、检查、发现、诊断等实体并合并到知识图谱
5. 重新导出 `.ckg.json`、`.mmd` 和 `.svg`

## 为什么这样设计

这样做有几个好处：

1. 当前胸痛流程可以直接使用
2. 后续加入新的病种时，不需要推翻现有结构
3. 知识图谱可以随着文献与指南更新而持续演化
4. 既有“存储格式”，也有“可展示图片”，适合毕设答辩与后续系统拓展
