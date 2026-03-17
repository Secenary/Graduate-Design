"""
数据生成脚本 - 基于transitions.json工作流生成伪造患者数据（异步版本）
"""

import os
import json
import random
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 初始化异步OpenAI客户端
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

# 并发限制信号量（限制同时进行的API请求数量）
MAX_CONCURRENT_REQUESTS = 10

# 定义诊断路径
DIAGNOSIS_PATHS = {
    "STEMI": {
        "path": ["node_01", "node_02", "node_03", "node_05", "node_06", "node_08", "node_10", "node_14"],
        "description": "急性胸痛 → 缺血性胸痛 → ST段抬高 → 心肌标志物升高 → STEMI",
        "key_findings": "心电图显示ST段抬高，心肌损伤标志物（肌钙蛋白、CK-MB）升高"
    },
    "变异性心绞痛": {
        "path": ["node_01", "node_02", "node_03", "node_05", "node_06", "node_08", "node_11", "node_15"],
        "description": "急性胸痛 → 缺血性胸痛 → ST段抬高 → 心肌标志物未升高 → 变异性心绞痛",
        "key_findings": "心电图显示ST段一过性抬高，心肌损伤标志物未升高"
    },
    "NSTEMI": {
        "path": ["node_01", "node_02", "node_03", "node_05", "node_07", "node_09", "node_12", "node_16"],
        "description": "急性胸痛 → 缺血性胸痛 → 非ST段抬高 → 心肌标志物升高 → NSTEMI",
        "key_findings": "心电图显示非ST段抬高（ST段压低或T波改变），心肌损伤标志物升高"
    },
    "UA": {
        "path": ["node_01", "node_02", "node_03", "node_05", "node_07", "node_09", "node_13", "node_17"],
        "description": "急性胸痛 → 缺血性胸痛 → 非ST段抬高 → 心肌标志物未升高 → UA",
        "key_findings": "心电图显示非ST段抬高，心肌损伤标志物未升高"
    },
    "其他": {
        "path": ["node_01", "node_02", "node_04", "node_18"],
        "description": "急性胸痛 → 非缺血性胸痛 → 其他",
        "key_findings": "胸痛特征不符合典型心绞痛，需考虑其他病因"
    }
}

# 患者姓名池
FIRST_NAMES = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴",
               "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗"]
