const sampleCases = [
  {
    title: "典型 STEMI 病例",
    description:
      "患者男，65岁。胸骨后压榨性胸痛3小时，向左肩放射，伴大汗、恶心。心电图提示V1-V4导联ST段抬高0.3mV。肌钙蛋白I 2.5ng/mL，CK-MB 45U/L。",
  },
  {
    title: "典型 NSTEMI 病例",
    description:
      "患者女，58岁。反复胸闷胸痛30分钟，劳力后加重，伴气短。心电图示V4-V6导联ST段压低并T波倒置。肌钙蛋白T 0.8ng/mL，CK-MB 32U/L。",
  },
  {
    title: "非缺血性胸痛病例",
    description:
      "患者男，34岁。胸部刺痛2天，深呼吸和转身时加重，按压胸壁可诱发。心电图基本正常，肌钙蛋白正常，无明显放射痛和出汗。",
  },
];

const methods = [
  { key: "direct", label: "直接诊断" },
  { key: "direct_generation", label: "直接生成" },
  { key: "intermediate_state", label: "中间状态" },
  { key: "step_by_step", label: "逐步引导" },
  { key: "full_workflow", label: "全流程" },
];

const workflowSteps = [
  {
    id: "ischemic",
    title: "Step 1",
    text: "先判断胸痛是否符合缺血性胸痛特征，如胸骨后压榨感、放射痛、持续超过 20 分钟、伴大汗恶心等。",
  },
  {
    id: "st",
    title: "Step 2",
    text: "若为缺血性胸痛，再依据心电图判断是否存在 ST 段抬高。",
  },
  {
    id: "biomarker",
    title: "Step 3",
    text: "继续结合肌钙蛋白、CK-MB 等心肌标志物是否升高。",
  },
  {
    id: "final",
    title: "Final",
    text: "根据规则树输出最终诊断结果，并显示对应的临床解释路径。",
  },
];

const graphNodes = [
  { id: "start", x: 90, y: 120, title: "急性胸痛", desc: "初始就诊入口", badge: "START" },
  { id: "ischemic_yes", x: 320, y: 65, title: "缺血性胸痛", desc: "症状符合缺血特征", badge: "STEP 1" },
  { id: "ischemic_no", x: 320, y: 190, title: "非缺血性胸痛", desc: "排向其他病因", badge: "STEP 1" },
  { id: "st_yes", x: 565, y: 50, title: "ST 段抬高", desc: "进入抬高分支", badge: "STEP 2" },
  { id: "st_no", x: 565, y: 140, title: "非 ST 段抬高", desc: "压低或无抬高", badge: "STEP 2" },
  { id: "other", x: 565, y: 240, title: "其他", desc: "非缺血性胸痛", badge: "FINAL" },
  { id: "stemi", x: 830, y: 32, title: "STEMI", desc: "ST 抬高 + 标志物升高", badge: "FINAL" },
  { id: "variant", x: 830, y: 102, title: "变异型心绞痛", desc: "ST 抬高 + 标志物未升高", badge: "FINAL" },
  { id: "nstemi", x: 830, y: 172, title: "NSTEMI", desc: "非 ST 抬高 + 标志物升高", badge: "FINAL" },
  { id: "ua", x: 830, y: 242, title: "UA", desc: "非 ST 抬高 + 标志物未升高", badge: "FINAL" },
];

const graphEdges = [
  { from: "start", to: "ischemic_yes", label: "是" },
  { from: "start", to: "ischemic_no", label: "否" },
  { from: "ischemic_no", to: "other", label: "归类" },
  { from: "ischemic_yes", to: "st_yes", label: "ST 抬高" },
  { from: "ischemic_yes", to: "st_no", label: "非 ST 抬高" },
  { from: "st_yes", to: "stemi", label: "标志物升高" },
  { from: "st_yes", to: "variant", label: "标志物未升高" },
  { from: "st_no", to: "nstemi", label: "标志物升高" },
  { from: "st_no", to: "ua", label: "标志物未升高" },
];

const state = {
  sampleIndex: 0,
  backendAvailable: false,
  lastResult: null,
  lastDoctorReview: null,
  graphVersionInfo: null,
  graphHistory: [],
  trainingStatus: null,
};

const descriptionInput = document.querySelector("#patient-description");
const ischemicSelect = document.querySelector("#ischemic-select");
const stSelect = document.querySelector("#st-select");
const biomarkerSelect = document.querySelector("#biomarker-select");
const analysisModeSelect = document.querySelector("#analysis-mode");
const modelInput = document.querySelector("#model-input");
const apiKeyInput = document.querySelector("#api-key-input");
const baseUrlInput = document.querySelector("#base-url-input");
const backendMethodSelect = document.querySelector("#backend-method");
const serverStatus = document.querySelector("#server-status");
const diagnosisResult = document.querySelector("#diagnosis-result");
const diagnosisPath = document.querySelector("#diagnosis-path");
const confidenceChip = document.querySelector("#confidence-chip");
const ischemicResult = document.querySelector("#ischemic-result");
const stResult = document.querySelector("#st-result");
const biomarkerResult = document.querySelector("#biomarker-result");
const reasonList = document.querySelector("#reason-list");
const methodCards = document.querySelector("#method-cards");
const workflow = document.querySelector("#workflow");
const knowledgeGraph = document.querySelector("#knowledge-graph");
const preprocessSummary = document.querySelector("#preprocess-summary");
const noteStyleSections = document.querySelector("#note-style-sections");
const structuredFactsList = document.querySelector("#structured-facts-list");
const trajectoryQualitySummary = document.querySelector("#trajectory-quality-summary");
const trajectoryQualityList = document.querySelector("#trajectory-quality-list");
const questionGainList = document.querySelector("#question-gain-list");
const nextQuestionList = document.querySelector("#next-question-list");
const singleTurnSampleList = document.querySelector("#single-turn-sample-list");
const replayStatus = document.querySelector("#replay-status");
const caseReplayList = document.querySelector("#case-replay-list");
const showFinalGraphButton = document.querySelector("#show-final-graph");
const reviewerNameInput = document.querySelector("#reviewer-name");
const reviewActionSelect = document.querySelector("#review-action");
const reviewDiagnosisSelect = document.querySelector("#review-diagnosis");
const reviewCommentInput = document.querySelector("#review-comment");
const reviewSaveStatus = document.querySelector("#review-save-status");
const reviewHistoryList = document.querySelector("#review-history-list");
const exportReportLink = document.querySelector("#report-export-link");
const mineruTitleInput = document.querySelector("#mineru-title-input");
const mineruPayloadInput = document.querySelector("#mineru-payload-input");
const graphBuildStatus = document.querySelector("#graph-build-status");
const graphArtifacts = document.querySelector("#graph-artifacts");
const graphPreviewImage = document.querySelector("#graph-preview-image");
const graphVersionBadge = document.querySelector("#graph-version-badge");
const graphVersionMeta = document.querySelector("#graph-version-meta");
const graphHistoryList = document.querySelector("#graph-history-list");
const trainingSummary = document.querySelector("#training-summary");
const trainingPatientCount = document.querySelector("#training-patient-count");
const trainingSftCount = document.querySelector("#training-sft-count");
const trainingPreferenceCount = document.querySelector("#training-preference-count");
const trainingRlCount = document.querySelector("#training-rl-count");
const trainingPrepareStatus = document.querySelector("#training-prepare-status");
const trainingDatasetList = document.querySelector("#training-dataset-list");
const trainingRecipeList = document.querySelector("#training-recipe-list");

const STORAGE_KEYS = {
  apiKey: "fuwai_api_key",
  baseUrl: "fuwai_base_url",
  model: "fuwai_model",
};

