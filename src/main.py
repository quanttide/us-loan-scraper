# src/main.py
# 主执行文件：编排数据处理流程 (V18 - CIK级全局去重版)

import logging
import pandas as pd
from tqdm import tqdm
import csv
import os
import gc
import hashlib  # 用于计算句子哈希
import settings
import utils


def process_attachment_file(attachment_file: settings.Path, cik: str, filing_id_str: str) -> list[dict]:
    """
    处理单个附件文件。
    """
    results = []
    new_contract_id = f"{filing_id_str}_{attachment_file.name}"

    # 1. 文本提取
    text = utils.get_document_text(attachment_file)
    if not text:
        return []

    # 2. 关键词筛选
    if not settings.LOAN_KEYWORDS_REGEX.search(text):
        return []

    # 3. 元信息提取
    effective_date = utils.extract_effective_date(text)
    if effective_date is None:
        return []

    # 4. 句子识别 (utils 内部已进行指纹去重)
    sentences = utils.find_supply_chain_sentences(text)

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
    主执行函数。
    去重策略：在处理每个 CIK (公司) 时，维护一个内存集合，防止该公司在不同文件或不同 Filing 中产生重复句子。
    """
    logging.basicConfig(**settings.LOGGING_CONFIG)
    utils.setup_nltk()

    logging.info("正在加载 CIK 映射表...")
    cik_map_df = utils.load_cik_map(settings.CIK_MAP_PATH)

    cik_name_lookup = {}
    if not cik_map_df.empty:
        cik_map_df['CIK'] = cik_map_df['CIK'].astype(str)
        cik_map_df = cik_map_df.drop_duplicates(subset=['CIK'])
        cik_name_lookup = pd.Series(
            cik_map_df[settings.CIK_NAME_COLUMN].values,
            index=cik_map_df['CIK']
        ).to_dict()

    if not settings.BASE_DATA_PATH.exists():
        logging.error(f"基础数据路径未找到: {settings.BASE_DATA_PATH}")
        return

    cik_dirs = [d for d in settings.BASE_DATA_PATH.iterdir() if d.is_dir() and d.name.isdigit()]
    if not cik_dirs:
        return

    if not settings.OUTPUT_CSV_PATH.parent.exists():
        settings.OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(settings.OUTPUT_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=settings.OUTPUT_COLUMNS)
        writer.writeheader()

    logging.info(f"开始处理 {len(cik_dirs)} 个 CIK 目录...")
    total_sentences_found = 0

    for i, cik_dir in enumerate(tqdm(cik_dirs, desc="处理 CIKs")):
        cik_batch_results = []
        cik_from_folder = cik_dir.name
        true_company_cik = cik_from_folder
        current_company_name = "unknown"

        # 【核心修改：CIK 级别的去重集合】
        # 确保同一家公司内，无论在哪个文件夹，相同的句子只记录一次
        cik_unique_hashes = set()

        # --- A. 获取 CIK 和 公司名 ---
        main_report_files = list(cik_dir.glob("*.txt"))

        if not main_report_files:
            for sub_dir in cik_dir.iterdir():
                if sub_dir.is_dir():
                    candidate = sub_dir / f"{sub_dir.name}.txt"
                    if candidate.exists():
                        main_report_files.append(candidate)
                        break

        if main_report_files:
            try:
                main_report_content = utils.get_document_text(main_report_files[0])
                if main_report_content:
                    extracted_cik = utils.get_cik_from_8k_text(main_report_content)
                    if extracted_cik:
                        true_company_cik = extracted_cik

                    parsed_name = utils.parse_company_name_from_main_filing(main_report_content)
                    if parsed_name:
                        current_company_name = parsed_name
            except Exception:
                pass

        if current_company_name == "unknown":
            current_company_name = cik_name_lookup.get(true_company_cik, "unknown")

        # --- B. 处理该 CIK 下的 Filing 文件夹 ---
        filing_dirs = [d for d in cik_dir.iterdir() if d.is_dir()]

        for filing_dir in filing_dirs:
            filing_id_str = filing_dir.name

            # 获取所有文件
            all_files_in_filing = list(filing_dir.glob("*.htm")) + list(filing_dir.glob("*.txt"))

            for attachment_file in all_files_in_filing:
                # 过滤 (8-K) 主文件
                if "(8-K)" in attachment_file.name.upper() or "(8-K/A)" in attachment_file.name.upper():
                    continue

                file_stem_clean = attachment_file.stem.replace('-', '')
                filing_id_clean = filing_id_str.replace('-', '')
                if file_stem_clean == filing_id_clean:
                    continue

                try:
                    file_results = process_attachment_file(attachment_file, true_company_cik, filing_id_str)

                    if file_results:
                        for res in file_results:
                            sentence = res['含供应链信息句子']

                            # 【去重逻辑】
                            # 使用 MD5 哈希在 CIK 范围内去重
                            sent_hash = hashlib.md5(sentence.encode('utf-8')).hexdigest()

                            if sent_hash not in cik_unique_hashes:
                                cik_unique_hashes.add(sent_hash)

                                # 只有不重复的才加入结果集
                                res['公司名称'] = current_company_name
                                cik_batch_results.append(res)

                except Exception as e:
                    logging.error(f"处理附件 {attachment_file.name} 出错: {e}")

        # --- C. 写入 CSV ---
        if cik_batch_results:
            try:
                with open(settings.OUTPUT_CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=settings.OUTPUT_COLUMNS)
                    writer.writerows(cik_batch_results)

                total_sentences_found += len(cik_batch_results)
            except Exception as e:
                logging.error(f"写入 CSV 失败: {e}")

        # 清理内存
        del cik_batch_results
        del cik_unique_hashes  # 显式删除去重集合

        # 定期 GC
        if i % 10 == 0:
            gc.collect()

    logging.info(f"所有任务处理完毕。共找到 {total_sentences_found} 条数据。")
    logging.info(f"结果已保存在 {settings.OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    run_processing()