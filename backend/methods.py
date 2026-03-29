"""
方法实现模块 - 五种诊断方法的实现（异步版本）
"""

import os
import json
import re
import asyncio
from openai import AsyncOpenAI
from .prompts import (
    DIRECT_DIAGNOSIS_PROMPT,
    DIRECT_GENERATION_PROMPT,
    INTERMEDIATE_STATE_PROMPT,
    FULL_WORKFLOW_PROMPT,
    LLM_JUDGE_PROMPT,
    STEP1_ISCHEMIC_CHEST_PAIN_PROMPT,
    STEP2_ST_ELEVATION_PROMPT,
    STEP3_BIOMARKER_PROMPT,
    PROACTIVE_QUESTION_PROMPT,
    PROACTIVE_DIAGNOSIS_PROMPT,
    get_workflow_description
)
from .clinical_reasoning_enhancer import (
    STAGE_LABELS,
    extract_structured_facts,
    compute_combined_reward,
    build_preprocessed_case,
    build_next_question_recommendations,
)

HALT_DIAGNOSIS = "待补充检查"

CHEST_PAIN_KEYWORDS = ["胸痛", "胸闷", "胸骨后", "心前区", "胸部不适", "压榨性疼痛"]
SYMPTOM_LOCATION_KEYWORDS = ["胸骨后", "心前区", "左肩", "左臂", "背部", "后背", "下颌", "放射"]
SYMPTOM_QUALITY_KEYWORDS = ["压榨", "压榨性", "紧缩", "窒息", "闷痛", "刺痛", "锐痛", "烧灼", "撕裂"]
SYMPTOM_DURATION_KEYWORDS = ["分钟", "小时", "天", "持续", "发作", "突发"]
SYMPTOM_ASSOCIATED_KEYWORDS = ["大汗", "出汗", "恶心", "呕吐", "气短", "劳力后", "深呼吸", "按压", "体位改变"]
ECG_KEYWORDS = ["心电图", "ECG", "导联", "ST段", "T波", "Q波", "ST抬高", "ST压低"]
BIOMARKER_KEYWORDS = ["肌钙蛋白", "cTn", "CK-MB", "心肌标志物", "troponin", "肌钙蛋白I", "肌钙蛋白T"]
INSUFFICIENT_KEYWORDS = ["信息不足", "证据不足", "无法判断", "不能判断", "需补充", "未提供", "缺少", "不明确", "未查", "未做"]
ECG_MISSING_PATTERNS = ["未查心电图", "未做心电图", "暂无心电图", "无心电图结果", "心电图待完善", "ECG未做"]
BIOMARKER_MISSING_PATTERNS = ["未查肌钙蛋白", "未查CK-MB", "未查心肌标志物", "暂无心肌标志物", "无肌钙蛋白结果", "标志物待完善"]

def get_client(client_config: dict | None = None) -> AsyncOpenAI:
    """
    根据环境变量或运行时传入配置创建 OpenAI 客户端。
    """
    client_config = client_config or {}
    api_key = client_config.get("api_key") or os.getenv("OPENAI_API_KEY")
    base_url = client_config.get("base_url") or os.getenv("OPENAI_BASE_URL") or None
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


def normalize_patient_input(patient_input) -> dict:
    """
    统一患者输入格式，兼容旧版字符串病历与新版互动式病例。
    """
    if isinstance(patient_input, dict):
        interactive_case = patient_input.get("interactive_case")
        if interactive_case:
            initial_presentation = interactive_case.get("initial_presentation", "").strip()
            rounds = interactive_case.get("rounds", [])
            full_description = patient_input.get("full_description") or build_interactive_transcript(
                initial_presentation,
                rounds
            )
            return {
                "initial_presentation": initial_presentation,
                "rounds": rounds,
                "full_description": full_description
            }

        description = patient_input.get("description", "").strip()
        return {
            "initial_presentation": description,
            "rounds": [],
            "full_description": patient_input.get("full_description", description).strip()
        }

    description = str(patient_input).strip()
    return {
        "initial_presentation": description,
        "rounds": [],
        "full_description": description
    }