const HALT_DIAGNOSIS = "待补充检查";
const REVIEW_DIAGNOSES = [
  "STEMI",
  "NSTEMI",
  "UA",
  "变异性心绞痛",
  "其他",
  "待补充症状学信息",
  "待补充心电图检查",
  "待补充心肌标志物检查",
];
const REPLAY_KEYWORDS = {
  1: ["胸痛", "胸闷", "胸骨后", "压榨", "放射", "左肩", "左臂", "大汗", "恶心", "持续", "小时", "分钟"],
  2: ["心电图", "ECG", "导联", "ST段", "ST 抬高", "ST抬高", "T波", "Q波"],
  3: ["肌钙蛋白", "cTn", "CK-MB", "心肌标志物", "ng/mL", "U/L", "升高", "阳性"],
};

function isHaltDiagnosis(diagnosis) {
  return typeof diagnosis === "string" && diagnosis.startsWith("待补充");
}

function renderWorkflow(activeUntil = "") {
  const activeOrder = ["ischemic", "st", "biomarker", "final"];
  const activeIndex = activeOrder.indexOf(activeUntil);
  workflow.innerHTML = workflowSteps
    .map((step, index) => {
      const isActive = activeIndex >= index;
      return `
        <article class="workflow-step ${isActive ? "active" : ""}">
          <h3>${step.title}</h3>
          <p>${step.text}</p>
        </article>
      `;
    })
    .join("");
}

function renderKnowledgeGraph(activePath = { nodes: [], edges: [] }) {
  const activeNodes = new Set(activePath.nodes || []);
  const activeEdges = new Set(activePath.edges || []);
  const hasActivePath = activeNodes.size > 0;

  const edgeMarkup = graphEdges
    .map((edge) => {
      const fromNode = graphNodes.find((node) => node.id === edge.from);
      const toNode = graphNodes.find((node) => node.id === edge.to);
      const x1 = fromNode.x + 140;
      const y1 = fromNode.y + 28;
      const x2 = toNode.x;
      const y2 = toNode.y + 28;
      const midX = (x1 + x2) / 2;
      const curve = Math.abs(y2 - y1) > 40 ? 28 : 0;
      const path = `M ${x1} ${y1} C ${midX - 40} ${y1 + curve}, ${midX + 40} ${y2 - curve}, ${x2} ${y2}`;
      const edgeKey = `${edge.from}->${edge.to}`;
      const activeClass = activeEdges.has(edgeKey) ? "active" : hasActivePath ? "dimmed" : "";
      const labelY = (y1 + y2) / 2 - 10;

      return `
        <g>
          <path class="graph-edge ${activeClass}" d="${path}"></path>
          <text x="${midX}" y="${labelY}" text-anchor="middle" class="graph-node-desc">${edge.label}</text>
        </g>
      `;
    })
    .join("");

  const nodeMarkup = graphNodes
    .map((node) => {
      const isActive = activeNodes.has(node.id);
      const isFinalActive = isActive && ["stemi", "variant", "nstemi", "ua", "other"].includes(node.id);
      const className = [
        "graph-node",
        isActive ? "active" : "",
        isFinalActive ? "final-active" : "",
        !isActive && hasActivePath ? "dimmed" : "",
      ].join(" ").trim();

      return `
        <g class="${className}" transform="translate(${node.x}, ${node.y})">
          <rect class="graph-node-card" width="140" height="58" rx="18"></rect>
          <rect class="graph-badge" x="12" y="10" width="48" height="16" rx="8"></rect>
          <text class="graph-badge-text" x="36" y="21" text-anchor="middle">${node.badge}</text>
          <text class="graph-node-label" x="16" y="36">${node.title}</text>
          <text class="graph-node-desc" x="16" y="51">${node.desc}</text>
        </g>
      `;
    })
    .join("");

  knowledgeGraph.innerHTML = `
    <svg class="knowledge-svg" viewBox="0 0 1000 320" role="img" aria-label="急性胸痛诊断知识图谱">
      ${edgeMarkup}
      ${nodeMarkup}
    </svg>
  `;
}

function normalizeChoice(value, autoValue) {
  if (value === "yes") return true;
  if (value === "no") return false;
  return autoValue;
}

function containsAny(text, keywords) {
  return keywords.some((keyword) => text.includes(keyword));
}

function hasSufficientSymptomInfo(text) {
  const chestPainKeywords = ["胸痛", "胸闷", "胸骨后", "心前区", "胸部不适"];
  const locationKeywords = ["胸骨后", "心前区", "左肩", "左臂", "背部", "后背", "下颌", "放射"];
  const qualityKeywords = ["压榨", "压榨性", "紧缩", "窒息", "闷痛", "刺痛", "锐痛", "烧灼", "撕裂"];
  const durationKeywords = ["分钟", "小时", "天", "持续", "发作", "突发"];
  const associatedKeywords = ["大汗", "出汗", "恶心", "呕吐", "气短", "劳力后", "深呼吸", "按压", "体位改变"];

  if (!containsAny(text, chestPainKeywords)) {
    return false;
  }

  let dimensions = 0;
  if (containsAny(text, locationKeywords)) dimensions += 1;
  if (containsAny(text, qualityKeywords)) dimensions += 1;
  if (containsAny(text, durationKeywords)) dimensions += 1;
  if (containsAny(text, associatedKeywords)) dimensions += 1;

  return dimensions >= 2;
}

function hasEcgInfo(text) {
  if (containsAny(text, ["未查心电图", "未做心电图", "暂无心电图", "无心电图结果", "心电图待完善", "ECG未做"])) {
    return false;
  }
  return containsAny(text, ["心电图", "ECG", "导联", "ST段", "T波", "Q波"]);
}

function hasBiomarkerInfo(text) {
  if (containsAny(text, ["未查肌钙蛋白", "未查CK-MB", "未查心肌标志物", "暂无心肌标志物", "无肌钙蛋白结果", "标志物待完善"])) {
    return false;
  }
  return containsAny(text, ["肌钙蛋白", "cTn", "CK-MB", "心肌标志物", "troponin"]);
}

function makeFrontendHaltResult(haltStep, reason, missingItems, graphPath) {
  const diagnosis = haltStep === 1
    ? "待补充症状学信息"
    : haltStep === 2
      ? "待补充心电图检查"
      : "待补充心肌标志物检查";

  return {
    diagnosis,
    haltCategory: HALT_DIAGNOSIS,
    path: "诊断已暂停，当前证据链不完整。",
    confidence: "需补充检查",
    haltStep,
    reason,
    missingItems,
    recommendation: `请由本项目中的医生补充以下检查或信息：${missingItems.join("、")}。`,
    activeUntil: haltStep === 1 ? "ischemic" : haltStep === 2 ? "st" : "biomarker",
    graphPath,
  };
}

function inferIschemic(text) {
  const positiveKeywords = [
    "胸骨后",
    "压榨",
    "压榨性",
    "闷痛",
    "左肩",
    "放射",
    "大汗",
    "恶心",
    "持续",
    "劳力后",
    "胸闷",
    "心前区",
  ];
  const negativeKeywords = [
    "刺痛",
    "按压",
    "深呼吸",
    "转身",
    "咳嗽",
    "反酸",
    "烧灼感",
    "胸壁",
  ];
  const positiveScore = positiveKeywords.filter((item) => text.includes(item)).length;
  const negativeScore = negativeKeywords.filter((item) => text.includes(item)).length;
  return positiveScore >= 2 && positiveScore >= negativeScore;
}

function inferStElevation(text) {
  const positiveKeywords = ["ST段抬高", "ST抬高", "导联ST段抬高"];
  const negativeKeywords = ["ST段压低", "T波倒置", "心电图正常", "无明显ST段抬高"];
  if (containsAny(text, positiveKeywords)) return true;
  if (containsAny(text, negativeKeywords)) return false;
  return false;
}

function inferBiomarker(text) {
  const positiveKeywords = ["肌钙蛋白", "CK-MB", "升高", "阳性", "高于正常"];
  const negativeKeywords = ["肌钙蛋白正常", "CK-MB正常", "标志物正常", "未升高"];
  if (containsAny(text, negativeKeywords)) return false;
  if (containsAny(text, positiveKeywords) && containsAny(text, ["升高", "阳性", "ng/mL", "U/L"])) return true;
  return false;
}

