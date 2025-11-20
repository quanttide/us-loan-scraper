# utils.py
# 包含所有数据处理、文本提取和 NLP 分析的辅助函数

import logging
import re
from pathlib import Path
import pandas as pd
import nltk
from bs4 import BeautifulSoup
import settings  # 导入配置以获取 HEADER_ONLY_CHAR_LIMIT 和 MIN_SENTENCE_LENGTH

# (★★★ V3 修改 ★★★)
# 从 settings.py 导入 V3 分层关键词
try:
    from settings import (
        CORE_KEYWORDS_REGEX,
        CONTEXT_KEYWORDS_REGEX,
        OPERATIONAL_CONTEXT_REGEX
    )
except ImportError:
    logging.critical("无法从 settings.py 导入 V3 关键词 (CORE_KEYWORDS_REGEX, ...)。")
    # 设置一个Bypass/Fallback，防止崩溃
    CORE_KEYWORDS_REGEX = re.compile(r'a^')  # 匹配不到任何东西
    CONTEXT_KEYWORDS_REGEX = re.compile(r'a^')
    OPERATIONAL_CONTEXT_REGEX = re.compile(r'a^')


# --- 1. NLTK 环境设置 ---

def setup_nltk():
    """
    (需求 4) 仅下载分句所需的 NLTK 包 ('punkt' 和 'punkt_tab')。
    """
    required_packages = ['punkt', 'punkt_tab']
    logging.info(f"正在验证/下载 NLTK 资源: {required_packages}...")

    all_downloaded = True
    for package in required_packages:
        try:
            # (修改) 使用 nltk.data.find 检查，如果找不到才下载
            nltk.data.find(f'tokenizers/{package}')
            logging.info(f"NLTK 资源 '{package}' 已存在。")
        except LookupError:
            logging.info(f"正在下载 NLTK 资源 '{package}'...")
            if not nltk.download(package, quiet=True):
                logging.error(f"下载 NLTK '{package}' 失败。")
                all_downloaded = False
            else:
                logging.info(f"NLTK 资源 '{package}' 下载成功。")
        except Exception as e:
            logging.error(f"NLTK 检查/下载 '{package}' 时发生意外错误: {e}")
            all_downloaded = False

    if all_downloaded:
        logging.info("所有 NLTK 资源准备就绪。")


# --- 2. 数据加载 ---