def build_interactive_transcript(initial_presentation: str, rounds: list, include_rounds: int | None = None) -> str:
    """
    构建逐轮问诊文本，只暴露当前已经问到的信息。
    """
    parts = [f"患者初始主诉：{initial_presentation}"]
    usable_rounds = rounds if include_rounds is None else rounds[:include_rounds]

    for round_info in usable_rounds:
        round_no = round_info.get("round", len(parts))
        doctor_question = round_info.get("doctor_question", "").strip()
        patient_answer = round_info.get("patient_answer", "").strip()
        if doctor_question:
            parts.append(f"第{round_no}轮医生提问：{doctor_question}")
        if patient_answer:
            parts.append(f"第{round_no}轮患者回答：{patient_answer}")

    return "\n".join(parts)


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def has_sufficient_symptom_info(text: str) -> bool:
    """
    判断第一步是否有足够症状学信息支持缺血性胸痛评估。
    """
    if not contains_any(text, CHEST_PAIN_KEYWORDS):
        return False

    dimensions = 0
    if contains_any(text, SYMPTOM_LOCATION_KEYWORDS):
        dimensions += 1
    if contains_any(text, SYMPTOM_QUALITY_KEYWORDS):
        dimensions += 1
    if contains_any(text, SYMPTOM_DURATION_KEYWORDS):
        dimensions += 1
    if contains_any(text, SYMPTOM_ASSOCIATED_KEYWORDS):
        dimensions += 1

    return dimensions >= 2


def has_ecg_info(text: str) -> bool:
    if contains_any(text, ECG_MISSING_PATTERNS):
        return False
    return contains_any(text, ECG_KEYWORDS)


def has_biomarker_info(text: str) -> bool:
    if contains_any(text, BIOMARKER_MISSING_PATTERNS):
        return False
    return contains_any(text, BIOMARKER_KEYWORDS)


def make_halt_result(
    method: str,
    halt_step: int,
    reason: str,
    missing_items: list[str],
    steps: list | None = None,
    intermediate_states: dict | None = None,
    interaction_trace: str = "",
    raw_response: str = ""
) -> dict:
    """
    生成“待补充检查”的标准返回结构。
    """
    if halt_step == 1:
        specific_diagnosis = "待补充症状学信息"
    elif halt_step == 2:
        specific_diagnosis = "待补充心电图检查"
    else:
        specific_diagnosis = "待补充心肌标志物检查"

    recommendation = f"请由本项目中的医生补充以下检查或信息后，再继续第{halt_step}步判断：{', '.join(missing_items)}。"
    return {
        "method": method,
        "status": "needs_more_data",
        "diagnosis": specific_diagnosis,
        "halt_category": HALT_DIAGNOSIS,
        "halt_step": halt_step,
        "reason": reason,
        "missing_items": missing_items,
        "recommendation": recommendation,
        "steps": steps or [],
        "intermediate_states": intermediate_states or {},
        "interaction_trace": interaction_trace,
        "raw_response": raw_response,
    }


def get_step_contexts(patient_case: dict) -> dict:
    """
    为三步诊断生成逐步暴露的上下文。
    """
    initial_presentation = patient_case["initial_presentation"]
    rounds = patient_case["rounds"]
    full_description = patient_case["full_description"]

    if rounds:
        return {
            "step1": build_interactive_transcript(initial_presentation, rounds, include_rounds=1),
            "step2": build_interactive_transcript(initial_presentation, rounds, include_rounds=2),
            "step3": build_interactive_transcript(initial_presentation, rounds, include_rounds=3),
        }

    return {
        "step1": full_description,
        "step2": full_description,
        "step3": full_description,
    }


async def call_llm(prompt: str, model: str = "gpt-4o-mini", client_config: dict | None = None) -> str:
    """
    调用大语言模型

    Args:
        prompt: 输入提示词
        model: 模型名称

    Returns:
        模型输出的文本
    """
    client = get_client(client_config)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一位专业的心血管内科医生，具有丰富的临床诊断经验。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=1000
    )
    return response.choices[0].message.content


def parse_diagnosis(response: str) -> str:
    """
    从模型响应中解析诊断结果

    Args:
        response: 模型输出的文本

    Returns:
        标准化的诊断结果
    """
    response = response.strip()

    if HALT_DIAGNOSIS in response or "待补充心电图检查" in response or "待补充心肌标志物检查" in response or "待补充症状学信息" in response:
        return HALT_DIAGNOSIS

    # 定义诊断关键词映射 - 注意：NSTEMI 必须在 STEMI 之前检查，因为 "STEMI" 包含在 "NSTEMI" 中
    # 使用有序检查，先检查更具体的关键词
    diagnosis_checks = [
        ("NSTEMI", ["NSTEMI", "急性非ST段抬高心肌梗死", "非ST段抬高心肌梗死", "急性非ST段抬高型心肌梗死"]),
        ("STEMI", ["STEMI", "急性ST段抬高心肌梗死", "ST段抬高心肌梗死", "急性ST段抬高型心肌梗死"]),
        ("UA", ["UA", "不稳定型心绞痛", "不稳定性心绞痛"]),
        ("变异性心绞痛", ["变异性心绞痛", "变异型心绞痛", "Prinzmetal", "血管痉挛性心绞痛"]),
        ("其他", ["其他", "非缺血性胸痛", "非心源性胸痛"])
    ]

    # 按顺序查找匹配的诊断
    for diagnosis, keywords in diagnosis_checks:
        for keyword in keywords:
            if keyword in response:
                return diagnosis

    return "未知"


