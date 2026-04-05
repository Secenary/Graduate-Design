(() => {
  const STORAGE_KEYS = {
    user: "fuwai_shell_user",
    session: "fuwai_shell_session",
    view: "fuwai_shell_view",
    activity: "fuwai_shell_activity",
  };

  const shellState = {
    registerMode: false,
    currentView: "dashboard",
    currentCase: null,
    activeWorkflowId: "acute-chest-pain",
    workflowConfig: null,
    workflowConfigs: {},
    workflowStatuses: {},
    workflowDefinitions: [],
    selectedNodeId: null,
    selectedTransitionIndex: null,
    caseStats: null,
    cases: [],
    tags: [],
    activities: [],
    departmentFilter: "\u5168\u90e8\u5206\u79d1",
  };

  const SERVICE_LINES = [
    {
      id: "acute-chest-pain",
      workflowId: "acute-chest-pain",
      configPath: "config/transitions.json",
      name: "\u6025\u6027\u80f8\u75db",
      enName: "胸痛诊疗线",
      specialty: "\u5fc3\u8840\u7ba1\u5185\u79d1",
      departments: ["\u5fc3\u8840\u7ba1\u5185\u79d1", "\u6025\u8bca\u79d1"],
      workflowName: "\u6025\u6027\u80f8\u75db\u4e34\u5e8a\u8bc4\u4f30\u4e0e\u8bca\u65ad\u6d41\u7a0b",
      status: "live",
      statusLabel: "\u5df2\u63a5\u5165",
      summary: "\u5f53\u524d\u4ed3\u5e93\u5df2\u6253\u901a\u8bca\u65ad\u3001\u75c5\u4f8b\u5e93\u3001\u77e5\u8bc6\u56fe\u8c31\u4e0e\u8bad\u7ec3\u6570\u636e\u95ed\u73af\uff0c\u53ef\u76f4\u63a5\u8fdb\u5165\u4e34\u5e8a\u5de5\u4f5c\u53f0\u3002",
      primaryActionLabel: "\u8fdb\u5165\u5de5\u4f5c\u53f0",
      primaryView: "workspace",
      secondaryActionLabel: "\u67e5\u770b\u75c5\u4f8b",
      secondaryView: "cases",
    },
    {
      id: "acute-abdominal-pain",
      workflowId: "acute-abdominal-pain",
      configPath: "config/workflows/acute_abdominal_pain.json",
      name: "\u6025\u6027\u8179\u75db",
      enName: "腹痛分诊线",
      specialty: "\u666e\u901a\u5916\u79d1",
      departments: ["\u666e\u901a\u5916\u79d1", "\u6025\u8bca\u79d1"],
      workflowName: "\u6025\u6027\u8179\u75db\u4e34\u5e8a\u5206\u8bca\u6d41\u7a0b",
      status: "draft",
      statusLabel: "\u5f85\u7f16\u8f91",
      summary: "\u5df2\u8865\u5165\u53ef\u7f16\u8f91\u7684\u8179\u75db\u77e5\u8bc6\u56fe\u8c31\u8349\u7a3f\uff0c\u53ef\u5148\u7ef4\u62a4\u8179\u819c\u523a\u6fc0\u5f81\u3001\u5b9e\u9a8c\u5ba4\u68c0\u67e5\u3001\u5f71\u50cf\u4e0e\u4f1a\u8bca\u5206\u652f\u3002",
      primaryActionLabel: "\u8fdb\u5165\u7f16\u8f91",
      primaryView: "tree",
      secondaryActionLabel: "\u67e5\u770b\u8349\u7a3f",
      secondaryView: "tree",
    },
    {
      id: "stroke",
      workflowId: "stroke",
      configPath: "config/workflows/stroke.json",
      name: "\u8111\u5352\u4e2d",
      enName: "卒中分诊线",
      specialty: "\u795e\u7ecf\u5185\u79d1",
      departments: ["\u795e\u7ecf\u5185\u79d1", "\u5352\u4e2d\u4e2d\u5fc3"],
      workflowName: "\u8111\u5352\u4e2d\u6025\u8bca\u5206\u8bca\u6d41\u7a0b",
      status: "draft",
      statusLabel: "\u5f85\u7f16\u8f91",
      summary: "\u5df2\u8865\u5165\u53ef\u7f16\u8f91\u7684\u5352\u4e2d\u77e5\u8bc6\u56fe\u8c31\u8349\u7a3f\uff0c\u53ef\u7ee7\u7eed\u6269\u5c55\u65f6\u95f4\u7a97\u3001\u5f71\u50cf\u5224\u8bfb\u3001\u6eb6\u6813\u4e0e\u53d6\u6813\u8bc4\u4f30\u8282\u70b9\u3002",
      primaryActionLabel: "\u8fdb\u5165\u7f16\u8f91",
      primaryView: "tree",
      secondaryActionLabel: "\u67e5\u770b\u8349\u7a3f",
      secondaryView: "tree",
    },
  ];

  const pageShell = document.querySelector(".page-shell");
  if (!pageShell) return;

  document.body.insertAdjacentHTML(
    "afterbegin",
    `
      <section id="login-screen" class="auth-screen">
        <div class="auth-backdrop"></div>
        <div class="auth-layout">
          <article class="auth-brand-panel">
            <p class="auth-kicker">MediAnnotate Clinical</p>
            <h1>把决策流程、病例标注和知识图谱放到同一套临床工作台里。</h1>
            <p class="auth-copy">现有项目的诊断、图谱、训练与审核能力会被保留，并按参考网页的多工作区交互重新组织。</p>
            <div class="auth-feature-list">
              <article><strong>流程目录</strong><span>统一查看流程入口、图谱版本和当前任务。</span></article>
              <article><strong>病例工作流</strong><span>病例库、诊断结果、医生复核和报告导出联动。</span></article>
              <article><strong>图谱增强</strong><span>MinerU 导入、术语审核、训练数据准备一体化。</span></article>
            </div>
          </article>
          <article class="auth-card">
            <div class="auth-card-head">
              <p id="auth-mode-label" class="auth-card-kicker">登录工作台</p>
              <h2 id="auth-title">深圳阜外医院临床决策门户</h2>
              <p id="auth-subtitle">当前为本地演示登录，资料会保存在浏览器中。</p>
            </div>
            <form id="auth-form" class="auth-form">
              <label class="auth-field auth-register-only"><span>姓名</span><input id="auth-name" type="text" placeholder="例如：张医生"></label>
              <label class="auth-field"><span>手机号</span><input id="auth-phone" type="tel" placeholder="用于本地登录识别"></label>
              <label class="auth-field auth-register-only"><span>科室</span><input id="auth-department" type="text" placeholder="例如：心血管内科"></label>
              <label class="auth-field auth-register-only"><span>角色</span><input id="auth-role" type="text" placeholder="例如：临床审核专家"></label>
              <label class="auth-field"><span>密码</span><input id="auth-password" type="password" placeholder="任意内容即可，本地不会上传"></label>
              <button id="auth-submit" class="auth-submit" type="submit">进入工作台</button>
              <button id="auth-mode-toggle" class="auth-toggle" type="button">切换到注册模式</button>
            </form>
            <div class="auth-footer"><span>本地会话</span><span>病例标注</span><span>图谱联动</span></div>
          </article>
        </div>
      </section>
      <div id="app-shell" class="shell" hidden>
        <header class="shell-header">
          <div class="shell-brand"><div class="shell-brand-mark"><img src="/assets/fuwai-emblem.jpg" alt="深圳阜外医院院徽"></div><div><p>中国医学科学院阜外医院深圳医院</p><strong id="dashboard-workflow-name">急性胸痛临床评估与诊断流程</strong></div></div>
          <nav class="shell-nav">
            <button class="shell-nav-button active" type="button" data-target-view="dashboard">流程目录</button>
            <button class="shell-nav-button" type="button" data-target-view="tree">路径编辑</button>
            <button class="shell-nav-button" type="button" data-target-view="parser">资料解析</button>
            <button class="shell-nav-button" type="button" data-target-view="cases">病例库</button>
            <button class="shell-nav-button" type="button" data-target-view="annotation">标注复核</button>
            <button class="shell-nav-button" type="button" data-target-view="workspace">诊断工作台</button>
            <button class="shell-nav-button" type="button" data-target-view="profile">个人中心</button>
          </nav>
          <div class="shell-actions"><div id="shell-health-status" class="shell-health-chip">服务检测中</div><div class="shell-user-card"><span id="shell-user-name">本地用户</span><small id="shell-user-role">临床审核</small></div><button id="shell-logout" class="shell-logout-button" type="button">退出</button></div>
        </header>
        <main class="shell-main">
          <section class="app-view is-active" data-view="dashboard"><div class="view-container"><div class="view-head"><div><p class="view-kicker">疾病工作区</p><h1>疾病流程目录</h1><p class="view-copy">查看当前临床线，切换不同分科，并把诊断、病例、知识图谱与训练数据集中在同一工作台。</p></div><div class="view-head-actions"><button class="primary-button" type="button" data-go-view="workspace">新建诊断任务</button><button class="ghost-button" type="button" data-go-view="cases">打开病例库</button></div></div><div class="dashboard-hero"><div class="dashboard-poster"><p class="dashboard-poster-kicker">当前病种线</p><h2 id="dashboard-active-line-title">急性胸痛工作区</h2><p id="dashboard-active-line-copy">从病历接收到结构化推理、图谱复核与医生审核导出，完整串联当前流程。</p><div class="dashboard-badges"><span id="dashboard-server-chip">后端检测中</span><span id="dashboard-graph-version">图谱版本待同步</span><span id="dashboard-training-count">训练数据待同步</span></div></div><div class="dashboard-summary-list"><article><strong id="dashboard-case-count">0</strong><span>病例总数</span></article><article><strong id="dashboard-review-count">0</strong><span>复核数</span></article><article><strong id="dashboard-today-count">0</strong><span>今日新增</span></article></div></div><section class="dashboard-section department-hub-section"><div class="section-head"><div><p class="section-kicker">分科总览</p><h2>三条临床线</h2><p class="mini-note">三条临床线均已具备入口，其中急性腹痛与脑卒中已补入可编辑知识图谱草稿。</p></div></div><div id="department-filter-list" class="department-filter-list"></div><div id="service-line-grid" class="service-line-grid"></div></section><section class="dashboard-section"><div class="section-head"><div><p class="section-kicker">流程目录</p><h2>流程目录</h2><p class="mini-note">按分科查看已接入流程与待编辑草稿。</p></div></div><div class="catalog-table-shell"><table class="catalog-table"><thead><tr><th>流程</th><th>状态</th><th>图谱</th><th>入口</th></tr></thead><tbody id="workflow-catalog-body"></tbody></table></div></section><section class="dashboard-grid"><article class="dashboard-panel"><p class="section-kicker">快速路径</p><h3>建议操作路径</h3><ol class="dashboard-sequence"><li>先在诊断工作台完成分析并保存结构化结果。</li><li>再到标注复核查看病例路径与医生备注。</li><li>最后用资料解析工具补充图谱并准备训练数据。</li></ol></article><article class="dashboard-panel accent"><p class="section-kicker">闭环推进</p><h3>闭环推进</h3><p id="dashboard-next-action" class="mini-note">等待后端状态、图谱版本和训练指标同步。</p><div class="dashboard-action-row"><button class="ghost-button" type="button" data-go-view="tree">打开路径编辑器</button><button class="secondary-button" type="button" data-go-view="parser">打开图谱工具</button></div></article></section></div></section>
          <section class="app-view" data-view="tree" hidden><div class="view-container"><div class="view-head"><div><p class="view-kicker">路径编辑</p><h1>流程树编辑器</h1><p class="view-copy">在不同病种线之间切换，维护对应的知识图谱草稿配置、转移关系与节点内容。</p></div><div class="view-head-actions"><button id="workflow-editor-save" class="primary-button" type="button">保存配置</button><button id="workflow-editor-export" class="ghost-button" type="button">导出草稿 JSON</button><button id="workflow-editor-reset" class="secondary-button" type="button">重置当前配置</button></div></div><section class="workflow-switcher-shell"><div><p class="section-kicker">知识图谱草稿</p><h3>选择草稿图谱</h3><p id="workflow-editor-caption" class="mini-note">当前正在维护急性胸痛知识图谱草稿。</p></div><div id="workflow-switcher-list" class="workflow-switcher-list"></div></section><div class="tree-summary-grid"><article class="tree-summary-card"><span>节点数</span><strong id="workflow-node-count">0</strong></article><article class="tree-summary-card"><span>转移数</span><strong id="workflow-transition-count">0</strong></article><article class="tree-summary-card"><span>当前节点</span><strong id="workflow-selected-label">未选择</strong></article><article class="tree-summary-card"><span>保存状态</span><strong id="workflow-save-status">未加载</strong></article></div><div class="tree-editor-layout"><aside class="tree-editor-sidebar"><section class="tree-editor-card"><div class="inline-head"><h3>节点列表</h3><button id="workflow-add-node" class="ghost-button" type="button">新增节点</button></div><div id="workflow-node-list" class="tree-list"></div></section><section class="tree-editor-card"><div class="inline-head"><h3>节点详情</h3><button id="workflow-delete-node" class="secondary-button" type="button">删除节点</button></div><div class="tree-form-grid"><label><span>节点 ID</span><input id="workflow-node-id" class="text-like-input" type="text" readonly></label><label><span>节点类型</span><select id="workflow-node-type"><option value="状态节点">状态节点</option><option value="判断节点">判断节点</option></select></label><label class="tree-form-span"><span>节点内容</span><textarea id="workflow-node-content" class="text-input compact-textarea" rows="5"></textarea></label></div></section><section class="tree-editor-card"><div class="inline-head"><h3>转移规则</h3><button id="workflow-add-transition" class="ghost-button" type="button">新增转移</button></div><div id="workflow-transition-list" class="tree-list"></div><label class="tree-form-span"><span>当前条件</span><input id="workflow-transition-condition" class="text-like-input" type="text" placeholder="例如：是 / 否"></label><button id="workflow-delete-transition" class="secondary-button tree-inline-button" type="button">删除转移</button></section></aside><section class="tree-preview-card"><div class="inline-head"><div><h3>关系画布</h3><p class="mini-note">在左侧选择节点或转移后，这里会高亮对应关系。</p></div></div><div id="workflow-canvas" class="tree-canvas"><div class="tree-empty-state">加载流程配置后，可在这里预览结构。</div></div></section></div></div></section>
          <section class="app-view" data-view="parser" hidden><div class="view-container"><div class="view-head"><div><p class="view-kicker">资料解析</p><h1>资料解析、图谱增强与训练准备</h1><p class="view-copy">这里会承接现有 MinerU、图谱增强和训练数据工作台。</p></div></div><div id="parser-view-shell" class="page-shell view-shell parser-shell"></div></div></section>
          <section class="app-view" data-view="cases" hidden><div class="view-container"><div class="view-head"><div><p class="view-kicker">病例库</p><h1>病例库与标注入口</h1><p class="view-copy">直接使用当前 Flask + SQLite 病例接口，支持筛选、载入、删除与手动新增。</p></div><div class="view-head-actions"><button id="case-refresh" class="ghost-button" type="button">刷新</button><button id="open-case-modal" class="primary-button" type="button">新增病例</button></div></div><div class="case-metrics-grid"><article class="tree-summary-card"><span>病例总数</span><strong id="case-total-count">0</strong></article><article class="tree-summary-card"><span>今日新增</span><strong id="case-today-count">0</strong></article><article class="tree-summary-card"><span>复核记录</span><strong id="case-review-total">0</strong></article><article class="tree-summary-card"><span>标签分布</span><strong id="case-tag-total">0</strong></article></div><div class="case-toolbar"><div class="case-toolbar-search"><input id="case-search" class="text-like-input" type="text" placeholder="搜索病例描述、诊断结果或 病例 ID"></div><select id="case-diagnosis-filter"><option value="">全部诊断</option><option value="STEMI">STEMI</option><option value="NSTEMI">NSTEMI</option><option value="UA">UA</option><option value="变异型心绞痛">变异型心绞痛</option><option value="其他">其他</option></select><select id="case-status-filter"><option value="">全部状态</option><option value="completed">已完成</option><option value="needs_more_data">待补充</option><option value="service_unavailable">服务暂停</option></select></div><div id="case-tag-cloud" class="case-tag-cloud"></div><div class="catalog-table-shell"><table class="catalog-table case-table"><thead><tr><th>病例摘要</th><th>诊断 / 状态</th><th>标签</th><th>时间</th><th>操作</th></tr></thead><tbody id="case-table-body"></tbody></table><div id="case-table-empty" class="tree-empty-state" hidden>当前没有匹配的病例记录。</div></div></div></section>
          <section class="app-view" data-view="annotation" hidden><div class="view-container"><div class="view-head"><div><p class="view-kicker">标注复核</p><h1>病例标注与医生复核</h1><p class="view-copy">分析后的病例会自动跳转到这里，集中查看决策路径、知识图谱高亮、病例回放与复核导出。</p></div><div class="view-head-actions"><button id="annotation-open-workspace" class="ghost-button" type="button">回到诊断工作台</button><button id="annotation-run-analysis" class="primary-button" type="button">重新分析当前病例</button></div></div><section class="card annotation-summary-card"><div class="annotation-summary-head"><div><p class="section-kicker">当前病例</p><h2 id="annotation-case-title">尚未选择病例</h2><p id="annotation-case-meta" class="mini-note">可以从病例库选择已有病例，或在诊断工作台完成一次分析后自动进入。</p></div><div class="annotation-summary-stats"><span id="annotation-case-id" class="status-chip">病例 ID -</span><span id="annotation-case-status" class="status-chip">状态待定</span><span id="annotation-case-updated" class="status-chip">更新时间 -</span></div></div><div id="annotation-case-text" class="annotation-case-text">这里会显示当前病例的病历正文或工作台中的输入内容。</div></section><div id="annotation-view-shell" class="page-shell view-shell annotation-shell"></div></div></section>
          <section class="app-view" data-view="workspace" hidden><div id="workspace-view-shell"></div></section>
          <section class="app-view" data-view="profile" hidden><div class="view-container"><div class="view-head"><div><p class="view-kicker">个人中心</p><h1>个人中心与系统状态</h1><p class="view-copy">本地保存登录信息，并汇总当前后端、图谱、病例库与训练数据状态。</p></div></div><div class="profile-grid"><section class="profile-hero-card"><div class="profile-avatar" id="profile-avatar">医</div><div><p class="section-kicker">当前用户</p><h2 id="profile-name">未登录</h2><p id="profile-role" class="mini-note">临床审核</p></div><div class="profile-mini-stats"><article><strong id="profile-case-count">0</strong><span>病例</span></article><article><strong id="profile-review-count">0</strong><span>复核</span></article><article><strong id="profile-training-count">0</strong><span>训练样本</span></article></div></section><section class="profile-card"><div class="inline-head"><h3>资料设置</h3><button id="profile-save" class="primary-button" type="button">保存资料</button></div><div class="tree-form-grid"><label><span>姓名</span><input id="profile-name-input" class="text-like-input" type="text"></label><label><span>手机号</span><input id="profile-phone-input" class="text-like-input" type="text"></label><label><span>科室</span><input id="profile-department-input" class="text-like-input" type="text"></label><label><span>角色</span><input id="profile-role-input" class="text-like-input" type="text"></label></div><p id="profile-save-status" class="mini-note">更改后会保存在浏览器中，用于顶部导航和本地演示会话。</p></section><section class="profile-card"><h3>系统概览</h3><div id="profile-system-list" class="history-list"></div></section><section class="profile-card"><h3>最近动作</h3><div id="profile-activity" class="history-list"></div></section></div></div></section>
        </main>
      </div>
      <div id="case-modal" class="dialog-shell" hidden><div class="dialog-backdrop"></div><div class="dialog-card"><div class="inline-head"><div><p class="section-kicker">新增病例</p><h3>新增病例到病例库</h3></div><button id="close-case-modal" class="ghost-button" type="button">关闭</button></div><div class="tree-form-grid"><label class="tree-form-span"><span>病历描述</span><textarea id="case-modal-description" class="text-input compact-textarea" rows="7"></textarea></label><label><span>初始诊断</span><input id="case-modal-diagnosis" class="text-like-input" type="text" placeholder="可选"></label><label><span>状态</span><select id="case-modal-status"><option value="completed">已完成</option><option value="needs_more_data">待补充</option><option value="service_unavailable">服务暂停</option></select></label><label class="tree-form-span"><span>标签</span><input id="case-modal-tags" class="text-like-input" type="text" placeholder="多个标签请用逗号分隔"></label></div><div class="action-row"><button id="submit-case-modal" class="primary-button" type="button">保存病例</button></div><p id="case-modal-status-text" class="mini-note">保存后将自动刷新病例库列表。</p></div></div>
    `
  );

  const authScreen = document.getElementById("login-screen");
  const appShell = document.getElementById("app-shell");
  const authForm = document.getElementById("auth-form");
  const authModeToggle = document.getElementById("auth-mode-toggle");
  const authModeLabel = document.getElementById("auth-mode-label");
  const authSubtitle = document.getElementById("auth-subtitle");
  const authRegisterFields = Array.from(document.querySelectorAll(".auth-register-only"));
  const navButtons = Array.from(document.querySelectorAll(".shell-nav-button"));
  const viewSections = Array.from(document.querySelectorAll(".app-view"));
  const workspaceHost = document.getElementById("workspace-view-shell");
  const parserHost = document.getElementById("parser-view-shell");
  const annotationHost = document.getElementById("annotation-view-shell");
  const caseModal = document.getElementById("case-modal");

  const hero = pageShell.querySelector(".hero");
  const layout = pageShell.querySelector(".layout");
  const inputSection = document.querySelector("#patient-description")?.closest("section.card");
  const resultSection = document.querySelector("#diagnosis-result")?.closest("section.card");
  const graphSection = document.querySelector("#knowledge-graph")?.closest("section.card");
  const reasoningSection = document.querySelector("#preprocess-summary")?.closest("section.card");
  const trainingSection = document.querySelector("#training-summary")?.closest("section.card");
  const replaySection = document.querySelector("#case-replay-list")?.closest("section.card");
  const mineruSection = document.querySelector("#mineru-title-input")?.closest("section.card");
  const kgSection = document.querySelector("#kg-review-list")?.closest("section.card");
  const mappingSection = layout?.querySelector(".mapping-grid")?.closest("section.card");

  function getStoredUser() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEYS.user) || "null");
    } catch {
      return null;
    }
  }

  function saveStoredUser(user) {
    localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
  }

  function getDefaultUser() {
    return { name: "张医生", phone: "", department: "心血管内科", role: "临床审核专家" };
  }

  function toggleRegisterMode(registerMode) {
    shellState.registerMode = registerMode;
    authRegisterFields.forEach((field) => {
      field.style.display = registerMode ? "block" : "none";
    });
    authModeLabel.textContent = registerMode ? "注册本地会话" : "登录工作台";
    authSubtitle.textContent = registerMode ? "填写本地资料后即可进入工作台。" : "输入手机号和任意密码即可继续。";
    authModeToggle.textContent = registerMode ? "切换到登录模式" : "切换到注册模式";
  }

  function ensureSection(section, host) {
    if (!section || !host) return;
    section.hidden = false;
    host.appendChild(section);
  }

  function organizeLegacySections() {
    if (mappingSection) mappingSection.remove();
    if (reasoningSection) reasoningSection.hidden = false;
    if (trainingSection) trainingSection.hidden = false;
    ensureSection(resultSection, annotationHost);
    ensureSection(graphSection, annotationHost);
    ensureSection(reasoningSection, annotationHost);
    ensureSection(replaySection, annotationHost);
    ensureSection(mineruSection, parserHost);
    ensureSection(kgSection, parserHost);
    ensureSection(trainingSection, parserHost);
    if (layout && inputSection) {
      Array.from(layout.children).forEach((child) => {
        if (child !== inputSection) child.remove();
      });
      if (inputSection.parentElement !== layout) layout.appendChild(inputSection);
    }
    workspaceHost.appendChild(pageShell);
  }

  function getAppState() {
    return typeof state !== "undefined" ? state : null;
  }

  function getDescriptionValue() {
    const el = document.getElementById("patient-description");
    return el ? el.value.trim() : "";
  }

  function setDescriptionValue(text) {
    const el = document.getElementById("patient-description");
    if (el) el.value = text || "";
  }

  function saveActivities() {
    localStorage.setItem(STORAGE_KEYS.activity, JSON.stringify(shellState.activities.slice(0, 10)));
  }

  function pushActivity(text) {
    const timestamp = new Date().toLocaleString("zh-CN", { hour12: false });
    shellState.activities.unshift({ text, timestamp });
    shellState.activities = shellState.activities.slice(0, 10);
    saveActivities();
    renderActivities();
  }

  function renderActivities() {
    const container = document.getElementById("profile-activity");
    if (!container) return;
    if (!shellState.activities.length) {
      container.innerHTML = '<p class="mini-note">这里会记录病例载入、图谱构建、训练准备等最近操作。</p>';
      return;
    }
    container.innerHTML = shellState.activities
      .map((item) => `<article class="history-item"><div><strong>${item.text}</strong><span>${item.timestamp}</span></div></article>`)
      .join("");
  }

  function updateUserUI(user) {
    const currentUser = user || getStoredUser() || getDefaultUser();
    document.getElementById("shell-user-name").textContent = currentUser.name || "本地用户";
    document.getElementById("shell-user-role").textContent = currentUser.role || "临床审核";
    document.getElementById("profile-name").textContent = currentUser.name || "本地用户";
    document.getElementById("profile-role").textContent = `${currentUser.department || "未填写科室"} · ${currentUser.role || "临床审核"}`;
    document.getElementById("profile-avatar").textContent = (currentUser.name || "医").slice(0, 1);
    document.getElementById("profile-name-input").value = currentUser.name || "";
    document.getElementById("profile-phone-input").value = currentUser.phone || "";
    document.getElementById("profile-department-input").value = currentUser.department || "";
    document.getElementById("profile-role-input").value = currentUser.role || "";
    const reviewerInput = document.getElementById("reviewer-name");
    if (reviewerInput && !reviewerInput.value.trim()) reviewerInput.value = currentUser.name || "";
  }

  function renderHealth() {
    const appState = getAppState();
    const online = !!appState?.backendAvailable;
    const statusText = document.getElementById("server-status")?.textContent || (online ? "后端在线" : "后端离线");
    document.getElementById("shell-health-status").textContent = statusText;
    document.getElementById("dashboard-server-chip").textContent = online ? "后端在线" : "后端离线";
  }

  function navigateToView(view) {
    shellState.currentView = view;
    localStorage.setItem(STORAGE_KEYS.view, view);
    viewSections.forEach((section) => {
      const active = section.dataset.view === view;
      section.hidden = !active;
      section.classList.toggle("is-active", active);
    });
    navButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.targetView === view);
    });
  }

  function enterApp(user) {
    saveStoredUser(user);
    localStorage.setItem(STORAGE_KEYS.session, "active");
    authScreen.style.display = "none";
    appShell.hidden = false;
    updateUserUI(user);
    navigateToView(localStorage.getItem(STORAGE_KEYS.view) || "dashboard");
  }

  function leaveApp() {
    localStorage.removeItem(STORAGE_KEYS.session);
    authScreen.style.display = "grid";
    appShell.hidden = true;
    toggleRegisterMode(false);
  }

  function getDepartmentFilters() {
    return ["\u5168\u90e8\u5206\u79d1", ...new Set(SERVICE_LINES.map((item) => item.specialty))];
  }

  function getVisibleServiceLines() {
    if (shellState.departmentFilter === "\u5168\u90e8\u5206\u79d1") return SERVICE_LINES;
    return SERVICE_LINES.filter((item) => item.specialty === shellState.departmentFilter);
  }

  function getServiceLine(workflowId = shellState.activeWorkflowId) {
    return SERVICE_LINES.find((item) => item.workflowId === workflowId) || SERVICE_LINES[0];
  }

  function getWorkflowDefinition(workflowId = shellState.activeWorkflowId) {
    return shellState.workflowDefinitions.find((item) => item.workflow_id === workflowId) || null;
  }

  function getWorkflowConfigPath(workflowId = shellState.activeWorkflowId) {
    return getWorkflowDefinition(workflowId)?.relative_config_path || getServiceLine(workflowId).configPath;
  }

  function getWorkflowStatus(workflowId = shellState.activeWorkflowId) {
    return shellState.workflowStatuses[workflowId] || null;
  }

  function getWorkflowVersionLabel(workflowId = shellState.activeWorkflowId) {
    const workflowStatus = getWorkflowStatus(workflowId);
    if (!workflowStatus?.exists) return getServiceLine(workflowId).status === "live" ? "\u672a\u751f\u6210" : "\u5f85\u7f16\u8f91";
    return workflowStatus.version_info?.graph_version || "\u5df2\u751f\u6210";
  }

  function renderWorkflowSwitcher() {
    const activeLine = getServiceLine();
    const switcher = document.getElementById("workflow-switcher-list");
    const caption = document.getElementById("workflow-editor-caption");
    if (switcher) {
      switcher.innerHTML = SERVICE_LINES.map((line) => `
        <button class="workflow-switcher-button ${line.workflowId === shellState.activeWorkflowId ? "active" : ""}" type="button" data-workflow-switch="${line.workflowId}">
          <strong>${line.name}</strong>
          <span>${line.statusLabel} \u00b7 ${getWorkflowVersionLabel(line.workflowId)}</span>
        </button>`).join("");
    }
    if (caption) {
      caption.textContent = `\u5f53\u524d\u7ef4\u62a4 ${activeLine.workflowName}\uff0c\u914d\u7f6e\u6587\u4ef6\uff1a${getWorkflowConfigPath(activeLine.workflowId)}`;
    }
  }

  function renderDashboard() {
    const appState = getAppState();
    const summary = appState?.trainingStatus?.summary || {};
    const filters = getDepartmentFilters();
    const visibleLines = getVisibleServiceLines();
    const activeLine = getServiceLine();

    document.getElementById("dashboard-case-count").textContent = shellState.caseStats?.total_cases ?? 0;
    document.getElementById("dashboard-review-count").textContent = shellState.caseStats?.total_reviews ?? 0;
    document.getElementById("dashboard-today-count").textContent = shellState.caseStats?.today_cases ?? 0;
    document.getElementById("dashboard-graph-version").textContent = getWorkflowVersionLabel(activeLine.workflowId);
    document.getElementById("dashboard-training-count").textContent = `SFT ${summary.sft_total || 0} / 偏好 ${summary.preference_total || 0}`;
    document.getElementById("dashboard-workflow-name").textContent = shellState.workflowConfig?.workflow_name || activeLine.workflowName;
    document.getElementById("dashboard-active-line-title").textContent = `${activeLine.name}工作区`;
    document.getElementById("dashboard-active-line-copy").textContent = activeLine.summary;

    document.getElementById("dashboard-next-action").textContent = activeLine.status === "live"
      ? appState?.backendAvailable
        ? `\u5f53\u524d\u7b5b\u9009\uff1a${shellState.departmentFilter}\u3002${activeLine.name}\u7ebf\u5df2\u53ef\u76f4\u63a5\u8fdb\u5165\u8bca\u65ad\u3001\u75c5\u4f8b\u590d\u6838\u548c\u56fe\u8c31\u589e\u5f3a\u6d41\u7a0b\uff1b\u8bad\u7ec3\u6837\u672c ${summary.sft_total || 0} / ${summary.preference_total || 0} / ${summary.rl_total || 0}\u3002`
        : `\u5f53\u524d\u7b5b\u9009\uff1a${shellState.departmentFilter}\u3002\u540e\u7aef\u5f53\u524d\u79bb\u7ebf\uff0c\u53ef\u5148\u6d4f\u89c8\u5206\u79d1\u76ee\u5f55\u4e0e\u8def\u5f84\u7ed3\u6784\uff1b\u82e5\u9700\u8fd0\u884c\u8bca\u65ad\u6216\u56fe\u8c31\u589e\u5f3a\uff0c\u8bf7\u6062\u590d\u670d\u52a1\u540e\u7ee7\u7eed\u3002`
      : `\u5f53\u524d\u5df2\u5207\u6362\u5230${activeLine.name}\u7ebf\u3002\u8be5\u7ebf\u7684\u77e5\u8bc6\u56fe\u8c31\u8349\u7a3f\u5df2\u7ecf\u5c31\u4f4d\uff0c\u53ef\u5148\u5728\u8def\u5f84\u7f16\u8f91\u5668\u8865\u5145\u8282\u70b9\u3001\u8f6c\u79fb\u548c\u8bca\u7597\u5206\u652f\u3002`;

    document.getElementById("department-filter-list").innerHTML = filters.map((filter) => `
      <button class="department-filter-button ${shellState.departmentFilter === filter ? "active" : ""}" type="button" data-department-filter="${filter}">${filter}</button>`).join("");

    document.getElementById("service-line-grid").innerHTML = visibleLines.map((line) => `
      <article class="service-line-card ${line.status}">
        <div class="service-line-head">
          <div>
            <p class="service-line-kicker">${line.specialty}</p>
            <h3>${line.name}</h3>
            <p class="service-line-subtitle">${line.enName}</p>
          </div>
          <span class="service-line-status ${line.status}">${line.statusLabel}</span>
        </div>
        <p class="service-line-copy">${line.summary}</p>
        <div class="service-line-tags">${line.departments.map((department) => `<span class="service-tag">${department}</span>`).join("")}</div>
        <div class="service-line-actions">
          <button class="primary-button" type="button" data-go-view="${line.primaryView}" data-workflow-id="${line.workflowId}">${line.primaryActionLabel}</button>
          <button class="ghost-button" type="button" data-go-view="${line.secondaryView}" data-workflow-id="${line.workflowId}">${line.secondaryActionLabel}</button>
          <button class="ghost-button service-filter-button" type="button" data-department-filter="${line.specialty}">\u53ea\u770b\u672c\u4e13\u79d1</button>
        </div>
      </article>`).join("");

    document.getElementById("workflow-catalog-body").innerHTML = visibleLines.map((line) => {
      const workflowName = shellState.workflowConfigs[line.workflowId]?.workflow_name || line.workflowName;
      const versionText = getWorkflowVersionLabel(line.workflowId);
      const actions = line.status === "live"
        ? `<div class="case-row-actions"><button type="button" data-go-view="workspace" data-workflow-id="${line.workflowId}">\u8fdb\u5165\u5de5\u4f5c\u53f0</button><button type="button" data-go-view="tree" data-workflow-id="${line.workflowId}">\u8def\u5f84\u7f16\u8f91</button><button type="button" data-go-view="cases" data-workflow-id="${line.workflowId}">\u67e5\u770b\u75c5\u4f8b</button></div>`
        : `<div class="case-row-actions"><button type="button" data-go-view="tree" data-workflow-id="${line.workflowId}">\u8def\u5f84\u7f16\u8f91</button><button type="button" data-department-filter="${line.specialty}">\u67e5\u770b\u5206\u79d1</button></div>`;
      return `
        <tr>
          <td><strong>${workflowName}</strong><br><span class="mini-note">${line.departments.join(" / ")} \u00b7 ${line.summary}</span></td>
          <td><span class="status-chip service-status ${line.status}">${line.statusLabel}</span></td>
          <td>${versionText}</td>
          <td>${actions}</td>
        </tr>`;
    }).join("");
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || data.message || "请求失败");
    return data;
  }

  function formatCaseStatus(status, fallback = "\u72b6\u6001\u5f85\u5b9a") {
    const labels = {
      completed: "\u5df2\u5b8c\u6210",
      needs_more_data: "\u5f85\u8865\u5145",
      service_unavailable: "\u670d\u52a1\u6682\u505c",
    };
    return labels[status] || status || fallback;
  }

  function formatMethodLabel(method) {
    const labels = {
      step_by_step: "\u9010\u6b65\u5f15\u5bfc",
      all_methods: "\u7efc\u5408\u7b56\u7565",
      direct: "\u76f4\u63a5\u5224\u65ad",
      direct_generation: "\u76f4\u63a5\u751f\u6210",
      intermediate_state: "\u4e2d\u95f4\u72b6\u6001\u63a8\u7406",
      full_workflow: "\u5168\u6d41\u7a0b\u63a8\u7406",
      saved_case: "\u75c5\u4f8b\u56de\u653e",
    };
    return labels[method] || method || "";
  }

  async function loadCaseStats() {
    try {
      const [statsData, tagsData] = await Promise.all([
        requestJson("/api/cases/statistics"),
        requestJson("/api/cases/tags"),
      ]);
      shellState.caseStats = statsData.statistics || null;
      shellState.tags = tagsData.tags || [];
    } catch (error) {
      console.error(error);
    }
  }

  async function loadCases() {
    const search = document.getElementById("case-search")?.value?.trim() || "";
    const diagnosis = document.getElementById("case-diagnosis-filter")?.value || "";
    const status = document.getElementById("case-status-filter")?.value || "";
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (diagnosis) params.set("diagnosis", diagnosis);
    if (status) params.set("status", status);
    params.set("limit", "50");
    try {
      const data = await requestJson(`/api/cases?${params.toString()}`);
      shellState.cases = data.cases || [];
    } catch (error) {
      console.error(error);
      shellState.cases = [];
    }
    renderCaseLibrary();
  }

  function renderCaseLibrary() {
    const body = document.getElementById("case-table-body");
    const empty = document.getElementById("case-table-empty");
    if (!body || !empty) return;
    document.getElementById("case-total-count").textContent = shellState.caseStats?.total_cases ?? 0;
    document.getElementById("case-today-count").textContent = shellState.caseStats?.today_cases ?? 0;
    document.getElementById("case-review-total").textContent = shellState.caseStats?.total_reviews ?? 0;
    document.getElementById("case-tag-total").textContent = shellState.tags.length;
    const tagCloud = document.getElementById("case-tag-cloud");
    if (tagCloud) {
      tagCloud.innerHTML = shellState.tags.map((tag) => `<button class="case-tag" type="button" data-tag="${tag.tag}">${tag.tag} · ${tag.count}</button>`).join("");
    }
    if (!shellState.cases.length) {
      body.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    body.innerHTML = shellState.cases.map((item) => {
      const excerpt = (item.patient_description || "").slice(0, 72);
      const tags = (item.tags || []).map((tag) => `<span class="case-chip">${tag}</span>`).join("") || '<span class="mini-note">无标签</span>';
      return `
        <tr>
          <td><strong>${item.case_id}</strong><br><span class="mini-note">${excerpt}${item.patient_description?.length > 72 ? "..." : ""}</span></td>
          <td><strong>${item.diagnosis || "未记录"}</strong><br><span class="mini-note">${formatCaseStatus(item.status, "\u5df2\u5b8c\u6210")}</span></td>
          <td>${tags}</td>
          <td>${item.updated_at || item.created_at || "-"}</td>
          <td><div class="case-row-actions"><button type="button" data-action="annotate" data-case-id="${item.case_id}">标注复核</button><button type="button" data-action="workspace" data-case-id="${item.case_id}">载入工作台</button><button type="button" data-action="delete" data-case-id="${item.case_id}">删除</button></div></td>
        </tr>`;
    }).join("");
  }

  function updateAnnotationSummary(record) {
    document.getElementById("annotation-case-title").textContent = record?.diagnosis ? `${record.diagnosis} 病例` : "当前分析病例";
    document.getElementById("annotation-case-meta").textContent = record?.method ? `方法：${formatMethodLabel(record.method)} · 模型：${record.model || "gpt-4o-mini"}` : "可从病例库选择已有病例，或在诊断工作台完成一次分析后自动进入。";
    document.getElementById("annotation-case-id").textContent = `病例 ID ${record?.case_id || "-"}`;
    document.getElementById("annotation-case-status").textContent = formatCaseStatus(record?.status);
    document.getElementById("annotation-case-updated").textContent = record?.updated_at || record?.created_at || new Date().toLocaleString("zh-CN", { hour12: false });
    document.getElementById("annotation-case-text").textContent = record?.patient_description || getDescriptionValue() || "这里会显示当前病例的病历正文或工作台中的输入内容。";
  }

  async function openCaseRecord(caseId, mode = "annotation") {
    try {
      const data = await requestJson(`/api/cases/${caseId}`);
      const record = data.case || {};
      shellState.currentCase = record;
      setDescriptionValue(record.patient_description || "");
      const payload = {
        case_id: record.case_id,
        patient_description: record.patient_description,
        diagnosis: record.diagnosis,
        status: record.status,
        model: record.model,
        method: record.method,
        primary_method: record.method || "saved_case",
        graph_path: record.graph_path || { nodes: [], edges: [] },
        intermediate_states: record.intermediate_states || {},
        steps: record.steps || [],
        halt_step: record.halt_step,
        reason: record.halt_reason || "",
        missing_items: record.missing_items || [],
        recommendation: record.recommendation || "",
        diagnosis_path_text: typeof buildResultPathFromDiagnosis === "function" ? buildResultPathFromDiagnosis(record.diagnosis || "") : "",
        confidence_text: record.confidence || `病例记录 · ${record.model || "gpt-4o-mini"}`,
        results: null,
        graph_version_info: getAppState()?.graphVersionInfo || {},
        graph_history: getAppState()?.graphHistory || [],
      };
      const reasons = typeof buildBackendReasons === "function" ? buildBackendReasons(payload) : [`病例 ${record.case_id}`];
      if (typeof renderAnalysisPayload === "function") renderAnalysisPayload(payload, reasons);
      if (Array.isArray(record.reviews) && typeof renderReviewHistory === "function") {
        setTimeout(() => renderReviewHistory(record.reviews), 80);
      }
      updateAnnotationSummary(record);
      pushActivity(`载入病例 ${record.case_id}`);
      navigateToView(mode === "workspace" ? "workspace" : "annotation");
    } catch (error) {
      console.error(error);
      alert(error.message);
    }
  }

  function extractWorkflowLabel(node) {
    const raw = String(node?.content || node?.id || "").replace(/\s+/g, " ").trim();
    const parts = raw.split(/[，,]/).map((item) => item.trim()).filter(Boolean);
    return parts[parts.length - 1] || raw || node?.id || "节点";
  }

  function layoutWorkflow(config) {
    const nodes = config?.nodes || [];
    const transitions = config?.transitions || [];
    const levelMap = Object.fromEntries(nodes.map((node) => [node.id, 0]));
    for (let i = 0; i < nodes.length; i += 1) {
      transitions.forEach((edge) => {
        levelMap[edge.to] = Math.max(levelMap[edge.to] || 0, (levelMap[edge.from] || 0) + 1);
      });
    }
    const groups = {};
    nodes.forEach((node) => {
      const level = levelMap[node.id] || 0;
      groups[level] = groups[level] || [];
      groups[level].push(node);
    });
    const positions = {};
    Object.entries(groups).forEach(([level, items]) => {
      items.forEach((node, index) => {
        positions[node.id] = { x: 140 + Number(level) * 260, y: 90 + index * 140 };
      });
    });
    return positions;
  }

  function renderWorkflowEditor() {
    const config = shellState.workflowConfig;
    if (!config) return;
    const activeLine = getServiceLine();
    renderWorkflowSwitcher();
    document.getElementById("workflow-node-count").textContent = (config.nodes || []).length;
    document.getElementById("workflow-transition-count").textContent = (config.transitions || []).length;
    document.getElementById("workflow-selected-label").textContent = extractWorkflowLabel((config.nodes || []).find((node) => node.id === shellState.selectedNodeId));
    document.getElementById("dashboard-workflow-name").textContent = config.workflow_name || activeLine.workflowName;
    document.getElementById("workflow-node-list").innerHTML = (config.nodes || []).map((node) => `<button class="tree-item ${node.id === shellState.selectedNodeId ? "active" : ""}" type="button" data-node-id="${node.id}">${extractWorkflowLabel(node)}</button>`).join("");
    document.getElementById("workflow-transition-list").innerHTML = (config.transitions || []).map((edge, index) => `<button class="tree-item ${index === shellState.selectedTransitionIndex ? "active" : ""}" type="button" data-transition-index="${index}">${edge.from} \u2192 ${edge.to}${edge.condition ? ` \u00b7 ${edge.condition}` : ""}</button>`).join("");
    const activeNode = (config.nodes || []).find((node) => node.id === shellState.selectedNodeId) || config.nodes?.[0];
    if (activeNode) {
      shellState.selectedNodeId = activeNode.id;
      document.getElementById("workflow-node-id").value = activeNode.id;
      document.getElementById("workflow-node-type").value = activeNode.type || "\u72b6\u6001\u8282\u70b9";
      document.getElementById("workflow-node-content").value = activeNode.content || "";
    }
    const activeTransition = config.transitions?.[shellState.selectedTransitionIndex] || null;
    document.getElementById("workflow-transition-condition").value = activeTransition?.condition || "";
    const positions = layoutWorkflow(config);
    const edges = (config.transitions || []).map((edge, index) => {
      const from = positions[edge.from];
      const to = positions[edge.to];
      if (!from || !to) return "";
      const midX = (from.x + to.x) / 2;
      const midY = (from.y + to.y) / 2;
      return `<g><path d="M ${from.x + 84} ${from.y + 28} C ${midX} ${from.y + 28}, ${midX} ${to.y + 28}, ${to.x} ${to.y + 28}" stroke="${index === shellState.selectedTransitionIndex ? "#0b5fff" : "rgba(17,32,51,0.22)"}" stroke-width="${index === shellState.selectedTransitionIndex ? 3 : 2}" fill="none"></path>${edge.condition ? `<text x="${midX}" y="${midY - 10}" text-anchor="middle" fill="#627286" font-size="12">${edge.condition}</text>` : ""}</g>`;
    }).join("");
    const nodes = (config.nodes || []).map((node) => {
      const pos = positions[node.id] || { x: 0, y: 0 };
      const active = node.id === shellState.selectedNodeId;
      return `<g transform="translate(${pos.x}, ${pos.y})"><rect width="168" height="56" rx="18" fill="${active ? "rgba(11,95,255,0.12)" : "rgba(255,255,255,0.96)"}" stroke="${active ? "#0b5fff" : "rgba(17,32,51,0.16)"}" stroke-width="${active ? 3 : 2}"></rect><text x="16" y="24" fill="#0f6f8f" font-size="11">${node.type || "\u8282\u70b9"}</text><text x="16" y="42" fill="#112033" font-size="14" font-weight="700">${extractWorkflowLabel(node)}</text></g>`;
    }).join("");
    document.getElementById("workflow-canvas").innerHTML = `<svg viewBox="0 0 1200 760" style="width:100%;min-width:960px;height:auto">${edges}${nodes}</svg>`;
  }

  async function loadWorkflowDefinitions() {
    try {
      const data = await requestJson("/api/workflow/configs");
      shellState.workflowDefinitions = data.workflows || [];
    } catch (error) {
      console.error(error);
      shellState.workflowDefinitions = [];
    }
  }

  function syncActiveWorkflowGraphState(workflowId = shellState.activeWorkflowId) {
    if (workflowId !== shellState.activeWorkflowId) return;
    const workflowStatus = getWorkflowStatus(workflowId);
    const appState = getAppState();
    if (appState) {
      appState.graphVersionInfo = workflowStatus?.exists ? (workflowStatus.version_info || {}) : null;
      appState.graphHistory = workflowStatus?.history || [];
    }
    if (typeof renderGraphArtifacts === "function") renderGraphArtifacts(workflowStatus?.exists ? workflowStatus.artifacts || null : null);
    if (typeof renderGraphVersionInfo === "function") renderGraphVersionInfo(workflowStatus?.exists ? workflowStatus.version_info || {} : {}, workflowStatus?.history || []);
  }

  async function loadWorkflowGraphStatus(workflowId = shellState.activeWorkflowId, options = {}) {
    const targetWorkflowId = workflowId || shellState.activeWorkflowId;
    try {
      const data = await requestJson(`/api/knowledge-graph/status?workflow_id=${encodeURIComponent(targetWorkflowId)}`);
      shellState.workflowStatuses[targetWorkflowId] = data;
    } catch (error) {
      console.error(error);
      shellState.workflowStatuses[targetWorkflowId] = { exists: false, version_info: {}, history: [], artifacts: {}, error: error.message };
    }
    if (options.syncAppState !== false) syncActiveWorkflowGraphState(targetWorkflowId);
    renderDashboard();
    return shellState.workflowStatuses[targetWorkflowId];
  }

  async function loadAllWorkflowGraphStatuses() {
    await Promise.all(SERVICE_LINES.map((line) => loadWorkflowGraphStatus(line.workflowId, {
      syncAppState: line.workflowId === shellState.activeWorkflowId,
    })));
  }

  async function loadWorkflowConfig(workflowId = shellState.activeWorkflowId, options = {}) {
    const targetWorkflowId = workflowId || shellState.activeWorkflowId;
    shellState.activeWorkflowId = targetWorkflowId;
    if (!shellState.workflowConfigs[targetWorkflowId] || options.force) {
      try {
        const data = await requestJson(`/api/workflow/config?workflow_id=${encodeURIComponent(targetWorkflowId)}`);
        shellState.workflowConfigs[targetWorkflowId] = data.config;
        if (data.workflow) {
          shellState.workflowDefinitions = [
            ...shellState.workflowDefinitions.filter((item) => item.workflow_id !== data.workflow.workflow_id),
            data.workflow,
          ];
        }
      } catch {
        const response = await fetch(`/${getWorkflowConfigPath(targetWorkflowId)}`);
        shellState.workflowConfigs[targetWorkflowId] = await response.json();
      }
    }
    shellState.workflowConfig = shellState.workflowConfigs[targetWorkflowId];
    shellState.selectedNodeId = shellState.workflowConfig?.nodes?.[0]?.id || null;
    shellState.selectedTransitionIndex = 0;
    document.getElementById("workflow-save-status").textContent = `已加载 ${getWorkflowConfigPath(targetWorkflowId)}`;
    renderWorkflowEditor();
    renderDashboard();
    return shellState.workflowConfig;
  }

  async function activateWorkflow(workflowId, view = shellState.currentView, options = {}) {
    if (!workflowId) return;
    const targetLine = getServiceLine(workflowId);
    shellState.departmentFilter = targetLine.specialty || shellState.departmentFilter;
    await Promise.all([
      loadWorkflowConfig(workflowId, { force: options.forceConfig }),
      loadWorkflowGraphStatus(workflowId, { syncAppState: true }),
    ]);
    renderDashboard();
    renderProfile();
    if (view) navigateToView(view);
  }

  function renderProfile() {
    const stats = shellState.caseStats || {};
    const appState = getAppState();
    const activeLine = getServiceLine();
    const activeStatus = getWorkflowStatus(activeLine.workflowId);
    document.getElementById("profile-case-count").textContent = stats.total_cases ?? 0;
    document.getElementById("profile-review-count").textContent = stats.total_reviews ?? 0;
    document.getElementById("profile-training-count").textContent = appState?.trainingStatus?.summary?.sft_total ?? 0;
    document.getElementById("profile-system-list").innerHTML = [
      `\u540e\u7aef\u670d\u52a1\uff1a${document.getElementById("server-status")?.textContent || "\u68c0\u6d4b\u4e2d"}`,
      `\u5f53\u524d\u6d41\u7a0b\uff1a${shellState.workflowConfig?.workflow_name || activeLine.workflowName}`,
      `\u56fe\u8c31\u7248\u672c\uff1a${activeStatus?.exists ? (activeStatus.version_info?.graph_version || "\u5df2\u751f\u6210") : activeLine.status === "live" ? "\u672a\u751f\u6210" : "\u5f85\u7f16\u8f91"}`,
      `\u8bad\u7ec3\u6570\u636e\uff1aSFT ${appState?.trainingStatus?.summary?.sft_total || 0} / \u504f\u597d ${appState?.trainingStatus?.summary?.preference_total || 0} / RL ${appState?.trainingStatus?.summary?.rl_total || 0}`,
      `\u914d\u7f6e\u6587\u4ef6\uff1a${getWorkflowConfigPath(activeLine.workflowId)}`,
    ].map((item) => `<article class="history-item"><p>${item}</p></article>`).join("");
  }

  async function saveWorkflowConfig() {
    const activeLine = getServiceLine();
    try {
      const data = await requestJson("/api/workflow/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: shellState.activeWorkflowId,
          config: shellState.workflowConfig,
        }),
      });
      shellState.workflowConfigs[shellState.activeWorkflowId] = data.config;
      document.getElementById("workflow-save-status").textContent = `已保存到 ${data.workflow?.relative_config_path || getWorkflowConfigPath(shellState.activeWorkflowId)}`;
      pushActivity(`保存${activeLine.name}知识图谱草稿`);
      renderDashboard();
      renderProfile();
    } catch (error) {
      document.getElementById("workflow-save-status").textContent = error.message;
    }
  }

  async function createCaseFromModal() {
    const description = document.getElementById("case-modal-description").value.trim();
    if (!description) {
      document.getElementById("case-modal-status-text").textContent = "请先填写病历描述。";
      return;
    }
    try {
      const data = await requestJson("/api/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_description: description,
          diagnosis: document.getElementById("case-modal-diagnosis").value.trim(),
          status: document.getElementById("case-modal-status").value,
          model: document.getElementById("model-input")?.value || "gpt-4o-mini",
        }),
      });
      const tags = document.getElementById("case-modal-tags").value.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean);
      await Promise.all(tags.map((tag) => requestJson(`/api/cases/${data.case_id}/tags`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tag }) }).catch(() => null)));
      caseModal.hidden = true;
      document.getElementById("case-modal-description").value = "";
      document.getElementById("case-modal-diagnosis").value = "";
      document.getElementById("case-modal-tags").value = "";
      document.getElementById("case-modal-status-text").textContent = "保存后将自动刷新病例库列表。";
      pushActivity(`新增病例 ${data.case_id}`);
      await Promise.all([loadCaseStats(), loadCases()]);
      renderDashboard();
      renderProfile();
    } catch (error) {
      document.getElementById("case-modal-status-text").textContent = error.message;
    }
  }

  organizeLegacySections();
  toggleRegisterMode(false);
  try {
    shellState.activities = JSON.parse(localStorage.getItem(STORAGE_KEYS.activity) || "[]");
    if (!Array.isArray(shellState.activities)) shellState.activities = [];
  } catch {
    shellState.activities = [];
  }
  renderActivities();

  authModeToggle.addEventListener("click", () => toggleRegisterMode(!shellState.registerMode));
  authForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const existing = getStoredUser() || getDefaultUser();
    const user = {
      name: document.getElementById("auth-name").value.trim() || existing.name || "张医生",
      phone: document.getElementById("auth-phone").value.trim() || existing.phone || "",
      department: document.getElementById("auth-department").value.trim() || existing.department || "心血管内科",
      role: document.getElementById("auth-role").value.trim() || existing.role || "临床审核专家",
    };
    enterApp(user);
    pushActivity(shellState.registerMode ? "注册并进入工作台" : "登录工作台");
  });
  document.getElementById("shell-logout").addEventListener("click", leaveApp);
  navButtons.forEach((button) => button.addEventListener("click", () => navigateToView(button.dataset.targetView)));
  document.addEventListener("click", async (event) => {
    const workflowSwitch = event.target.closest("[data-workflow-switch]");
    if (workflowSwitch) {
      await activateWorkflow(workflowSwitch.dataset.workflowSwitch, "tree");
      return;
    }
    const goButton = event.target.closest("[data-go-view]");
    if (goButton) {
      const workflowId = goButton.dataset.workflowId;
      if (workflowId) {
        await activateWorkflow(workflowId, goButton.dataset.goView);
      } else {
        navigateToView(goButton.dataset.goView);
      }
      return;
    }
    const departmentButton = event.target.closest("[data-department-filter]");
    if (departmentButton) {
      shellState.departmentFilter = departmentButton.dataset.departmentFilter;
      renderDashboard();
      return;
    }
    const nodeButton = event.target.closest("[data-node-id]");
    if (nodeButton) { shellState.selectedNodeId = nodeButton.dataset.nodeId; renderWorkflowEditor(); return; }
    const transitionButton = event.target.closest("[data-transition-index]");
    if (transitionButton) { shellState.selectedTransitionIndex = Number(transitionButton.dataset.transitionIndex); renderWorkflowEditor(); return; }
    const caseAction = event.target.closest("[data-action]");
    if (caseAction) {
      const caseId = caseAction.dataset.caseId;
      if (caseAction.dataset.action === "annotate") openCaseRecord(caseId, "annotation");
      if (caseAction.dataset.action === "workspace") openCaseRecord(caseId, "workspace");
      if (caseAction.dataset.action === "delete" && window.confirm("确认删除该病例吗？")) {
        requestJson(`/api/cases/${caseId}`, { method: "DELETE" }).then(async () => {
          pushActivity(`删除病例 ${caseId}`);
          await Promise.all([loadCaseStats(), loadCases()]);
          renderDashboard();
          renderProfile();
        }).catch((error) => alert(error.message));
      }
      return;
    }
    const tagButton = event.target.closest("[data-tag]");
    if (tagButton) {
      document.getElementById("case-search").value = tagButton.dataset.tag;
      loadCases();
    }
  });

  document.getElementById("annotation-open-workspace").addEventListener("click", () => navigateToView("workspace"));
  document.getElementById("annotation-run-analysis").addEventListener("click", () => { navigateToView("workspace"); if (typeof runDiagnosis === "function") runDiagnosis(); });
  document.getElementById("open-case-modal").addEventListener("click", () => { caseModal.hidden = false; });
  document.getElementById("close-case-modal").addEventListener("click", () => { caseModal.hidden = true; });
  document.getElementById("submit-case-modal").addEventListener("click", createCaseFromModal);
  document.getElementById("case-refresh").addEventListener("click", async () => { await Promise.all([loadCaseStats(), loadCases()]); renderDashboard(); renderProfile(); });
  document.getElementById("case-search").addEventListener("input", loadCases);
  document.getElementById("case-diagnosis-filter").addEventListener("change", loadCases);
  document.getElementById("case-status-filter").addEventListener("change", loadCases);
  document.getElementById("profile-save").addEventListener("click", () => {
    const user = {
      name: document.getElementById("profile-name-input").value.trim() || "张医生",
      phone: document.getElementById("profile-phone-input").value.trim(),
      department: document.getElementById("profile-department-input").value.trim() || "心血管内科",
      role: document.getElementById("profile-role-input").value.trim() || "临床审核专家",
    };
    saveStoredUser(user);
    updateUserUI(user);
    document.getElementById("profile-save-status").textContent = "本地资料已保存。";
    pushActivity("更新个人资料");
  });
  document.getElementById("workflow-node-content").addEventListener("input", (event) => {
    const node = shellState.workflowConfig?.nodes?.find((item) => item.id === shellState.selectedNodeId);
    if (node) node.content = event.target.value;
    renderWorkflowEditor();
  });
  document.getElementById("workflow-node-type").addEventListener("change", (event) => {
    const node = shellState.workflowConfig?.nodes?.find((item) => item.id === shellState.selectedNodeId);
    if (node) node.type = event.target.value;
    renderWorkflowEditor();
  });
  document.getElementById("workflow-transition-condition").addEventListener("input", (event) => {
    const edge = shellState.workflowConfig?.transitions?.[shellState.selectedTransitionIndex];
    if (edge) edge.condition = event.target.value;
    renderWorkflowEditor();
  });
  document.getElementById("workflow-add-node").addEventListener("click", () => {
    const node = { id: `node_${Date.now()}`, type: "状态节点", content: "新节点" };
    shellState.workflowConfig.nodes.push(node);
    shellState.selectedNodeId = node.id;
    renderWorkflowEditor();
  });
  document.getElementById("workflow-delete-node").addEventListener("click", () => {
    shellState.workflowConfig.nodes = shellState.workflowConfig.nodes.filter((item) => item.id !== shellState.selectedNodeId);
    shellState.workflowConfig.transitions = shellState.workflowConfig.transitions.filter((edge) => edge.from !== shellState.selectedNodeId && edge.to !== shellState.selectedNodeId);
    shellState.selectedNodeId = shellState.workflowConfig.nodes?.[0]?.id || null;
    renderWorkflowEditor();
  });
  document.getElementById("workflow-add-transition").addEventListener("click", () => {
    const nodes = shellState.workflowConfig.nodes || [];
    if (nodes.length < 2) return;
    const from = shellState.selectedNodeId || nodes[0].id;
    const to = nodes.find((item) => item.id !== from)?.id || nodes[0].id;
    shellState.workflowConfig.transitions.push({ from, to, condition: "" });
    shellState.selectedTransitionIndex = shellState.workflowConfig.transitions.length - 1;
    renderWorkflowEditor();
  });
  document.getElementById("workflow-delete-transition").addEventListener("click", () => {
    shellState.workflowConfig.transitions.splice(shellState.selectedTransitionIndex, 1);
    shellState.selectedTransitionIndex = Math.max(0, shellState.selectedTransitionIndex - 1);
    renderWorkflowEditor();
  });
  document.getElementById("workflow-editor-save").addEventListener("click", saveWorkflowConfig);
  document.getElementById("workflow-editor-reset").addEventListener("click", () => loadWorkflowConfig(shellState.activeWorkflowId, { force: true }));
  document.getElementById("workflow-editor-export").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(shellState.workflowConfig, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${shellState.activeWorkflowId}-workflow-draft.json`;
    link.click();
    URL.revokeObjectURL(url);
  });

  if (typeof runDiagnosis === "function") {
    const originalRunDiagnosis = runDiagnosis;
    runDiagnosis = async function (...args) {
      const value = await originalRunDiagnosis.apply(this, args);
      const appState = getAppState();
      if (appState?.lastResult) {
        shellState.currentCase = appState.lastResult;
        updateAnnotationSummary({ ...appState.lastResult, updated_at: new Date().toLocaleString("zh-CN", { hour12: false }) });
        navigateToView("annotation");
        pushActivity(`完成诊断分析 ${appState.lastResult.case_id || "frontend"}`);
      }
      await Promise.all([loadCaseStats(), loadCases()]);
      renderHealth();
      renderDashboard();
      renderProfile();
      return value;
    };
  }

  if (typeof saveDoctorReview === "function") {
    const originalSaveDoctorReview = saveDoctorReview;
    saveDoctorReview = async function (...args) {
      const value = await originalSaveDoctorReview.apply(this, args);
      await Promise.all([loadCaseStats(), loadCases()]);
      renderDashboard();
      renderProfile();
      pushActivity("保存医生复核");
      return value;
    };
  }

  if (typeof loadKnowledgeGraphStatus === "function") {
    loadKnowledgeGraphStatus = async function (...args) {
      return loadWorkflowGraphStatus(shellState.activeWorkflowId, { syncAppState: true });
    };
  }

  if (typeof buildBaseKnowledgeGraph === "function") {
    buildBaseKnowledgeGraph = async function (...args) {
      const graphBuildStatusEl = document.getElementById("graph-build-status");
      if (graphBuildStatusEl) graphBuildStatusEl.textContent = "正在生成基础知识图谱...";
      const response = await fetch(`/api/knowledge-graph/build?workflow_id=${encodeURIComponent(shellState.activeWorkflowId)}`);
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "基础知识图谱生成失败");
      }
      shellState.workflowStatuses[shellState.activeWorkflowId] = data;
      syncActiveWorkflowGraphState(shellState.activeWorkflowId);
      if (graphBuildStatusEl) graphBuildStatusEl.textContent = data.message;
      renderDashboard();
      renderProfile();
      pushActivity(`生成${getServiceLine().name}基础知识图谱`);
      return data;
    };
  }

  if (typeof ingestMineruKnowledgeGraph === "function") {
    ingestMineruKnowledgeGraph = async function (...args) {
      const rawPayload = mineruPayloadInput.value.trim();
      if (!rawPayload) {
        throw new Error("请先粘贴 MinerU 解析结果");
      }
      let mineruPayload;
      try {
        mineruPayload = JSON.parse(rawPayload);
      } catch {
        mineruPayload = { markdown: rawPayload };
      }
      graphBuildStatus.textContent = "正在合并 MinerU 文档结果...";
      const response = await fetch("/api/knowledge-graph/mineru-ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          workflow_id: shellState.activeWorkflowId,
          title: mineruTitleInput.value.trim(),
          mineru_payload: mineruPayload,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "MinerU 图谱合并失败");
      }
      shellState.workflowStatuses[shellState.activeWorkflowId] = data;
      syncActiveWorkflowGraphState(shellState.activeWorkflowId);
      graphBuildStatus.textContent = data.message;
      renderDashboard();
      renderProfile();
      pushActivity(`??${getServiceLine().name} MinerU ??`);
      return data;
    };
  }

  updateUserUI(getStoredUser() || getDefaultUser());
  renderHealth();
  Promise.all([loadCaseStats(), loadCases(), loadWorkflowDefinitions(), loadWorkflowConfig()]).then(async () => {
    await loadAllWorkflowGraphStatuses();
    renderDashboard();
    renderProfile();
  });
  if (localStorage.getItem(STORAGE_KEYS.session) === "active") {
    enterApp(getStoredUser() || getDefaultUser());
  }
})();
