# main.py
# 主执行文件：编排数据处理流程

import logging
import pandas as pd
from tqdm import tqdm

# 导入配置
import settings

# 导入工具函数
import utils


def process_attachment_file(attachment_file: settings.Path, cik: str, filing_id_str: str) -> list[dict]:
    """
    (修改 - 反馈 3) 处理单个附件文件：预筛选、提取、解析、匹配。
    """
    results = []

    # (需求 3) 构造新的贷款合同ID: FilingID_AttachmentName(no_ext)
    attachment_name_stem = attachment_file.stem
    new_contract_id = f"{filing_id_str}_{attachment_name_stem}"

    # 1. 文本提取 (调用 utils)
    text = utils.get_document_text(attachment_file)
    if not text:
        logging.warning(f"无法从附件 {attachment_file.name} 提取文本。")
        return []

    # 2. (新增 - 反馈 3) 筛选 1: 贷款合同关键词筛选
    # 必须包含 "loan", "credit", "agreement" 等词
    if not settings.LOAN_KEYWORDS_REGEX.search(text):
        logging.info(f"跳过附件 {attachment_file.name}: 未找到贷款关键词 (判定为非贷款合同)。")
        return []

    # 3. (原 2) 筛选 2: 元信息提取 (调用 utils) (需求 2)
    effective_date = utils.extract_effective_date(text)

    # 4. (原 3) 关键检查：如果找不到日期，则不收录
    if effective_date is None:
        logging.info(f"跳过附件 {attachment_file.name}: 找到了贷款关键词，但未找到有效日期。")
        return []  # <-- 立即停止处理并返回空

    # 5. (原 4) 句子识别 (调用 utils) (需求 4)
    sentences = utils.find_supply_chain_sentences(text)

    # 6. (原 5) 结构化整合
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
    (V9 - 修复 "unknown" 公司名问题)
    主执行函数：重构公司名解析逻辑，始终以文件为先。
    """

    # 1. 配置日志
    logging.basicConfig(**settings.LOGGING_CONFIG)

    # 2. 准备 NLTK (需求 4)
    utils.setup_nltk()

    # 3. 加载 CIK 映射表 (作为回退)
    cik_map_df = utils.load_cik_map(settings.CIK_MAP_PATH)
    if cik_map_df.empty:
        logging.warning("CIK 映射表为空。将仅依赖文件内解析的公司名称。")
        cik_map_df = pd.DataFrame(columns=['CIK', settings.CIK_NAME_COLUMN])
    else:
        # 确保 CIK 列是字符串，以便合并
        cik_map_df['CIK'] = cik_map_df['CIK'].astype(str)

    # 4. 遍历所有 CIK/FilingID 目录
    all_results = []

    # (新) (反馈 2) CIK 和公司名的 "真实来源"
    # 我们将首先填充这个 map，它拥有最高优先级
    parsed_names_map = {}

    if not settings.BASE_DATA_PATH.exists():
        logging.error(f"基础数据路径未找到: {settings.BASE_DATA_PATH}")
        return

    cik_dirs = [d for d in settings.BASE_DATA_PATH.iterdir() if d.is_dir() and d.name.isdigit()]

    if not cik_dirs:
        logging.error(f"在 {settings.BASE_DATA_PATH} 下未找到任何 CIK 目录。")
        return

    logging.info(f"开始遍历 {len(cik_dirs)} 个 CIK 目录...")

    for cik_dir in tqdm(cik_dirs, desc="处理 CIKs"):

        cik_from_folder = cik_dir.name  # (例如 '1010305')
        true_company_cik = cik_from_folder  # 默认使用文件夹 CIK
        main_report_content = None

        # --- (新) CIK 和公司名解析逻辑 (反馈 2) ---

        # 1. 查找并读取主 8-K .txt 文件
        main_report_files = list(cik_dir.glob("*.txt"))
        if main_report_files:
            main_report_path = main_report_files[0]
            main_report_content = utils.get_document_text(main_report_path)
        else:
            logging.warning(f"CIK {cik_from_folder}: 在 {cik_dir} 下未找到任何 .txt 主文件。")

        # 2. (新) 如果主文件内容读取成功，始终尝试解析 CIK 和 公司名
        if main_report_content:
            # (反馈 1) 尝试获取真实的 CIK (已去除前导0)
            extracted_cik = utils.get_cik_from_8k_text(main_report_content)

            if extracted_cik:
                true_company_cik = extracted_cik  # 使用从文件解析出的 CIK
                if extracted_cik != cik_from_folder:
                    logging.info(f"CIK 修正: 文件夹 {cik_from_folder} -> 文件 CIK {true_company_cik}。")
            else:
                logging.warning(f"CIK {cik_from_folder}: 未能从主文件解析 CIK，回退使用文件夹名称。")

            # (新) (反馈 2) 无论 CIK 是否在映射表中，始终尝试解析公司名
            company_name = utils.parse_company_name_from_main_filing(main_report_content)

            if company_name:
                # 存储这个“真实”名称，它将覆盖 CSV 中的任何内容
                if true_company_cik not in parsed_names_map:
                    parsed_names_map[true_company_cik] = company_name
            else:
                logging.warning(f"CIK {true_company_cik}: 无法从主文件解析公司名 (文件: {main_report_path.name})。")
        # --- CIK 和公司名逻辑结束 ---

        # --- 核心逻辑：遍历所有附件 ---
        filing_dirs = [d for d in cik_dir.iterdir() if d.is_dir()]
        for filing_dir in filing_dirs:
            filing_id_str = filing_dir.name  # e.g., "000110465904040804"

            all_files_in_filing = list(filing_dir.glob("*.txt")) + list(filing_dir.glob("*.htm"))

            if not all_files_in_filing:
                continue

            for attachment_file in all_files_in_filing:
                file_name_stem = attachment_file.stem

                # (修复) 关键检查：跳过 8-K 主报告
                if file_name_stem.replace('-', '') == filing_id_str:
                    logging.debug(f"Skipping main report: {attachment_file.name}")
                    continue

                # --- 如果是附件，则处理 ---
                try:
                    # 将 true_company_cik 传递给处理函数
                    file_results = process_attachment_file(attachment_file, true_company_cik, filing_id_str)
                    if file_results:
                        all_results.extend(file_results)
                except Exception as e:
                    logging.error(f"处理附件 {attachment_file} 时发生严重错误: {e}", exc_info=True)

    if not all_results:
        logging.info("处理完成，未找到任何匹配的句子。")
        return

    # 5. 转换为 DataFrame
    logging.info(f"共找到 {len(all_results)} 条匹配句子。正在转换为 DataFrame...")
    results_df = pd.DataFrame(all_results)
    results_df['公司ID'] = results_df['公司ID'].astype(str)

    # 6. (新) 合并公司名称 (反馈 2 解决方案)
    logging.info(f"共找到 {len(parsed_names_map)} 个从文件解析的公司名。")

    # 步骤 6a: 从我们解析的 map 创建 DataFrame (高优先级)
    parsed_names_df = pd.DataFrame(
        parsed_names_map.items(),
        columns=['CIK', settings.CIK_NAME_COLUMN]
    )
    parsed_names_df['CIK'] = parsed_names_df['CIK'].astype(str)

    # 步骤 6b: 合并两个名称来源 (解析的 + CSV回退的)
    # drop_duplicates 确保 parsed_names_df (文件解析) 优先
    final_name_map = pd.concat([
        parsed_names_df,
        cik_map_df
    ]).drop_duplicates(subset=['CIK'], keep='first')

    # 步骤 6c: 将结果与最终的名称映射表合并
    final_df = pd.merge(
        results_df,
        final_name_map[['CIK', settings.CIK_NAME_COLUMN]],
        left_on='公司ID',
        right_on='CIK',
        how='left'
    )

    final_df = final_df.rename(columns={settings.CIK_NAME_COLUMN: '公司名称'})
    final_df['公司名称'] = final_df['公司名称'].fillna('unknown')

    # 7. 整理并保存
    final_df = final_df[settings.OUTPUT_COLUMNS]
    final_df = final_df.drop_duplicates()

    logging.info(f"正在保存 {len(final_df)} 条最终数据到 {settings.OUTPUT_CSV_PATH}...")
    final_df.to_csv(settings.OUTPUT_CSV_PATH, index=False, encoding='utf-8-sig')
    logging.info(f"所有任务处理完毕。成功找到 {len(final_df)} 条数据。")


if __name__ == "__main__":
    run_processing()