function boolLabel(value, fallback = "未判定") {
  if (value === true) return "是";
  if (value === false) return "否";
  return fallback;
}

function splitTextFragments(text) {
  return String(text || "")
    .split(/[。\n；;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function pickReplayAnswer(text, roundNumber) {
  const fragments = splitTextFragments(text);
  const keywords = REPLAY_KEYWORDS[roundNumber] || [];
  const matched = fragments.filter((fragment) => keywords.some((keyword) => fragment.includes(keyword)));
  return matched.join("；") || text || "-";
}

function buildFrontendRoundGraphPath(decisions, diagnosis, roundNumber, haltStep) {
  if (roundNumber === 1) {
    if (decisions.ischemic === false) {
      return { nodes: ["start", "ischemic_no", "other"], edges: ["start->ischemic_no", "ischemic_no->other"] };
    }
    if (decisions.ischemic === true) {
      return { nodes: ["start", "ischemic_yes"], edges: ["start->ischemic_yes"] };
    }
    return { nodes: ["start"], edges: [] };
  }

  if (roundNumber === 2) {
    if (haltStep === 2 || decisions.stElevation === null || decisions.stElevation === undefined) {
      return { nodes: ["start", "ischemic_yes"], edges: ["start->ischemic_yes"] };
    }
    const targetNode = decisions.stElevation ? "st_yes" : "st_no";
    const targetEdge = decisions.stElevation ? "ischemic_yes->st_yes" : "ischemic_yes->st_no";
    return { nodes: ["start", "ischemic_yes", targetNode], edges: ["start->ischemic_yes", targetEdge] };
  }

  return getGraphPath(decisions, { diagnosis, haltStep });
}

function buildFrontendReplay(text, decisions, result) {
  const haltStep = result.haltStep || null;
  const roundCount = !decisions.ischemic ? 1 : haltStep || 3;
  const rounds = [];

  for (let roundNumber = 1; roundNumber <= roundCount; roundNumber += 1) {
    const stepResult = roundNumber === 1
      ? boolLabel(decisions.ischemic, haltStep === 1 ? "信息不足" : "未执行")
      : roundNumber === 2
        ? boolLabel(decisions.stElevation, haltStep === 2 ? "信息不足" : "未执行")
        : boolLabel(decisions.biomarkerElevated, haltStep === 3 ? "信息不足" : "未执行");

    rounds.push({
      round: roundNumber,
      stage: `第 ${roundNumber} 轮`,
      ai_question: roundNumber === 1
        ? "请补充胸痛的部位、性质、持续时间以及是否伴有放射痛、大汗、恶心等症状。"
        : roundNumber === 2
          ? "请提供心电图结果，尤其是导联范围与 ST-T 改变情况。"
          : "请提供肌钙蛋白、CK-MB 等心肌标志物检测结果。",
      user_answer: pickReplayAnswer(text, roundNumber),
      step_result: stepResult,
      graph_path: buildFrontendRoundGraphPath(decisions, result.diagnosis, roundNumber, haltStep),
      workflow_target: roundNumber === 1 ? "ischemic" : roundNumber === 2 ? "st" : "biomarker",
      note: haltStep === roundNumber ? result.reason || result.recommendation || "" : "",
    });
  }

  return {
    case_id: `frontend_${Date.now()}`,
    initial_presentation: text,
    rounds,
    final_graph_path: getGraphPath(decisions, result),
  };
}

function deriveDiagnosis({ ischemic, stElevation, biomarkerElevated }) {
  if (!ischemic) {
    return {
      diagnosis: "其他",
      path: "急性胸痛 → 非缺血性胸痛 → 其他",
      confidence: "规则直判",
      activeUntil: "final",
    };
  }

  if (stElevation && biomarkerElevated) {
    return {
      diagnosis: "STEMI",
      path: "急性胸痛 → 缺血性胸痛 → ST 段抬高 → 心肌标志物升高 → STEMI",
      confidence: "高度匹配",
      activeUntil: "final",
    };
  }

  if (stElevation && !biomarkerElevated) {
    return {
      diagnosis: "变异型心绞痛",
      path: "急性胸痛 → 缺血性胸痛 → ST 段抬高 → 心肌标志物未升高 → 变异型心绞痛",
      confidence: "高度匹配",
      activeUntil: "final",
    };
  }

  if (!stElevation && biomarkerElevated) {
    return {
      diagnosis: "NSTEMI",
      path: "急性胸痛 → 缺血性胸痛 → 非 ST 段抬高 → 心肌标志物升高 → NSTEMI",
      confidence: "高度匹配",
      activeUntil: "final",
    };
  }

  return {
    diagnosis: "UA",
    path: "急性胸痛 → 缺血性胸痛 → 非 ST 段抬高 → 心肌标志物未升高 → UA",
    confidence: "规则匹配",
    activeUntil: "final",
  };
}

function getGraphPath(decisions, result) {
  if (result && isHaltDiagnosis(result.diagnosis)) {
    if (result.haltStep === 1) {
      return { nodes: ["start"], edges: [] };
    }
    if (result.haltStep === 2) {
      return { nodes: ["start", "ischemic_yes"], edges: ["start->ischemic_yes"] };
    }
    if (result.haltStep === 3) {
      const targetNode = decisions.stElevation ? "st_yes" : "st_no";
      const targetEdge = decisions.stElevation ? "ischemic_yes->st_yes" : "ischemic_yes->st_no";
      return {
        nodes: ["start", "ischemic_yes", targetNode],
        edges: ["start->ischemic_yes", targetEdge],
      };
    }
  }

  if (!decisions.ischemic) {
    return {
      nodes: ["start", "ischemic_no", "other"],
      edges: ["start->ischemic_no", "ischemic_no->other"],
    };
  }

  if (decisions.stElevation && decisions.biomarkerElevated) {
    return {
      nodes: ["start", "ischemic_yes", "st_yes", "stemi"],
      edges: ["start->ischemic_yes", "ischemic_yes->st_yes", "st_yes->stemi"],
    };
  }

  if (decisions.stElevation && !decisions.biomarkerElevated) {
    return {
      nodes: ["start", "ischemic_yes", "st_yes", "variant"],
      edges: ["start->ischemic_yes", "ischemic_yes->st_yes", "st_yes->variant"],
    };
  }

  if (!decisions.stElevation && decisions.biomarkerElevated) {
    return {
      nodes: ["start", "ischemic_yes", "st_no", "nstemi"],
      edges: ["start->ischemic_yes", "ischemic_yes->st_no", "st_no->nstemi"],
    };
  }

  return {
    nodes: ["start", "ischemic_yes", "st_no", "ua"],
    edges: ["start->ischemic_yes", "ischemic_yes->st_no", "st_no->ua"],
  };
}

function buildReasons(text, decisions, result) {
  const reasons = [];

  if (decisions.ischemic) {
    reasons.push("症状更符合缺血性胸痛特征，存在胸骨后压榨感、放射痛、胸闷或伴随自主神经症状。");
  } else {
    reasons.push("症状更偏向非缺血性胸痛，提示需要考虑胸壁、呼吸或消化系统等其他病因。");
  }

  if (decisions.stElevation) {
    reasons.push("病历中出现 ST 段抬高线索，因此走 ST 段抬高分支。");
  } else if (decisions.ischemic) {
    reasons.push("未识别到 ST 段抬高，进入非 ST 段抬高分支。");
  }

  if (decisions.biomarkerElevated) {
    reasons.push("心肌标志物提示升高，支持存在心肌损伤。");
  } else if (decisions.ischemic) {
    reasons.push("未识别到标志物升高，需结合 ECG 与症状考虑 UA 或变异型心绞痛。");
  }

  if (!text.trim()) {
    reasons.push("当前结果主要来自结构化选择，因为病历文本为空。");
  }

  reasons.push(`最终网页规则引擎输出为 ${result.diagnosis}。`);
  return reasons;
}

function buildResultPathFromDiagnosis(diagnosis) {
  if (isHaltDiagnosis(diagnosis)) return `诊断已暂停：${diagnosis}。请补充对应检查后再继续。`;
  if (diagnosis === "其他") return "急性胸痛 → 非缺血性胸痛 → 其他";
  if (diagnosis === "STEMI") return "急性胸痛 → 缺血性胸痛 → ST 段抬高 → 心肌标志物升高 → STEMI";
  if (diagnosis === "变异型心绞痛" || diagnosis === "变异性心绞痛") return "急性胸痛 → 缺血性胸痛 → ST 段抬高 → 心肌标志物未升高 → 变异型心绞痛";
  if (diagnosis === "NSTEMI") return "急性胸痛 → 缺血性胸痛 → 非 ST 段抬高 → 心肌标志物升高 → NSTEMI";
  if (diagnosis === "UA") return "急性胸痛 → 缺血性胸痛 → 非 ST 段抬高 → 心肌标志物未升高 → UA";
  return "请结合模型输出查看诊断路径。";
}

function populateReviewDiagnosisOptions(selectedDiagnosis = "") {
  reviewDiagnosisSelect.innerHTML = REVIEW_DIAGNOSES
    .map((diagnosis) => `<option value="${diagnosis}">${diagnosis}</option>`)
    .join("");
  reviewDiagnosisSelect.value = REVIEW_DIAGNOSES.includes(selectedDiagnosis)
    ? selectedDiagnosis
    : REVIEW_DIAGNOSES[0];
}

function renderReviewHistory(reviews = []) {
  if (!reviews.length) {
    reviewHistoryList.innerHTML = '<p class="mini-note">暂无医生复核记录。</p>';
    return;
  }

  reviewHistoryList.innerHTML = reviews
    .slice()
    .reverse()
    .map(
      (review) => `
        <article class="review-item">
          <strong>${review.reviewed_diagnosis || "-"}</strong>
          <p>${review.reviewer_name || "未署名医生"} · ${review.review_action || "confirm"}</p>
          <p>${review.comment || "无复核备注"}</p>
          <span>${review.reviewed_at || ""}</span>
        </article>
      `
    )
    .join("");
}

function renderGraphVersionInfo(versionInfo = {}, history = []) {
  state.graphVersionInfo = versionInfo && Object.keys(versionInfo).length ? versionInfo : null;
  state.graphHistory = Array.isArray(history) ? history : [];

  if (!state.graphVersionInfo) {
    graphVersionBadge.textContent = "未生成";
    graphVersionMeta.textContent = "生成图谱后，这里会显示当前版本、更新时间和最新更新来源。";
    graphHistoryList.innerHTML = '<p class="mini-note">暂无更新记录。</p>';
    return;
  }

  const version = state.graphVersionInfo.graph_version || `v${state.graphVersionInfo.graph_version_number || 0}`;
  graphVersionBadge.textContent = version;
  graphVersionMeta.textContent = [
    state.graphVersionInfo.updated_at ? `更新时间：${state.graphVersionInfo.updated_at}` : "",
    state.graphVersionInfo.latest_update_type ? `更新类型：${state.graphVersionInfo.latest_update_type}` : "",
    state.graphVersionInfo.latest_source_title ? `来源：${state.graphVersionInfo.latest_source_title}` : "",
  ].filter(Boolean).join(" · ");

  if (!state.graphHistory.length) {
    graphHistoryList.innerHTML = '<p class="mini-note">暂无更新记录。</p>';
    return;
  }

  graphHistoryList.innerHTML = state.graphHistory
    .slice()
    .reverse()
    .map(
      (entry) => `
        <article class="history-item">
          <div>
            <strong>${entry.version || "-"}</strong>
            <span>${entry.updated_at || ""}</span>
          </div>
          <p>${entry.update_type || "unknown"} · ${entry.source_title || "未注明来源"}</p>
          <p>实体 ${entry.entity_count || 0} / 关系 ${entry.relation_count || 0} / 文档 ${entry.document_count || 0}</p>
        </article>
      `
    )
    .join("");
}

function formatSize(bytes = 0) {
  if (!bytes) return "0 B";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function renderTrainingStatus(data = null) {
  state.trainingStatus = data;

  if (!data) {
    trainingSummary.textContent = "这里会展示当前训练数据规模、配方文件，并支持一键重新生成训练数据。";
    trainingPatientCount.textContent = "-";
    trainingSftCount.textContent = "-";
    trainingPreferenceCount.textContent = "-";
    trainingRlCount.textContent = "-";
    trainingPrepareStatus.textContent = "后端在线后，这里会自动读取 training_data 与 training_configs。";
    trainingDatasetList.innerHTML = '<p class="mini-note">暂无训练数据状态。</p>';
    trainingRecipeList.innerHTML = '<p class="mini-note">暂无训练配方信息。</p>';
    return;
  }

  const summary = data.summary || {};
  const datasets = data.datasets || [];
  const recipes = data.recipes || [];
  const stats = data.stats || {};

  trainingSummary.textContent = `当前已整理 ${summary.generated_patients || 0} 条病例、${summary.doctor_reviews || 0} 条医生复核记录，网页可直接展示 SFT / 偏好学习 / RL 数据准备结果。`;
  trainingPatientCount.textContent = summary.generated_patients ?? 0;
  trainingSftCount.textContent = summary.sft_total ?? 0;
  trainingPreferenceCount.textContent = summary.preference_total ?? 0;
  trainingRlCount.textContent = summary.rl_total ?? 0;
  trainingPrepareStatus.textContent = `SFT ${summary.sft_total ?? 0} / 偏好 ${summary.preference_total ?? 0} / RL ${summary.rl_total ?? 0}，可直接用于论文实验设计。`;

  trainingDatasetList.innerHTML = datasets.length
    ? datasets
        .map(
          (dataset) => `
            <article class="history-item">
              <div>
                <strong>${dataset.name}</strong>
                <span>${dataset.count || 0} 条</span>
              </div>
              <p>${dataset.file || "-"}</p>
              <p>大小 ${formatSize(dataset.size_bytes || 0)}${stats[dataset.name] !== undefined ? ` · 统计值 ${stats[dataset.name]}` : ""}</p>
              ${dataset.download_url ? `<a class="dataset-link" href="${dataset.download_url}" target="_blank" rel="noreferrer">查看文件</a>` : ""}
            </article>
          `
        )
        .join("")
    : '<p class="mini-note">当前还没有生成训练数据文件。</p>';

  trainingRecipeList.innerHTML = recipes.length
    ? recipes
        .map(
          (recipe) => `
            <article class="history-item">
              <div>
                <strong>${recipe.name}</strong>
                <span>${recipe.file}</span>
              </div>
              <p>用于 SFT / 偏好学习 / RL 训练配置示例。</p>
              <a class="dataset-link" href="${recipe.download_url}" target="_blank" rel="noreferrer">查看配方</a>
            </article>
          `
        )
        .join("")
    : '<p class="mini-note">当前还没有检测到训练配方文件。</p>';
}

function renderReasoningEnhancement(data = null) {
  const preprocessing = data?.preprocessed_case || null;
  const questionGainAnalysis = data?.question_gain_analysis || null;
  const trajectoryQuality = data?.trajectory_quality || null;
  const nextQuestionRecommendations = data?.next_question_recommendations || [];
  const singleTurnReasoningSamples = data?.single_turn_reasoning_samples || [];

  if (!preprocessing) {
    preprocessSummary.textContent = "完成一次后端分析后，这里会展示 note-style sections、结构化事实和证据覆盖情况。";
    noteStyleSections.innerHTML = "";
    structuredFactsList.innerHTML = "";
  } else {
    preprocessSummary.textContent = preprocessing.summary || "已完成病例预处理。";
    const sections = preprocessing.note_style_sections || {};
    noteStyleSections.innerHTML = [
      { label: "主诉", value: sections.chief_complaint || "-" },
      { label: "现病史", value: sections.history_of_present_illness || "-" },
      { label: "心电图", value: sections.electrocardiogram || "-" },
      { label: "心肌标志物", value: sections.cardiac_biomarkers || "-" },
      { label: "工作诊断", value: sections.working_diagnosis || "-" },
    ]
      .map(
        (item) => `
          <article class="history-item">
            <div><strong>${item.label}</strong></div>
            <p>${item.value}</p>
          </article>
        `
      )
      .join("");

    const coverageEntries = ["step1", "step2", "step3"]
      .map((key) => preprocessing.coverage?.[key])
      .filter(Boolean)
      .map((item) => `
        <article class="fact-item">
          <strong>${item.label}</strong>
          <p>覆盖率：${Math.round((item.completion_ratio || 0) * 100)}%</p>
          <p>已识别：${(item.identified || []).map((fact) => fact.label).join("、") || "无"}</p>
          <p>仍缺失：${(item.missing || []).map((fact) => fact.label).join("、") || "无"}</p>
        </article>
      `);
    const factEntries = (preprocessing.structured_facts || []).slice(0, 10).map(
      (fact) => `
        <article class="fact-item">
          <strong>${fact.label}</strong>
          <p>${fact.evidence || "-"}</p>
          <span>Step ${fact.stage}</span>
        </article>
      `
    );
    structuredFactsList.innerHTML = [...coverageEntries, ...factEntries].join("");
  }

  if (!questionGainAnalysis || !trajectoryQuality) {
    trajectoryQualitySummary.textContent = "这里会显示每轮提问的 SIG-lite 分数、轨迹质量和下一问建议。";
    trajectoryQualityList.innerHTML = "";
    questionGainList.innerHTML = "";
    nextQuestionList.innerHTML = "";
  } else {
    trajectoryQualitySummary.textContent = trajectoryQuality.summary || "已完成轨迹质量评估。";
    trajectoryQualityList.innerHTML = `
      <article class="history-item">
        <div><strong>${trajectoryQuality.quality_label || "-"}</strong><span>综合得分 ${trajectoryQuality.composite_score || 0}</span></div>
        <p>步骤合规：${trajectoryQuality.step_compliance_score || 0}</p>
        <p>证据覆盖：${trajectoryQuality.coverage_score || 0}</p>
        <p>低冗余：${trajectoryQuality.redundancy_score || 0}</p>
        <p>平均 SIG-lite：${trajectoryQuality.average_sig_lite_score || 0}</p>
      </article>
    `;

    questionGainList.innerHTML = (questionGainAnalysis.rounds || [])
      .map(
        (item) => `
          <article class="history-item">
            <div><strong>第 ${item.round} 轮</strong><span>${item.quality_label || "-"}</span></div>
            <p>SIG-lite：${item.sig_lite_score || 0}</p>
            <p>${item.explanation || ""}</p>
            <p>新增事实：${(item.new_facts || []).map((fact) => fact.label).join("、") || "无"}</p>
          </article>
        `
      )
      .join("");

    nextQuestionList.innerHTML = nextQuestionRecommendations.length
      ? nextQuestionRecommendations
          .map(
            (item) => `
              <article class="history-item">
                <div><strong>${item.stage_label || "-"}</strong><span>预估增益 ${item.estimated_sig_lite_gain || 0}</span></div>
                <p>${item.question || ""}</p>
                <p>${item.rationale || ""}</p>
              </article>
            `
          )
          .join("")
      : '<p class="mini-note">当前证据链较完整，暂无额外下一问建议。</p>';
  }

  if (!singleTurnReasoningSamples.length) {
    singleTurnSampleList.innerHTML = '<p class="mini-note">完成后端分析后，这里会显示单轮推理训练样本。</p>';
    return;
  }

  singleTurnSampleList.innerHTML = singleTurnReasoningSamples
    .map(
      (sample) => `
        <article class="sample-item">
          <div class="inline-head">
            <strong>${sample.stage || "-"}</strong>
            <span>样本 ${sample.sample_id || "-"}</span>
          </div>
          <p><strong>可见上下文：</strong>${sample.visible_context || "-"}</p>
          <p><strong>目标问题：</strong>${sample.target_question || "-"}</p>
          <p><strong>预期回答：</strong>${sample.expected_patient_answer || "-"}</p>
          <p><strong>监督信号：</strong>${sample.supervision_signal?.question_value_label || "-"} / SIG-lite ${sample.supervision_signal?.sig_lite_score || 0}</p>
        </article>
      `
    )
    .join("");
}

function renderCaseReplay(caseReplay) {
  if (!caseReplay || !Array.isArray(caseReplay.rounds) || !caseReplay.rounds.length) {
    replayStatus.textContent = "完成一次分析后，这里会展示每一轮 AI 提问、患者回答和对应的知识图谱高亮。";
    caseReplayList.innerHTML = "";
    return;
  }

  replayStatus.textContent = caseReplay.initial_presentation
    ? `初始主诉：${caseReplay.initial_presentation}`
    : "可点击每一轮“查看本轮高亮”，观察知识图谱如何逐步点亮。";

  caseReplayList.innerHTML = caseReplay.rounds
    .map(
      (round) => `
        <article class="replay-card" data-round="${round.round}">
          <div class="inline-head">
            <h4>${round.stage || `第 ${round.round} 轮`}</h4>
            <span class="replay-pill">${round.step_result || "-"}</span>
          </div>
          <p><strong>AI 提问：</strong>${round.ai_question || "-"}</p>
          <p><strong>患者回答：</strong>${round.user_answer || "-"}</p>
          ${round.note ? `<p class="mini-note">${round.note}</p>` : ""}
          <button class="ghost-button replay-button" type="button" data-round="${round.round}">查看本轮高亮</button>
        </article>
      `
    )
    .join("");
}

function activateReplayRound(roundNumber) {
  const rounds = state.lastResult?.case_replay?.rounds || [];
  const round = rounds.find((item) => item.round === roundNumber);
  if (!round) return;

  replayStatus.textContent = `正在查看第 ${round.round} 轮：${round.step_result || "未执行"}`;
  renderWorkflow(round.workflow_target || "");
  renderKnowledgeGraph(round.graph_path || { nodes: [], edges: [] });

  caseReplayList.querySelectorAll(".replay-card").forEach((card) => {
    card.classList.toggle("active", Number(card.dataset.round) === round.round);
  });
}

function restoreFinalGraphHighlight() {
  if (!state.lastResult) {
    return;
  }

  const workflowTarget = state.lastResult.status === "needs_more_data"
    ? state.lastResult.halt_step === 1 ? "ischemic" : state.lastResult.halt_step === 2 ? "st" : "biomarker"
    : "final";

  replayStatus.textContent = "已恢复最终诊断高亮。";
  renderWorkflow(workflowTarget);
  renderKnowledgeGraph(state.lastResult.graph_path || state.lastResult.case_replay?.final_graph_path || { nodes: [], edges: [] });
  caseReplayList.querySelectorAll(".replay-card").forEach((card) => card.classList.remove("active"));
}

function setLastResult(result) {
  state.lastResult = result || null;
  state.lastDoctorReview = null;
  exportReportLink.innerHTML = "";
  reviewCommentInput.value = "";
  reviewActionSelect.value = "confirm";
  reviewSaveStatus.textContent = "医生复核会保存为闭环记录，可在诊断报告中一并导出。";
  populateReviewDiagnosisOptions(result?.diagnosis || "");
  renderCaseReplay(result?.case_replay || null);
  renderReasoningEnhancement(result || null);
  loadRecentReviews().catch((error) => {
    reviewHistoryList.innerHTML = `<p class="mini-note">${error.message}</p>`;
  });
  if (result?.graph_version_info || state.graphVersionInfo) {
    renderGraphVersionInfo(result.graph_version_info || state.graphVersionInfo || {}, result.graph_history || state.graphHistory || []);
  }
}

function renderMethodCards(results, fallbackDiagnosis = "-") {
  if (!results || typeof results !== "object") {
    methodCards.innerHTML = methods
      .map(
        (method) => `
          <article class="method-item">
            <span>${method.label}</span>
            <strong>${fallbackDiagnosis}</strong>
          </article>
        `
      )
      .join("");
    return;
  }

  methodCards.innerHTML = methods
    .map((method) => {
      const result = results[method.key];
      return `
        <article class="method-item">
          <span>${method.label}</span>
          <strong>${result ? result.diagnosis : "-"}</strong>
        </article>
      `;
    })
    .join("");
}

function setServerStatus(text, online = false) {
  serverStatus.textContent = text;
  serverStatus.style.color = online ? "var(--good)" : "var(--primary)";
}

function loadApiSettings() {
  apiKeyInput.value = localStorage.getItem(STORAGE_KEYS.apiKey) || "";
  baseUrlInput.value = localStorage.getItem(STORAGE_KEYS.baseUrl) || "";
  modelInput.value = localStorage.getItem(STORAGE_KEYS.model) || modelInput.value;
}

function saveApiSettings() {
  localStorage.setItem(STORAGE_KEYS.apiKey, apiKeyInput.value.trim());
  localStorage.setItem(STORAGE_KEYS.baseUrl, baseUrlInput.value.trim());
  localStorage.setItem(STORAGE_KEYS.model, modelInput.value.trim());
  setServerStatus("已保存 API 设置，可直接发起后端分析", true);
}

function clearApiSettings() {
  localStorage.removeItem(STORAGE_KEYS.apiKey);
  localStorage.removeItem(STORAGE_KEYS.baseUrl);
  localStorage.removeItem(STORAGE_KEYS.model);
  apiKeyInput.value = "";
  baseUrlInput.value = "";
  modelInput.value = "gpt-4o-mini";
  setServerStatus("已清除浏览器中的 API 设置", false);
}

function normalizeArtifactUrl(path) {
  const normalized = String(path || "").replace(/\\/g, "/");
  const workspaceIndex = normalized.indexOf("/knowledge_graph/");
  if (workspaceIndex >= 0) {
    return normalized.slice(workspaceIndex);
  }
  if (normalized.startsWith("/")) {
    return normalized;
  }
  return `/${normalized}`;
}

function renderGraphArtifacts(artifacts) {
  if (!artifacts) {
    graphArtifacts.innerHTML = "";
    graphPreviewImage.style.display = "none";
    graphPreviewImage.removeAttribute("src");
    return;
  }

  const entries = [
    { key: "graph_json", label: "专有存储格式 .ckg.json" },
    { key: "mermaid", label: "Mermaid 图文件 .mmd" },
    { key: "svg", label: "SVG 图谱图片" },
    { key: "history", label: "图谱版本历史 .history.json" },
  ].filter((item) => artifacts[item.key]);

  graphArtifacts.innerHTML = entries
    .map((item) => {
      const url = normalizeArtifactUrl(artifacts[item.key]);
      return `
        <div class="artifact-item">
          <span>${item.label}</span>
          <a href="${url}" target="_blank" rel="noreferrer">打开</a>
        </div>
      `;
    })
    .join("");

  if (artifacts.svg) {
    graphPreviewImage.src = `${normalizeArtifactUrl(artifacts.svg)}?t=${Date.now()}`;
    graphPreviewImage.style.display = "block";
  } else {
    graphPreviewImage.style.display = "none";
    graphPreviewImage.removeAttribute("src");
  }
}

async function loadKnowledgeGraphStatus() {
  const response = await fetch("/api/knowledge-graph/status");
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "知识图谱状态读取失败");
  }

  if (!data.exists) {
    renderGraphArtifacts(null);
    renderGraphVersionInfo({}, []);
    return;
  }

  renderGraphArtifacts(data.artifacts);
  renderGraphVersionInfo(data.version_info, data.history);
}

async function buildBaseKnowledgeGraph() {
  graphBuildStatus.textContent = "正在生成基础知识图谱...";
  const response = await fetch("/api/knowledge-graph/build");
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "基础知识图谱生成失败");
  }
  graphBuildStatus.textContent = data.message;
  renderGraphArtifacts(data.artifacts);
  renderGraphVersionInfo(data.version_info, data.history);
}