def load_cik_map(map_path: Path) -> pd.DataFrame:
    """
    加载 CIK-公司名称映射表。
    """
    if not map_path.exists():
        logging.error(f"CIK 映射表文件未找到: {map_path}")
        return pd.DataFrame()

    try:
        logging.info(f"正在加载 CIK 映射表: {map_path}")
        try:
            df = pd.read_csv(map_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(map_path, encoding='latin1')

        if 'CIK' not in df.columns:
            logging.error(f"CIK 映射表 {map_path} 中未找到 'CIK' 列。")
            return pd.DataFrame()

        # (新增) 确保 CIK 列是字符串
        if 'CIK' in df.columns:
            df['CIK'] = df['CIK'].astype(str)

        return df

    except Exception as e:
        logging.error(f"加载 CIK 映射表时发生错误: {e}")
        return pd.DataFrame()


# --- 3. 文本提取 ---

def get_document_text(file_path: Path) -> str | None:
    """
    (★ ★ ★ 关键修改 ★ ★ ★)
    不再信任 .txt 扩展名。统一使用 BeautifulSoup 处理所有文件
    (无论是 .txt 还是 .htm)，以剥离 <PAGE> 或 <html> 标签。
    """
    content = None
    try:
        # 1. 统一读取
        content_bytes = file_path.read_bytes()
        try:
            raw_text = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            raw_text = content_bytes.decode('latin1')

        # 2. 统一使用 BeautifulSoup 解析
        # 无论 .txt 还是 .htm，都用 lxml (或 html.parser) 清理
        try:
            soup = BeautifulSoup(raw_text, 'lxml')
        except Exception:
            logging.debug("lxml 解析器未找到或失败，切换到内置 html.parser")
            soup = BeautifulSoup(raw_text, 'html.parser')

        # 3. 统一提取文本，保留换行符
        content = soup.get_text(separator="\n", strip=True)

    except Exception as e:
        logging.warning(f"读取或解析文件失败 {file_path}: {e}")
        return None

    # 4. (保持) 统一的温和清理
    if content:
        # 1. 将多个空格和制表符替换为单个空格（保留换行符）
        content = re.sub(r'[ \t]+', ' ', content)
        # 2. 将多个连续的换行符替换为单个换行符（保留段落）
        content = re.sub(r'\n+', '\n', content)
        # 3. 移除开头和结尾的空白
        content = content.strip()
        return content

    return None


# --- 4. 元信息提取 (日期) ---
# (此部分来自您的 utils.py，保持不变)

# (需求 2) 关键词
PREAMBLE_KEYWORDS = r"(?:Effective Date|as of|dated this|dated as of|dated|Agreement\s+dated)"

# (修复 1) 限制月份
MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"

# (修复 2) 增加格式
DATE_REGEX_1 = re.compile(
    # (修改) 允许 st/nd/th, 例如 "December 22nd, 2004"
    rf"{PREAMBLE_KEYWORDS}\s+({MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})",
    re.IGNORECASE
)

DATE_REGEX_3 = re.compile(
    rf"{PREAMBLE_KEYWORDS}\s+(\d{{4}}-\d{{2}}-\d{{2}})",
    re.IGNORECASE
)
DATE_REGEX_4 = re.compile(
    # (修改) 允许 st/nd/th, 例如 "December 22nd, 2004" (无 preamble)
    rf"({MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})",
    re.IGNORECASE
)
DATE_REGEX_5 = re.compile(
    r"(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE
)

HEADER_PATTERNS = [DATE_REGEX_1, DATE_REGEX_3]
FALLBACK_PATTERNS = [DATE_REGEX_4, DATE_REGEX_5]


def extract_effective_date(text: str) -> str | None:
    """
    (V8)
    - 阶段 1: 在头部搜索高精度 (带Preamble) 的日期。
    - 阶段 2: 如果失败，在头部搜索低精度 (无Preamble) 的日期。
    - 阶段 3: 如果全部失败，则在全文中搜索所有模式（高精度+低精度）。
    """
    if not text:
        return None

    limit = 5000
    try:
        # (V3 修改) 从 settings.py 动态获取
        limit = settings.HEADER_ONLY_CHAR_LIMIT
    except AttributeError:
        if not hasattr(settings, 'HEADER_ONLY_CHAR_LIMIT_DEFAULTED'):
            logging.warning("settings.py 中未定义 HEADER_ONLY_CHAR_LIMIT，默认使用 5000。")
            setattr(settings, 'HEADER_ONLY_CHAR_LIMIT_DEFAULTED', True)

    header_text = text[:limit]

    # --- 阶段 1 & 2: 搜索头部 ---
    for pattern in HEADER_PATTERNS + FALLBACK_PATTERNS:
        match = pattern.search(header_text)
        if match:
            date_str = match.group(1).strip()
            cleaned_date = " ".join(date_str.split())
            return cleaned_date

    # --- 阶段 3: 全文回退搜索 ---
    logging.debug(f"日期头部搜索失败，正在扩展到全文进行(高+低)精度搜索...")

    for pattern in HEADER_PATTERNS + FALLBACK_PATTERNS:
        match = pattern.search(text)
        if match:
            date_str = match.group(1).strip()
            cleaned_date = " ".join(date_str.split())
            logging.debug(f"在全文中找到回退日期: {cleaned_date}")
            return cleaned_date

    return None


# --- 5. 供应链句子分析 ---
# (★★★ 此部分为V3修改核心 ★★★)
# (已移除此处的本地 Regex 定义, 改为从 settings.py 导入)

def find_supply_chain_sentences(text: str) -> list[str]:
    """
    (V3 - 增加上下文判断)
    使用 settings.py 中定义的分层关键词策略。
    """
    if not text:
        return []

    # (V2 修复) "缝合"被硬回车截断的句子
    text_for_splitting = text.replace('\n', ' ')

    matched_sentences = []

    try:
        sentences = nltk.sent_tokenize(text_for_splitting)
    except Exception as e:
        logging.error(f"NLTK 分句失败: {e}。文本可能过大或格式异常。")
        return []

    for sentence in sentences:

        # 移除多余空白
        cleaned_sentence = " ".join(sentence.split())

        # 检查最小长度 (从 settings.py 动态获取)
        try:
            if len(cleaned_sentence) < settings.MIN_SENTENCE_LENGTH:
                continue
        except AttributeError:
            logging.warning("settings.py 中未定义 MIN_SENTENCE_LENGTH，默认使用 50。")
            if len(cleaned_sentence) < 50:
                continue

        # --- (★★★ V3 核心逻辑 ★★★) ---
        # (使用从 settings.py 导入的 REGEX)

        # 规则 1: 如果包含“核心关键词”，无条件采纳
        if CORE_KEYWORDS_REGEX.search(cleaned_sentence):
            matched_sentences.append(cleaned_sentence)

        # 规则 2: 否则，如果包含“情境关键词”...
        elif CONTEXT_KEYWORDS_REGEX.search(cleaned_sentence):

            # ...则它必须也包含“运营情境词”才被采纳
            if OPERATIONAL_CONTEXT_REGEX.search(cleaned_sentence):
                matched_sentences.append(cleaned_sentence)
            # else:
            # (跳过) 匹配了 supplier/customer，但无运营上下文
            # (例如 "illegal gift to supplier, customer...")

        # --- (V3 逻辑结束) ---

    return matched_sentences


# --- 6. CIK 与公司名称解析 ---
# (此部分来自您的 utils.py，保持不变)

def get_cik_from_8k_text(file_content: str) -> str | None:
    """
    (修改 - 反馈 1) 从 8-K 文件的原始 .txt 文本内容中提取 CIK。
    """

    # 标志：re.IGNORECASE (忽略大小写) 和 re.DOTALL (使 . 匹配换行符)
    flags = re.IGNORECASE | re.DOTALL

    # 策略 1：首选查找 SUBJECT COMPANY CIK
    pattern_subject = re.compile(
        r"SUBJECT COMPANY:.*?CENTRAL INDEX KEY:\s*(\d{10})",
        flags
    )
    match_subject = pattern_subject.search(file_content)

    if match_subject:
        return match_subject.group(1).lstrip('0')  # <-- 去除前导0

    # 策略 2：备选方案，查找 Filer CIK (兼容 FILER: 和 FILED BY:)
    pattern_filer = re.compile(
        # (?:...) 是一个非捕获组，用于匹配 "FILER:" 或 "FILED BY:"
        r"(?:FILER:|FILED BY:).*?CENTRAL INDEX KEY:\s*(\d{10})",
        flags
    )
    match_filer = pattern_filer.search(file_content)

    if match_filer:
        return match_filer.group(1).lstrip('0')  # <-- 去除前导0

    # 如果两种策略都失败
    logging.warning(f"警告：未能在文件中找到 CIK 标签。")
    return None


# (需求 1) 用于从 8-K 主 .txt 文件中解析公司名
COMPANY_NAME_REGEX = re.compile(
    r"COMPANY CONFORMED NAME:\s+(.*)",
    re.IGNORECASE
)


def parse_company_name_from_main_filing(content: str | None) -> str | None:
    """
    (修改 - 反馈 2) 从 8-K 主 .txt 文件内容中解析公司名称。
    """
    if not content:
        logging.warning("因内容为空，无法解析公司名称。")
        return None

    try:
        match = COMPANY_NAME_REGEX.search(content)

        if match:
            name = match.group(1).strip()
            # (修改) 此处日志级别改为 debug，因为 V9 会始终尝试解析
            logging.debug(f"从主文件成功解析到公司名: {name}")
            return name
        else:
            logging.warning("在主文件中未找到 'COMPANY CONFORMED NAME' 标签。")
            return None

    except Exception as e:
        logging.error(f"解析主文件内容以获取公司名时失败: {e}")
        return None