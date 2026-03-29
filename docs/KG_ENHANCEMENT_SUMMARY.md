# 知识图谱增强实现摘要

当前实现覆盖了从病例术语提取到医生审核再到图谱合并的完整链路。

## 已实现内容

- 从住院病例文本中抽取症状、检查、临床发现和诊断术语
- 将候选术语按语义聚合为待审核列表
- 在网页中展示审核项、图谱快照与流程节点
- 支持医生手动把待审核项匹配到诊断流程节点
- 审核通过后把别名、新实体和流程关系合并到知识图谱
- 支持导出增强后的 `.ckg.json`

## 主要文件

- `backend/kg_enhancement.py`
- `backend/routes/kg_enhancement.py`
- `frontend/kg-enhancement.html`
- `frontend/kg-enhancement.js`
- `results/kg_enhancement_state.json`

## 当前定位

这个模块现在更适合作为人工增强与审核工具，而不是完全自动合并工具。关键医学映射仍然建议保留医生确认。