async function ingestMineruKnowledgeGraph() {
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
      title: mineruTitleInput.value.trim(),
      mineru_payload: mineruPayload,
    }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "MinerU 图谱合并失败");
  }
  graphBuildStatus.textContent = data.message;
  renderGraphArtifacts(data.artifacts);
  renderGraphVersionInfo(data.version_info, data.history);
}

function renderAnalysisPayload(data, reasons) {
  const diagnosis = data.diagnosis || "未知";
  const states = data.intermediate_states || {};
  const workflowTarget = data.status === "needs_more_data"
    ? data.halt_step === 1 ? "ischemic" : data.halt_step === 2 ? "st" : "biomarker"
    : data.activeUntil || "final";

  diagnosisResult.textContent = diagnosis;
  diagnosisPath.textContent = data.diagnosis_path_text || buildResultPathFromDiagnosis(diagnosis);
  confidenceChip.textContent = data.confidence_text || "已完成分析";
  ischemicResult.textContent = states.ischemic_chest_pain === undefined || states.ischemic_chest_pain === null ? (data.halt_step === 1 ? "信息不足" : "-") : boolLabel(states.ischemic_chest_pain);
  stResult.textContent = states.st_elevation === undefined || states.st_elevation === null ? (data.halt_step === 2 ? "信息不足" : "-") : boolLabel(states.st_elevation);
  biomarkerResult.textContent = states.biomarker_elevated === undefined || states.biomarker_elevated === null ? (data.halt_step === 3 ? "信息不足" : "-") : boolLabel(states.biomarker_elevated);
  reasonList.innerHTML = reasons.map((reason) => `<li>${reason}</li>`).join("");

  renderMethodCards(data.results, diagnosis);
  renderWorkflow(workflowTarget);
  renderKnowledgeGraph(data.graph_path || { nodes: [], edges: [] });
  setLastResult(data);
}