async def direct_diagnosis(patient_input, model: str = "gpt-4o-mini", client_config: dict | None = None) -> dict:
    """
    直接诊断方法（带选项）

    输入患者主述，模型从选项中选择诊断结果

    Args:
        patient_input: 患者病历描述或互动式病例
        model: 使用的模型名称

    Returns:
        包含诊断结果和原始响应的字典
    """
    strict_result = await run_strict_stepwise_assessment(
        patient_input,
        model=model,
        client_config=client_config,
        method_name="direct_diagnosis"
    )
    if strict_result.get("status") == "needs_more_data" or strict_result["diagnosis"] == "其他":
        return strict_result

    patient_case = normalize_patient_input(patient_input)
    patient_description = patient_case["full_description"]
    prompt = DIRECT_DIAGNOSIS_PROMPT.format(patient_description=patient_description)
    response = await call_llm(prompt, model, client_config=client_config)
    diagnosis = parse_diagnosis(response)

    return {
        "method": "direct_diagnosis",
        "diagnosis": diagnosis,
        "raw_response": response
    }


async def direct_generation_diagnosis(patient_input, model: str = "gpt-4o-mini", client_config: dict | None = None) -> dict:
    """
    直接生成方法（不提供选项）

    输入患者主述，模型自由生成诊断结果

    Args:
        patient_input: 患者病历描述或互动式病例
        model: 使用的模型名称

    Returns:
        包含诊断结果和原始响应的字典
    """
    strict_result = await run_strict_stepwise_assessment(
        patient_input,
        model=model,
        client_config=client_config,
        method_name="direct_generation_diagnosis"
    )
    if strict_result.get("status") == "needs_more_data" or strict_result["diagnosis"] == "其他":
        return strict_result

    patient_case = normalize_patient_input(patient_input)
    patient_description = patient_case["full_description"]
    prompt = DIRECT_GENERATION_PROMPT.format(patient_description=patient_description)
    response = await call_llm(prompt, model, client_config=client_config)
    diagnosis = parse_diagnosis(response)

    return {
        "method": "direct_generation_diagnosis",
        "diagnosis": diagnosis,
        "raw_response": response
    }


async def intermediate_state_diagnosis(patient_input, model: str = "gpt-4o-mini", client_config: dict | None = None) -> dict:
    """
    中间状态方法

    输入患者主述，模型先生成缺失的过程状态，再基于过程状态判断诊断结果

    Args:
        patient_input: 患者病历描述或互动式病例
        model: 使用的模型名称

    Returns:
        包含诊断结果、中间状态和原始响应的字典
    """
    strict_result = await run_strict_stepwise_assessment(
        patient_input,
        model=model,
        client_config=client_config,
        method_name="intermediate_state_diagnosis"
    )
    if strict_result.get("status") == "needs_more_data" or strict_result["diagnosis"] == "其他":
        return strict_result

    patient_case = normalize_patient_input(patient_input)
    patient_description = patient_case["full_description"]
    prompt = INTERMEDIATE_STATE_PROMPT.format(patient_description=patient_description)
    response = await call_llm(prompt, model, client_config=client_config)
    diagnosis = parse_diagnosis(response)

    # 解析中间状态
    intermediate_states = {}
    lines = response.split('\n')
    for line in lines:
        if '缺血性胸痛' in line and ':' in line:
            intermediate_states['ischemic_chest_pain'] = '是' in line
        elif 'ST段抬高' in line and ':' in line:
            if '是' in line:
                intermediate_states['st_elevation'] = True
            elif '否' in line:
                intermediate_states['st_elevation'] = False
        elif '心肌标志物升高' in line and ':' in line:
            if '是' in line:
                intermediate_states['biomarker_elevated'] = True
            elif '否' in line:
                intermediate_states['biomarker_elevated'] = False

    return {
        "method": "intermediate_state_diagnosis",
        "diagnosis": diagnosis,
        "intermediate_states": intermediate_states,
        "raw_response": response
    }


