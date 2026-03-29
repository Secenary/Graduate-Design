# 知识图谱增强模块说明

本模块用于从住院病例文件中提取临床术语变体，通过医生审核后将这些变体合并到知识图谱中，从而完善知识图谱的语义表达能力。

## 功能特性

### 1. 临床术语提取
- 从 `/data/cardiovascular_files` 目录下的病例文件中自动提取临床术语
- 支持 4 类术语提取：
  - **症状 (symptom)**: 胸痛、胸闷、心悸、气促等
  - **临床发现 (finding)**: ST 段抬高、肌钙蛋白升高、T 波倒置等
  - **检查 (exam)**: 心电图、超声心动图、冠脉 CTA 等
  - **诊断 (diagnosis)**: STEMI、NSTEMI、不稳定型心绞痛等

### 2. 语义匹配
- 使用预定义的术语同义词组进行语义匹配
- 基于字符串相似度算法计算匹配置信度
- 自动将提取的术语映射到现有知识图谱实体

### 3. 医生审核工作流
- 将术语按语义分组展示
- 支持批量审核（通过/拒绝）
- 记录审核医生姓名和审核意见
- 支持审核状态持久化

### 4. 知识图谱增量更新
- 将审核通过的术语作为别名添加到现有实体
- 为新术语创建新的知识图谱实体
- 导出增强后的知识图谱文件

## 快速开始

### 1. 启动服务

```bash
python server.py
```

服务默认运行在 `http://localhost:8000`

### 2. 访问知识图谱增强页面

打开浏览器访问：
```
http://localhost:8000/kg-enhancement.html
```

### 3. 使用流程

1. **提取术语**: 点击"提取术语"按钮，系统会自动扫描病例文件并提取临床术语
2. **审核术语**: 在审核列表中查看提取的术语变体，点击"通过"或"拒绝"
3. **合并到图谱**: 审核完成后，点击"合并到图谱"将术语整合到知识图谱

## API 接口

### 状态查询
```bash
GET /api/kg-enhancement/status
```

### 提取术语
```bash
POST /api/kg-enhancement/extract
Content-Type: application/json

{
  "case_dir": "/path/to/case/files"  // 可选，默认使用 data/cardiovascular_files
}
```

### 获取审核项目
```bash
GET /api/kg-enhancement/review-items
```

### 提交审核
```bash
POST /api/kg-enhancement/review
Content-Type: application/json

{
  "group_key": "term_symptom_胸痛",
  "action": "approve",  // approve | reject
  "reviewer_name": "张医生",
  "comment": "术语准确，同意添加"
}
```

### 合并术语到知识图谱
```bash
POST /api/kg-enhancement/merge
```

### 导出增强知识图谱
```bash
POST /api/kg-enhancement/export
Content-Type: application/json

{
  "output_name": "enhanced_knowledge_graph"
}
```

## 术语匹配规则

### 预定义同义词组

系统内置了以下同义词组用于语义匹配：

```python
SYNONYM_GROUPS = {
    "ischemic_chest_pain": [
        "缺血性胸痛",
        "心源性胸痛",
        "心绞痛样胸痛",
        "典型胸痛",
        "冠心病胸痛",
    ],
    "st_elevation": [
        "ST 段抬高",
        "ST 抬高",
        "ST 段上抬",
        "ST 段弓背向上抬高",
    ],
    "troponin_elevated": [
        "肌钙蛋白升高",
        "肌钙蛋白阳性",
        "cTn 升高",
        "cTnI 升高",
        "cTnT 升高",
        "心肌损伤标志物升高",
    ],
    # ... 更多同义词组
}
```

### 匹配置信度

- **高 (≥0.8)**: 完全匹配或同义词组内匹配
- **中 (0.6-0.8)**: 字符串相似度较高
- **低 (<0.6)**: 相似度较低，需要人工确认

## 数据持久化

### 审核状态文件
审核状态保存在 `results/kg_enhancement_state.json`

### 增强知识图谱
增强后的知识图谱保存在 `knowledge_graph/` 目录：
- `{graph_id}_enhanced.ckg.json`: 增强后的知识图谱
- 包含新增的实体和别名

## 扩展术语提取规则

在 `backend/kg_enhancement.py` 中的 `TermExtractor.TERM_PATTERNS` 添加新的提取规则：

```python
TERM_PATTERNS = {
    "symptom": [
        r"新的症状模式",
        # ...
    ],
    "finding": [
        r"新的临床发现模式",
        # ...
    ],
    # ...
}
```

## 审核状态说明

- **pending (待审核)**: 新提取的术语，等待医生审核
- **approved (已通过)**: 医生审核通过，可以合并到知识图谱
- **rejected (已拒绝)**: 医生拒绝，不会合并到知识图谱

## 注意事项

1. **术语质量**: 提取的术语质量取决于病例文件的规范性和术语模式的完整性
2. **审核必要性**: 所有术语必须经过医生审核后才能合并到知识图谱
3. **版本管理**: 每次合并操作会生成新的知识图谱版本文件
4. **性能考虑**: 大量病例文件提取可能需要较长时间

## 故障排除

### 无法提取术语
- 检查病例文件路径是否正确
- 确认病例文件格式为 Markdown (.md)
- 查看服务器日志获取详细错误信息

### 匹配置信度低
- 检查术语是否拼写正确
- 考虑在 `SYNONYM_GROUPS` 中添加新的同义词
- 手动审核确认术语准确性

### 合并失败
- 确认知识图谱文件存在且格式正确
- 检查是否有已审核通过的术语
- 查看服务器日志获取详细错误信息

## 未来扩展

1. **多病种支持**: 扩展到其他心血管疾病病种
2. **自动推荐**: 基于使用频率自动推荐术语
3. **术语关系**: 提取术语间的语义关系
4. **版本对比**: 支持知识图谱版本对比和回滚
