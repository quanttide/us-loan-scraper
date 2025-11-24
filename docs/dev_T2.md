### 一、项目目标

基于 SEC Edgar 下载的合同文件 (htm/txt)，识别含供应链关键词（`supplier`, `customer`, `supply chain` 及其变体）的句子。构建一个「公司ID - 公司名称 - 合同ID - 贷款生效日期 - 供应链句子」的结构化数据集 (Firm-Contract-Sentence Level)。

### 二、文件结构与元信息规则

#### 1. 文件存储结构

```
data/
└── Archives/edgar/data/
    └── [CIK]/            # 公司唯一标识 (公司ID)
        └── [FilingID]/       # 申报文件唯一标识 (合同ID)
            ├── [文档].htm
        └── [文档].txt
```

#### 2. 元信息提取规则 (已修订)

- **公司 ID (CIK)**：从路径中提取 `[CIK]`。
- **合同 ID (FilingID)**：从路径中提取 `[FilingID]`。
- **公司名称 (Company Name)**：
  - **(已废除)** 废除从合同文本中解析 "Party A" 或 "借款人" 的方案。
  - **(新方案)** 采用 `CIK` 作为唯一标识。在数据构建的最后阶段，通过外部权威的 **CIK-公司名称映射表** (如 SEC 官方 CIK-Ticker-Name Mappings) 进行左连接 (VLookup)，批量填充标准化的公司名称。
- **贷款生效日期 (Effective Date)**：
  - **(优化)** 仅在合同文本的**头部区域** (如前 5000 字符) 搜索 "Effective Date", "as of" 等关键词及关联的日期格式 (YYYY-MM-DD, Month DD, YYYY)。
  - 若头部区域未找到，则标记为 "unknown"。

### 三、核心流程设计

#### 1. 数据准备阶段

- **文件遍历**：递归扫描 `data/Archives/edgar/data/` 目录，按 CIK -> FilingID 层级遍历。
- **文件筛选**：优先处理 `.txt` 文件。若无，则处理 `.htm` 文件。

#### 2. 文本提取与预处理阶段

- **文本提取 (工具化)**：
  - 对 `.txt` 文件：读取文本，处理编码问题 (尝试 `utf-8`, `latin-1`)。
  - 对 `.htm` 文件：**必须使用 `BeautifulSoup` (或 `lxml`)**。调用 `soup.get_text(separator=" ", strip=True)` 提取纯文本，确保标签间文本正确连接。
- **预处理**：
  - 清洗：去除多余的空白字符、特殊控制符 (如 `\xa0`)。
  - **分句 (工具化)**：**必须使用 `NLTK` (`nltk.sent_tokenize`) 或 `spaCy`**。禁止使用基于标点符号的简单规则，以确保 "U.S.A.", "Inc." 等缩写不导致句子错误拆分。

#### 3. 供应链句子识别阶段

- **关键词匹配 (高精度)**：

  - 编译一个**包含词边界 (`\b`)** 的正则表达式，并设置忽略大小写 (`re.IGNORECASE`)。

  - **Regex 示例**：

    Python

    ```
    import re
    KEYWORDS = r'\b(supplier(s)?|customer(s)?|supply[\s\-]chain)\b'
    compiled_regex = re.compile(KEYWORDS, re.IGNORECASE)
    ```

- **句子筛选**：

  - 遍历由 `NLTK/spaCy` 拆分出的所有句子。
  - 对每个句子执行 `compiled_regex.search(sentence)`。
  - 保留所有匹配成功的句子（保留原句大小写和内容）。
  
  
  
  > [!IMPORTANT]
  >
  > 确认一下逻辑：对于这样一个文件夹，我们首先读取0001144204-04-022949.txt文件（这是8-k)报表的txt版本，我们在里面读取到公司名和对应CIK，具体读取方法是关键字搜寻COMPANY CONFORMED NAME:和CENTRAL INDEX KEY:（需要去空格），然后到000114420404022949文件夹中读取附件，里面的8-k文件略过例如：0001-(8-K)_v010499_8-k.txt，文件名里有(8-K)，剩下的再去具体找供应链句子

#### 4. 数据集构建阶段

- **结构化整合**：
  - 初始化一个列表 (List) 用于存放结果。
  - 对于每个处理的合同文件，提取元信息 (CIK, FilingID, Effective Date)。
  - 对于该合同中筛选出的每个句子，生成一条记录：`{CIK, FilingID, Effective_Date, Sentence_Text}`。
  - 同一合同的多个句子会生成多行数据。