async def full_workflow_diagnosis(patient_input, model: str = "gpt-4o-mini", client_config: dict | None = None) -> dict:
    """
    全流程方法

    输入患者主述和完整的工作流说明，模型输出诊断结果

    Args:
        patient_input: 患者病历描述或互动式病例
        model: 使用的模型名称

    Returns:
        包含诊断结果和原始响应的字典
    """
    strict_result = await run_strict_stepwise_assessment(
        patient_input,
        model=model,
        client_config=client_config,
        method_name="full_workflow_diagnosis"
    )
    if strict_result.get("status") == "needs_more_data" or strict_result["diagnosis"] == "其他":
        return strict_result

    patient_case = normalize_patient_input(patient_input)
    patient_description = patient_case["full_description"]
    workflow_description = get_workflow_description()
    prompt = FULL_WORKFLOW_PROMPT.format(
        workflow_description=workflow_description,
        patient_description=patient_description
    )
    response = await call_llm(prompt, model, client_config=client_config)
    diagnosis = parse_diagnosis(response)

    return {
        "method": "full_workflow_diagnosis",
        "diagnosis": diagnosis,
        "raw_response": response
    }


def parse_step_result(response: str, step_type: str) -> bool | None:
    """
    解析步骤判断结果

    Args:
        response: 模型输出的文本
        step_type: 步骤类型 (ischemic/st_elevation/biomarker)

    Returns:
        布尔值判断结果
    """
    response = response.strip()
    unresolved = object()
    explicit_insufficient_keywords = ["信息不足", "证据不足", "无法判断", "不能判断", "无法确定", "不能确定"]
    contextual_insufficient_keywords = INSUFFICIENT_KEYWORDS
    supplement_none_pattern = re.compile(r"(需补充信息|补充信息|需补充检查)\s*[:：]\s*(无|无需补充)\s*$")
    decision_markers = ("判断", "答案", "结论")

    if step_type == 'ischemic':
        positive_keywords = ['是缺血性胸痛', '考虑缺血性胸痛', '支持缺血性胸痛', '符合缺血性胸痛', '典型心绞痛', '典型缺血']
        negative_keywords = ['非缺血性胸痛', '不是缺血性胸痛', '不考虑缺血性胸痛', '不支持缺血性胸痛']
    elif step_type == 'st_elevation':
        positive_keywords = ['存在ST段抬高', 'ST段抬高', 'ST抬高']
        negative_keywords = ['无ST段抬高', '未见ST段抬高', '非ST段抬高', 'ST段压低', 'ST压低', 'T波倒置', '心电图正常']
    else:  # biomarker
        positive_keywords = ['心肌标志物升高', '肌钙蛋白升高', 'CK-MB升高', '存在心肌损伤', '阳性', '超过正常']
        negative_keywords = ['心肌标志物正常', '肌钙蛋白正常', 'CK-MB正常', '未升高', '阴性', '范围内']

    def has_insufficient_signal(text: str) -> bool:
        if contains_any(text, explicit_insufficient_keywords):
            return True
        if contains_any(text, contextual_insufficient_keywords):
            return supplement_none_pattern.search(text) is None
        return False

    def parse_decision_text(text: str):
        decision_text = text.strip().strip("[]【】()（）")
        if not decision_text:
            return unresolved
        if has_insufficient_signal(decision_text):
            return None
        if decision_text.startswith('是'):
            return True
        if decision_text.startswith('否'):
            return False
        if decision_text.startswith('无') and not decision_text.startswith('无法'):
            return False
        if any(keyword in decision_text for keyword in negative_keywords):
            return False
        if any(keyword in decision_text for keyword in positive_keywords):
            return True
        return unresolved

    # 只优先解析明确的结论行，避免被“需补充信息：无”这类格式字段误伤。
    for raw_line in response.splitlines():
        line = raw_line.strip()
        if not line or not any(marker in line for marker in decision_markers):
            continue

        match = re.search(r"(?:判断|答案|结论)\s*[:：]\s*([^\n\r]+)", line)
        decision_text = match.group(1) if match else line
        result = parse_decision_text(decision_text)
        if result is not unresolved:
            return result

    # 没有明确结论行时再做保守兜底。
    has_negative = any(keyword in response for keyword in negative_keywords)
    has_positive = any(keyword in response for keyword in positive_keywords)

    if has_negative and not has_positive:
        return False
    if has_positive and not has_negative:
        return True

    for raw_line in response.splitlines():
        line = raw_line.strip()
        if line and has_insufficient_signal(line):
            return None

    return None


