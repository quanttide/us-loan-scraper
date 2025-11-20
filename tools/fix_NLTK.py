# fix_nltk.py
# 这是一个一次性的手动修复脚本 (v2 - 最终版)

import nltk
import logging

# 配置日志，以便我们能看到详细信息
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# NLTK 错误日志中明确要求的所有资源
required_packages = [
    'punkt',
    'punkt_tab',
    'words',
    'averaged_perceptron_tagger',
    'averaged_perceptron_tagger_eng',  # 修复上一个错误
    'maxent_ne_chunker',
    'maxent_ne_chunker_tab'  # <-- 新增：修复当前的错误
]

logging.info(f"--- 开始手动修复 NLTK 资源 (v2) ---")
logging.info(f"将尝试下载: {required_packages}")

all_success = True
for package in required_packages:
    try:
        logging.info(f"正在下载 '{package}'...")
        # (重要) 我们在这里不使用 quiet=True
        # 你应该会在终端看到下载进度条或 "already up-to-date"
        nltk.download(package, raise_on_error=True)
        logging.info(f"--- 成功处理 '{package}' ---")
    except Exception as e:
        logging.error(f"!!! 下载 '{package}' 失败: {e} !!!")
        logging.error("请检查你的网络连接、防火墙或代理设置。")
        all_success = False

if all_success:
    logging.info("--- NLTK 修复程序执行完毕 ---")
    logging.info("所有 NLTK 资源均已准备就绪。请现在运行 main.py。")
else:
    logging.error("!!! 部分 NLTK 资源下载失败。请解决网络问题后重试。 !!!")