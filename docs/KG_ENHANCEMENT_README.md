# 知识图谱增强模块说明

该模块用于从病例文本中提取术语，经过医生审核后，把这些术语及其人工指定的流程节点关系合并进知识图谱。

## 核心流程

1. 从 `data/cardiovascular_files/` 提取候选术语
2. 按同义和近义关系聚合为待审核项
3. 医生在页面中审核通过或拒绝
4. 医生可把待审核项手动匹配到诊断流程节点
5. 合并审核结果并导出增强后的知识图谱

## 页面入口

```text
http://localhost:8000/kg-enhancement.html
```

## 相关接口

- `GET /api/kg-enhancement/status`
- `POST /api/kg-enhancement/extract`
- `GET /api/kg-enhancement/review-items`
- `POST /api/kg-enhancement/review`
- `POST /api/kg-enhancement/workflow-match`
- `POST /api/kg-enhancement/merge`
- `POST /api/kg-enhancement/export`

## 关键行为

- 审核状态会持久化到 `results/kg_enhancement_state.json`
- 手动流程节点匹配会随审核记录一并保存
- 合并时会把别名、新实体和流程链接一起写回图谱

## 相关代码

- `backend/kg_enhancement.py`
- `backend/routes/kg_enhancement.py`
- `frontend/kg-enhancement.html`
- `frontend/kg-enhancement.js`
