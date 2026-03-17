"""
方法实现模块 - 五种诊断方法的实现（异步版本）
"""

import os
import json
import re
import asyncio
from openai import AsyncOpenAI
from prompts import (
    DIRECT_DIAGNOSIS_PROMPT,
    DIRECT_GENERATION_PROMPT,
    INTERMEDIATE_STATE_PROMPT,
    FULL_WORKFLOW_PROMPT,
    LLM_JUDGE_PROMPT,
    STEP1_ISCHEMIC_CHEST_PAIN_PROMPT,
    STEP2_ST_ELEVATION_PROMPT,
    STEP3_BIOMARKER_PROMPT,
    get_workflow_description
)

# 初始化异步OpenAI客户端
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))


async def call_llm(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    调用大语言模型

    Args:
        prompt: 输入提示词
        model: 模型名称

    Returns:
        模型输出的文本
    """
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


async def direct_diagnosis(patient_description: str, model: str = "gpt-4o-mini") -> dict:
    """
    直接诊断方法（带选项）

    输入患者主述，模型从选项中选择诊断结果

    Args:
        patient_description: 患者病历描述
        model: 使用的模型名称

    Returns:
        包含诊断结果和原始响应的字典
    """
    prompt = DIRECT_DIAGNOSIS_PROMPT.format(patient_description=patient_description)
    response = await call_llm(prompt, model)
    diagnosis = parse_diagnosis(response)

    return {
        "method": "direct_diagnosis",
        "diagnosis": diagnosis,
        "raw_response": response
    }


async def direct_generation_diagnosis(patient_description: str, model: str = "gpt-4o-mini") -> dict:
    """
    直接生成方法（不提供选项）

    输入患者主述，模型自由生成诊断结果

    Args:
        patient_description: 患者病历描述
        model: 使用的模型名称

    Returns:
        包含诊断结果和原始响应的字典
    """
    prompt = DIRECT_GENERATION_PROMPT.format(patient_description=patient_description)
    response = await call_llm(prompt, model)
    diagnosis = parse_diagnosis(response)

    return {
        "method": "direct_generation_diagnosis",
        "diagnosis": diagnosis,
        "raw_response": response
    }


async def intermediate_state_diagnosis(patient_description: str, model: str = "gpt-4o-mini") -> dict:
    """
    中间状态方法

    输入患者主述，模型先生成缺失的过程状态，再基于过程状态判断诊断结果

    Args:
        patient_description: 患者病历描述
        model: 使用的模型名称

    Returns:
        包含诊断结果、中间状态和原始响应的字典
    """
    prompt = INTERMEDIATE_STATE_PROMPT.format(patient_description=patient_description)
    response = await call_llm(prompt, model)
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


async def full_workflow_diagnosis(patient_description: str, model: str = "gpt-4o-mini") -> dict:
    """
    全流程方法

    输入患者主述和完整的工作流说明，模型输出诊断结果

    Args:
        patient_description: 患者病历描述
        model: 使用的模型名称

    Returns:
        包含诊断结果和原始响应的字典
    """
    workflow_description = get_workflow_description()
    prompt = FULL_WORKFLOW_PROMPT.format(
        workflow_description=workflow_description,
        patient_description=patient_description
    )
    response = await call_llm(prompt, model)
    diagnosis = parse_diagnosis(response)

    return {
        "method": "full_workflow_diagnosis",
        "diagnosis": diagnosis,
        "raw_response": response
    }


def parse_step_result(response: str, step_type: str) -> bool:
    """
    解析步骤判断结果

    Args:
        response: 模型输出的文本
        step_type: 步骤类型 (ischemic/st_elevation/biomarker)

    Returns:
        布尔值判断结果
    """
    response = response.strip()

    # 查找判断行的内容
    for line in response.split('\n'):
        if '判断' in line or '答案' in line:
            # 检查是否包含"是"
            if '是' in line and ('否' not in line or line.index('是') < line.index('否')):
                return True
            elif '否' in line:
                return False

    # 如果没有明确的判断行，尝试从整个响应中推断
    if step_type == 'ischemic':
        positive_keywords = ['是缺血性', '缺血性胸痛', '典型心绞痛', '典型缺血']
        negative_keywords = ['非缺血性', '否', '不是缺血', '不考虑缺血']
    elif step_type == 'st_elevation':
        positive_keywords = ['ST段抬高', 'ST抬高', '抬高']
        negative_keywords = ['ST段压低', '非ST段抬高', 'ST压低', 'T波倒置', '正常']
    else:  # biomarker
        positive_keywords = ['升高', '增高', '阳性', '超过正常']
        negative_keywords = ['正常', '未升高', '阴性', '范围内']

    for keyword in positive_keywords:
        if keyword in response:
            return True
    for keyword in negative_keywords:
        if keyword in response:
            return False

    return False


async def step_by_step_diagnosis(patient_description: str, model: str = "gpt-4o-mini") -> dict:
    """
    多轮引导方法（逐步引导）

    逐步引导模型思考，每一步只判断一个节点：
    1. 判断是否为缺血性胸痛
    2. 判断心电图ST段是否抬高（如果是缺血性胸痛）
    3. 判断心肌标志物是否升高

    Args:
        patient_description: 患者病历描述
        model: 使用的模型名称

    Returns:
        包含诊断结果、各步骤结果和原始响应的字典
    """
    steps = []  # 记录每一步的结果

    # 步骤1：判断是否为缺血性胸痛
    step1_prompt = STEP1_ISCHEMIC_CHEST_PAIN_PROMPT.format(patient_description=patient_description)
    step1_response = await call_llm(step1_prompt, model)
    is_ischemic = parse_step_result(step1_response, 'ischemic')

    steps.append({
        "step": 1,
        "question": "是否为缺血性胸痛？",
        "answer": "是" if is_ischemic else "否",
        "raw_response": step1_response
    })

    # 如果不是缺血性胸痛，直接诊断为"其他"
    if not is_ischemic:
        return {
            "method": "step_by_step_diagnosis",
            "diagnosis": "其他",
            "steps": steps,
            "raw_response": step1_response
        }

    # 步骤2：判断ST段是否抬高
    step2_prompt = STEP2_ST_ELEVATION_PROMPT.format(patient_description=patient_description)
    step2_response = await call_llm(step2_prompt, model)
    st_elevation = parse_step_result(step2_response, 'st_elevation')

    steps.append({
        "step": 2,
        "question": "ST段是否抬高？",
        "answer": "是" if st_elevation else "否",
        "raw_response": step2_response
    })

    # 步骤3：判断心肌标志物是否升高
    st_elevation_status = "已抬高" if st_elevation else "未抬高"
    step3_prompt = STEP3_BIOMARKER_PROMPT.format(
        patient_description=patient_description,
        st_elevation_status=st_elevation_status
    )
    step3_response = await call_llm(step3_prompt, model)
    biomarker_elevated = parse_step_result(step3_response, 'biomarker')

    steps.append({
        "step": 3,
        "question": "心肌标志物是否升高？",
        "answer": "是" if biomarker_elevated else "否",
        "raw_response": step3_response
    })

    # 根据步骤2和步骤3的结果确定诊断
    if st_elevation and biomarker_elevated:
        diagnosis = "STEMI"
    elif st_elevation and not biomarker_elevated:
        diagnosis = "变异性心绞痛"
    elif not st_elevation and biomarker_elevated:
        diagnosis = "NSTEMI"
    else:
        diagnosis = "UA"

    return {
        "method": "step_by_step_diagnosis",
        "diagnosis": diagnosis,
        "steps": steps,
        "intermediate_states": {
            "ischemic_chest_pain": is_ischemic,
            "st_elevation": st_elevation,
            "biomarker_elevated": biomarker_elevated
        },
        "raw_response": f"步骤1: {step1_response}\n\n步骤2: {step2_response}\n\n步骤3: {step3_response}"
    }


async def run_all_methods(patient_description: str, model: str = "gpt-4o-mini") -> dict:
    """
    运行所有五种诊断方法（并发执行）

    Args:
        patient_description: 患者病历描述
        model: 使用的模型名称

    Returns:
        包含五种方法结果的字典
    """
    # 并发运行五种方法
    results = await asyncio.gather(
        direct_diagnosis(patient_description, model),
        direct_generation_diagnosis(patient_description, model),
        intermediate_state_diagnosis(patient_description, model),
        full_workflow_diagnosis(patient_description, model),
        step_by_step_diagnosis(patient_description, model)
    )

    return {
        "direct": results[0],
        "direct_generation": results[1],
        "intermediate_state": results[2],
        "full_workflow": results[3],
        "step_by_step": results[4]
    }


async def llm_judge_evaluate(
    patient_description: str,
    ground_truth: str,
    model_prediction: str,
    judge_model: str = "gpt-4o-mini"
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