LAST_NAMES = ["伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "军",
              "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "秀兰", "霞"]

# 症状描述模板
CHEST_PAIN_DESCRIPTIONS = {
    "STEMI": [
        "胸骨后剧烈压榨性疼痛，持续不缓解",
        "突发心前区撕裂样疼痛，伴大汗淋漓",
        "胸骨后持续压榨感，向左肩背部放射",
        "剧烈胸痛伴濒死感，持续超过30分钟"
    ],
    "变异性心绞痛": [
        "静息状态下突发胸痛，多在夜间或清晨发作",
        "无明显诱因出现胸骨后疼痛，持续时间较短",
        "休息时胸痛发作，活动后反而缓解",
        "夜间阵发性胸痛，伴出汗"
    ],
    "NSTEMI": [
        "胸骨后闷痛，伴有心悸气短",
        "心前区压迫感，持续20-30分钟",
        "胸痛伴出汗，程度较STEMI轻",
        "胸闷气短，伴左上肢麻木"
    ],
    "UA": [
        "新发胸痛，程度较轻但逐渐加重",
        "原有心绞痛发作频率增加，持续时间延长",
        "轻微活动即出现胸痛",
        "静息时偶有胸痛发作"
    ],
    "其他": [
        "胸痛伴咳嗽，深呼吸时加重",
        "胸骨后烧灼感，与进食相关",
        "胸痛伴反酸嗳气，平卧时加重",
        "胸部刺痛，位置不固定，持续时间短暂"
    ]
}

# 心电图描述
ECG_FINDINGS = {
    "STEMI": [
        "V1-V4导联ST段弓背向上抬高0.3mV",
        "II、III、aVF导联ST段抬高0.2mV",
        "V3-V5导联ST段抬高0.25mV，伴病理性Q波",
        "广泛前壁导联ST段抬高0.4mV"
    ],
    "变异性心绞痛": [
        "发作时V1-V3导联ST段抬高0.2mV，缓解后恢复正常",
        "II、III、aVF导联ST段一过性抬高",
        "发作时前壁导联ST段抬高，缓解后恢复",
        "胸导联ST段短暂抬高后恢复正常"
    ],
    "NSTEMI": [
        "V4-V6导联ST段水平压低0.15mV，T波倒置",
        "II、III、aVF导联ST段下斜型压低0.1mV",
        "广泛导联ST段压低，以V4-V6为著",
        "前壁导联T波深倒置，伴ST段压低"
    ],
    "UA": [
        "V4-V6导联ST段水平压低0.1mV",
        "II、III、aVF导联ST段压低0.08mV",
        "前壁导联T波低平或倒置",
        "心电图大致正常或轻度ST-T改变"
    ],
    "其他": [
        "心电图正常",
        "窦性心动过速，余未见明显异常",
        "非特异性ST-T改变",
        "偶发房性早搏"
    ]
}

# 心肌标志物结果
BIOMARKER_RESULTS = {
    "STEMI": [
        "肌钙蛋白I：2.5 ng/mL（升高，正常值<0.04 ng/mL），CK-MB：85 U/L（升高，正常值<25 U/L）",
        "肌钙蛋白T：1.8 ng/mL（升高），CK-MB：92 U/L（升高）",
        "肌钙蛋白I：3.2 ng/mL（升高），CK-MB：78 U/L（升高）",
        "肌钙蛋白T：2.1 ng/mL（升高），CK-MB：105 U/L（升高）"
    ],
    "变异性心绞痛": [
        "肌钙蛋白I：0.02 ng/mL（正常），CK-MB：18 U/L（正常）",
        "肌钙蛋白T：<0.01 ng/mL（正常），CK-MB：15 U/L（正常）",
        "肌钙蛋白I：0.01 ng/mL（正常），CK-MB：20 U/L（正常）",
        "肌钙蛋白T：0.02 ng/mL（正常），CK-MB：16 U/L（正常）"
    ],
    "NSTEMI": [
        "肌钙蛋白I：0.8 ng/mL（升高），CK-MB：45 U/L（升高）",
        "肌钙蛋白T：0.5 ng/mL（升高），CK-MB：38 U/L（升高）",
        "肌钙蛋白I：0.6 ng/mL（升高），CK-MB：52 U/L（升高）",
        "肌钙蛋白T：0.9 ng/mL（升高），CK-MB：42 U/L（升高）"
    ],
    "UA": [
        "肌钙蛋白I：0.02 ng/mL（正常），CK-MB：18 U/L（正常）",
        "肌钙蛋白T：<0.01 ng/mL（正常），CK-MB：20 U/L（正常）",
        "肌钙蛋白I：0.01 ng/mL（正常），CK-MB：22 U/L（正常）",
        "肌钙蛋白T：0.02 ng/mL（正常），CK-MB：15 U/L（正常）"
    ],
    "其他": [
        "肌钙蛋白I：<0.01 ng/mL（正常），CK-MB：12 U/L（正常）",
        "肌钙蛋白T：<0.01 ng/mL（正常），CK-MB：15 U/L（正常）",
        "肌钙蛋白I：正常范围，CK-MB：正常范围",
        "心肌标志物均在正常范围内"
    ]
}


def generate_patient_case(diagnosis: str, index: int) -> dict:
    """
    使用大语言模型生成患者病例（同步版本，已弃用）

    Args:
        diagnosis: 诊断类型
        index: 患者序号

    Returns:
        包含患者信息的字典
    """
    path_info = DIAGNOSIS_PATHS[diagnosis]

    # 随机生成患者基本信息
    age = random.randint(45, 80)
    gender = random.choice(["男", "女"])
    name = f"{random.choice(FIRST_NAMES)}{random.choice(LAST_NAMES)}"

    # 根据诊断类型调整典型年龄
    if diagnosis == "STEMI":
        age = random.randint(50, 75)
    elif diagnosis == "变异性心绞痛":
        age = random.randint(40, 65)
    elif diagnosis == "其他":
        age = random.randint(25, 70)

    # 选择症状、心电图、标志物描述
    chest_pain = random.choice(CHEST_PAIN_DESCRIPTIONS[diagnosis])
    ecg = random.choice(ECG_FINDINGS[diagnosis])
    biomarker = random.choice(BIOMARKER_RESULTS[diagnosis])

    # 构建提示词
    prompt = f"""请根据以下临床信息，生成一个详细的患者病历描述。

诊断类型：{diagnosis}
临床路径：{path_info['description']}

患者基本信息：
- 姓名：{name}
- 年龄：{age}岁
- 性别：{gender}

关键临床特征：
- 主诉症状：{chest_pain}
- 心电图表现：{ecg}
- 心肌标志物：{biomarker}

要求：
1. 生成完整的病历格式，包括主诉、现病史、既往史、家族史、危险因素
2. 症状描述要真实可信，符合该诊断的典型表现
3. 不要在病历中直接写出最终诊断结果
4. 病历要包含足够的临床信息，使医生能够做出正确诊断
5. 用专业医学术语描述

请直接输出病历内容，不要有任何额外说明。"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一位经验丰富的临床医生，擅长撰写规范的病历记录。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8,
        max_tokens=1500
    )

    description = response.choices[0].message.content

    return {
        "patient_id": f"P{index:03d}",
        "description": description,
        "result_state": diagnosis,
        "path": path_info["path"]
    }


async def generate_patient_case_async(
    diagnosis: str,
    index: int,
    semaphore: asyncio.Semaphore = None
) -> dict:
    """
    使用大语言模型生成患者病例（异步版本）

    Args:
        diagnosis: 诊断类型
        index: 患者序号
        semaphore: 用于限制并发的信号量

    Returns:
        包含患者信息的字典
    """
    path_info = DIAGNOSIS_PATHS[diagnosis]

    # 随机生成患者基本信息
    age = random.randint(45, 80)
    gender = random.choice(["男", "女"])
    name = f"{random.choice(FIRST_NAMES)}{random.choice(LAST_NAMES)}"

    # 根据诊断类型调整典型年龄
    if diagnosis == "STEMI":
        age = random.randint(50, 75)
    elif diagnosis == "变异性心绞痛":
        age = random.randint(40, 65)
    elif diagnosis == "其他":
        age = random.randint(25, 70)

    # 选择症状、心电图、标志物描述
    chest_pain = random.choice(CHEST_PAIN_DESCRIPTIONS[diagnosis])
    ecg = random.choice(ECG_FINDINGS[diagnosis])
    biomarker = random.choice(BIOMARKER_RESULTS[diagnosis])

    # 构建提示词
    prompt = f"""请根据以下临床信息，生成一个详细的患者病历描述。

诊断类型：{diagnosis}
临床路径：{path_info['description']}

患者基本信息：
- 姓名：{name}
- 年龄：{age}岁
- 性别：{gender}

关键临床特征：
- 主诉症状：{chest_pain}
- 心电图表现：{ecg}
- 心肌标志物：{biomarker}

要求：
1. 生成完整的病历格式，包括主诉、现病史、既往史、家族史、危险因素
2. 症状描述要真实可信，符合该诊断的典型表现
3. 不要在病历中直接写出最终诊断结果
4. 病历要包含足够的临床信息，使医生能够做出正确诊断
5. 用专业医学术语描述

请直接输出病历内容，不要有任何额外说明。"""

    async def _call_api():
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一位经验丰富的临床医生，擅长撰写规范的病历记录。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1500
        )
        return response.choices[0].message.content

    # 如果提供了信号量，则使用它来限制并发
    if semaphore:
        async with semaphore:
            description = await _call_api()
    else:
        description = await _call_api()

    return {
        "patient_id": f"P{index:03d}",
        "description": description,
        "result_state": diagnosis,
        "path": path_info["path"]
    }


async def generate_all_patients_async(
    total_count: int = 100,
    output_path: str = "generated_data/patients.jsonl",
    max_concurrent: int = MAX_CONCURRENT_REQUESTS
) -> list:
    """
    生成所有患者数据（异步并发版本）

    Args:
        total_count: 总患者数量
        output_path: 输出文件路径
        max_concurrent: 最大并发数

    Returns:
        患者数据列表
    """
    # 确保输出目录存在
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 每种诊断类型的数量（平均分配）
    diagnoses = list(DIAGNOSIS_PATHS.keys())
    count_per_diagnosis = total_count // len(diagnoses)

    # 创建并发限制信号量
    semaphore = asyncio.Semaphore(max_concurrent)

    # 构建所有任务
    tasks = []
    index = 1

    for diagnosis in diagnoses:
        for i in range(count_per_diagnosis):
            tasks.append((diagnosis, index))
            index += 1

    # 处理余数
    remaining = total_count - len(tasks)
    for i in range(remaining):
        diagnosis = random.choice(diagnoses)
        tasks.append((diagnosis, index))
        index += 1

    print(f"开始生成 {total_count} 条患者数据（并发数: {max_concurrent}）...")

    # 并发生成所有患者数据
    async def generate_with_progress(task_tuple, task_index, total):
        diagnosis, idx = task_tuple
        if task_index % 10 == 0 or task_index == total:
            print(f"  进度: {task_index}/{total}", end="\r")
        try:
            return await generate_patient_case_async(diagnosis, idx, semaphore)
        except Exception as e:
            print(f"\n  生成失败 P{idx:03d}: {e}")
            return None

    results = await asyncio.gather(
        *[generate_with_progress(t, i, len(tasks)) for i, t in enumerate(tasks, 1)],
        return_exceptions=True
    )

    # 过滤掉失败的结果
    patients = [r for r in results if r is not None and not isinstance(r, Exception)]

    # 按 patient_id 排序
    patients.sort(key=lambda x: x["patient_id"])

    # 保存为jsonl格式
    with open(output_file, 'w', encoding='utf-8') as f:
        for patient in patients:
            f.write(json.dumps(patient, ensure_ascii=False) + '\n')

    print(f"\n\n数据生成完成！共生成 {len(patients)} 条患者数据")
    print(f"保存位置: {output_file}")

    # 统计各类型数量
    diagnosis_counts = {}
    for patient in patients:
        d = patient["result_state"]
        diagnosis_counts[d] = diagnosis_counts.get(d, 0) + 1

    print("\n各诊断类型数量:")
    for d, c in sorted(diagnosis_counts.items()):
        print(f"  {d}: {c}")

    return patients


def generate_all_patients(total_count: int = 100, output_path: str = "generated_data/patients.jsonl"):
    """
    生成所有患者数据（同步包装器）

    Args:
        total_count: 总患者数量
        output_path: 输出文件路径
    """
    return asyncio.run(generate_all_patients_async(
        total_count=total_count,
        output_path=output_path
    ))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='生成患者数据')
    parser.add_argument('--count', type=int, default=100, help='生成患者数量')
    parser.add_argument('--concurrent', type=int, default=MAX_CONCURRENT_REQUESTS, help='最大并发数')
    args = parser.parse_args()

    # 使用异步版本
    asyncio.run(generate_all_patients_async(
        total_count=args.count,
        max_concurrent=args.concurrent
    ))