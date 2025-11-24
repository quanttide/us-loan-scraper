# src/main.py
# 主执行文件：编排数据处理流程 (优化版 - 解决内存爆满问题)

import logging
import pandas as pd
from tqdm import tqdm
import csv  # 引入 csv 模块用于增量写入
import os

# 导入配置
import settings

# 导入工具函数
import utils


def process_attachment_file(attachment_file: settings.Path, cik: str, filing_id_str: str) -> list[dict]:
    """
    处理单个附件文件：预筛选、提取、解析、匹配。
    """
    results = []

    # 构造新的贷款合同ID
    attachment_name_stem = attachment_file.stem
    new_contract_id = f"{filing_id_str}_{attachment_name_stem}"

    # 1. 文本提取
    text = utils.get_document_text(attachment_file)
    if not text:
        # logging.warning(f"无法从附件 {attachment_file.name} 提取文本。") # 减少日志输出节省IO
        return []

    # 2. 筛选 1: 贷款合同关键词筛选
    if not settings.LOAN_KEYWORDS_REGEX.search(text):
        return []

    # 3. 筛选 2: 元信息提取
    effective_date = utils.extract_effective_date(text)

    # 4. 关键检查
    if effective_date is None:
        return []

    # 5. 句子识别
    sentences = utils.find_supply_chain_sentences(text)

    # 6. 结构化整合 (注意：这里暂不包含公司名称，在外层循环添加)
    for sentence in sentences:
        results.append({
            "公司ID": cik,
            "贷款合同ID": new_contract_id,
            "贷款起效日期": effective_date,
            "含供应链信息句子": sentence
        })

    return results


def run_processing():
    """
    (V10 - 内存优化版)
    主执行函数：支持增量写入，防止内存爆炸。
    """

    # 1. 配置日志
    logging.basicConfig(**settings.LOGGING_CONFIG)

    # 2. 准备 NLTK
    utils.setup_nltk()

    # 3. 加载 CIK 映射表 (转为字典以提高查找速度)
    logging.info("正在加载 CIK 映射表...")
    cik_map_df = utils.load_cik_map(settings.CIK_MAP_PATH)

    # 转换为字典: { 'CIK字符串': '公司名称' }
    cik_name_lookup = {}
    if not cik_map_df.empty:
        # 确保 CIK 是字符串且去重
        cik_map_df['CIK'] = cik_map_df['CIK'].astype(str)
        # 如果有重复CIK，保留第一个
        cik_map_df = cik_map_df.drop_duplicates(subset=['CIK'])
        cik_name_lookup = pd.Series(
            cik_map_df[settings.CIK_NAME_COLUMN].values,
            index=cik_map_df['CIK']
        ).to_dict()

    logging.info(f"CIK 映射表加载完成，共 {len(cik_name_lookup)} 条记录。")

    if not settings.BASE_DATA_PATH.exists():
        logging.error(f"基础数据路径未找到: {settings.BASE_DATA_PATH}")
        return

    cik_dirs = [d for d in settings.BASE_DATA_PATH.iterdir() if d.is_dir() and d.name.isdigit()]
    if not cik_dirs:
        logging.error(f"在 {settings.BASE_DATA_PATH} 下未找到任何 CIK 目录。")
        return

    # --- (新) 初始化输出文件 ---
    # 如果文件目录不存在，创建它
    if not settings.OUTPUT_CSV_PATH.parent.exists():
        settings.OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 写入 CSV 头部 (Header)
    # 使用 'w' 模式清空旧文件并写入表头
    with open(settings.OUTPUT_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=settings.OUTPUT_COLUMNS)
        writer.writeheader()

    logging.info(f"已初始化输出文件: {settings.OUTPUT_CSV_PATH}")
    logging.info(f"开始遍历 {len(cik_dirs)} 个 CIK 目录 (增量写入模式)...")

    total_sentences_found = 0

    # 4. 遍历所有 CIK
    for cik_dir in tqdm(cik_dirs, desc="处理 CIKs"):

        # 内存优化：每个 CIK 处理完后，results 都会被重置
        cik_batch_results = []

        cik_from_folder = cik_dir.name
        true_company_cik = cik_from_folder
        main_report_content = None
        current_company_name = "unknown"

        # --- A. 获取 CIK 和 公司名 (即时处理) ---
        main_report_files = list(cik_dir.glob("*.txt"))

        # 尝试从主文件解析
        if main_report_files:
            try:
                main_report_content = utils.get_document_text(main_report_files[0])
            except Exception:
                pass  # 如果读取主文件失败，忽略，继续处理附件

        if main_report_content:
            # 1. 尝试修正 CIK
            extracted_cik = utils.get_cik_from_8k_text(main_report_content)
            if extracted_cik:
                true_company_cik = extracted_cik

            # 2. 尝试从文件解析公司名
            parsed_name = utils.parse_company_name_from_main_filing(main_report_content)
            if parsed_name:
                current_company_name = parsed_name

        # 3. 如果文件里没解析到名字，查映射表 (Fallback)
        if current_company_name == "unknown":
            # dict.get(key, default) 查找速度非常快
            current_company_name = cik_name_lookup.get(true_company_cik, "unknown")

        # 释放主文件内容内存
        main_report_content = None

        # --- B. 处理该 CIK 下的所有附件 ---
        filing_dirs = [d for d in cik_dir.iterdir() if d.is_dir()]

        for filing_dir in filing_dirs:
            filing_id_str = filing_dir.name

            # 查找 txt 和 htm
            all_files_in_filing = list(filing_dir.glob("*.txt")) + list(filing_dir.glob("*.htm"))

            for attachment_file in all_files_in_filing:
                file_name_stem = attachment_file.stem

                # 跳过 8-K 主报告 (避免重复)
                if file_name_stem.replace('-', '') == filing_id_str:
                    continue

                try:
                    file_results = process_attachment_file(attachment_file, true_company_cik, filing_id_str)

                    if file_results:
                        # 立即注入公司名称
                        for res in file_results:
                            res['公司名称'] = current_company_name
                            cik_batch_results.append(res)

                except Exception as e:
                    logging.error(f"处理附件 {attachment_file.name} 出错: {e}")

        # --- C. 增量写入 (Batch Write) ---
        if cik_batch_results:
            try:
                with open(settings.OUTPUT_CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=settings.OUTPUT_COLUMNS)
                    writer.writerows(cik_batch_results)

                total_sentences_found += len(cik_batch_results)
            except Exception as e:
                logging.error(f"写入 CSV 失败: {e}")

        # --- D. 显式释放内存 ---
        # 虽然 Python 有 GC，但清空大列表是个好习惯
        del cik_batch_results

    logging.info(f"所有任务处理完毕。共找到 {total_sentences_found} 条数据。")
    logging.info(f"结果已保存在 {settings.OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    run_processing()