async def run_strict_stepwise_assessment(
    patient_input,
    model: str = "gpt-4o-mini",
    client_config: dict | None = None,
    method_name: str = "step_by_step_diagnosis"
) -> dict:
    """
    严格按三步诊断链执行：
    1. 症状学
    2. 心电图
    3. 心肌标志物

    证据不全时立即停止，不允许跳步。
    """
    patient_case = normalize_patient_input(patient_input)
    contexts = get_step_contexts(patient_case)
    steps = []
    intermediate_states = {}

    if not has_sufficient_symptom_info(contexts["step1"]):
        return make_halt_result(
            method=method_name,
            halt_step=1,
            reason="第一步缺少足够的胸痛症状学信息，无法判断是否为缺血性胸痛。",
            missing_items=["胸痛部位/性质/持续时间等症状学信息"],
            interaction_trace=contexts["step1"],
        )

    step1_prompt = STEP1_ISCHEMIC_CHEST_PAIN_PROMPT.format(patient_description=contexts["step1"])
    step1_response = await call_llm(step1_prompt, model, client_config=client_config)
    is_ischemic = parse_step_result(step1_response, "ischemic")
    intermediate_states["ischemic_chest_pain"] = is_ischemic
    steps.append({
        "step": 1,
        "question": "是否为缺血性胸痛？",
        "answer": "是" if is_ischemic is True else "否" if is_ischemic is False else "信息不足",
        "raw_response": step1_response,
    })

    if is_ischemic is None:
        return make_halt_result(
            method=method_name,
            halt_step=1,
            reason="第一步无法根据现有症状信息完成缺血性胸痛判断。",
            missing_items=["更完整的症状学病史", "缺血性胸痛相关伴随症状与危险因素"],
            steps=steps,
            intermediate_states=intermediate_states,
            interaction_trace=contexts["step1"],
            raw_response=step1_response,
        )

    if is_ischemic is False:
        return {
            "method": method_name,
            "status": "completed",
            "diagnosis": "其他",
            "steps": steps,
            "intermediate_states": intermediate_states,
            "interaction_trace": contexts["step1"],
            "raw_response": step1_response,
        }

    if not has_ecg_info(contexts["step2"]):
        return make_halt_result(
            method=method_name,
            halt_step=2,
            reason="第二步缺少心电图证据，不能判断是否存在 ST 段抬高。",
            missing_items=["心电图检查（ECG）"],
            steps=steps,
            intermediate_states=intermediate_states,
            interaction_trace=contexts["step2"],
        )

    step2_prompt = STEP2_ST_ELEVATION_PROMPT.format(patient_description=contexts["step2"])
    step2_response = await call_llm(step2_prompt, model, client_config=client_config)
    st_elevation = parse_step_result(step2_response, "st_elevation")
    intermediate_states["st_elevation"] = st_elevation
    steps.append({
        "step": 2,
        "question": "ST段是否抬高？",
        "answer": "是" if st_elevation is True else "否" if st_elevation is False else "信息不足",
        "raw_response": step2_response,
    })

    if st_elevation is None:
        return make_halt_result(
            method=method_name,
            halt_step=2,
            reason="第二步无法根据现有心电图信息完成 ST 段判断。",
            missing_items=["更明确的心电图结果", "导联与 ST-T 改变描述"],
            steps=steps,
            intermediate_states=intermediate_states,
            interaction_trace=contexts["step2"],
            raw_response=step2_response,
        )

    if not has_biomarker_info(contexts["step3"]):
        return make_halt_result(
            method=method_name,
            halt_step=3,
            reason="第三步缺少心肌标志物证据，不能完成最终诊断。",
            missing_items=["心肌标志物检查（肌钙蛋白/CK-MB）"],
            steps=steps,
            intermediate_states=intermediate_states,
            interaction_trace=contexts["step3"],
        )

    st_elevation_status = "已抬高" if st_elevation else "未抬高"
    step3_prompt = STEP3_BIOMARKER_PROMPT.format(
        patient_description=contexts["step3"],
        st_elevation_status=st_elevation_status
    )
    step3_response = await call_llm(step3_prompt, model, client_config=client_config)
    biomarker_elevated = parse_step_result(step3_response, "biomarker")
    intermediate_states["biomarker_elevated"] = biomarker_elevated
    steps.append({
        "step": 3,
        "question": "心肌标志物是否升高？",
        "answer": "是" if biomarker_elevated is True else "否" if biomarker_elevated is False else "信息不足",
        "raw_response": step3_response,
    })

    if biomarker_elevated is None:
        return make_halt_result(
            method=method_name,
            halt_step=3,
            reason="第三步无法根据现有心肌标志物信息完成判断。",
            missing_items=["更完整的肌钙蛋白/CK-MB 检查结果"],
            steps=steps,
            intermediate_states=intermediate_states,
            interaction_trace=contexts["step3"],
            raw_response=step3_response,
        )

    if st_elevation and biomarker_elevated:
        diagnosis = "STEMI"
    elif st_elevation and not biomarker_elevated:
        diagnosis = "变异性心绞痛"
    elif not st_elevation and biomarker_elevated:
        diagnosis = "NSTEMI"
    else:
        diagnosis = "UA"

    return {
        "method": method_name,
        "status": "completed",
        "diagnosis": diagnosis,
        "steps": steps,
        "intermediate_states": intermediate_states,
        "interaction_trace": f"{contexts['step1']}\n\n{contexts['step2']}\n\n{contexts['step3']}",
        "raw_response": f"步骤1: {step1_response}\n\n步骤2: {step2_response}\n\n步骤3: {step3_response}",
    }


