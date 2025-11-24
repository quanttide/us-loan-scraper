# src/utils.py
# (V18 - 完整版：指纹去重 + 增强解析)

import logging
import re
from pathlib import Path
import pandas as pd
import nltk
from bs4 import BeautifulSoup
import settings

# 导入正则
try:
    from settings import (
        CORE_KEYWORDS_REGEX,
        CONTEXT_KEYWORDS_REGEX,
        OPERATIONAL_CONTEXT_REGEX
    )
except ImportError:
    # 防止 IDE 报错的占位符
    CORE_KEYWORDS_REGEX = re.compile(r'a^')
    CONTEXT_KEYWORDS_REGEX = re.compile(r'a^')
    OPERATIONAL_CONTEXT_REGEX = re.compile(r'a^')


# --- 1. NLTK 环境设置 ---

def setup_nltk():
    """
    仅下载分句所需的 NLTK 包。
    """
    required_packages = ['punkt', 'punkt_tab']
    logging.info(f"正在验证/下载 NLTK 资源: {required_packages}...")

    all_downloaded = True
    for package in required_packages:
        try:
            nltk.data.find(f'tokenizers/{package}')
        except LookupError:
            logging.info(f"正在下载 NLTK 资源 '{package}'...")
            try:
                nltk.download(package, quiet=True)
            except Exception as e:
                logging.error(f"下载 NLTK '{package}' 失败: {e}")
                all_downloaded = False

    if all_downloaded:
        logging.info("所有 NLTK 资源准备就绪。")


# --- 2. 数据加载 ---