function applyFrontendResult() {
  const text = descriptionInput.value.trim();
  const symptomInfoReady = ischemicSelect.value !== "auto" || hasSufficientSymptomInfo(text);

  if (!symptomInfoReady) {
    const haltResult = makeFrontendHaltResult(
      1,
      "第一步缺少足够的胸痛症状学信息，无法判断是否为缺血性胸痛。",
      ["胸痛部位/性质/持续时间等症状学信息"],
      { nodes: ["start"], edges: [] }
    );
    const decisions = { ischemic: null, stElevation: null, biomarkerElevated: null };
    const payload = {
      case_id: `frontend_${Date.now()}`,
      patient_description: text,
      diagnosis: haltResult.diagnosis,
      status: "needs_more_data",
      primary_method: "frontend_rule",
      graph_path: haltResult.graphPath,
      intermediate_states: {
        ischemic_chest_pain: null,
        st_elevation: null,
        biomarker_elevated: null,
      },
      steps: [
        { step: 1, question: "是否为缺血性胸痛？", answer: "信息不足" },
      ],
      halt_step: 1,
      reason: haltResult.reason,
      missing_items: haltResult.missingItems,
      recommendation: haltResult.recommendation,
      diagnosis_path_text: haltResult.path,
      confidence_text: haltResult.confidence,
      results: null,
    };
    payload.case_replay = buildFrontendReplay(text, decisions, {
      diagnosis: payload.diagnosis,
      haltStep: payload.halt_step,
      reason: payload.reason,
      recommendation: payload.recommendation,
    });
    renderAnalysisPayload(payload, [haltResult.reason, haltResult.recommendation]);
    return;
  }

  const inferredIschemic = inferIschemic(text);
  const decisions = {
    ischemic: normalizeChoice(ischemicSelect.value, inferredIschemic),
    stElevation: null,
    biomarkerElevated: null,
  };

  if (decisions.ischemic) {
    const ecgReady = stSelect.value !== "auto" || hasEcgInfo(text);
    if (!ecgReady) {
      const haltResult = makeFrontendHaltResult(
        2,
        "第二步缺少心电图证据，不能判断是否存在 ST 段抬高。",
        ["心电图检查（ECG）"],
        { nodes: ["start", "ischemic_yes"], edges: ["start->ischemic_yes"] }
      );
      const payload = {
        case_id: `frontend_${Date.now()}`,
        patient_description: text,
        diagnosis: haltResult.diagnosis,
        status: "needs_more_data",
        primary_method: "frontend_rule",
        graph_path: haltResult.graphPath,
        intermediate_states: {
          ischemic_chest_pain: true,
          st_elevation: null,
          biomarker_elevated: null,
        },
        steps: [
          { step: 1, question: "是否为缺血性胸痛？", answer: "是" },
          { step: 2, question: "ST 段是否抬高？", answer: "信息不足" },
        ],
        halt_step: 2,
        reason: haltResult.reason,
        missing_items: haltResult.missingItems,
        recommendation: haltResult.recommendation,
        diagnosis_path_text: haltResult.path,
        confidence_text: haltResult.confidence,
        results: null,
      };
      payload.case_replay = buildFrontendReplay(text, decisions, {
        diagnosis: payload.diagnosis,
        haltStep: payload.halt_step,
        reason: payload.reason,
        recommendation: payload.recommendation,
      });
      renderAnalysisPayload(payload, [haltResult.reason, haltResult.recommendation]);
      return;
    }

    const inferredSt = inferStElevation(text);
    decisions.stElevation = normalizeChoice(stSelect.value, inferredSt);

    const biomarkerReady = biomarkerSelect.value !== "auto" || hasBiomarkerInfo(text);
    if (!biomarkerReady) {
      const partialGraph = getGraphPath(
        { ischemic: true, stElevation: decisions.stElevation, biomarkerElevated: false },
        { diagnosis: "待补充心肌标志物检查", haltStep: 3 }
      );
      const haltResult = makeFrontendHaltResult(
        3,
        "第三步缺少心肌标志物证据，不能完成最终诊断。",
        ["心肌标志物检查（肌钙蛋白/CK-MB）"],
        partialGraph
      );
      const payload = {
        case_id: `frontend_${Date.now()}`,
        patient_description: text,
        diagnosis: haltResult.diagnosis,
        status: "needs_more_data",
        primary_method: "frontend_rule",
        graph_path: haltResult.graphPath,
        intermediate_states: {
          ischemic_chest_pain: true,
          st_elevation: decisions.stElevation,
          biomarker_elevated: null,
        },
        steps: [
          { step: 1, question: "是否为缺血性胸痛？", answer: "是" },
          { step: 2, question: "ST 段是否抬高？", answer: boolLabel(decisions.stElevation) },
          { step: 3, question: "心肌标志物是否升高？", answer: "信息不足" },
        ],
        halt_step: 3,
        reason: haltResult.reason,
        missing_items: haltResult.missingItems,
        recommendation: haltResult.recommendation,
        diagnosis_path_text: haltResult.path,
        confidence_text: haltResult.confidence,
        results: null,
      };
      payload.case_replay = buildFrontendReplay(text, decisions, {
        diagnosis: payload.diagnosis,
        haltStep: payload.halt_step,
        reason: payload.reason,
        recommendation: payload.recommendation,
      });
      renderAnalysisPayload(payload, [haltResult.reason, haltResult.recommendation]);
      return;
    }

    const inferredBiomarker = inferBiomarker(text);
    decisions.biomarkerElevated = normalizeChoice(biomarkerSelect.value, inferredBiomarker);
  }

  const result = deriveDiagnosis(decisions);
  const reasons = buildReasons(text, decisions, result);
  const graphPath = getGraphPath(decisions, result);
  const payload = {
    case_id: `frontend_${Date.now()}`,
    patient_description: text,
    diagnosis: result.diagnosis,
    status: "completed",
    primary_method: "frontend_rule",
    graph_path: graphPath,
    intermediate_states: {
      ischemic_chest_pain: decisions.ischemic,
      st_elevation: decisions.ischemic ? decisions.stElevation : null,
      biomarker_elevated: decisions.ischemic ? decisions.biomarkerElevated : null,
    },
    steps: decisions.ischemic
      ? [
          { step: 1, question: "是否为缺血性胸痛？", answer: boolLabel(decisions.ischemic) },
          { step: 2, question: "ST 段是否抬高？", answer: boolLabel(decisions.stElevation) },
          { step: 3, question: "心肌标志物是否升高？", answer: boolLabel(decisions.biomarkerElevated) },
        ]
      : [
          { step: 1, question: "是否为缺血性胸痛？", answer: "否" },
        ],
    halt_step: null,
    reason: "",
    missing_items: [],
    recommendation: "",
    diagnosis_path_text: result.path,
    confidence_text: result.confidence,
    activeUntil: result.activeUntil,
    results: null,
  };
  payload.case_replay = buildFrontendReplay(text, decisions, {
    diagnosis: payload.diagnosis,
    haltStep: payload.halt_step,
  });

  renderAnalysisPayload(payload, reasons);
}