- **数据校验**：
  - 去重：删除 CIK, FilingID, Sentence_Text 完全相同的重复行。
  - 标记：对缺失的 "Effective Date" 标记为 "unknown"。
- **最终输出 (CSV)**：
  1. 将结果列表转换为 `pandas` DataFrame。
  2. 读取预先准备的 "CIK-公司名称映射表"。
  3. 通过 `CIK` 字段执行 `merge` (Left Join)，将 "公司名称" 字段匹配到 DataFrame 中。
  4. 按指定顺序 (`公司ID`, `公司名称`, `合同ID`, `贷款起效日期`, `含供应链信息句子`) 输出为 CSV 文件。

### 四、质量控制要点

1. **文本提取完整性**：
   - 采用多编码尝试。
   - `BeautifulSoup` 提取时保留表格文本。
2. **元信息准确性**：
   - 日期提取：必须验证 "Header-Only" 策略的覆盖率，确保 99% 以上的日期能在此区域找到。
   - 公司名称：准确性由 CIK 映射表保证。QC 重点在于检查 Join 后的 `CIK` 与 `公司名称` 是否 100% 匹配，有无 CIK 缺失。
3. **关键词匹配精度**：
   - 必须使用带词边界 `\b` 的 Regex。严禁使用 `if "supplier" in sentence` 此类简单字符串查找，以防止部分匹配 (如 "microsupplier")。
   - 必须支持连字符 (`supply-chain`) 和空格 (`supply chain`) 的等价匹配。

### 五、实施步骤

1. **环境与数据准备**：
   -  **获取并清洗 CIK-公司名称映射表**，保存为 CSV 或 Parquet 格式。
   - 明确工具栈：`Python 3.x`, `pandas`, `BeautifulSoup4`, `lxml`, `nltk` (或 `spaCy`)。
2. **需求确认**：明确需处理的文件范围。
3. **规则迭代 (小批量)**：
   -  基于 1-2 个样本文件，验证元信息 (特别是日期) 的 "Header-Only" 提取逻辑。
   - 验证 `NLTK/spaCy` 分句效果。
   -  验证 `Regex` 关键词库的准确性。
4. **批量处理**：(不变) 对全量文件执行提取流程，生成初步数据集 (不含公司名称)。
5. **数据整合与校验**：
   -  执行 CIK 映射表 Join，生成最终数据集。
   - 抽样检查数据集 (尤其是 `unknown` 日期 和匹配到的句子)，修正规则。
6. **成果交付**： 输出最终 CSV 数据集及提取日志。



### 六、风险与应对

- **风险 1**：合同文本格式混乱（如扫描件转文本导致乱码）。
  - **应对**：跳过乱码率（基于非标准 ASCII 字符比例判断）超 30% 的文件，标记后人工处理。
- **风险 2**：元信息缺失（如无生效日期）。
  - **应对**：在数据集中用 "unknown" 标记，不影响句子提取。
- **风险 3**：关键词漏检（如同义词未收录，如 `vendor`, `distributor`）。
  - **应对**：通过样本文件复盘，逐步扩展关键词 Regex 库





## 每个指标的详细获取方式

### 1.公司ID 和公司名

先从获取的data文件夹中获取对应CIK，若`cik_trickers.csv`中没有，则读取对应8-K文件的txt发布文件，获取最底下的发布公司名和其对应的CIK（放在对应公司CIK的文件夹下，例如`data/Archives/edgar/data/3906/0001299933-04-002457.txt` 

### 2 贷款起效日期

贷款起效日期并不与8-K文件披露日期相同，需要在具体文件中查看

### 3 贷款合同ID

采用 **Form 8-K**  ·**SEC Accession No+附件文件名** 的方式，例如 [sec.gov/Archives/edgar/data/1442236/000119380524000491/e663474_ex10-2.htm](https://www.sec.gov/Archives/edgar/data/1442236/000119380524000491/e663474_ex10-2.htm) ID则为：`000119380524000491_e663474_ex10-2`

### 4 含供应链信息句子

包含供应链信息的句子主要是根据其描述的内容来确定。通常要包括以下关键词: customer, customers, supplier, suppliers, supply chain, supply chains.