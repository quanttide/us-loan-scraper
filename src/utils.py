# src/utils.py
# (V5.8 - 修复 lxml 报错，改用内置解析器)

import re
import nltk
import logging
import hashlib
import pandas as pd
from bs4 import BeautifulSoup
from pathlib import Path

# 导入配置
import settings

# 配置日志
logger = logging.getLogger(__name__)


def setup_nltk():
    """
    初始化 NLTK，确保 punkt 分词器可用。
    """
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        logger.info("Downloading NLTK punkt tokenizer...")
        nltk.download('punkt')
        nltk.download('punkt_tab')


def load_cik_map(file_path):
    """
    加载 CIK 映射表 (Ticker -> CIK)。
    """
    try:
        if not Path(file_path).exists():
            logger.error(f"CIK map file not found: {file_path}")
            return pd.DataFrame()

        # 读取 CSV，强制 CIK 为字符串以保留前导零
        df = pd.read_csv(file_path, dtype={'CIK': str})
        return df
    except Exception as e:
        logger.error(f"Error loading CIK map: {e}")
        return pd.DataFrame()


def get_document_text(file_path):
    """
    读取文件并清理 HTML 标签 (如果存在)。
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # 简单的 HTML 标签清洗
        if "<HTML>" in content.upper() or "<?XML" in content.upper():
            # 🔴 修复：改用 'html.parser' (Python内置)，避免 lxml 缺失报错
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            return text
        else:
            return content
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return ""


def extract_effective_date(text):
    """
    提取贷款生效日期，提取不到返回空字符串。
    """
    # 截取头部以提高效率
    header_text = text[:settings.HEADER_ONLY_CHAR_LIMIT]

    match = settings.DATE_REGEX.search(header_text)
    if match:
        return match.group(1).strip()
    return ""


def find_supply_chain_sentences(text: str) -> list[str]:
    """
    分句并筛选包含供应链信息的句子。

    【核心逻辑 V5.6】
    句子保留的条件是：
    1. 包含核心词 (CORE_KEYWORDS_REGEX) -> 如 "supply chain"
       OR
    2. 同时包含实体词 (CONTEXT_KEYWORDS_REGEX) AND 运营/关系词 (OPERATIONAL_CONTEXT_REGEX)
       -> 如 "maintain relationship" (运营) + "with suppliers" (实体)
    """
    if not text:
        return []

    # 1. NLTK 分句
    try:
        sentences = nltk.sent_tokenize(text)
    except Exception:
        # 回退方案
        sentences = text.split('. ')

    valid_sentences = []
    seen_hashes = set()  # 单文件内去重

    for sent in sentences:
        # 清洗空白字符
        sent_clean = sent.strip().replace('\n', ' ')

        # 基础长度过滤
        if len(sent_clean) < settings.MIN_SENTENCE_LENGTH:
            continue

        # --- 🔍 筛选逻辑核心 ---

        # A. 核心词直接命中
        has_core = bool(settings.CORE_KEYWORDS_REGEX.search(sent_clean))

        # B. 实体词 + 运营词 组合命中
        has_context = bool(settings.CONTEXT_KEYWORDS_REGEX.search(sent_clean))
        has_operational = bool(settings.OPERATIONAL_CONTEXT_REGEX.search(sent_clean))

        is_relevant = has_core or (has_context and has_operational)

        if is_relevant:
            # --- 🚫 噪音过滤 ---
            if settings.NOISE_LEGAL_JARGON_REGEX.search(sent_clean):
                continue
            if settings.NOISE_TABLE_REGEX.search(sent_clean):
                continue
            if settings.NOISE_LIST_REGEX.search(sent_clean):
                continue
            if settings.NOISE_DOTS_REGEX.search(sent_clean):
                continue
            if settings.NOISE_PAGE_NUMBER_REGEX.search(sent_clean):
                continue
            if settings.NOISE_GARBAGE_REGEX.search(sent_clean):
                continue
            if settings.NOISE_DEFINITION_REGEX.search(sent_clean):
                continue

            # --- 🔒 指纹去重 ---
            sent_hash = hashlib.md5(sent_clean.encode('utf-8')).hexdigest()

            if sent_hash not in seen_hashes:
                seen_hashes.add(sent_hash)
                valid_sentences.append(sent_clean)

    return valid_sentences