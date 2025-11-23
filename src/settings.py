# settings.py
# (V4 - 修正版)
# 严格遵循 V13 的词汇表，仅对其应用上下文判断

import re
import logging
from pathlib import Path

# --- 1. 路径配置 ---

# 根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# SEC 文件基础路径
BASE_DATA_PATH = BASE_DIR / "data" / "Archives" / "edgar" / "data"

# BASE_DATA_PATH = BASE_DIR.parent / "py-sec-edgar" / "data" / "Archives" / "edgar" / "data"

# CIK 映射表路径
CIK_MAP_PATH = BASE_DIR / "refdata" / "cik_tickers.csv"

# 最终输出文件
OUTPUT_CSV_PATH = BASE_DIR / "supply_chain_sentences.csv"

# --- 2. 提取规则配置 ---

# (V10/V11) 筛选 1：贷款合同关键词 (用于 main.py 预筛选)
LOAN_KEYWORDS_REGEX = re.compile(
    r'\b(loan|credit|facility|agreement|indenture)\b',
    re.IGNORECASE
)

# --- (★★★ V4 修正逻辑 ★★★) ---
# 基于 V13 的词汇表进行收紧

# 规则 1: 核心关键词 (来自 V13)
# (V4 修正: 只保留 V13 中的 'supply-chain' 作为核心词)
CORE_KEYWORDS_REGEX = re.compile(
    r"""
    \b(
    supply[\s\-]chain(s)?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# 规则 2: 情境关键词 (来自 V13)
# (V4 修正: V13 中的其他词汇全部放入这里)
CONTEXT_KEYWORDS_REGEX = re.compile(
    r"""
    \b(
    supplier(s)? |
    customer(s)? |
    vendor(s)? |
    distributor(s)? |
    reseller(s)?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# 规则 3: 运营情境词 (用于辅助"情境关键词")
# (这个列表保持不变，用于过滤 "illegal gift to supplier" 等情况)
OPERATIONAL_CONTEXT_REGEX = re.compile(
    r"""
    \b(
    agreement(s)? |
    contract(s)? |
    order(s)? |
    parts |
    component(s)? |
    goods |
    materials |
    fulfillment |
    transport(s)? | transportation
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)
# --- (V4 逻辑结束) ---


# (V10/V11) 最小句子/段落长度 (用于排除标题)
MIN_SENTENCE_LENGTH = 50

# (V8) 筛选 3：生效日期提取
DATE_REGEX = re.compile(
    r"(?:effective\s+(?:as\s+of|date)\s*[:=\s]?|dated\s+as\s+of)\s*([\w\s,]+\d{4})",
    re.IGNORECASE
)
# 头部搜索范围 (字符数)
HEADER_SEARCH_CHARS = 5000

# 新增：定义日期提取的头部搜索范围 (字符数)
HEADER_ONLY_CHAR_LIMIT = 5000

# --- 3. 数据表配置 ---

# CIK 映射表中代表公司名称的列名
CIK_NAME_COLUMN = 'COMPANY_NAME'

# 最终输出的列顺序
OUTPUT_COLUMNS = [
    '公司ID',
    '公司名称',
    '贷款合同ID',
    '贷款起效日期',
    '含供应链信息句子'
]

# --- 4. 日志配置 ---
LOGGING_CONFIG = {
    "level": logging.INFO,
    "format": '%(asctime)s - %(levelname)s - %(message)s'
}