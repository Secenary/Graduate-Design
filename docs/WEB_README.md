# 网页运行说明

## 入口位置

- 后端运行入口：`server.py`
- 后端实际代码：`backend/server.py`
- 网页实际资源：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`

## 启动方式

```bash
python server.py
```

浏览器打开：

```text
http://localhost:8000
```

## 当前网页模块

- 病例输入与后端模型诊断
- 严格三步诊断链展示
- 知识图谱路径高亮
- Note2Chat / ProMed 风格推理增强展示
- 训练中心：展示 SFT / 偏好学习 / RL 数据准备结果
- 病例回放与医生复核
- MinerU 图谱更新与版本记录
- 诊断报告导出

## 训练中心说明

网页中的“训练中心”会调用：

- `GET /api/training/status`
- `POST /api/training/prepare`

它会展示：

- 当前病例数与医生复核数
- SFT 样本量
- 偏好学习样本量
- Reward / RL 样本量
- 每个训练数据文件的下载入口
- 训练配方 YAML 文件入口