function buildBackendReasons(data) {
  const reasons = [];
  const steps = data.steps || [];

  if (steps.length > 0) {
    steps.forEach((step) => {
      reasons.push(`第 ${step.step} 步：${step.question} → ${step.answer}`);
    });
  }

  if (data.primary_method) {
    reasons.push(`主展示结果来自后端方法：${data.primary_method}。`);
  }

  if (data.reason) {
    reasons.push(data.reason);
  }

  if (data.recommendation) {
    reasons.push(data.recommendation);
  }

  if (data.diagnosis) {
    reasons.push(`模型最终输出诊断为 ${data.diagnosis}。`);
  }

  return reasons;
}

function applyBackendResult(data) {
  const diagnosis = data.diagnosis || "未知";
  const reasons = buildBackendReasons(data);
  const payload = {
    ...data,
    diagnosis_path_text: buildResultPathFromDiagnosis(diagnosis),
    confidence_text: data.status === "needs_more_data"
      ? "模型后端 · 已停止"
      : `模型后端 · ${data.model || modelInput.value.trim() || "默认模型"}`,
  };
  renderAnalysisPayload(payload, reasons);
}

async function checkBackendHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("health check failed");
    const data = await response.json();
    state.backendAvailable = Boolean(data.ok);
    if (data.default_model && !localStorage.getItem(STORAGE_KEYS.model) && !modelInput.value.trim()) {
      modelInput.value = data.default_model;
    }
    if (data.api_key_configured) {
      setServerStatus("后端在线，已检测到服务端默认 API 配置", true);
    } else if (data.accepts_runtime_api_settings) {
      setServerStatus("后端在线，请在网页中填写 API Key", true);
    } else {
      setServerStatus("后端在线，但未配置可用 API", false);
    }
    loadRecentReviews();
    loadTrainingStatus();
  } catch (error) {
    state.backendAvailable = false;
    renderTrainingStatus(null);
    setServerStatus("离线，当前仅可前端规则演示", false);
  }
}

