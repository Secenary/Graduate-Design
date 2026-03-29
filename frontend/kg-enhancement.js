(() => {
  const mineruTokenInput = document.querySelector("#mineru-token-input");
  const mineruTitleInput = document.querySelector("#mineru-title-input");
  const mineruModelVersionSelect = document.querySelector("#mineru-model-version");
  const mineruLanguageInput = document.querySelector("#mineru-language-input");
  const mineruPageRangesInput = document.querySelector("#mineru-page-ranges-input");
  const mineruEnableFormulaCheckbox = document.querySelector("#mineru-enable-formula");
  const mineruEnableTableCheckbox = document.querySelector("#mineru-enable-table");
  const mineruIsOcrCheckbox = document.querySelector("#mineru-is-ocr");
  const mineruNoCacheCheckbox = document.querySelector("#mineru-no-cache");
  const mineruSourceUrlInput = document.querySelector("#mineru-source-url-input");
  const mineruFileInput = document.querySelector("#mineru-file-input");
  const parseMineruUrlButton = document.querySelector("#parse-mineru-url");
  const parseMineruFileButton = document.querySelector("#parse-mineru-file");
  const graphBuildStatus = document.querySelector("#graph-build-status");
  const mineruResultMeta = document.querySelector("#mineru-result-meta");

  const kgReviewerNameInput = document.querySelector("#kg-reviewer-name-input");
  const kgCaseDirInput = document.querySelector("#kg-case-dir-input");
  const kgFilterCategory = document.querySelector("#kg-filter-category");
  const kgFilterStatus = document.querySelector("#kg-filter-status");
  const kgFilterConfidence = document.querySelector("#kg-filter-confidence");
  const kgEnhancementStatus = document.querySelector("#kg-enhancement-status");
  const kgReviewList = document.querySelector("#kg-review-list");
  const kgReviewCount = document.querySelector("#kg-review-count");
  const kgExportLink = document.querySelector("#kg-export-link");
  const refreshKgButton = document.querySelector("#refresh-kg-enhancement");
  const extractKgTermsButton = document.querySelector("#extract-kg-terms");
  const mergeKgTermsButton = document.querySelector("#merge-kg-terms");
  const kgBatchApproveButton = document.querySelector("#kg-batch-approve");
  const kgStatTerms = document.querySelector("#kg-stat-terms");
  const kgStatGroups = document.querySelector("#kg-stat-groups");
  const kgStatApproved = document.querySelector("#kg-stat-approved");
  const kgStatEntities = document.querySelector("#kg-stat-entities");
  const kgPreviewBadge = document.querySelector("#kg-preview-badge");
  const kgPreviewSummary = document.querySelector("#kg-preview-summary");
  const kgGraphCanvas = document.querySelector("#kg-graph-canvas");
  const kgPreviewSelection = document.querySelector("#kg-preview-selection");
  const kgPreviewRelations = document.querySelector("#kg-preview-relations");

  if (!mineruTokenInput || !kgReviewList || !kgGraphCanvas) {
    return;
  }

  const STORAGE_KEYS = {
    mineruToken: "fuwai_mineru_token",
    kgReviewerName: "fuwai_kg_reviewer_name",
  };

  const state = {
    reviewItems: [],
    filteredItems: [],
    selectedGroupKey: "",
    graphSnapshot: null,
    manualWorkflowDrafts: {},
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeText(value) {
    return String(value ?? "")
      .toLowerCase()
      .replace(/[\s/_\-()（）,:：]+/g, "");
  }

  function truncateText(value, max = 34) {
    const text = String(value ?? "").trim();
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  }

  function getNodeOrder(nodeId) {
    const match = String(nodeId || "").match(/node_(\d+)/);
    return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
  }

  function entityTypeLabel(entityType) {
    return {
      workflow: "工作流",
      workflow_node: "流程节点",
      symptom: "症状",
      finding: "临床发现",
      exam: "检查",
      diagnosis: "诊断",
      document: "文档",
      concept: "概念",
    }[entityType] || entityType;
  }

  function setGraphStatus(message, meta = "") {
    graphBuildStatus.textContent = message;
    mineruResultMeta.textContent = meta;
  }

  function setKgStatus(message) {
    kgEnhancementStatus.textContent = message;
  }

  function persistInputs() {
    mineruTokenInput.value = localStorage.getItem(STORAGE_KEYS.mineruToken) || "";
    kgReviewerNameInput.value = localStorage.getItem(STORAGE_KEYS.kgReviewerName) || "";

    mineruTokenInput.addEventListener("change", () => {
      localStorage.setItem(STORAGE_KEYS.mineruToken, mineruTokenInput.value.trim());
    });

    kgReviewerNameInput.addEventListener("change", () => {
      localStorage.setItem(STORAGE_KEYS.kgReviewerName, kgReviewerNameInput.value.trim());
    });
  }

  function collectMineruOptions() {
    return {
      token: mineruTokenInput.value.trim(),
      title: mineruTitleInput.value.trim(),
      model_version: mineruModelVersionSelect.value,
      language: mineruLanguageInput.value.trim() || "ch",
      page_ranges: mineruPageRangesInput.value.trim(),
      enable_formula: mineruEnableFormulaCheckbox.checked,
      enable_table: mineruEnableTableCheckbox.checked,
      is_ocr: mineruIsOcrCheckbox.checked,
      no_cache: mineruNoCacheCheckbox.checked,
    };
  }

  function buildMineruMeta(data) {
    const job = data.mineru_job || {};
    const summary = data.mineru_payload_summary || {};
    const parts = [];

    if (job.task_id) parts.push(`任务编号：${job.task_id}`);
    if (job.batch_id) parts.push(`批次编号：${job.batch_id}`);
    if (job.full_zip_url) parts.push("结果压缩包已生成");
    if (summary.markdown_chars) parts.push(`Markdown 文本 ${summary.markdown_chars} 字`);
    if (summary.content_blocks) parts.push(`内容块 ${summary.content_blocks}`);
    if (summary.archive_file_count) parts.push(`压缩包文件数 ${summary.archive_file_count}`);

    return parts.join(" | ");
  }

  async function refreshGraphStatus() {
    if (typeof loadKnowledgeGraphStatus === "function") {
      try {
        await loadKnowledgeGraphStatus();
      } catch {
        // Keep UI responsive even if graph status reload fails.
      }
    }
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({ ok: false, error: `请求失败：${response.status}` }));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `请求失败：${response.status}`);
    }
    return data;
  }

  async function importMineruByUrl() {
    const sourceUrl = mineruSourceUrlInput.value.trim();
    const options = collectMineruOptions();

    if (!sourceUrl) {
      throw new Error("请先填写远程文档链接。");
    }
    if (!options.token) {
      throw new Error("请先填写 MinerU 令牌，或在服务端配置 MINERU_API_TOKEN。");
    }

    setGraphStatus("正在调用 MinerU v4 解析远程文档并合并图谱...");
    const data = await requestJson("/api/knowledge-graph/mineru-url", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...options,
        url: sourceUrl,
      }),
    });

    setGraphStatus(data.message || "已完成 MinerU 远程文档解析。", buildMineruMeta(data));
    await refreshGraphStatus();
    await loadKgEnhancementStatus();
    await loadKgGraphSnapshot();
  }

  async function importMineruByFile() {
    const file = mineruFileInput.files?.[0];
    const options = collectMineruOptions();

    if (!file) {
      throw new Error("请先选择需要上传到 MinerU 的文件。");
    }
    if (!options.token) {
      throw new Error("请先填写 MinerU 令牌，或在服务端配置 MINERU_API_TOKEN。");
    }

    const formData = new FormData();
    formData.append("file", file);
    Object.entries(options).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) {
        formData.append(key, String(value));
      }
    });

    setGraphStatus("正在上传文件到 MinerU v4 并解析后合并图谱...");
    const data = await requestJson("/api/knowledge-graph/mineru-file", {
      method: "POST",
      body: formData,
    });

    setGraphStatus(data.message || "已完成 MinerU 文件解析。", buildMineruMeta(data));
    await refreshGraphStatus();
    await loadKgEnhancementStatus();
    await loadKgGraphSnapshot();
  }

  function getCategoryLabel(category) {
    return {
      symptom: "症状",
      finding: "临床发现",
      exam: "检查",
      diagnosis: "诊断",
    }[category] || category;
  }

  function getStatusLabel(status) {
    return {
      pending: "待审核",
      approved: "已通过",
      rejected: "已拒绝",
    }[status] || status;
  }

  function setSelectedGroup(groupKey) {
    state.selectedGroupKey = groupKey || "";
    renderKgReviewItems();
    renderKgPreview();
  }

  function ensureSelectedGroup() {
    if (!state.filteredItems.length) {
      state.selectedGroupKey = "";
      return;
    }

    const stillVisible = state.filteredItems.some((item) => item.group_key === state.selectedGroupKey);
    if (!stillVisible) {
      state.selectedGroupKey = state.filteredItems[0].group_key;
    }
  }

  function getSelectedItem() {
    ensureSelectedGroup();
    return state.filteredItems.find((item) => item.group_key === state.selectedGroupKey) || null;
  }

  function normalizeWorkflowNodeIds(nodeIds) {
    return [...new Set((Array.isArray(nodeIds) ? nodeIds : [])
      .map((nodeId) => String(nodeId || "").trim())
      .filter(Boolean))]
      .sort((left, right) => {
        const orderDiff = getNodeOrder(left) - getNodeOrder(right);
        return orderDiff || left.localeCompare(right, "zh-CN");
      });
  }

  function workflowNodeListEquals(left, right) {
    const normalizedLeft = normalizeWorkflowNodeIds(left);
    const normalizedRight = normalizeWorkflowNodeIds(right);
    return normalizedLeft.length === normalizedRight.length
      && normalizedLeft.every((nodeId, index) => nodeId === normalizedRight[index]);
  }

  function getSavedWorkflowNodeIds(item) {
    return normalizeWorkflowNodeIds(item?.manual_workflow_node_ids || []);
  }

  function hasWorkflowNodeDraft(groupKey) {
    return Object.prototype.hasOwnProperty.call(state.manualWorkflowDrafts, groupKey);
  }

  function getWorkflowNodeDraft(groupKey) {
    return hasWorkflowNodeDraft(groupKey)
      ? normalizeWorkflowNodeIds(state.manualWorkflowDrafts[groupKey])
      : null;
  }

  function setWorkflowNodeDraft(groupKey, nodeIds) {
    if (!groupKey) {
      return;
    }
    state.manualWorkflowDrafts[groupKey] = normalizeWorkflowNodeIds(nodeIds);
  }

  function clearWorkflowNodeDraft(groupKey) {
    if (!groupKey) {
      return;
    }
    delete state.manualWorkflowDrafts[groupKey];
  }

  function getEditableWorkflowNodeIds(item, fallbackNodeIds = []) {
    if (!item) {
      return [];
    }

    const draft = getWorkflowNodeDraft(item.group_key);
    if (draft !== null) {
      return draft;
    }

    const saved = getSavedWorkflowNodeIds(item);
    return saved.length ? saved : normalizeWorkflowNodeIds(fallbackNodeIds);
  }

  function hasWorkflowNodeDraftChanges(item) {
    if (!item) {
      return false;
    }

    const draft = getWorkflowNodeDraft(item.group_key);
    if (draft === null) {
      return false;
    }

    return !workflowNodeListEquals(draft, getSavedWorkflowNodeIds(item));
  }

  function updateKgStats(statusData = null) {
    if (statusData) {
      kgStatTerms.textContent = String(statusData.extracted_terms_count || 0);
      kgStatGroups.textContent = String(statusData.review_items_count ?? state.reviewItems.length ?? 0);
      kgStatApproved.textContent = String(statusData.approved_groups_count ?? state.reviewItems.filter((item) => item.review_status === "approved").length);
      kgStatEntities.textContent = String(statusData.entity_count || 0);
    } else {
      kgStatGroups.textContent = String(state.reviewItems.length);
      kgStatApproved.textContent = String(state.reviewItems.filter((item) => item.review_status === "approved").length);
    }
  }

  async function loadKgEnhancementStatus() {
    try {
      const data = await requestJson("/api/kg-enhancement/status", { method: "GET" });
      updateKgStats(data);
      setKgStatus(data.kg_loaded ? "已连接到当前最新知识图谱，可继续抽取、审核与合并。" : "当前还没有可用图谱，请先生成基础图谱或导入 MinerU 文档。");
      return data;
    } catch (error) {
      setKgStatus(error.message);
      return null;
    }
  }

  async function loadKgGraphSnapshot() {
    try {
      const data = await requestJson("/api/kg-enhancement/graph-snapshot", { method: "GET" });
      state.graphSnapshot = data.graph || null;
      renderKgPreview();
      return state.graphSnapshot;
    } catch (error) {
      state.graphSnapshot = null;
      renderKgPreview(error.message || String(error));
      return null;
    }
  }

  async function loadKgReviewItems() {
    try {
      const data = await requestJson("/api/kg-enhancement/review-items", { method: "GET" });
      state.reviewItems = data.review_items || [];
      updateKgStats();
      applyKgFilters();
    } catch (error) {
      kgReviewList.innerHTML = `<div class="kg-empty-state">${escapeHtml(error.message)}</div>`;
      kgReviewCount.textContent = "0 / 0 组";
      renderKgPreview(error.message || String(error));
    }
  }

  function applyKgFilters() {
    const category = kgFilterCategory.value;
    const status = kgFilterStatus.value;
    const confidence = kgFilterConfidence.value;

    state.filteredItems = state.reviewItems.filter((item) => {
      if (category !== "all" && item.category !== category) {
        return false;
      }
      if (status !== "all" && item.review_status !== status) {
        return false;
      }

      const score = Number(item.match_confidence || 0);
      if (confidence === "high" && score < 0.8) return false;
      if (confidence === "medium" && (score < 0.6 || score >= 0.8)) return false;
      if (confidence === "low" && score >= 0.6) return false;
      return true;
    });

    ensureSelectedGroup();
    renderKgReviewItems();
    renderKgPreview();
  }
  function renderKgReviewItems() {
    const items = state.filteredItems;
    kgReviewCount.textContent = `${items.length} / ${state.reviewItems.length} \u7ec4`;

    if (!items.length) {
      kgReviewList.innerHTML = '<div class="kg-empty-state">\u6ca1\u6709\u7b26\u5408\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u7684\u5f85\u5ba1\u6838\u9879\u3002</div>';
      return;
    }

    kgReviewList.innerHTML = items.map((item) => {
      const encodedKey = encodeURIComponent(item.group_key);
      const context = item.contexts?.[0] || "";
      const confidenceText = item.match_confidence ? `\u5339\u914d ${(Number(item.match_confidence) * 100).toFixed(0)}%` : "\u6682\u65e0\u5339\u914d\u5b9e\u4f53";
      const isSelected = item.group_key === state.selectedGroupKey;
      const manualMatchCount = getSavedWorkflowNodeIds(item).length;
      return `
        <article class="kg-review-card ${isSelected ? "selected" : ""}" data-group-card="${encodedKey}">
          <div class="kg-review-head">
            <div>
              <span class="term-badge ${escapeHtml(item.category)}">${escapeHtml(getCategoryLabel(item.category))}</span>
              <strong style="margin-left: 12px; font-size: 1rem;">${escapeHtml(item.representative_term)}</strong>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end;">
              ${isSelected ? '<span class="kg-selected-flag">\u9884\u89c8\u4e2d</span>' : ""}
              <span class="kg-status-badge ${escapeHtml(item.review_status)}">${escapeHtml(getStatusLabel(item.review_status))}</span>
            </div>
          </div>

          <div class="kg-meta-row">
            <span>\u9891\u6b21 ${escapeHtml(item.total_frequency)}</span>
            <span>${escapeHtml(confidenceText)}</span>
            ${item.matched_entity_id ? `<span>\u5b9e\u4f53 ${escapeHtml(item.matched_entity_id)}</span>` : ""}
            ${manualMatchCount ? `<span>\u624b\u52a8\u8282\u70b9 ${escapeHtml(manualMatchCount)}</span>` : ""}
          </div>

          <div class="kg-variation-list">
            ${(item.variations || []).map((variation) => `<span class="kg-variation-tag">${escapeHtml(variation)}</span>`).join("")}
          </div>

          ${context ? `<div class="kg-context-box">${escapeHtml(context)}</div>` : ""}

          <label class="field-label" style="margin-top: 14px;" for="kg-comment-${encodedKey}">\u5ba1\u6838\u5907\u6ce8</label>
          <input id="kg-comment-${encodedKey}" data-comment-key="${encodedKey}" class="text-like-input" type="text" value="${escapeHtml(item.review_comment || "")}" placeholder="\u53ef\u9009\u5ba1\u6838\u5907\u6ce8">

          <div class="kg-review-actions">
            <button class="ghost-button" type="button" data-kg-preview="${encodedKey}">\u9884\u89c8</button>
            <button class="primary-button" type="button" data-kg-action="approve" data-group-key="${encodedKey}">\u901a\u8fc7</button>
            <button class="secondary-button" type="button" data-kg-action="reject" data-group-key="${encodedKey}">\u9a73\u56de</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderDetailList(container, items, emptyText) {
    if (!container) {
      return;
    }

    container.innerHTML = items.length
      ? items.map((item) => `
          <article class="kg-detail-item">
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.value)}</p>
          </article>
        `).join("")
      : `<div class="kg-empty-state">${escapeHtml(emptyText)}</div>`;
  }

  function describeWorkflowNode(node) {
    if (!node) {
      return "";
    }

    const title = String(node.name || node.id || "").replace(/^node_\d+\s*/, "").trim();
    const detail = node.properties?.content || node.content || node.description || "";
    return detail ? `${title} | ${detail}` : title;
  }

  function buildManualMatchPanel(manualMatch) {
    if (!manualMatch || !manualMatch.item) {
      return "";
    }

    const selectedNodes = manualMatch.selectedNodes || [];
    const selectedNodeIds = new Set(selectedNodes.map((node) => node.id));
    const suggestedNodes = (manualMatch.inferredNodes || []).filter((node) => !selectedNodeIds.has(node.id));
    const statusText = manualMatch.isDirty
      ? "\u672a\u4fdd\u5b58"
      : manualMatch.hasSavedManualMapping
        ? "\u5df2\u4fdd\u5b58"
        : selectedNodes.length
          ? "\u53ef\u4fdd\u5b58"
          : "\u672a\u8bbe\u7f6e";

    return `
      <article class="kg-manual-match-panel">
        <div class="kg-manual-match-head">
          <strong>\u624b\u52a8\u6d41\u7a0b\u5339\u914d</strong>
          <span class="kg-manual-match-status ${manualMatch.isDirty ? "dirty" : manualMatch.hasSavedManualMapping ? "saved" : ""}">${escapeHtml(statusText)}</span>
        </div>
        <p class="mini-note">\u70b9\u51fb\u4e0a\u65b9\u6d41\u7a0b\u56fe\u8282\u70b9\u5373\u53ef\u6dfb\u52a0\u6216\u79fb\u9664\u5339\u914d\u3002\u4fdd\u5b58\u540e\uff0c\u8fd9\u4e9b\u624b\u52a8\u5339\u914d\u4f1a\u5728\u672f\u8bed\u5408\u5e76\u65f6\u56de\u5199\u5230\u77e5\u8bc6\u56fe\u8c31\u3002</p>
        <div class="kg-manual-match-chip-list">
          ${selectedNodes.length
            ? selectedNodes.map((node) => `<span class="kg-node-chip" title="${escapeHtml(describeWorkflowNode(node))}">${escapeHtml(String(node.name || node.id || "").replace(/^node_\d+\s*/, ""))}</span>`).join("")
            : '<span class="kg-node-chip empty">\u5c1a\u672a\u9009\u62e9\u6d41\u7a0b\u8282\u70b9</span>'}
        </div>
        ${suggestedNodes.length
          ? `<p class="kg-manual-match-hint">\u7cfb\u7edf\u5efa\u8bae\uff1a${escapeHtml(suggestedNodes.map((node) => String(node.name || node.id || "").replace(/^node_\d+\s*/, "")).join(", "))}</p>`
          : ""}
        <div class="kg-manual-match-actions">
          <button class="primary-button" type="button" data-kg-save-workflow-match ${manualMatch.canSave ? "" : "disabled"}>\u4fdd\u5b58\u6d41\u7a0b\u5339\u914d</button>
          <button class="ghost-button" type="button" data-kg-reset-workflow-match ${manualMatch.isDirty ? "" : "disabled"}>\u91cd\u7f6e</button>
          <button class="secondary-button" type="button" data-kg-clear-workflow-match ${selectedNodes.length ? "" : "disabled"}>\u6e05\u7a7a</button>
        </div>
      </article>
    `;
  }

  function renderSelectionPane(model) {
    renderDetailList(kgPreviewSelection, model.selectionDetails, "\u6682\u65e0\u660e\u7ec6\u3002");
    if (!model.item) {
      return;
    }

    kgPreviewSelection.insertAdjacentHTML("beforeend", buildManualMatchPanel(model.manualMatch));
  }

  function buildGraphIndex(snapshot) {
    const entities = snapshot?.entities || [];
    const relations = snapshot?.relations || [];
    return {
      entities,
      relations,
      entitiesById: new Map(entities.map((entity) => [entity.id, entity])),
      workflowNodes: entities
        .filter((entity) => entity.entity_type === "workflow_node")
        .sort((left, right) => getNodeOrder(left.id) - getNodeOrder(right.id)),
      transitions: relations.filter((relation) => relation.relation_type === "transitions_to"),
      mentions: relations.filter((relation) => relation.relation_type === "mentions"),
    };
  }

  function scoreEntityMatch(entity, item) {
    if (!entity || entity.entity_type === "workflow_node" || entity.entity_type === "workflow") {
      return 0;
    }

    const candidateTexts = [item.representative_term, ...(item.variations || [])].map(normalizeText).filter(Boolean);
    const entityTexts = [entity.name, ...(entity.aliases || [])].map(normalizeText).filter(Boolean);
    let score = 0;

    if (entity.entity_type === item.category) {
      score += 120;
    }

    for (const candidate of candidateTexts) {
      if (!candidate) continue;
      if (entityTexts.some((value) => value === candidate)) {
        score = Math.max(score, 520);
      }
      if (entityTexts.some((value) => value.includes(candidate) || candidate.includes(value))) {
        score = Math.max(score, 340);
      }
      const descriptionText = normalizeText(entity.description || "");
      if (descriptionText && (descriptionText.includes(candidate) || candidate.includes(descriptionText))) {
        score = Math.max(score, 180);
      }
    }

    return score;
  }

  function resolveMatchedEntity(item, index) {
    if (!item || !index) {
      return null;
    }

    if (item.matched_entity_id && index.entitiesById.has(item.matched_entity_id)) {
      return index.entitiesById.get(item.matched_entity_id);
    }

    let bestEntity = null;
    let bestScore = 0;
    for (const entity of index.entities) {
      const score = scoreEntityMatch(entity, item);
      if (score > bestScore) {
        bestScore = score;
        bestEntity = entity;
      }
    }

    return bestScore >= 180 ? bestEntity : null;
  }

  function collectDirectWorkflowNodeIds(item, entity, index) {
    const workflowNodeIds = new Set(index.workflowNodes.map((node) => node.id));
    const directNodeIds = new Set();

    if (entity) {
      (entity.source_refs || []).forEach((sourceRef) => {
        if (workflowNodeIds.has(sourceRef)) {
          directNodeIds.add(sourceRef);
        }
      });

      index.mentions.forEach((relation) => {
        if (relation.target === entity.id && workflowNodeIds.has(relation.source)) {
          directNodeIds.add(relation.source);
        }
        if (relation.source === entity.id && workflowNodeIds.has(relation.target)) {
          directNodeIds.add(relation.target);
        }
      });
    }

    if (!directNodeIds.size && item) {
      const candidateTexts = [item.representative_term, ...(item.variations || [])].map(normalizeText).filter(Boolean);
      index.workflowNodes.forEach((node) => {
        const contentText = normalizeText(node.properties?.content || node.description || node.name);
        if (candidateTexts.some((candidate) => contentText.includes(candidate) || candidate.includes(contentText))) {
          directNodeIds.add(node.id);
        }
      });
    }

    return directNodeIds;
  }

  function collectNeighborData(directNodeIds, transitions) {
    const neighborNodeIds = new Set();
    const highlightTransitionIds = new Set();

    transitions.forEach((relation) => {
      if (directNodeIds.has(relation.source) || directNodeIds.has(relation.target)) {
        highlightTransitionIds.add(relation.id);
        if (!directNodeIds.has(relation.source)) {
          neighborNodeIds.add(relation.source);
        }
        if (!directNodeIds.has(relation.target)) {
          neighborNodeIds.add(relation.target);
        }
      }
    });

    return { neighborNodeIds, highlightTransitionIds };
  }
  function computeWorkflowLayout(workflowNodes, transitions, startX = 420) {
    const positions = new Map();
    const workflowIds = new Set(workflowNodes.map((node) => node.id));
    const indegree = new Map(workflowNodes.map((node) => [node.id, 0]));
    const outgoing = new Map(workflowNodes.map((node) => [node.id, []]));

    transitions.forEach((relation) => {
      if (!workflowIds.has(relation.source) || !workflowIds.has(relation.target)) {
        return;
      }
      indegree.set(relation.target, (indegree.get(relation.target) || 0) + 1);
      outgoing.get(relation.source).push(relation.target);
    });

    const roots = workflowNodes
      .filter((node) => (indegree.get(node.id) || 0) === 0)
      .map((node) => node.id)
      .sort((left, right) => getNodeOrder(left) - getNodeOrder(right));

    const queue = [...roots];
    const remainingIndegree = new Map(indegree);
    const level = new Map(roots.map((nodeId) => [nodeId, 0]));

    while (queue.length) {
      const nodeId = queue.shift();
      const nextLevel = level.get(nodeId) || 0;
      (outgoing.get(nodeId) || []).forEach((targetId) => {
        level.set(targetId, Math.max(level.get(targetId) || 0, nextLevel + 1));
        const nextIndegree = (remainingIndegree.get(targetId) || 0) - 1;
        remainingIndegree.set(targetId, nextIndegree);
        if (nextIndegree === 0) {
          queue.push(targetId);
        }
      });
    }

    workflowNodes.forEach((node) => {
      if (!level.has(node.id)) {
        level.set(node.id, 0);
      }
    });

    const columns = new Map();
    workflowNodes.forEach((node) => {
      const column = level.get(node.id) || 0;
      if (!columns.has(column)) {
        columns.set(column, []);
      }
      columns.get(column).push(node);
    });

    const orderedColumns = [...columns.keys()].sort((left, right) => left - right);
    const columnWidth = 184;
    const rowHeight = 110;
    const nodeWidth = 164;
    const nodeHeight = 76;

    orderedColumns.forEach((column) => {
      const nodes = columns.get(column).sort((left, right) => getNodeOrder(left.id) - getNodeOrder(right.id));
      nodes.forEach((node, index) => {
        positions.set(node.id, {
          x: startX + column * columnWidth,
          y: 42 + index * rowHeight,
          width: nodeWidth,
          height: nodeHeight,
        });
      });
    });

    const maxColumn = orderedColumns.length ? orderedColumns[orderedColumns.length - 1] : 0;
    const maxRows = Math.max(1, ...[...columns.values()].map((nodes) => nodes.length));

    return {
      positions,
      width: startX + (maxColumn + 1) * columnWidth + 80,
      height: 60 + maxRows * rowHeight,
    };
  }

  function averageY(nodeIds, positions) {
    const points = nodeIds
      .map((nodeId) => positions.get(nodeId))
      .filter(Boolean)
      .map((position) => position.y + position.height / 2);

    if (!points.length) {
      return null;
    }

    return points.reduce((sum, value) => sum + value, 0) / points.length;
  }

  function buildReadableNodeContent(node) {
    const raw = node?.properties?.content || node?.description || node?.name || "";
    return truncateText(raw.replace(/^患者\/主体,\s*临床表现,\s*/g, ""), 28);
  }

  function renderKgGraphSvg(model) {
    const {
      snapshot,
      index,
      item,
      entity,
      layout,
      focusNodeIds,
      inferredNodeIds,
      neighborNodeIds,
      highlightTransitionIds,
      manualMatch,
    } = model;
    const positions = layout.positions;
    const hasSelection = Boolean(item);
    const focusSet = new Set(focusNodeIds);
    const suggestedSet = new Set(inferredNodeIds);
    const neighborSet = new Set(neighborNodeIds);
    const averageFocusY = averageY([...focusSet], positions) || 150;
    const termBox = { x: 24, y: Math.max(30, averageFocusY - 88), width: 160, height: 68 };
    const entityBox = { x: 216, y: Math.max(30, averageFocusY - 88), width: 172, height: 78 };

    const transitionMarkup = index.transitions.map((relation) => {
      const from = positions.get(relation.source);
      const to = positions.get(relation.target);
      if (!from || !to) {
        return "";
      }

      const x1 = from.x + from.width;
      const y1 = from.y + from.height / 2;
      const x2 = to.x;
      const y2 = to.y + to.height / 2;
      const midX = (x1 + x2) / 2;
      const path = `M ${x1} ${y1} C ${midX - 36} ${y1}, ${midX + 36} ${y2}, ${x2} ${y2}`;
      const label = relation.properties?.condition || relation.label || "Continue";
      const className = [
        "kg-graph-link",
        highlightTransitionIds.has(relation.id)
          ? "active"
          : focusSet.has(relation.source) || focusSet.has(relation.target) || neighborSet.has(relation.source) || neighborSet.has(relation.target)
            ? "related"
            : "",
        hasSelection && !highlightTransitionIds.has(relation.id) && !neighborSet.has(relation.source) && !neighborSet.has(relation.target) && !focusSet.has(relation.source) && !focusSet.has(relation.target)
          ? "dimmed"
          : "",
      ].filter(Boolean).join(" ");

      return `
        <g>
          <path class="${className}" d="${path}" marker-end="url(#kg-arrow-soft)"></path>
          <text class="kg-graph-link-label" x="${midX}" y="${(y1 + y2) / 2 - 10}" text-anchor="middle">${escapeHtml(label)}</text>
        </g>
      `;
    }).join("");

    const workflowMarkup = index.workflowNodes.map((node) => {
      const position = positions.get(node.id);
      if (!position) {
        return "";
      }

      const className = [
        "kg-graph-node",
        hasSelection ? "clickable" : "",
        focusSet.has(node.id) ? "active" : neighborSet.has(node.id) ? "related" : "",
        hasSelection && !focusSet.has(node.id) && suggestedSet.has(node.id) ? "suggested" : "",
        hasSelection && !focusSet.has(node.id) && !neighborSet.has(node.id) && !suggestedSet.has(node.id) ? "dimmed" : "",
      ].filter(Boolean).join(" ");
      const nodeType = node.properties?.node_type || "\u6d41\u7a0b\u8282\u70b9";
      const title = truncateText(node.name.replace(/^node_\d+\s*/, ""), 16);
      const content = buildReadableNodeContent(node);

      return `
        <g class="${className}" data-kg-workflow-node="${escapeHtml(node.id)}" transform="translate(${position.x}, ${position.y})">
          <rect width="${position.width}" height="${position.height}" rx="18"></rect>
          <text class="kg-graph-badge" x="16" y="22">${escapeHtml(nodeType)}</text>
          <text class="kg-graph-title" x="16" y="44">${escapeHtml(title)}</text>
          <text class="kg-graph-desc" x="16" y="62">${escapeHtml(content)}</text>
        </g>
      `;
    }).join("");

    const summaryInfoMarkup = !hasSelection ? `
      <g class="kg-graph-info" transform="translate(24, 38)">
        <rect width="340" height="134" rx="20"></rect>
        <text class="kg-graph-badge" x="18" y="28">\u77e5\u8bc6\u56fe\u8c31</text>
        <text class="kg-graph-title" x="18" y="54">${escapeHtml(truncateText(snapshot.name || "\u77e5\u8bc6\u56fe\u8c31", 20))}</text>
        <text class="kg-graph-desc" x="18" y="80">\u7248\u672c ${escapeHtml(snapshot.metadata?.graph_version || "-")} | \u5b9e\u4f53 ${escapeHtml(snapshot.entity_count || index.entities.length)}</text>
        <text class="kg-graph-desc" x="18" y="100">\u5173\u7cfb ${escapeHtml(snapshot.relation_count || index.relations.length)} | \u66f4\u65b0\u65f6\u95f4 ${escapeHtml(truncateText(snapshot.metadata?.updated_at || "\u672a\u8bb0\u5f55", 22))}</text>
        <text class="kg-graph-desc" x="18" y="120">\u5148\u9009\u62e9\u4e00\u4e2a\u672f\u8bed\u7ec4\uff0c\u518d\u70b9\u51fb\u6d41\u7a0b\u8282\u70b9\u5efa\u7acb\u624b\u52a8\u5339\u914d\u3002</text>
      </g>
    ` : "";

    const focusMarkup = item ? (() => {
      const entityTitle = entity ? entity.name : "\u65b0\u5b9e\u4f53";
      const entityBadge = entity ? entityTypeLabel(entity.entity_type) : `${getCategoryLabel(item.category)}\u5019\u9009\u9879`;
      const entityClass = entity ? "entity" : "unmatched";
      const selectionEdgeLabel = manualMatch.isDirty
        ? "\u7f16\u8f91\u4e2d"
        : item.match_confidence
          ? `\u5339\u914d ${(Number(item.match_confidence) * 100).toFixed(0)}%`
          : "\u5f85\u786e\u8ba4";
      const selectionEdgePath = `M ${termBox.x + termBox.width} ${termBox.y + termBox.height / 2} C 192 ${termBox.y + termBox.height / 2}, 204 ${entityBox.y + entityBox.height / 2}, ${entityBox.x} ${entityBox.y + entityBox.height / 2}`;
      const mentionMarkup = [...focusSet].map((nodeId) => {
        const position = positions.get(nodeId);
        if (!position) {
          return "";
        }
        const y1 = entityBox.y + entityBox.height / 2;
        const y2 = position.y + position.height / 2;
        const x1 = entityBox.x + entityBox.width;
        const x2 = position.x;
        const midX = (x1 + x2) / 2;
        const path = `M ${x1} ${y1} C ${midX - 24} ${y1}, ${midX + 24} ${y2}, ${x2} ${y2}`;
        return `
          <g>
            <path class="kg-graph-link selection mention" d="${path}" marker-end="url(#kg-arrow-strong)"></path>
            <text class="kg-graph-link-label" x="${midX}" y="${(y1 + y2) / 2 - 10}" text-anchor="middle">\u6d41\u7a0b\u5173\u8054</text>
          </g>
        `;
      }).join("");

      return `
        <g class="kg-graph-focus term" transform="translate(${termBox.x}, ${termBox.y})">
          <rect width="${termBox.width}" height="${termBox.height}" rx="18"></rect>
          <text class="kg-graph-badge" x="16" y="24">\u5f53\u524d\u672f\u8bed</text>
          <text class="kg-graph-title" x="16" y="48">${escapeHtml(truncateText(item.representative_term, 12))}</text>
        </g>
        <g>
          <path class="kg-graph-link selection" d="${selectionEdgePath}" marker-end="url(#kg-arrow-strong)"></path>
          <text class="kg-graph-link-label" x="${(termBox.x + termBox.width + entityBox.x) / 2}" y="${termBox.y + termBox.height / 2 - 10}" text-anchor="middle">${escapeHtml(selectionEdgeLabel)}</text>
        </g>
        <g class="kg-graph-focus ${entityClass}" transform="translate(${entityBox.x}, ${entityBox.y})">
          <rect width="${entityBox.width}" height="${entityBox.height}" rx="18"></rect>
          <text class="kg-graph-badge" x="16" y="24">${escapeHtml(entityBadge)}</text>
          <text class="kg-graph-title" x="16" y="48">${escapeHtml(truncateText(entityTitle, 12))}</text>
          <text class="kg-graph-desc" x="16" y="66">${escapeHtml(entity ? truncateText(entity.id, 24) : "\u5ba1\u6838\u901a\u8fc7\u540e\u521b\u5efa")}</text>
        </g>
        ${mentionMarkup}
      `;
    })() : "";

    const width = Math.max(layout.width, 1320);
    const height = Math.max(layout.height, 360);

    return `
      <svg class="kg-graph-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="\u77e5\u8bc6\u56fe\u8c31\u6d41\u7a0b\u9884\u89c8">
        <defs>
          <marker id="kg-arrow-soft" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 12 6 L 0 12 z" fill="rgba(107, 90, 79, 0.52)"></path>
          </marker>
          <marker id="kg-arrow-strong" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 12 6 L 0 12 z" fill="rgba(36, 92, 63, 0.82)"></path>
          </marker>
        </defs>
        ${summaryInfoMarkup}
        ${transitionMarkup}
        ${workflowMarkup}
        ${focusMarkup}
      </svg>
    `;
  }

  function buildPreviewModel(item, snapshot) {
    const index = buildGraphIndex(snapshot);
    const entity = item ? resolveMatchedEntity(item, index) : null;
    const inferredNodeIds = item ? collectDirectWorkflowNodeIds(item, entity, index) : new Set();
    const focusNodeIds = item ? new Set(getEditableWorkflowNodeIds(item, [...inferredNodeIds])) : new Set();
    const { neighborNodeIds, highlightTransitionIds } = collectNeighborData(focusNodeIds, index.transitions);
    const layout = computeWorkflowLayout(index.workflowNodes, index.transitions);
    const focusNodes = [...focusNodeIds]
      .map((nodeId) => index.entitiesById.get(nodeId))
      .filter(Boolean)
      .sort((left, right) => getNodeOrder(left.id) - getNodeOrder(right.id));
    const inferredNodes = [...inferredNodeIds]
      .map((nodeId) => index.entitiesById.get(nodeId))
      .filter(Boolean)
      .sort((left, right) => getNodeOrder(left.id) - getNodeOrder(right.id));
    const transitionRelations = index.transitions
      .filter((relation) => highlightTransitionIds.has(relation.id))
      .sort((left, right) => getNodeOrder(left.source) - getNodeOrder(right.source));
    const hasSavedManualMapping = getSavedWorkflowNodeIds(item).length > 0;
    const isDirty = hasWorkflowNodeDraftChanges(item);
    const canSave = Boolean(item) && (isDirty || (!hasSavedManualMapping && focusNodes.length > 0));

    const selectionDetails = item
      ? [
          { label: "\u5f53\u524d\u672f\u8bed", value: item.representative_term },
          { label: "\u7c7b\u522b", value: getCategoryLabel(item.category) },
          { label: "\u53d8\u4f53", value: (item.variations || []).join(", ") || "\u65e0" },
          { label: "\u9891\u6b21", value: `${item.total_frequency || 0} \u6b21` },
          { label: "\u5339\u914d\u5b9e\u4f53", value: entity ? `${entity.name} (${entityTypeLabel(entity.entity_type)})` : "\u5f53\u524d\u8fd8\u6ca1\u6709\u5339\u914d\u5230\u5b9e\u4f53\uff0c\u5ba1\u6838\u901a\u8fc7\u540e\u4f1a\u521b\u5efa\u65b0\u5b9e\u4f53\u3002" },
          { label: "\u5b9e\u4f53 ID", value: entity ? entity.id : item.matched_entity_id || "\u65e0" },
          { label: "\u6d41\u7a0b\u8282\u70b9", value: focusNodes.length ? focusNodes.map((node) => describeWorkflowNode(node)).join("; ") : "\u5c1a\u672a\u5339\u914d\u6d41\u7a0b\u8282\u70b9\uff0c\u53ef\u5728\u56fe\u4e2d\u70b9\u51fb\u8282\u70b9\u8fdb\u884c\u624b\u52a8\u6307\u5b9a\u3002" },
          { label: "\u5339\u914d\u65b9\u5f0f", value: isDirty ? "\u624b\u52a8\u4fee\u6539\u5f85\u4fdd\u5b58" : hasSavedManualMapping ? "\u5df2\u4fdd\u5b58\u624b\u52a8\u5339\u914d" : inferredNodes.length ? "\u7cfb\u7edf\u5efa\u8bae" : "\u5c1a\u672a\u5339\u914d\u8282\u70b9" },
          { label: "\u6765\u6e90\u6587\u4ef6", value: (item.source_files || []).join(", ") || "\u65e0" },
        ]
      : [
          { label: "\u5f53\u524d\u56fe\u8c31", value: snapshot.name || "\u672a\u547d\u540d\u56fe\u8c31" },
          { label: "\u56fe\u8c31\u7248\u672c", value: snapshot.metadata?.graph_version || "\u672a\u77e5" },
          { label: "\u56fe\u8c31\u89c4\u6a21", value: `${snapshot.entity_count || index.entities.length} \u4e2a\u5b9e\u4f53 / ${snapshot.relation_count || index.relations.length} \u6761\u5173\u7cfb` },
          { label: "\u4f7f\u7528\u8bf4\u660e", value: "\u5148\u5728\u5de6\u4fa7\u9009\u62e9\u672f\u8bed\u7ec4\uff0c\u53f3\u4fa7\u4f1a\u9ad8\u4eae\u5b83\u5f53\u524d\u5173\u8054\u7684\u56fe\u8c31\u8def\u5f84\uff0c\u5e76\u652f\u6301\u70b9\u51fb\u6d41\u7a0b\u8282\u70b9\u624b\u52a8\u5339\u914d\u3002" },
        ];

    const relationDetails = item
      ? [
          {
            label: `${item.representative_term} -> ${entity ? entity.name : "\u65b0\u5b9e\u4f53"}`,
            value: `${item.match_confidence ? `\u5339\u914d ${(Number(item.match_confidence) * 100).toFixed(0)}%` : "\u6682\u65e0\u73b0\u6709\u5b9e\u4f53\u5339\u914d"} | \u5ba1\u6838\u72b6\u6001 ${getStatusLabel(item.review_status)}`,
          },
          ...(focusNodes.length
            ? focusNodes.map((node) => ({
                label: `${entity ? entity.name : item.representative_term} -> ${node.name}`,
                value: `\u5f53\u524d\u6d41\u7a0b\u5173\u8054 | \u8282\u70b9\u7c7b\u578b ${node.properties?.node_type || "\u6d41\u7a0b\u8282\u70b9"} | \u8282\u70b9\u5185\u5bb9 ${node.properties?.content || node.description || "-"}`,
              }))
            : [{
                label: "\u6d41\u7a0b\u5173\u8054",
                value: "\u8fd8\u6ca1\u6709\u5173\u8054\u6d41\u7a0b\u8282\u70b9\uff0c\u53ef\u70b9\u51fb\u4e0a\u65b9\u56fe\u4e2d\u7684\u8282\u70b9\u8865\u5145\u624b\u52a8\u5173\u8054\u3002",
              }]),
          ...transitionRelations.map((relation) => {
            const sourceNode = index.entitiesById.get(relation.source);
            const targetNode = index.entitiesById.get(relation.target);
            return {
              label: `${sourceNode?.name || relation.source} -> ${targetNode?.name || relation.target}`,
              value: `\u8f6c\u79fb\u6761\u4ef6 ${relation.properties?.condition || relation.label || "\u7ee7\u7eed"} | \u5173\u7cfb\u7c7b\u578b ${relation.relation_type}`,
            };
          }),
        ].slice(0, 12)
      : index.transitions.slice(0, 6).map((relation) => {
          const sourceNode = index.entitiesById.get(relation.source);
          const targetNode = index.entitiesById.get(relation.target);
          return {
            label: `${sourceNode?.name || relation.source} -> ${targetNode?.name || relation.target}`,
            value: `\u6d41\u7a0b\u6d41\u8f6c | \u6761\u4ef6 ${relation.properties?.condition || relation.label || "\u7ee7\u7eed"}`,
          };
        });

    return {
      item,
      badge: item
        ? isDirty
          ? "\u7f16\u8f91\u4e2d"
          : hasSavedManualMapping
            ? "\u5df2\u4fdd\u5b58\u6d41\u7a0b\u5339\u914d"
            : entity
              ? "\u5df2\u5339\u914d\u5b9e\u4f53"
              : "\u5f85\u8865\u5145\u5b9e\u4f53"
        : "\u6d41\u7a0b\u6982\u89c8",
      summary: item
        ? isDirty
          ? `\u5df2\u8c03\u6574\u201c${item.representative_term}\u201d\u7684\u6d41\u7a0b\u8282\u70b9\uff0c\u8bf7\u4fdd\u5b58\u4ee5\u6301\u4e45\u5316\u624b\u52a8\u5339\u914d\u3002`
          : hasSavedManualMapping
            ? `\u201c${item.representative_term}\u201d\u5df2\u7ecf\u4fdd\u5b58\u624b\u52a8\u6d41\u7a0b\u5339\u914d\u3002`
            : entity
              ? `\u5df2\u9ad8\u4eae\u201c${item.representative_term}\u201d\u5339\u914d\u5b9e\u4f53\uff0c\u5173\u8054\u6d41\u7a0b\u8282\u70b9\u53ca\u9644\u8fd1\u6d41\u8f6c\u5173\u7cfb\u3002`
              : `\u5df2\u9ad8\u4eae\u201c${item.representative_term}\u201d\u7684\u53ef\u80fd\u6d41\u7a0b\u8282\u70b9\uff0c\u5f53\u524d\u8fd8\u6ca1\u6709\u76f4\u63a5\u5b9e\u4f53\u5339\u914d\u3002`
        : `\u5f53\u524d\u56fe\u8c31\u5305\u542b ${snapshot.entity_count || index.entities.length} \u4e2a\u5b9e\u4f53\u548c ${snapshot.relation_count || index.relations.length} \u6761\u5173\u7cfb\u3002\u9009\u62e9\u4e00\u4e2a\u672f\u8bed\u7ec4\u5373\u53ef\u67e5\u770b\u6216\u624b\u52a8\u5339\u914d\u6d41\u7a0b\u8282\u70b9\u3002`,
      selectionDetails,
      relationDetails,
      manualMatch: {
        item,
        selectedNodes: focusNodes,
        selectedNodeIds: [...focusNodeIds],
        inferredNodes,
        inferredNodeIds: [...inferredNodeIds],
        hasSavedManualMapping,
        isDirty,
        canSave,
      },
      svg: renderKgGraphSvg({
        snapshot,
        index,
        item,
        entity,
        layout,
        focusNodeIds,
        inferredNodeIds,
        neighborNodeIds,
        highlightTransitionIds,
        manualMatch: {
          hasSavedManualMapping,
          isDirty,
        },
      }),
    };
  }

  function renderKgPreview(errorMessage = "") {
    if (errorMessage) {
      kgPreviewBadge.textContent = "\u9884\u89c8\u5f02\u5e38";
      kgPreviewSummary.textContent = errorMessage;
      kgGraphCanvas.innerHTML = `<div class="kg-empty-state">${escapeHtml(errorMessage)}</div>`;
      renderDetailList(kgPreviewSelection, [], "\u65e0\u6cd5\u52a0\u8f7d\u5f53\u524d\u660e\u7ec6\u3002");
      renderDetailList(kgPreviewRelations, [], "\u65e0\u6cd5\u52a0\u8f7d\u5173\u7cfb\u660e\u7ec6\u3002");
      return;
    }

    if (!state.graphSnapshot) {
      kgPreviewBadge.textContent = "\u56fe\u8c31\u672a\u52a0\u8f7d";
      kgPreviewSummary.textContent = "\u52a0\u8f7d\u77e5\u8bc6\u56fe\u8c31\u540e\uff0c\u8fd9\u91cc\u4f1a\u5c55\u793a\u5f53\u524d\u6d41\u7a0b\u6982\u89c8\u548c\u672f\u8bed\u5230\u8282\u70b9\u7684\u5173\u8054\u3002";
      kgGraphCanvas.innerHTML = '<div class="kg-empty-state">\u77e5\u8bc6\u56fe\u8c31\u5c1a\u672a\u52a0\u8f7d\uff0c\u8bf7\u5148\u751f\u6210\u57fa\u7840\u56fe\u8c31\u6216\u5bfc\u5165 MinerU \u6587\u6863\u3002</div>';
      renderDetailList(kgPreviewSelection, [], "\u56fe\u8c31\u52a0\u8f7d\u540e\u4f1a\u5728\u8fd9\u91cc\u663e\u793a\u660e\u7ec6\u3002");
      renderDetailList(kgPreviewRelations, [], "\u56fe\u8c31\u52a0\u8f7d\u540e\u4f1a\u5728\u8fd9\u91cc\u663e\u793a\u5173\u7cfb\u8bf4\u660e\u3002");
      return;
    }

    const selectedItem = getSelectedItem();
    const model = buildPreviewModel(selectedItem, state.graphSnapshot);
    kgPreviewBadge.textContent = model.badge;
    kgPreviewSummary.textContent = model.summary;
    kgGraphCanvas.innerHTML = model.svg;
    renderSelectionPane(model);
    renderDetailList(kgPreviewRelations, model.relationDetails, "\u6682\u65e0\u5173\u7cfb\u660e\u7ec6\u3002");
  }

  function getReviewerName() {
    const reviewer = kgReviewerNameInput.value.trim();
    if (!reviewer) {
      throw new Error("请先填写审核医生姓名。");
    }
    return reviewer;
  }

  async function extractKgTerms() {
    const caseDir = kgCaseDirInput.value.trim();
    setKgStatus("\u6b63\u5728\u4ece\u75c5\u4f8b\u76ee\u5f55\u62bd\u53d6\u672f\u8bed...");
    const data = await requestJson("/api/kg-enhancement/extract", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        case_dir: caseDir,
      }),
    });

    setKgStatus(data.message || "\u672f\u8bed\u62bd\u53d6\u5b8c\u6210\u3002");
    await loadKgEnhancementStatus();
    await loadKgReviewItems();
    await loadKgGraphSnapshot();
  }

  async function saveKgWorkflowMatch(groupKey, workflowNodeIds) {
    const reviewerName = getReviewerName();
    const normalizedNodeIds = normalizeWorkflowNodeIds(workflowNodeIds);

    setKgStatus(normalizedNodeIds.length ? "\u6b63\u5728\u4fdd\u5b58\u6d41\u7a0b\u8282\u70b9\u5339\u914d..." : "\u6b63\u5728\u6e05\u7a7a\u6d41\u7a0b\u8282\u70b9\u5339\u914d...");
    await requestJson("/api/kg-enhancement/workflow-match", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        group_key: groupKey,
        reviewer_name: reviewerName,
        workflow_node_ids: normalizedNodeIds,
      }),
    });

    clearWorkflowNodeDraft(groupKey);
    setKgStatus(normalizedNodeIds.length ? "\u5df2\u4fdd\u5b58\u6d41\u7a0b\u8282\u70b9\u5339\u914d\u3002" : "\u5df2\u6e05\u7a7a\u6d41\u7a0b\u8282\u70b9\u5339\u914d\u3002");
    await loadKgReviewItems();
    renderKgPreview();
  }

  async function submitKgReview(groupKey, action) {
    const reviewerName = getReviewerName();
    const encodedKey = encodeURIComponent(groupKey);
    const commentInput = kgReviewList.querySelector(`[data-comment-key="${encodedKey}"]`);
    const comment = commentInput ? commentInput.value.trim() : "";

    setKgStatus(`正在${action === "approve" ? "通过" : "拒绝"}术语组...`);
    await requestJson("/api/kg-enhancement/review", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        group_key: groupKey,
        action,
        reviewer_name: reviewerName,
        comment,
      }),
    });

    setKgStatus(`已${action === "approve" ? "通过" : "拒绝"}术语组审核。`);
    await loadKgEnhancementStatus();
    await loadKgReviewItems();
  }

  async function batchApproveFiltered() {
    const pendingItems = state.filteredItems.filter((item) => item.review_status === "pending");
    if (!pendingItems.length) {
      throw new Error("当前筛选结果里没有待审核术语组。");
    }

    const reviewerName = getReviewerName();
    let successCount = 0;
    setKgStatus(`正在批量通过 ${pendingItems.length} 组术语...`);

    for (const item of pendingItems) {
      const encodedKey = encodeURIComponent(item.group_key);
      const commentInput = kgReviewList.querySelector(`[data-comment-key="${encodedKey}"]`);
      const comment = commentInput ? commentInput.value.trim() : "";
      try {
        await requestJson("/api/kg-enhancement/review", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            group_key: item.group_key,
            action: "approve",
            reviewer_name: reviewerName,
            comment,
          }),
        });
        successCount += 1;
      } catch {
        // Continue with the next item so one failure does not block the batch.
      }
    }

    setKgStatus(`批量审核完成：${successCount} / ${pendingItems.length} 组已通过。`);
    await loadKgEnhancementStatus();
    await loadKgReviewItems();
  }

  async function mergeKgTerms() {
    setKgStatus("正在将已通过术语合并到当前知识图谱...");
    const data = await requestJson("/api/kg-enhancement/merge", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    if (data.download_url) {
      kgExportLink.innerHTML = `<a href="${escapeHtml(data.download_url)}" target="_blank" rel="noreferrer">下载增强后的知识图谱</a>`;
    }

    const stats = data.stats || {};
    const summary = `Added entities ${stats.entities_added || 0}, added aliases ${stats.aliases_added || 0}, added workflow links ${stats.workflow_links_added || 0}`;
    setKgStatus(`${data.message || "合并完成。"} ${summary}`);
    await refreshGraphStatus();
    await loadKgEnhancementStatus();
    await loadKgReviewItems();
    await loadKgGraphSnapshot();
  }
  parseMineruUrlButton.addEventListener("click", async () => {
    try {
      await importMineruByUrl();
    } catch (error) {
      setGraphStatus(error.message || String(error));
    }
  });

  parseMineruFileButton.addEventListener("click", async () => {
    try {
      await importMineruByFile();
    } catch (error) {
      setGraphStatus(error.message || String(error));
    }
  });

  [kgFilterCategory, kgFilterStatus, kgFilterConfidence].forEach((element) => {
    element.addEventListener("change", applyKgFilters);
  });

  refreshKgButton.addEventListener("click", async () => {
    await loadKgEnhancementStatus();
    await loadKgReviewItems();
    await loadKgGraphSnapshot();
  });

  extractKgTermsButton.addEventListener("click", async () => {
    try {
      await extractKgTerms();
    } catch (error) {
      setKgStatus(error.message || String(error));
    }
  });

  mergeKgTermsButton.addEventListener("click", async () => {
    try {
      await mergeKgTerms();
    } catch (error) {
      setKgStatus(error.message || String(error));
    }
  });

  kgBatchApproveButton.addEventListener("click", async () => {
    try {
      await batchApproveFiltered();
    } catch (error) {
      setKgStatus(error.message || String(error));
    }
  });

  kgGraphCanvas.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !state.graphSnapshot) {
      return;
    }

    const nodeElement = event.target.closest("[data-kg-workflow-node]");
    if (!nodeElement) {
      return;
    }

    const selectedItem = getSelectedItem();
    if (!selectedItem) {
      return;
    }

    const model = buildPreviewModel(selectedItem, state.graphSnapshot);
    const editableNodeIds = getEditableWorkflowNodeIds(selectedItem, model.manualMatch.inferredNodeIds);
    const nodeId = nodeElement.getAttribute("data-kg-workflow-node") || "";
    const nextNodeIds = editableNodeIds.includes(nodeId)
      ? editableNodeIds.filter((currentId) => currentId !== nodeId)
      : [...editableNodeIds, nodeId];

    setWorkflowNodeDraft(selectedItem.group_key, nextNodeIds);
    renderKgPreview();
  });

  kgPreviewSelection.addEventListener("click", async (event) => {
    if (!(event.target instanceof Element) || !state.graphSnapshot) {
      return;
    }

    const selectedItem = getSelectedItem();
    if (!selectedItem) {
      return;
    }

    const saveButton = event.target.closest("button[data-kg-save-workflow-match]");
    if (saveButton) {
      try {
        const model = buildPreviewModel(selectedItem, state.graphSnapshot);
        await saveKgWorkflowMatch(selectedItem.group_key, model.manualMatch.selectedNodeIds);
      } catch (error) {
        setKgStatus(error.message || String(error));
      }
      return;
    }

    const resetButton = event.target.closest("button[data-kg-reset-workflow-match]");
    if (resetButton) {
      clearWorkflowNodeDraft(selectedItem.group_key);
      renderKgPreview();
      return;
    }

    const clearButton = event.target.closest("button[data-kg-clear-workflow-match]");
    if (clearButton) {
      setWorkflowNodeDraft(selectedItem.group_key, []);
      renderKgPreview();
    }
  });

  kgReviewList.addEventListener("click", async (event) => {
    const actionButton = event.target.closest("button[data-kg-action]");
    if (actionButton) {
      const groupKey = decodeURIComponent(actionButton.dataset.groupKey || "");
      const action = actionButton.dataset.kgAction;
      if (!groupKey || !action) {
        return;
      }
      setSelectedGroup(groupKey);
      try {
        await submitKgReview(groupKey, action);
      } catch (error) {
        setKgStatus(error.message || String(error));
      }
      return;
    }

    const previewButton = event.target.closest("button[data-kg-preview]");
    if (previewButton) {
      const groupKey = decodeURIComponent(previewButton.dataset.kgPreview || "");
      if (groupKey) {
        setSelectedGroup(groupKey);
      }
      return;
    }

    const ignoredControl = event.target.closest("input, textarea, select, button, a, label");
    if (ignoredControl) {
      return;
    }

    const card = event.target.closest("[data-group-card]");
    if (card) {
      const groupKey = decodeURIComponent(card.dataset.groupCard || "");
      if (groupKey) {
        setSelectedGroup(groupKey);
      }
    }
  });

  persistInputs();
  loadKgEnhancementStatus();
  loadKgReviewItems();
  loadKgGraphSnapshot();
})();
