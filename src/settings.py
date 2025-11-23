# src/settings.py
# (V5 - 普适性格式清洗版)

import re
import logging
from pathlib import Path

# --- 1. 路径配置 ---

# 根目录(us_loan)
BASE_DIR = Path(__file__).resolve().parent.parent

# SEC 文件基础路径
BASE_DATA_PATH = BASE_DIR / "data" / "Archives" / "edgar" / "data"

# BASE_DATA_PATH = BASE_DIR.parent / "py-sec-edgar" / "data" / "Archives" / "edgar" / "data"

# CIK 映射表路径
CIK_MAP_PATH = BASE_DIR / "refdata" / "cik_tickers.csv"

# 最终输出文件
OUTPUT_CSV_PATH = BASE_DIR / "supply_chain_sentences.csv"

# --- 2. 提取规则配置 ---

# 筛选 1：贷款合同关键词 (用于 main.py 预筛选)
LOAN_KEYWORDS_REGEX = re.compile(
    r'\b(loan|credit|facility|agreement|indenture)\b',
    re.IGNORECASE
)

# --- 关键词配置 (保持原有的宽松逻辑) ---

# 规则 1: 核心关键词
CORE_KEYWORDS_REGEX = re.compile(
    r"""
    \b(
    supply[\s\-]chain(s)?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# 规则 2: 情境关键词
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

# 规则 3: 运营情境词
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

# --- ★★★ 新增：普适性噪音清洗规则 ★★★ ---

# 1. 目录/长省略号模式：匹配连续 3 个及以上的点号
# 用于过滤 "Inventory.......................50" 这类目录行
NOISE_DOTS_REGEX = re.compile(r'\.{3,}')

# 2. 垃圾字符模式：匹配仅由符号、数字、空格组成的句子
# 正常句子必须包含一定量的字母
NOISE_GARBAGE_REGEX = re.compile(r'^[\d\W\s]+$')

# 3. 目录页码结尾模式：匹配以数字结尾的行（用于结合标点检查）
# 用于识别 "Risk Factors 15" 这种没有句号且以页码结尾的行
NOISE_PAGE_NUMBER_REGEX = re.compile(r'\s+\d+\s*$')


# --- 其他配置 ---

# 最小句子长度
MIN_SENTENCE_LENGTH = 50

# 生效日期提取
DATE_REGEX = re.compile(
    r"(?:effective\s+(?:as\s+of|date)\s*[:=\s]?|dated\s+as\s+of)\s*([\w\s,]+\d{4})",
    re.IGNORECASE
)

# 头部搜索范围 (字符数)
HEADER_ONLY_CHAR_LIMIT = 5000

# --- 3. 数据表配置 ---

CIK_NAME_COLUMN = 'COMPANY_NAME'

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