async def step_by_step_diagnosis(patient_input, model: str = "gpt-4o-mini", client_config: dict | None = None) -> dict:
    """
    多轮引导方法（逐步引导）

    逐步引导模型思考，每一步只判断一个节点：
    1. 判断是否为缺血性胸痛
    2. 判断心电图ST段是否抬高（如果是缺血性胸痛）
    3. 判断心肌标志物是否升高

    Args:
        patient_input: 患者病历描述或互动式病例
        model: 使用的模型名称

    Returns:
        包含诊断结果、各步骤结果和原始响应的字典
    """
    return await run_strict_stepwise_assessment(
        patient_input,
        model=model,
        client_config=client_config,
        method_name="step_by_step_diagnosis"
    )


async def run_all_methods(patient_input, model: str = "gpt-4o-mini", client_config: dict | None = None) -> dict:
    """
    运行所有五种诊断方法（并发执行）

    Args:
        patient_input: 患者病历描述或互动式病例
        model: 使用的模型名称

    Returns:
        包含五种方法结果的字典
    """
    strict_result = await step_by_step_diagnosis(
        patient_input,
        model=model,
        client_config=client_config
    )

    if strict_result.get("status") == "needs_more_data" or strict_result["diagnosis"] == "其他":
        return {
            "direct": dict(strict_result, method="direct_diagnosis"),
            "direct_generation": dict(strict_result, method="direct_generation_diagnosis"),
            "intermediate_state": dict(strict_result, method="intermediate_state_diagnosis"),
            "full_workflow": dict(strict_result, method="full_workflow_diagnosis"),
            "step_by_step": strict_result,
        }

    # 并发运行其余四种方法，逐步法复用 strict_result
    results = await asyncio.gather(
        direct_diagnosis(patient_input, model, client_config=client_config),
        direct_generation_diagnosis(patient_input, model, client_config=client_config),
        intermediate_state_diagnosis(patient_input, model, client_config=client_config),
        full_workflow_diagnosis(patient_input, model, client_config=client_config)
    )

    return {
        "direct": results[0],
        "direct_generation": results[1],
        "intermediate_state": results[2],
        "full_workflow": results[3],
        "step_by_step": strict_result
    }


