"""
心血管病例评估脚本 - 评估 data/cardiovascular_files 中的病例数据
"""

import os
import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from backend.methods import (
    direct_diagnosis,
    direct_generation_diagnosis,
    intermediate_state_diagnosis,
    full_workflow_diagnosis,
    step_by_step_diagnosis,
    llm_judge_evaluate
)

# 并发限制信号量
MAX_CONCURRENT_REQUESTS = 10


def parse_cardiovascular_case(filepath: str) -> Optional[Dict[str, Any]]:
    """
    解析心血管病例文件

    Args:
        filepath: 病例文件路径

    Returns:
        解析后的病例字典，包含 patient_id, description, full_description, result_state 等字段
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取患者基本信息
    name_match = re.search(r'\*\*姓名\*\*[:：]\s*(.+?)(?:\n|$)', content)
    age_match = re.search(r'\*\*年龄\*\*[:：]\s*(\d+)', content)
    gender_match = re.search(r'\*\*性别\*\*[:：]\s*(.+?)(?:\n|$)', content)

    # 提取主诉
    chief_complaint_match = re.search(r'\*\*主诉\*\*[:：]\s*(.+?)(?=\n\n|\n\*\*|$)', content, re.DOTALL)

    # 提取现病史
    present_illness_match = re.search(r'\*\*现病史\*\*[:：]\s*(.+?)(?=\n\n\*\*|\Z)', content, re.DOTALL)

    # 提取既往史
    past_history_match = re.search(r'\*\*既往史\*\*[:：]\s*(.+?)(?=\n\n\*\*个人史|\n\n\*\*婚育史|\n\n\*\*家族史|\n\n\*\*体格检查|\Z)', content, re.DOTALL)

    # 提取体格检查
    physical_exam_match = re.search(r'\*\*体格检查\*\*[:：]\s*(.+?)(?=\n\n\*\*辅助检查|\n\n\*\*初步诊断|\Z)', content, re.DOTALL)

    # 提取辅助检查
    aux_exam_match = re.search(r'\*\*辅助检查\*\*[:：](.+?)(?=\n\n\*\*初步诊断|\n\n#|\Z)', content, re.DOTALL)

    # 提取初步诊断
    initial_diagnosis_match = re.search(r'\*\*初步诊断\*\*[:：]\s*(.+?)(?=\n\n#|\n\n---|\Z)', content, re.DOTALL)

    # 提取最终诊断（从出院小结或诊疗经过中推断）
    discharge_diagnosis_match = re.search(r'\*\*出院诊断\*\*[:：]\s*(.+?)(?=\n\n|\Z)', content, re.DOTALL)

    if not name_match:
        return None

    # 从文件名提取 patient_id
    filename = os.path.basename(filepath)
    patient_id = filename.replace('.md', '')

    # 构建描述
    description_parts = []

    if chief_complaint_match:
        chief_complaint = chief_complaint_match.group(1).strip()
        description_parts.append(f"主诉：{chief_complaint}")

    if present_illness_match:
        present_illness = present_illness_match.group(1).strip()
        description_parts.append(f"现病史：{present_illness}")

    if past_history_match:
        past_history = past_history_match.group(1).strip()
        description_parts.append(f"既往史：{past_history}")

    if physical_exam_match:
        physical_exam = physical_exam_match.group(1).strip()
        description_parts.append(f"体格检查：{physical_exam}")

    if aux_exam_match:
        aux_exam = aux_exam_match.group(1).strip()
        description_parts.append(f"辅助检查：{aux_exam}")

    description = "\n".join(description_parts)

    # 完整描述（包括诊断和治疗过程）
    full_description = description

    if initial_diagnosis_match:
        initial_diagnosis = initial_diagnosis_match.group(1).strip()
        full_description += f"\n\n初步诊断：{initial_diagnosis}"

    if discharge_diagnosis_match:
        discharge_diagnosis = discharge_diagnosis_match.group(1).strip()
        full_description += f"\n\n出院诊断：{discharge_diagnosis}"

    # 确定 result_state（从出院诊断或初步诊断推断）
    result_state = "未知"

    if discharge_diagnosis_match or initial_diagnosis_match:
        diagnosis_text = ""
        if discharge_diagnosis_match:
            diagnosis_text = discharge_diagnosis_match.group(1)
        elif initial_diagnosis_match:
            diagnosis_text = initial_diagnosis_match.group(1)

        # 根据关键词判断诊断类型
        diagnosis_text_lower = diagnosis_text.lower()

        if any(kw in diagnosis_text for kw in ["肺栓塞", "肺动脉栓塞", "PE"]):
            result_state = "肺栓塞"
        elif any(kw in diagnosis_text for kw in ["深静脉血栓", "DVT", "静脉血栓"]):
            result_state = "深静脉血栓"
        elif any(kw in diagnosis_text for kw in ["STEMI", "ST 段抬高型心肌梗死", "急性 ST 段抬高"]):
            result_state = "STEMI"
        elif any(kw in diagnosis_text for kw in ["NSTEMI", "非 ST 段抬高型心肌梗死", "急性非 ST 段抬高"]):
            result_state = "NSTEMI"
        elif any(kw in diagnosis_text for kw in ["心绞痛", "UA", "不稳定型心绞痛", "变异性心绞痛"]):
            if "变异" in diagnosis_text:
                result_state = "变异性心绞痛"
            elif "不稳定" in diagnosis_text or "UA" in diagnosis_text:
                result_state = "UA"
            else:
                result_state = "心绞痛"
        elif any(kw in diagnosis_text for kw in ["心力衰竭", "心衰", "HF"]):
            result_state = "心力衰竭"
        elif any(kw in diagnosis_text for kw in ["高血压", "HTN"]):
            result_state = "高血压"
        elif any(kw in diagnosis_text for kw in ["糖尿病", "DM"]):
            result_state = "糖尿病"
        elif any(kw in diagnosis_text for kw in ["贫血"]):
            result_state = "贫血"
        elif any(kw in diagnosis_text for kw in ["冠心病", "CHD"]):
            result_state = "冠心病"
        else:
            result_state = "其他"

    # 如果没有任何诊断信息，尝试从内容推断
    if result_state == "未知":
        if "肺栓塞" in content or "D-二聚体" in content:
            result_state = "肺栓塞"
        elif "ST 段抬高" in content:
            result_state = "STEMI"
        elif "肌钙蛋白" in content and "升高" in content:
            result_state = "NSTEMI"

    return {
        "patient_id": patient_id,
        "name": name_match.group(1).strip() if name_match else "未知",
        "age": int(age_match.group(1)) if age_match else 0,
        "gender": gender_match.group(1).strip() if gender_match else "未知",
        "description": description,
        "full_description": full_description,
        "result_state": result_state,
        "initial_diagnosis": initial_diagnosis_match.group(1).strip() if initial_diagnosis_match else "",
        "discharge_diagnosis": discharge_diagnosis_match.group(1).strip() if discharge_diagnosis_match else "",
        "source_file": filepath
    }


def load_cardiovascular_cases(
    data_dir: str = "data/cardiovascular_files",
    sample_size: int = None
) -> List[Dict[str, Any]]:
    """
    加载心血管病例数据

    Args:
        data_dir: 病例文件目录
        sample_size: 采样数量，None 表示使用全部数据

    Returns:
        病例数据列表
    """
    cases = []
    data_path = Path(data_dir)

    if not data_path.exists():
        raise FileNotFoundError(f"未找到病例目录：{data_dir}")

    md_files = sorted(data_path.glob("*.md"))

    if sample_size and sample_size < len(md_files):
        import random
        md_files = random.sample(md_files, sample_size)

    for filepath in md_files:
        try:
            case = parse_cardiovascular_case(str(filepath))
            if case:
                cases.append(case)
                print(f"已加载：{case['patient_id']} - {case['result_state']}", end="\r")
        except Exception as e:
            print(f"\n解析失败 {filepath}: {e}")

    print(f"\n成功加载 {len(cases)} 条病例数据")
    return cases


async def run_cardiovascular_evaluation(
    cases: List[Dict[str, Any]],
    methods: List[str] = None,
    model: str = "Pro/MiniMaxAI/MiniMax-M2.5",
    use_llm_judge: bool = True,
    judge_model: str = "Pro/moonshotai/Kimi-K2.5",
    output_path: str = "results/cardiovascular_evaluation_results.json",
    max_concurrent: int = MAX_CONCURRENT_REQUESTS
) -> Dict[str, Any]:
    """
    运行心血管病例评估

    Args:
        cases: 病例数据列表
        methods: 要评估的方法列表
        model: 使用的模型名称
        use_llm_judge: 是否使用 LLM-as-Judge 评估
        judge_model: Judge 使用的模型名称
        output_path: 结果保存路径
        max_concurrent: 最大并发数

    Returns:
        评估结果字典
    """
    if methods is None:
        methods = ["direct", "direct_generation", "intermediate_state", "step_by_step", "full_workflow"]

    results = {
        "config": {
            "total_cases": len(cases),
            "methods": methods,
            "model": model,
            "use_llm_judge": use_llm_judge,
            "judge_model": judge_model if use_llm_judge else None,
            "data_source": "cardiovascular_files"
        },
        "method_results": {},
        "detailed_results": [],
        "case_statistics": {}
    }

    # 统计诊断类型分布
    diagnosis_counts = {}
    for case in cases:
        d = case["result_state"]
        diagnosis_counts[d] = diagnosis_counts.get(d, 0) + 1
    results["case_statistics"]["diagnosis_distribution"] = diagnosis_counts

    # 定义方法函数映射
    method_functions = {
        "direct": direct_diagnosis,
        "direct_generation": direct_generation_diagnosis,
        "intermediate_state": intermediate_state_diagnosis,
        "full_workflow": full_workflow_diagnosis,
        "step_by_step": step_by_step_diagnosis
    }

    # 创建并发限制信号量
    semaphore = asyncio.Semaphore(max_concurrent)

    # 对每种方法进行评估
    for method_name in methods:
        print(f"\n{'='*50}")
        print(f"评估方法：{method_name}")
        if use_llm_judge:
            print(f"评估方式：LLM-as-Judge ({judge_model})")
        print(f"{'='*50}")

        # 定义单个病例的评估函数
        async def evaluate_single_case(case: Dict[str, Any], idx: int, total: int) -> Dict[str, Any]:
            if idx % 5 == 0 or idx == total:
                print(f"处理病例 {idx}/{total}: {case['patient_id']}", end="\r")

            async with semaphore:
                try:
                    # 调用对应的方法
                    result = await method_functions[method_name](case, model)

                    prediction = result["diagnosis"]
                    ground_truth = case["result_state"]
                    patient_context = case.get("full_description") or case.get("description", "")

                    # 使用 LLM-as-Judge 或传统方式判断正确性
                    if use_llm_judge:
                        judge_result = await llm_judge_evaluate(
                            patient_description=patient_context,
                            ground_truth=ground_truth,
                            model_prediction=result.get("raw_response", prediction),
                            judge_model=judge_model
                        )
                        is_correct = judge_result["is_correct"]
                        judge_result_data = judge_result
                    else:
                        is_correct = prediction == ground_truth
                        judge_result_data = None

                    return {
                        "patient_id": case["patient_id"],
                        "ground_truth": ground_truth,
                        "prediction": prediction,
                        "correct": is_correct,
                        "raw_response": result.get("raw_response", ""),
                        "interaction_trace": result.get("interaction_trace", ""),
                        "intermediate_states": result.get("intermediate_states", {}),
                        "judge_result": judge_result_data,
                        "error": None
                    }

                except Exception as e:
                    return {
                        "patient_id": case["patient_id"],
                        "ground_truth": case["result_state"],
                        "prediction": "未知",
                        "correct": False,
                        "raw_response": "",
                        "interaction_trace": "",
                        "intermediate_states": {},
                        "judge_result": None,
                        "error": str(e)
                    }

        # 并发评估所有病例
        tasks = [evaluate_single_case(c, i, len(cases)) for i, c in enumerate(cases, 1)]
        method_results = await asyncio.gather(*tasks)

        # 收集预测结果
        predictions = [r["prediction"] for r in method_results]
        ground_truths = [r["ground_truth"] for r in method_results]

        # 计算准确率
        if use_llm_judge:
            correct_count = sum(1 for r in method_results if r["correct"])
            accuracy = correct_count / len(method_results) if method_results else 0

            evaluation = {
                "accuracy": accuracy,
                "correct": correct_count,
                "total": len(method_results),
                "metrics_by_class": {},
                "macro_precision": accuracy,
                "macro_recall": accuracy,
                "macro_f1": accuracy,
                "confusion_matrix": {}
            }
        else:
            # 简单准确率计算（非 LLM Judge 模式）
            correct_count = sum(1 for p, g in zip(predictions, ground_truths) if p == g)
            accuracy = correct_count / len(predictions) if predictions else 0

            evaluation = {
                "accuracy": accuracy,
                "correct": correct_count,
                "total": len(predictions),
                "metrics_by_class": {},
                "macro_precision": accuracy,
                "macro_recall": accuracy,
                "macro_f1": accuracy,
                "confusion_matrix": {}
            }

        results["method_results"][method_name] = evaluation

        print(f"\n\n{method_name} 方法评估结果:")
        print(f"  准确率：{evaluation['accuracy']:.2%} ({evaluation['correct']}/{evaluation['total']})")

        # 保存详细结果
        results["detailed_results"].append({
            "method": method_name,
            "results": method_results
        })

    # 保存结果
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n\n评估结果已保存至：{output_file}")

    return results


def print_cardiovascular_summary(results: Dict[str, Any]):
    """
    打印心血管病例评估结果摘要
    """
    use_llm_judge = results['config'].get('use_llm_judge', False)

    print("\n" + "="*60)
    print("心血管病例评估结果摘要")
    print("="*60)

    print(f"\n配置:")
    print(f"  模型：{results['config']['model']}")
    print(f"  病例数量：{results['config']['total_cases']}")
    print(f"  数据来源：{results['config']['data_source']}")
    print(f"  评估方法：{', '.join(results['config']['methods'])}")
    if use_llm_judge:
        print(f"  评估方式：LLM-as-Judge ({results['config']['judge_model']})")

    # 诊断类型分布
    print("\n" + "-"*60)
    print("诊断类型分布:")
    print("-"*60)
    for diagnosis, count in sorted(results["case_statistics"]["diagnosis_distribution"].items()):
        print(f"  {diagnosis}: {count} ({count/results['config']['total_cases']:.2%})")

    print("\n" + "-"*60)
    print("各方法性能对比:")
    print("-"*60)

    print(f"\n{'方法':<30} {'准确率':<15}")
    print("-"*47)

    for method_name, evaluation in results["method_results"].items():
        print(f"{method_name:<30} {evaluation['accuracy']:<15.2%}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='评估心血管病例诊断方法')
    parser.add_argument('--sample', type=int, default=None, help='采样数量，默认使用全部数据')
    parser.add_argument('--methods', type=str, default=None, help='评估方法，用逗号分隔')
    parser.add_argument('--judge', action='store_true', help='使用 LLM-as-Judge 评估方式')
    parser.add_argument('--judge-model', type=str, default='Pro/moonshotai/Kimi-K2.5', help='LLM-as-Judge 使用的模型')
    parser.add_argument('--concurrent', type=int, default=MAX_CONCURRENT_REQUESTS, help='最大并发数')
    parser.add_argument('--data-dir', type=str, default='data/cardiovascular_files', help='病例数据目录')
    parser.add_argument('--output', type=str, default='results/cardiovascular_evaluation_results.json', help='结果保存路径')
    args = parser.parse_args()

    # 加载环境变量
    load_dotenv()

    # 检查 API 密钥
    if not os.getenv("OPENAI_API_KEY"):
        print("错误：请设置 OPENAI_API_KEY 环境变量")
        print("可以创建 .env 文件并添加：OPENAI_API_KEY=your_api_key")
        exit(1)

    # 加载病例数据
    print("加载心血管病例数据...")
    try:
        cases = load_cardiovascular_cases(
            data_dir=args.data_dir,
            sample_size=args.sample
        )
        print(f"成功加载 {len(cases)} 条病例数据")
    except FileNotFoundError as e:
        print(f"错误：{e}")
        exit(1)

    # 解析方法参数
    methods = None
    if args.methods:
        methods = [m.strip() for m in args.methods.split(',')]

    # 运行评估
    async def main():
        results = await run_cardiovascular_evaluation(
            cases=cases,
            methods=methods,
            use_llm_judge=args.judge,
            judge_model=args.judge_model,
            output_path=args.output,
            max_concurrent=args.concurrent
        )
        print_cardiovascular_summary(results)

    asyncio.run(main())
