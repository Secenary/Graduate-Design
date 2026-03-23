# 网页版说明

这个仓库现在新增了一个带 Python 后端的网页入口：

- `server.py`：Flask 后端，负责静态页面与诊断 API
- `clinical_knowledge_graph.py`：临床知识图谱构建、MinerU 适配、图谱文件与图片导出
- `index.html`：网页主入口
- `styles.css`：页面样式
- `app.js`：前端诊断规则与交互逻辑

## 如何打开

### 方式 1：启动 Python 后端

```bash
python server.py
```

然后访问：

```text
http://localhost:8000
```

### 方式 2：仅查看静态页面

直接打开 `index.html` 也可以，但这种方式不会调用模型 API，只能使用前端规则模式。

## 当前网页版包含的能力

1. 病历文本输入
2. 结构化分诊条件选择
3. 基于 Python 后端的模型诊断 API
4. 基于现有决策树的前端即时诊断兜底
5. 诊断路径知识图谱高亮
6. 示例病例一键载入
7. 多种后端方法切换
8. 临床知识图谱生成与导出
9. MinerU 文档解析结果接入

## 与原项目的关系

原项目仍保留了 Python 脚本版的数据生成、提示词和评估逻辑。当前网页版已经接入 Python 后端，可以直接从网页调用 `methods.py` 中的诊断逻辑，适合演示、汇报和交互展示。

如果后续需要升级，可以继续加入：

- 从 `generated_data/patients.jsonl` 中读取真实示例病例
- 保存分析记录与评估结果
- 用户级病例历史记录

## 知识图谱接口

### 生成基础图谱

```bash
curl http://localhost:8000/api/knowledge-graph/build
```

### 接收 MinerU 文档解析结果并更新图谱

```bash
curl -X POST http://localhost:8000/api/knowledge-graph/mineru-ingest \
  -H "Content-Type: application/json" \
  -d '{
    "title": "急性胸痛指南",
    "mineru_payload": {
      "markdown": "# 急性胸痛\n心电图和肌钙蛋白是重要检查。"
    }
  }'
```

知识图谱详细说明见：

- [KNOWLEDGE_GRAPH_README.md](/F:/fuwai/KNOWLEDGE_GRAPH_README.md)
