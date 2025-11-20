import pandas as pd
import requests
import time
import logging
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# --- 配置 ---

# 配置日志
logging.basicConfig(
    filename='cik_fix.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 警告：必须替换为你自己的信息！
# SEC 要求 User-Agent 格式为 "Sample Company Name admin@samplecompany.com"
HEADERS = {
    "User-Agent": "wabcy",
    "Accept-Encoding": "gzip, deflate"
}

# 使用 SEC 官方的 REST API 端点
# 它返回干净的JSON，比 browse-edgar 好用
SEC_API_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_str}.json"


def build_session() -> requests.Session:
    """
    创建并配置一个健壮的 requests.Session。

    - 包含自动重试机制（针对 5xx 错误和速率限制 429）
    - 包含自定义的 User-Agent
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    # 配置重试策略
    retry_strategy = Retry(
        total=3,  # 总重试次数
        backoff_factor=1,  # 退避因子 (等待 1s, 2s, 4s...)
        status_forcelist=[429, 500, 502, 503, 504],  # 针对这些状态码进行重试
        allowed_methods=["GET"]  # 只对安全的GET方法重试
    )

    # 创建一个适配器并应用重试策略
    adapter = HTTPAdapter(max_retries=retry_strategy)

    # 将适配器挂载到 session
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def get_company_name_by_cik(cik: int, session: requests.Session) -> str | None:
    """
    通过CIK调用SEC API获取公司名称（使用官方API）。

    重试逻辑已由 session 的 HTTPAdapter 自动处理。
    """
    try:
        # CIK需要补全为10位数字（SEC API要求）
        cik_str = f"{cik:010d}"
        url = SEC_API_URL.format(cik_str=cik_str)

        # 使用 session 发起请求，timeout 仍然需要
        response = session.get(url, timeout=10)

        # 抛出HTTP错误（4xx, 5xx），Retry 机制会捕获 5xx
        response.raise_for_status()

        data = response.json()

        # 使用官方API的 'entityName' 字段，无需 .split()
        if "entityName" in data:
            return data["entityName"]
        else:
            logging.warning(f"CIK {cik} API响应中未找到 'entityName'")
            return None

    except requests.exceptions.HTTPError as e:
        # 特别处理 404 (Not Found)，这说明CIK无效，不应重试
        if e.response.status_code == 404:
            logging.warning(f"CIK {cik} (str: {cik_str}) 在SEC API未找到 (404)")
        else:
            # 其他 4xx 错误 (如 403 Forbidden)
            logging.error(f"CIK {cik} 请求失败 (HTTPError): {str(e)}")
        return None
    except requests.exceptions.RequestException as e:
        # 其他请求错误 (如 DNS, Timeout, ConnectionError)
        # 此时重试机制已执行完毕但仍失败
        logging.error(f"CIK {cik} 请求失败 (RequestException): {str(e)}")
        return None
    except (KeyError, ValueError) as e:
        # JSON 解析失败或 'entityName' 键不存在
        logging.error(f"CIK {cik} 解析失败: {str(e)}")
        return None


def fix_cik_tickers(input_file, output_file):
    """修复cik_tickers.csv文件，补全缺失的公司名称"""
    try:
        df = pd.read_csv(input_file)
    except FileNotFoundError:
        logging.error(f"输入文件未找到: {input_file}")
        print(f"错误：输入文件 {input_file} 未找到。")
        return

    logging.info(f"开始处理文件 {input_file}，共 {len(df)} 行数据")

    # 筛选出公司名称为空但CIK存在的行
    missing_mask = df["COMPANY_NAME"].isnull() & df["CIK"].notnull()
    missing_indices = df[missing_mask].index
    missing_count = len(missing_indices)

    if missing_count == 0:
        logging.info("没有需要补全的数据。")
        print("没有需要补全的数据。")
        return

    logging.info(f"发现 {missing_count} 行公司名称缺失，开始补全...")

    # 创建一个可重用的 Session
    session = build_session()

    # 逐行补全（使用tqdm显示进度）
    for idx in tqdm(missing_indices, total=missing_count, desc="补全公司名称"):
        cik = df.at[idx, "CIK"]

        # 调用函数获取名称
        # 注意：这里不再需要 time.sleep(5) 的重试逻辑
        # 因为 session 已经自动处理了失败重试
        company_name = get_company_name_by_cik(cik, session)

        if company_name:
            df.at[idx, "COMPANY_NAME"] = company_name
            # 日志级别改为 DEBUG 或 INFO，成功的日志太多会刷屏
            # logging.info(f"CIK {cik} 补全成功: {company_name}")
        else:
            # 补全失败（已重试），记录警告
            logging.warning(f"CIK {cik} 补全失败，保留为空")

        # 严格控制API请求频率（SEC限制每秒最多10次）
        # 放在循环的最后，确保每次迭代至少间隔 0.1 秒
        time.sleep(0.1)  # 10次/秒

    # 关闭 session
    session.close()

    # 保存修复后的文件
    df.to_csv(output_file, index=False)
    logging.info(f"修复完成，结果保存至 {output_file}")

    # 检查是否仍有缺失
    remaining_missing = df["COMPANY_NAME"].isnull() & df["CIK"].notnull()
    remaining_count = remaining_missing.sum()

    if remaining_count == 0:
        print("所有公司名称缺失的行已成功补全！")
    else:
        print(f"修复后仍有 {remaining_count} 行公司名称缺失，详情请查看日志")
        missing_ciks = df[remaining_missing]["CIK"].tolist()
        print(f"缺失公司名称的CIK列表 (前10个): {missing_ciks[:10]}...")


if __name__ == "__main__":

    # 检查 User-Agent 是否已修改
    if "Your Name" in HEADERS["User-Agent"]:
        print("=" * 80)
        print("!! 警告：请在代码中修改 HEADERS 字典中的 User-Agent !!")
        print("!! SEC 要求提供有效的联系方式 (如 'My Company Name my.email@company.com') !!")
        print("=" * 80)

    else:
        INPUT_FILE = "cik_tickers.csv"
        OUTPUT_FILE = "cik_tickers_fixed.csv"
        fix_cik_tickers(INPUT_FILE, OUTPUT_FILE)