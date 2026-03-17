"""
评估模块 - 评估不同诊断方法的准确性（异步版本）
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
from dotenv import load_dotenv

from methods import (
    direct_diagnosis,
    direct_generation_diagnosis,
    intermediate_state_diagnosis,
    full_workflow_diagnosis,
    step_by_step_diagnosis,
    llm_judge_evaluate,
    parse_diagnosis
)

# 并发限制信号量（限制同时进行的API请求数量）
MAX_CONCURRENT_REQUESTS = 10


def load_patients(filepath: str = "generated_data/patients.jsonl") -> List[Dict[str, Any]]:
    """
    加载患者数据

    Args:
        filepath: 数据文件路径

    Returns:
        患者数据列表
    """
    patients = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                patients.append(json.loads(line))
    return patients


def evaluate_method(predictions: List[str], ground_truths: List[str]) -> Dict[str, Any]:
    """
    评估单个方法的性能

    Args:
        predictions: 预测结果列表
        ground_truths: 真实标签列表

    Returns:
        评估指标字典
    """
    # 所有诊断类型
    diagnoses = ["STEMI", "NSTEMI", "UA", "变异性心绞痛", "其他", "未知"]

    # 计算总体准确率
    correct = sum(p == g for p, g in zip(predictions, ground_truths))
    accuracy = correct / len(predictions) if predictions else 0

    # 计算每个类别的指标
    metrics = {}
    for diagnosis in diagnoses:
        tp = sum(1 for p, g in zip(predictions, ground_truths) if p == diagnosis and g == diagnosis)
        fp = sum(1 for p, g in zip(predictions, ground_truths) if p == diagnosis and g != diagnosis)
        fn = sum(1 for p, g in zip(predictions, ground_truths) if p != diagnosis and g == diagnosis)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        metrics[diagnosis] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn
        }

    # 计算宏平均
    macro_precision = sum(m["precision"] for m in metrics.values()) / len(metrics)
    macro_recall = sum(m["recall"] for m in metrics.values()) / len(metrics)
    macro_f1 = sum(m["f1"] for m in metrics.values()) / len(metrics)

    # 构建混淆矩阵
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    for pred, true in zip(predictions, ground_truths):
        confusion_matrix[true][pred] += 1

    return {
        "accuracy": accuracy,
        "correct": correct,
        "total": len(predictions),
        "metrics_by_class": metrics,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "confusion_matrix": dict(confusion_matrix)
    }


async def run_evaluation(
    patients: List[Dict[str, Any]],
    methods: List[str] = None,
    model: str = "gpt-4o-mini",
    sample_size: int = None,
    use_llm_judge: bool = False,
    judge_model: str = "gpt-4o-mini",
    output_path: str = "results/evaluation_results.json",
    max_concurrent: int = MAX_CONCURRENT_REQUESTS
) -> Dict[str, Any]:
    """
    运行所有方法的评估（异步并发版本）

    Args:
        patients: 患者数据列表
        methods: 要评估的方法列表，默认为 ["direct", "direct_generation", "intermediate_state", "step_by_step", "full_workflow"]
        model: 使用的模型名称
        sample_size: 采样数量，None表示使用全部数据
        use_llm_judge: 是否使用LLM-as-Judge评估
        judge_model: Judge使用的模型名称
        output_path: 结果保存路径
        max_concurrent: 最大并发数

    Returns:
        评估结果字典
    """
    if methods is None:
        methods = ["direct", "direct_generation", "intermediate_state", "step_by_step", "full_workflow"]

    # 采样
    if sample_size and sample_size < len(patients):
        import random
        patients = random.sample(patients, sample_size)

    results = {
        "config": {
            "total_patients": len(patients),
            "methods": methods,
            "model": model,
            "use_llm_judge": use_llm_judge,
            "judge_model": judge_model if use_llm_judge else None
        },
        "method_results": {},
        "detailed_results": []
    }

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
        print(f"评估方法: {method_name}")
        if use_llm_judge:
            print(f"评估方式: LLM-as-Judge ({judge_model})")
        print(f"{'='*50}")

        # 定义单个患者的评估函数
        async def evaluate_single_patient(patient: Dict[str, Any], idx: int, total: int) -> Dict[str, Any]:
            if idx % 5 == 0 or idx == total:
                print(f"处理患者 {idx}/{total}: {patient['patient_id']}", end="\r")

            async with semaphore:
                try:
                    # 调用对应的方法
                    result = await method_functions[method_name](patient["description"], model)

                    prediction = result["diagnosis"]
                    ground_truth = patient["result_state"]

                    # 使用LLM-as-Judge或传统方式判断正确性
                    if use_llm_judge:
                        judge_result = await llm_judge_evaluate(
                            patient_description=patient["description"],
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
                        "patient_id": patient["patient_id"],
                        "ground_truth": ground_truth,
                        "prediction": prediction,
                        "correct": is_correct,
                        "raw_response": result.get("raw_response", ""),
                        "intermediate_states": result.get("intermediate_states", {}),
                        "judge_result": judge_result_data,
                        "error": None
                    }

                except Exception as e:
                    return {
                        "patient_id": patient["patient_id"],
                        "ground_truth": patient["result_state"],
                        "prediction": "未知",
                        "correct": False,
                        "raw_response": "",
                        "intermediate_states": {},
                        "judge_result": None,
                        "error": str(e)
                    }

        # 并发评估所有患者
        tasks = [evaluate_single_patient(p, i, len(patients)) for i, p in enumerate(patients, 1)]
        method_results = await asyncio.gather(*tasks)

        # 收集预测结果
        predictions = [r["prediction"] for r in method_results]
        ground_truths = [r["ground_truth"] for r in method_results]
        judge_results = [r["judge_result"] for r in method_results]

        # 计算评估指标
        if use_llm_judge:
            # 使用LLM-as-Judge的结果计算准确率
            correct_count = sum(1 for r in method_results if r["correct"])
            accuracy = correct_count / len(method_results) if method_results else 0

            evaluation = {
                "accuracy": accuracy,
                "correct": correct_count,
                "total": len(method_results),
                "metrics_by_class": {},  # LLM Judge模式不计算细粒度指标
                "macro_precision": accuracy,
                "macro_recall": accuracy,
                "macro_f1": accuracy,
                "confusion_matrix": {}
            }
        else:
            evaluation = evaluate_method(predictions, ground_truths)

        results["method_results"][method_name] = evaluation

        print(f"\n\n{method_name} 方法评估结果:")
        print(f"  准确率: {evaluation['accuracy']:.2%} ({evaluation['correct']}/{evaluation['total']})")
        if not use_llm_judge:
            print(f"  宏平均精确率: {evaluation['macro_precision']:.2%}")
            print(f"  宏平均召回率: {evaluation['macro_recall']:.2%}")
            print(f"  宏平均F1: {evaluation['macro_f1']:.2%}")

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

    print(f"\n\n评估结果已保存至: {output_file}")

    return results


def print_summary(results: Dict[str, Any]):
    """
    打印评估结果摘要

    Args:
        results: 评估结果字典
    """
    use_llm_judge = results['config'].get('use_llm_judge', False)

    print("\n" + "="*60)
    print("评估结果摘要")
    print("="*60)

    print(f"\n配置:")
    print(f"  模型: {results['config']['model']}")
    print(f"  患者数量: {results['config']['total_patients']}")
    print(f"  评估方法: {', '.join(results['config']['methods'])}")
    if use_llm_judge:
        print(f"  评估方式: LLM-as-Judge ({results['config']['judge_model']})")

    print("\n" + "-"*60)
    print("各方法性能对比:")
    print("-"*60)

    if use_llm_judge:
        # LLM Judge 模式只显示准确率
        print(f"\n{'方法':<30} {'准确率':<15}")
        print("-"*47)

        for method_name, evaluation in results["method_results"].items():
            print(f"{method_name:<30} {evaluation['accuracy']:<15.2%}")
    else:
        # 传统模式显示完整指标
        print(f"\n{'方法':<25} {'准确率':<12} {'精确率':<12} {'召回率':<12} {'F1分数':<12}")
        print("-"*73)

        for method_name, evaluation in results["method_results"].items():
            print(f"{method_name:<25} "
                  f"{evaluation['accuracy']:<12.2%} "
                  f"{evaluation['macro_precision']:<12.2%} "
                  f"{evaluation['macro_recall']:<12.2%} "
                  f"{evaluation['macro_f1']:<12.2%}")

    # 只在非LLM Judge模式下打印详细指标和混淆矩阵
    if not use_llm_judge:
        # 打印各类型性能
        print("\n" + "-"*60)
        print("各诊断类型详细指标:")
        print("-"*60)

        for method_name, evaluation in results["method_results"].items():
            print(f"\n{method_name} 方法:")
            for diagnosis, metrics in evaluation["metrics_by_class"].items():
                if metrics["tp"] + metrics["fp"] + metrics["fn"] > 0:  # 只显示有数据的类别
                    print(f"  {diagnosis}:")
                    print(f"    精确率: {metrics['precision']:.2%}, "
                          f"召回率: {metrics['recall']:.2%}, "
                          f"F1: {metrics['f1']:.2%}")

        # 打印混淆矩阵
        print("\n" + "-"*60)
        print("混淆矩阵 (以直接诊断法为例):")
        print("-"*60)

        if "direct" in results["method_results"]:
            confusion = results["method_results"]["direct"]["confusion_matrix"]
            diagnoses = ["STEMI", "NSTEMI", "UA", "变异性心绞痛", "其他"]

            # 打印表头
            header = "真实\\预测"
            for d in diagnoses:
                header += f"\t{d[:6]}"
            print(header)

            # 打印每行
            for true_label in diagnoses:
                row = f"{true_label[:6]}"
                for pred_label in diagnoses:
                    count = confusion.get(true_label, {}).get(pred_label, 0)
                    row += f"\t{count}"
                print(row)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='评估诊断方法')
    parser.add_argument('--sample', type=int, default=None, help='采样数量，默认使用全部数据')
    parser.add_argument('--methods', type=str, default=None, help='评估方法，用逗号分隔，如：direct,direct_generation,intermediate_state,step_by_step,full_workflow')
    parser.add_argument('--judge', action='store_true', help='使用LLM-as-Judge评估方式')
    parser.add_argument('--judge-model', type=str, default='gpt-4o-mini', help='LLM-as-Judge使用的模型')
    parser.add_argument('--concurrent', type=int, default=MAX_CONCURRENT_REQUESTS, help='最大并发数')
    args = parser.parse_args()

    # 加载环境变量
    load_dotenv()

    # 检查API密钥
    if not os.getenv("OPENAI_API_KEY"):
        print("错误: 请设置 OPENAI_API_KEY 环境变量")
        print("可以创建 .env 文件并添加: OPENAI_API_KEY=your_api_key")
        exit(1)

    # 加载患者数据
    print("加载患者数据...")
    try:
        patients = load_patients()
        print(f"成功加载 {len(patients)} 条患者数据")
    except FileNotFoundError:
        print("错误: 未找到患者数据文件")
        print("请先运行 python generate_data.py 生成数据")
        exit(1)

    # 解析方法参数
    methods = None
    if args.methods:
        methods = [m.strip() for m in args.methods.split(',')]

    # 运行评估
    async def main():
        results = await run_evaluation(
            patients=patients,
            sample_size=args.sample,
            methods=methods,
            use_llm_judge=args.judge,
            judge_model=args.judge_model,
            output_path="results/evaluation_results.json",
            max_concurrent=args.concurrent
        )
        print_summary(results)

    asyncio.run(main())