async def llm_judge_evaluate(
    patient_description: str,
    ground_truth: str,
    model_prediction: str,
    judge_model: str = "gpt-4o-mini",
    client_config: dict | None = None
) -> dict:
    """
    使用LLM-as-Judge评估诊断结果

    Args:
        patient_description: 患者病历描述
        ground_truth: 正确诊断
        model_prediction: 模型输出的诊断
        judge_model: 用于评估的模型名称

    Returns:
        包含判断结果和理由的字典
    """
    prompt = LLM_JUDGE_PROMPT.format(
        patient_description=patient_description,
        ground_truth=ground_truth,
        model_prediction=model_prediction
    )

    client = get_client(client_config)
    response = await client.chat.completions.create(
        model=judge_model,
        messages=[
            {"role": "system", "content": "你是一位资深的心血管内科专家，负责评估诊断结果的准确性。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=500
    )

    judge_response = response.choices[0].message.content

    # 解析判断结果 - 支持多种格式
    # 格式可能是：判断：正确 或 判断：[正确] 或 判断: 正确
    # 使用正则匹配判断结果
    match = re.search(r'判断[：:]\s*\[?\s*正确\s*\]?', judge_response)
    is_correct = match is not None and "错误" not in match.group(0)

    return {
        "is_correct": is_correct,
        "judge_response": judge_response,
        "ground_truth": ground_truth,
        "model_prediction": model_prediction
    }


# ---------------------------------------------------------------------------
# 主动问诊方法（融合 ProMed + Note2Chat）
# ---------------------------------------------------------------------------

STEP_LABELS = {1: "症状与病史", 2: "心电图", 3: "心肌标志物"}


def parse_think_block(response: str) -> tuple[dict[str, str], str]:
    """
    解析 LLM 响应中的 <think>...</think> 推理块与问题文本。

    Returns:
        (think_block_dict, question_text)
    """
    import re as _re

    think_block: dict[str, str] = {"summary": "", "plan": ""}
    question_text = response.strip()

    think_match = _re.search(r"<think>(.*?)</think>", response, _re.DOTALL)
    if think_match:
        block = think_match.group(1).strip()
        summary_match = _re.search(r"Summary[:：]\s*(.+?)(?=Plan[:：]|$)", block, _re.DOTALL)
        plan_match = _re.search(r"Plan[:：]\s*(.+?)$", block, _re.DOTALL)
        if summary_match:
            think_block["summary"] = summary_match.group(1).strip()
        if plan_match:
            think_block["plan"] = plan_match.group(1).strip()
        question_text = response[think_match.end():].strip()

    # 提取 "问题：" 后面的内容
    q_match = _re.search(r"问题[:：]\s*(.+?)$", question_text, _re.DOTALL)
    if q_match:
        question_text = q_match.group(1).strip()

    return think_block, question_text


def _build_collected_info_text(session) -> str:
    """从会话历史构建已收集信息的文本摘要。"""
    parts = [f"患者初始主诉：{session.patient_input}"]
    turn = 0
    for entry in session.conversation_history:
        if entry["role"] == "doctor":
            parts.append(f"\n医生追问：{entry['content']}")
        elif entry["role"] == "patient":
            turn += 1
            parts.append(f"患者回答（第{turn}轮）：{entry['content']}")
    return "\n".join(parts)


def _build_completed_judgments_text(session) -> str:
    """构建已完成判断的文本。"""
    judgments = []
    states = session.intermediate_states
    if "ischemic_chest_pain" in states:
        val = states["ischemic_chest_pain"]
        judgments.append(f"第1步（缺血性胸痛）：{'是' if val else '否'}")
    if "st_elevation" in states:
        val = states["st_elevation"]
        judgments.append(f"第2步（ST段抬高）：{'是' if val else '否'}")
    if "biomarker_elevated" in states:
        val = states["biomarker_elevated"]
        judgments.append(f"第3步（标志物升高）：{'是' if val else '否'}")
    return "；".join(judgments) if judgments else "尚未完成任何步骤的判断"


def _build_missing_info_text(halt_step: int, missing_items: list[str]) -> str:
    """构建缺失信息的文本。"""
    step_label = STEP_LABELS.get(halt_step, f"第{halt_step}步")
    items = "、".join(missing_items) if missing_items else "相关临床信息"
    return f"当前第{halt_step}步（{step_label}）需要：{items}"


async def generate_proactive_question(
    session,
    halt_step: int,
    missing_items: list[str],
    model: str = "gpt-4o-mini",
    client_config: dict | None = None,
) -> dict:
    """
    使用 LLM 生成主动追问，包含 <think> 推理块（Note2Chat 风格）。
    """
    collected_info = _build_collected_info_text(session)
    step_label = STEP_LABELS.get(halt_step, f"第{halt_step}步")
    completed_judgments = _build_completed_judgments_text(session)
    missing_info = _build_missing_info_text(halt_step, missing_items)

    # 使用增强 SIG 推荐补充所需事实
    preprocessed = build_preprocessed_case(
        {"initial_presentation": session.patient_input, "rounds": [], "full_description": session.build_accumulated_text()},
        session.diagnosis or "",
    )
    recommendations = build_next_question_recommendations(preprocessed, halt_step=halt_step)
    required_facts_text = "\n".join(
        f"- {rec['question']}（预计信息增益 {rec['estimated_sig_lite_gain']}）"
        for rec in recommendations[:3]
    ) if recommendations else "- 需要补充当前步骤的关键临床证据"

    prompt = PROACTIVE_QUESTION_PROMPT.format(
        collected_info=collected_info,
        current_step=halt_step,
        step_label=step_label,
        completed_judgments=completed_judgments,
        missing_info=missing_info,
        required_facts=required_facts_text,
    )

    response = await call_llm(prompt, model, client_config=client_config)
    think_block, question_text = parse_think_block(response)

    # 如果解析失败，使用推荐问题作为兜底
    if not question_text and recommendations:
        question_text = recommendations[0]["question"]
        think_block = {
            "summary": f"已收集到患者主诉和{session.turn_count}轮追问信息。",
            "plan": f"当前需补充第{halt_step}步（{step_label}）的关键信息。",
        }

    # 计算该问题的 SIG 增强评分
    existing_fact_ids = set(session.collected_facts.keys())
    sig_result = compute_combined_reward(
        new_facts=[],  # 问题尚未回答，预估分数
        existing_fact_ids=existing_fact_ids,
        current_step=halt_step,
        question_stage=halt_step,
        turn_number=session.turn_count,
        max_turns=session.max_turns,
    )

    return {
        "question": question_text,
        "think_block": think_block,
        "sig_score": sig_result["total_score"],
        "sig_components": sig_result["components"],
        "raw_response": response,
    }


async def proactive_diagnosis(
    patient_input,
    model: str = "gpt-4o-mini",
    client_config: dict | None = None,
    session=None,
) -> dict:
    """
    主动问诊诊断方法。

    复用三步诊断链，当信息不足时主动生成追问而非停止。
    融合 ProMed（SIG 奖励引导）与 Note2Chat（<think> 单轮推理）。
    """
    from .proactive_session import ProactiveSession

    # 如果有 session，用累积文本作为输入
    if session is not None:
        accumulated = session.build_accumulated_text()
        effective_input = {"description": accumulated, "full_description": accumulated}
    else:
        effective_input = patient_input

    # 运行标准三步诊断链
    result = await run_strict_stepwise_assessment(
        effective_input,
        model=model,
        client_config=client_config,
        method_name="proactive_diagnosis",
    )

    # 如果诊断完成，更新 session 并返回
    if result.get("status") == "completed":
        if session is not None:
            session.status = "completed"
            session.diagnosis = result["diagnosis"]
            session.diagnosis_detail = result
            session.steps = result.get("steps", [])
            session.intermediate_states = result.get("intermediate_states", {})
        return {
            "method": "proactive_diagnosis",
            "status": "completed",
            "session_id": session.session_id if session else None,
            "turn": session.turn_count if session else 0,
            "diagnosis": result["diagnosis"],
            "steps": result.get("steps", []),
            "intermediate_states": result.get("intermediate_states", {}),
            "raw_response": result.get("raw_response", ""),
        }

    # 需要更多数据 → 生成主动追问
    if result.get("status") == "needs_more_data" and session is not None:
        halt_step = result.get("halt_step", 1)
        missing_items = result.get("missing_items", [])

        # 更新 session 的中间状态
        session.current_step = halt_step
        session.steps = result.get("steps", session.steps)
        session.intermediate_states.update(result.get("intermediate_states", {}))

        # 更新已收集事实
        accumulated_text = session.build_accumulated_text()
        facts = extract_structured_facts(accumulated_text)
        session.collected_facts = {f["id"]: f["evidence"] for f in facts}

        # 检查是否达到最大轮数
        if session.turn_count >= session.max_turns:
            session.status = "max_turns_reached"
            return {
                "method": "proactive_diagnosis",
                "status": "max_turns_reached",
                "session_id": session.session_id,
                "turn": session.turn_count,
                "current_step": halt_step,
                "steps": session.steps,
                "intermediate_states": session.intermediate_states,
                "collected_facts": session.collected_facts,
                "message": f"已达到最大追问轮数（{session.max_turns}轮），但信息仍不足以完成诊断。",
                "missing_items": missing_items,
            }

        # 生成主动追问
        question_result = await generate_proactive_question(
            session=session,
            halt_step=halt_step,
            missing_items=missing_items,
            model=model,
            client_config=client_config,
        )

        # 记录医生追问
        session.append_doctor_turn(
            question=question_result["question"],
            think_block=question_result["think_block"],
            sig_score=question_result["sig_score"],
        )

        return {
            "method": "proactive_diagnosis",
            "status": "questioning",
            "session_id": session.session_id,
            "turn": session.turn_count,
            "current_step": halt_step,
            "question": question_result["question"],
            "think_block": question_result["think_block"],
            "sig_score": question_result["sig_score"],
            "sig_components": question_result.get("sig_components", {}),
            "collected_facts": session.collected_facts,
            "missing_items": missing_items,
            "steps": session.steps,
            "intermediate_states": session.intermediate_states,
        }

    # 无 session 的兜底：直接返回原始结果
    return result


if __name__ == "__main__":
    # 测试代码
    from dotenv import load_dotenv
    load_dotenv()

    async def test():
        test_patient = """
患者姓名：张三
年龄：65岁
性别：男
主诉：胸痛2小时，伴左肩放射痛

现病史：
患者2小时前无明显诱因出现胸骨后压榨性疼痛，疼痛向左肩、左上肢放射，伴出汗、恶心，休息后症状不缓解。既往有高血压病史10年，糖尿病病史5年。

既往史：
- 高血压病史10年，规律服用降压药，血压控制尚可
- 2型糖尿病病史5年，口服降糖药治疗
- 吸烟史30年，每日20支

家族史：
父亲有冠心病史，60岁发生心肌梗死

体格检查：
BP 150/90mmHg，HR 98次/分，R 20次/分，神志清楚，痛苦面容，双肺呼吸音清，未闻及干湿啰音，心界不大，心率98次/分，律齐，各瓣膜听诊区未闻及病理性杂音。

辅助检查：
心电图：V1-V4导联ST段弓背向上抬高0.3mV
肌钙蛋白I：2.5 ng/mL（升高）
CK-MB：85 U/L（升高）
"""

        result = await run_all_methods(test_patient)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(test())