async function loadRecentReviews() {
  if (!state.backendAvailable) {
    renderReviewHistory([]);
    return;
  }

  try {
    const response = await fetch("/api/reviews/recent?limit=5");
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "最近复核记录读取失败");
    }
    renderReviewHistory(data.reviews || []);
  } catch (error) {
    reviewHistoryList.innerHTML = `<p class="mini-note">${error.message}</p>`;
  }
}

async function loadTrainingStatus() {
  if (!state.backendAvailable) {
    renderTrainingStatus(null);
    return;
  }

  try {
    const response = await fetch("/api/training/status");
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "训练中心状态读取失败");
    }
    renderTrainingStatus(data);
  } catch (error) {
    trainingPrepareStatus.textContent = error.message;
  }
}

async function prepareTrainingDataArtifacts() {
  if (!state.backendAvailable) {
    throw new Error("后端未连接，无法生成训练数据。");
  }

  trainingPrepareStatus.textContent = "正在重新生成 SFT / 偏好学习 / RL 数据...";
  const response = await fetch("/api/training/prepare", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "训练数据生成失败");
  }

  renderTrainingStatus(data);
  trainingPrepareStatus.textContent = data.message;
}

async function saveDoctorReview() {
  if (!state.lastResult) {
    throw new Error("请先完成一次病例分析，再保存医生复核。");
  }
  if (!state.backendAvailable) {
    throw new Error("后端未连接，无法保存医生复核记录。");
  }

  reviewSaveStatus.textContent = "正在保存医生复核...";
  const response = await fetch("/api/review", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      case_id: state.lastResult.case_id,
      reviewer_name: reviewerNameInput.value.trim(),
      review_action: reviewActionSelect.value,
      reviewed_diagnosis: reviewDiagnosisSelect.value,
      comment: reviewCommentInput.value.trim(),
      ai_diagnosis: state.lastResult.diagnosis,
      patient_description: state.lastResult.patient_description || descriptionInput.value.trim(),
      graph_version: state.lastResult.graph_version_info?.graph_version || state.graphVersionInfo?.graph_version || "",
    }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "医生复核保存失败");
  }

  state.lastDoctorReview = data.review;
  reviewSaveStatus.textContent = data.message;
  renderReviewHistory(data.recent_reviews || [data.review]);
}

