# src/settings.py
# (V5.6 - 词库增强版：强化关系维护与服务型供应链提取)

import re
import logging
from pathlib import Path

# --- 1. 路径配置 ---

# 根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据源路径
BASE_DATA_PATH = BASE_DIR / "data" / "Archives" / "edgar" / "data"
# 服务器数据源 (如有需要保持覆盖)
# BASE_DATA_PATH = BASE_DIR.parent / "py-sec-edgar" / "data" / "Archives" / "edgar" / "data"

# CIK 映射表
CIK_MAP_PATH = BASE_DIR / "refdata" / "cik_tickers.csv"

# 输出文件
OUTPUT_CSV_PATH = BASE_DIR / "supply_chain_sentences.csv"

# --- 2. 提取规则配置 ---

# 预筛选：贷款合同关键词
LOAN_KEYWORDS_REGEX = re.compile(
    r'\b(loan|credit|facility|agreement|indenture)\b',
    re.IGNORECASE
)

# --- 关键词配置 (核心逻辑更新) ---

# 核心词 (直接命中)
CORE_KEYWORDS_REGEX = re.compile(
    r"""
    \b(
    supply[\s\-]chain(s)?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# 情境词 (实体对象：供应商/客户/合作伙伴)
# 更新：扩充了 manufacturer, licensor, client, franchisee 等
CONTEXT_KEYWORDS_REGEX = re.compile(
    r"""
    \b(
    # --- 供应商/上游 ---
    supplier(s)? |
    vendor(s)? |
    manufacturer(s)? |
    licensor(s)? |          # 关键：涉及IP/软件授权
    sub(-)?contractor(s)? | # 分包商
    service\s+provider(s)? |

    # --- 客户/下游 ---
    customer(s)? |
    client(s)? |            # 关键：Customer的常见同义词
    distributor(s)? |
    reseller(s)? |
    licensee(s)? |
    franchisee(s)?          # 关键：特许经营
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# 运营词 (必须与情境词同时出现)
# 更新：重点增加了“关系维护”类词汇，以及“服务/软件/库存”等词汇
OPERATIONAL_CONTEXT_REGEX = re.compile(
    r"""
    \b(
    # --- A. 关系维护类 (最重要的类别) ---
    relationship(s)? |      # 核心词：maintain relationship
    relation(s)? |
    doing\s+business |      # e.g., cease doing business with...
    goodwill |              # 商誉
    franchise |             # 特许经营权

    # --- B. 动作/状态类 ---
    supply | supplying | supplied |
    purchase | purchasing |
    procure | procurement | 
    order(s)? |
    fulfill | fulfillment |
    ship | shipping | shipment(s)? |
    deliver | delivery | deliverables |
    transport | transportation |
    provide\s+services |    # 提供服务

    # --- C. 合同/资产类 ---
    agreement(s)? |
    contract(s)? |
    inventory |             # 库存
    stock |
    material(s)? |
    goods |
    product(s)? |
    service(s)? |           # 服务型供应链
    part(s)? |
    component(s)? |
    equipment |
    software                # 软硬件供应链
    )\b
    """,
    re.IGNORECASE | re.VERBOSE
)

# --- ★★★ 噪音清洗规则 ★★★ ---

# 1. 目录/长省略号
NOISE_DOTS_REGEX = re.compile(r'\.{3,}')

# 2. 垃圾字符
NOISE_GARBAGE_REGEX = re.compile(r'^[\d\W\s]+$')

# 3. 目录页码结尾
NOISE_PAGE_NUMBER_REGEX = re.compile(r'\s+\d+\s*$')

# 4. 列表条款/小标题
NOISE_LIST_REGEX = re.compile(
    r"""
    ^
    \s* (?:                       
       \(?[a-zA-Z0-9]{1,3}\)  
       |
       [a-zA-Z0-9]{1,3}\.     
    )
    \s+
    .* (?:
       [;:]\s*$               
       |
       [a-zA-Z0-9]\s*$        
    )
    """,
    re.VERBOSE | re.IGNORECASE
)

# 5. 法律定义 (例如 "Term" means...)
NOISE_DEFINITION_REGEX = re.compile(
    r"""
    (?:
        ^\s* ["“] [^"”]+ ["”] \s+
        (?:
            ,?\s* as \s+ used \s+ (?:herein|in \s+ this \s+ \w+) ,?\s*
        )?
        (?: shall \s+ )?
        (?: mean | include ) s?
    )
    |
    (?:
        ^ \s* \(? [a-z0-9]+ \)? \s* For \s+ purposes \s+ of \s+ this \s+ (?:Agreement|Section|Indenture)
    )
    """,
    re.IGNORECASE | re.VERBOSE
)

# 6. 法律程序/动议
NOISE_LEGAL_JARGON_REGEX = re.compile(
    r"""
    (?:
        Motion(s)? \s+ (?:for|Relating \s+ to) \s+ (?:Order|Entry|Authority|Vendors|Customers)
    )
    |
    (?:
        under \s+ \d+ \s+ U\.S\.C\. \S* \s* $
    )
    """,
    re.IGNORECASE | re.VERBOSE
)

# 7. 表格/报表噪音 (Vendor List/Aging Reports)
NOISE_TABLE_REGEX = re.compile(
    r"""
    (?:
        -{5,}                     # 连续横杠分隔符
    )
    |
    (?:
        \bPAGE\s+\d+              # "PAGE 18"
    )
    |
    (?:
        \bVENDOR\s+ID\b           # "VENDOR ID"
    )
    |
    (?:
        \bAP\s+AGING\b            # "AP AGING"
    )
    |
    (?:
        \bTOTAL\s+[\d,]+          # "TOTAL 104,184"
    )
    |
    (?:
        ^\s*[\w\d]+\s+[\d,.]+\s+  # 疑似表格数据行 (代码+数字)
    )
    """,
    re.IGNORECASE | re.VERBOSE
)

# --- 其他配置 ---

MIN_SENTENCE_LENGTH = 50

DATE_REGEX = re.compile(
    r"(?:effective\s+(?:as\s+of|date)\s*[:=\s]?|dated\s+as\s+of)\s*([\w\s,]+\d{4})",
    re.IGNORECASE
)

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