def load_cik_map(map_path: Path) -> pd.DataFrame:
    """
    加载 CIK-公司名称映射表。
    """
    if not map_path.exists():
        return pd.DataFrame()

    try:
        # 尝试 utf-8，失败尝试 latin1
        try:
            df = pd.read_csv(map_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(map_path, encoding='latin1')

        if 'CIK' in df.columns:
            df['CIK'] = df['CIK'].astype(str)

        return df
    except Exception as e:
        logging.error(f"加载 CIK 映射表失败: {e}")
        return pd.DataFrame()


# --- 3. 文本提取 ---

def get_document_text(file_path: Path) -> str | None:
    """
    统一使用 BeautifulSoup 处理所有文件以剥离标签。
    """
    try:
        file_size = file_path.stat().st_size
        # 20MB 大小限制
        if file_size > 20 * 1024 * 1024:
            logging.warning(f"文件过大 ({file_size / 1024 / 1024:.2f} MB)，跳过: {file_path.name}")
            return None
    except Exception:
        pass

    content = None
    try:
        content_bytes = file_path.read_bytes()
        try:
            raw_text = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            raw_text = content_bytes.decode('latin1')

        try:
            soup = BeautifulSoup(raw_text, 'lxml')
        except Exception:
            soup = BeautifulSoup(raw_text, 'html.parser')

        content = soup.get_text(separator="\n", strip=True)

    except Exception as e:
        # logging.warning(f"解析文件失败 {file_path.name}: {e}")
        return None

    if content:
        # 清洗多余空白
        content = re.sub(r'[ \t]+', ' ', content)
        content = re.sub(r'\n+', '\n', content)
        content = content.strip()
        return content

    return None


# --- 4. 元信息提取 (日期) ---

PREAMBLE_KEYWORDS = r"(?:Effective Date|as of|dated this|dated as of|dated|Agreement\s+dated)"
MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"

DATE_REGEX_1 = re.compile(
    rf"{PREAMBLE_KEYWORDS}\s+({MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})",
    re.IGNORECASE
)
DATE_REGEX_3 = re.compile(
    rf"{PREAMBLE_KEYWORDS}\s+(\d{{4}}-\d{{2}}-\d{{2}})",
    re.IGNORECASE
)
DATE_REGEX_4 = re.compile(
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
    提取生效日期。
    """
    if not text:
        return None

    # 限制头部搜索范围
    limit = getattr(settings, 'HEADER_ONLY_CHAR_LIMIT', 5000)
    header_text = text[:limit]

    # 阶段 1 & 2: 搜索头部
    for pattern in HEADER_PATTERNS + FALLBACK_PATTERNS:
        match = pattern.search(header_text)
        if match:
            date_str = match.group(1).strip()
            cleaned_date = " ".join(date_str.split())
            return cleaned_date

    # 阶段 3: 全文回退搜索
    for pattern in HEADER_PATTERNS + FALLBACK_PATTERNS:
        match = pattern.search(text)
        if match:
            date_str = match.group(1).strip()
            cleaned_date = " ".join(date_str.split())
            return cleaned_date

    return None


# --- 5. 供应链句子分析 (核心修改：指纹去重) ---

def find_supply_chain_sentences(text: str) -> list[str]:
    """
    使用 settings.py 中定义的分层关键词策略，并过滤噪音。
    此处引入“指纹去重”逻辑。
    """
    if not text:
        return []

    # 预处理：将换行符替换为空格，防止句子被截断
    text_for_splitting = text.replace('\n', ' ')

    matched_sentences = []

    # 【指纹去重集合】
    # 存储标准化后的句子指纹（小写 + 仅保留字母/汉字），忽略标点和空格差异
    seen_fingerprints = set()

    try:
        sentences = nltk.sent_tokenize(text_for_splitting)
    except Exception as e:
        logging.error(f"NLTK 分句失败: {e}")
        return []

    for sentence in sentences:
        cleaned_sentence = " ".join(sentence.split())

        # 1. 长度检查
        if len(cleaned_sentence) < settings.MIN_SENTENCE_LENGTH:
            continue

        # 【生成指纹】
        # 移除所有非字母和非中文字符，并转为小写
        # 这样 "Sentence A." 和 "Sentence A" (无点) 会被视为相同
        fingerprint = re.sub(r'[^a-zA-Z\u4e00-\u9fa5]', '', cleaned_sentence).lower()

        # 如果指纹为空或已存在，跳过
        if not fingerprint:
            continue
        if fingerprint in seen_fingerprints:
            continue

        # 3. 格式与内容噪音清洗 (基于 settings.py 中的正则)
        if settings.NOISE_DOTS_REGEX.search(cleaned_sentence):
            continue
        if settings.NOISE_GARBAGE_REGEX.match(cleaned_sentence):
            continue
        if settings.NOISE_PAGE_NUMBER_REGEX.search(cleaned_sentence):
            # 仅当行尾是数字且没有句号时过滤
            if not cleaned_sentence.strip().endswith('.'):
                continue
        if settings.NOISE_LIST_REGEX.match(cleaned_sentence):
            continue

        # 4. 法律定义、程序与表格噪音过滤
        if settings.NOISE_DEFINITION_REGEX.search(cleaned_sentence):
            continue
        if settings.NOISE_LEGAL_JARGON_REGEX.search(cleaned_sentence):
            continue
        if hasattr(settings, 'NOISE_TABLE_REGEX') and settings.NOISE_TABLE_REGEX.search(cleaned_sentence):
            continue

        # --- (关键词逻辑) ---
        is_match = False
        if CORE_KEYWORDS_REGEX.search(cleaned_sentence):
            is_match = True
        elif CONTEXT_KEYWORDS_REGEX.search(cleaned_sentence):
            if OPERATIONAL_CONTEXT_REGEX.search(cleaned_sentence):
                is_match = True

        if is_match:
            matched_sentences.append(cleaned_sentence)
            seen_fingerprints.add(fingerprint)  # 记录指纹

    return matched_sentences


# --- 6. CIK 与公司名称解析 (增强版) ---

def get_cik_from_8k_text(file_content: str) -> str | None:
    """
    从 8-K 文件的原始 .txt 文本内容中提取 CIK。
    """
    if not file_content:
        return None

    flags = re.IGNORECASE | re.DOTALL

    # 1. 尝试标准的 "SUBJECT COMPANY" 块
    pattern_subject = re.compile(r"SUBJECT COMPANY:.*?CENTRAL INDEX KEY:\s*(\d{10})", flags)
    match_subject = pattern_subject.search(file_content)
    if match_subject:
        return match_subject.group(1).lstrip('0')

    # 2. 尝试 "FILER" 块
    pattern_filer = re.compile(r"(?:FILER:|FILED BY:).*?CENTRAL INDEX KEY:\s*(\d{10})", flags)
    match_filer = pattern_filer.search(file_content)
    if match_filer:
        return match_filer.group(1).lstrip('0')

    # 3. 直接查找 CENTRAL INDEX KEY (全局回退，限制前2000字符)
    header_part = file_content[:2000]
    pattern_direct = re.compile(r"CENTRAL INDEX KEY:\s*(\d{10})", flags)
    match_direct = pattern_direct.search(header_part)
    if match_direct:
        return match_direct.group(1).lstrip('0')

    return None


COMPANY_NAME_REGEX = re.compile(r"COMPANY CONFORMED NAME:\s+(.*)", re.IGNORECASE)


def parse_company_name_from_main_filing(content: str | None) -> str | None:
    """
    从 8-K 主 .txt 文件内容中解析公司名称。
    """
    if not content:
        return None

    # 限制搜索范围在前 2000 字符
    header_part = content[:2000]

    try:
        match = COMPANY_NAME_REGEX.search(header_part)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None