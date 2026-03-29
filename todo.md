# TODO

## 基本功能完善
- 任务状态：完成
- 任务内容：
    - 我需要利用transition.json文件，调用大语言模型，来伪造不同状态下的患者描述，要求包含患者的基本信息、以及一个最后的结果状态，要求患者主述尽可能符合真实情况，并且过程状态以及结果状态必须在transition.json文件中定义。
    - 伪造100条不同状态下的患者描述，放在@generated_data/ 中，用jsonl保存，其中主述放在"description"字段,结果状态放在"result_state"字段，注意主述中描绘了病人如何如何，但是不能包含结果状态。
    - 基于生成好的伪造患者描述，我需要调用不同的大语言模型，来测试现在的模型是否能够正确识别患者的结果状态。
        - 其中我们要对比不同的方法，包括：直接将患者主述输入模型，让模型直接输出结果状态；基于transition.json文件，利用大语言模型，来生成患者主述中缺失的过程状态，然后根据过程状态和结果状态，来判断患者的结果状态； 基于transition.txt文件全部流程都告诉模型，让模型输出结果状态

### 已完成模块
- [x] `prompts.py` - 提示词模块
- [x] `methods.py` - 方法实现模块
- [x] `evals.py` - 评估模块
- [x] `generate_data.py` - 数据生成脚本
- [x] `requirements.txt` - 依赖管理
- [x] `generated_data/` - 数据目录
- [x] `results/` - 结果目录

## 换为协程方式调用大语言模型
- 任务状态：完成
- 任务内容：
    - 我需要将现在的代码，从同步调用大语言模型，改为异步调用大语言模型，以提高效率。


## 增加中间状态多轮引导方法
- 任务状态：完成
- 任务内容：
    - 现在的中间状态方法，是直接让模型输出中间状态：
缺血性胸痛：[是/否]
ST段抬高：[是/否/不适用]
心肌标志物升高：[是/否/不适用]

还可以增加一种，逐步引导模型，来先考虑缺血性胸痛，然后得出结论后，我们先与规则对比，接着进入下一个判断节点，逐渐往复，直到得出最终结论。

### 已实现内容
- [x] `prompts.py` - 新增三个步骤的提示词模板
- [x] `methods.py` - 新增 `step_by_step_diagnosis` 方法
- [x] `evals.py` - 更新方法映射，支持新方法评估
- [x] `CLAUDE.md` - 更新文档说明

## API 管理模块（图谱工程化）
- 任务状态：完成
- 任务内容：
    - 将知识图谱生成部分工程化，提供 API 接口供医院系统集成
    - 参考 MinerU API 管理页面设计
    - 实现 API Key 申请审核流程
    - 支持 MinerU Agent 轻量解析接口

### 已实现功能
- [x] 后端 API 接口
  - `/api/docs` - API 文档接口
  - `/api/keys/apply` - API Key 申请接口
  - `/api/keys/review` - API Key 审核接口（管理员）
  - `/api/keys/applications` - 申请列表接口（管理员）
  - `/api/keys/status/<id>` - 申请状态查询接口
  - `/api/keys/list` - API Key 列表接口（管理员）
  - `/api/knowledge-graph/mineru-agent-url` - MinerU Agent URL 解析接口
  - `/api/knowledge-graph/mineru-agent-file` - MinerU Agent 文件上传接口

- [x] 前端 API 管理界面
  - API 文档展示（分类、接口详情、代码示例）
  - API Key 申请表单
  - API 在线测试工具
  - 管理员审核面板

- [x] 前端 MinerU Agent 知识图谱生成
  - 通过 URL 解析文档并合并到图谱
  - 通过文件上传解析文档并合并到图谱
  - 支持语言选择和页码范围设置

- [x] API Key 审核流程
  - 用户提交申请（姓名、邮箱、机构、用途）
  - 管理员审核（批准/拒绝）
  - 批准后自动生成 API Key（格式：fw_xxxxxxxxxxxxxxxx）

### MinerU Agent 轻量解析
- 参考 MinerU 官方 API 设计
- 支持 URL 解析和文件上传两种方式
- 自动轮询解析结果并合并到知识图谱
- 文件限制：10MB，20页
- IP 限频防滥用

## 临床病例数据库
- 任务状态：完成
- 任务内容：
    - 建立 SQLite 数据库存储临床病例
    - 支持病例的增删改查
    - 支持标签管理
    - 支持训练数据导出
    - 诊断时自动保存病例
    - 医生复核时保存到数据库

### 已实现功能
- [x] 数据库模型
  - `cases` - 病例表
  - `doctor_reviews` - 医生复核表
  - `case_tags` - 病例标签表
  - `training_exports` - 训练数据导出记录表

- [x] 后端 API 接口
  - `POST /api/cases` - 保存病例
  - `GET /api/cases` - 查询病例列表（支持筛选、分页）
  - `GET /api/cases/<id>` - 获取病例详情
  - `DELETE /api/cases/<id>` - 删除病例
  - `POST /api/cases/<id>/tags` - 添加标签
  - `DELETE /api/cases/<id>/tags/<tag>` - 移除标签
  - `GET /api/cases/tags` - 获取所有标签
  - `GET /api/cases/statistics` - 获取统计信息
  - `POST /api/cases/export-training` - 导出训练数据

- [x] 前端病例库界面
  - 统计概览（总病例、今日新增、已复核）
  - 搜索与筛选（诊断类型、状态、关键词）
  - 标签云展示
  - 病例卡片列表（分页）
  - 病例详情查看
  - 标签管理
  - 训练数据导出

- [x] 自动保存机制
  - 诊断完成后自动保存病例到数据库
  - 医生复核后保存复核记录到数据库