async function exportDiagnosisReport() {
  if (!state.lastResult) {
    throw new Error("请先完成一次病例分析，再导出诊断报告。");
  }
  if (!state.backendAvailable) {
    throw new Error("后端未连接，无法导出诊断报告。");
  }

  reviewSaveStatus.textContent = "正在生成诊断报告...";
  exportReportLink.innerHTML = "";

  const response = await fetch("/api/report/export", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      case_id: state.lastResult.case_id,
      patient_description: state.lastResult.patient_description || descriptionInput.value.trim(),
      diagnosis: state.lastResult.diagnosis,
      status: state.lastResult.status,
      model: state.lastResult.model || modelInput.value.trim() || "frontend-rule",
      method: state.lastResult.method || "frontend_rule",
      primary_method: state.lastResult.primary_method || "frontend_rule",
      diagnosis_path: buildResultPathFromDiagnosis(state.lastResult.diagnosis),
      steps: state.lastResult.steps || [],
      missing_items: state.lastResult.missing_items || [],
      reason: state.lastResult.reason || "",
      recommendation: state.lastResult.recommendation || "",
      case_replay: state.lastResult.case_replay || null,
      doctor_review: state.lastDoctorReview,
      graph_version_info: state.lastResult.graph_version_info || state.graphVersionInfo || {},
      preprocessed_case: state.lastResult.preprocessed_case || null,
      question_gain_analysis: state.lastResult.question_gain_analysis || null,
      trajectory_quality: state.lastResult.trajectory_quality || null,
      next_question_recommendations: state.lastResult.next_question_recommendations || [],
      single_turn_reasoning_samples: state.lastResult.single_turn_reasoning_samples || [],
    }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "诊断报告导出失败");
  }

  reviewSaveStatus.textContent = data.message;
  exportReportLink.innerHTML = `<a href="${data.download_url}" target="_blank" rel="noreferrer">打开导出的诊断报告</a>`;
}

async function runBackendDiagnosis() {
  const patientDescription = descriptionInput.value.trim();
  if (!patientDescription) {
    throw new Error("请先输入患者病历文本");
  }

  const response = await fetch("/api/diagnose", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      patient_description: patientDescription,
      model: modelInput.value.trim(),
      api_key: apiKeyInput.value.trim(),
      base_url: baseUrlInput.value.trim(),
      method: backendMethodSelect.value,
    }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "后端诊断失败");
  }

  return data;
}

async function runDiagnosis() {
  const useBackend = analysisModeSelect.value === "backend";

  if (useBackend && state.backendAvailable) {
    try {
      confidenceChip.textContent = "后端分析中...";
      const data = await runBackendDiagnosis();
      applyBackendResult(data);
      return;
    } catch (error) {
      setServerStatus("后端失败，已切换前端规则", false);
    }
  }

  applyFrontendResult();
}

function loadSample() {
  const sample = sampleCases[state.sampleIndex % sampleCases.length];
  state.sampleIndex += 1;
  descriptionInput.value = sample.description;
  ischemicSelect.value = "auto";
  stSelect.value = "auto";
  biomarkerSelect.value = "auto";
  runDiagnosis();
}

function resetForm() {
  descriptionInput.value = "";
  ischemicSelect.value = "auto";
  stSelect.value = "auto";
  biomarkerSelect.value = "auto";
  diagnosisResult.textContent = "未开始";
  diagnosisPath.textContent = "请先输入病例并点击开始分析。";
  confidenceChip.textContent = "等待分析";
  ischemicResult.textContent = "-";
  stResult.textContent = "-";
  biomarkerResult.textContent = "-";
  reasonList.innerHTML = "";
  methodCards.innerHTML = "";
  replayStatus.textContent = "完成一次分析后，这里会展示每一轮 AI 提问、患者回答和对应的知识图谱高亮。";
  caseReplayList.innerHTML = "";
  reviewCommentInput.value = "";
  reviewActionSelect.value = "confirm";
  reviewSaveStatus.textContent = "医生复核会保存为闭环记录，可在诊断报告中一并导出。";
  exportReportLink.innerHTML = "";
  state.lastResult = null;
  state.lastDoctorReview = null;
  renderReasoningEnhancement(null);
  renderWorkflow("");
  renderKnowledgeGraph();
}

document.querySelector("#run-diagnosis").addEventListener("click", () => {
  runDiagnosis();
});
document.querySelector("#load-sample").addEventListener("click", loadSample);
document.querySelector("#reset-form").addEventListener("click", resetForm);
document.querySelector("#save-api-settings").addEventListener("click", saveApiSettings);
document.querySelector("#clear-api-settings").addEventListener("click", clearApiSettings);
document.querySelector("#save-review").addEventListener("click", async () => {
  try {
    await saveDoctorReview();
  } catch (error) {
    reviewSaveStatus.textContent = error.message;
  }
});
document.querySelector("#export-report").addEventListener("click", async () => {
  try {
    await exportDiagnosisReport();
  } catch (error) {
    reviewSaveStatus.textContent = error.message;
  }
});
showFinalGraphButton.addEventListener("click", restoreFinalGraphHighlight);
caseReplayList.addEventListener("click", (event) => {
  const button = event.target.closest(".replay-button");
  if (!button) {
    return;
  }
  activateReplayRound(Number(button.dataset.round));
});
document.querySelector("#build-base-graph").addEventListener("click", async () => {
  try {
    await buildBaseKnowledgeGraph();
  } catch (error) {
    graphBuildStatus.textContent = error.message;
  }
});
document.querySelector("#ingest-mineru-graph").addEventListener("click", async () => {
  try {
    await ingestMineruKnowledgeGraph();
  } catch (error) {
    graphBuildStatus.textContent = error.message;
  }
});
document.querySelector("#prepare-training-data").addEventListener("click", async () => {
  try {
    await prepareTrainingDataArtifacts();
  } catch (error) {
    trainingPrepareStatus.textContent = error.message;
  }
});

loadApiSettings();
populateReviewDiagnosisOptions();
renderWorkflow("");
renderKnowledgeGraph();
renderReasoningEnhancement(null);
renderTrainingStatus(null);
checkBackendHealth();
loadRecentReviews();
loadKnowledgeGraphStatus().catch((error) => {
  graphVersionMeta.textContent = "后端在线后可读取知识图谱版本信息。";
});
