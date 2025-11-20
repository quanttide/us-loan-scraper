# 一 原需求

两个需求

### 1.  下载SEC EDGAR上全部的Credit Agreement文件

**大概步骤：**

1) 从2004或2005开始，8-K强制披露重大合约事件，必须披露贷款合同全文。贷款合同全文的链接附在8-K文件的附件中。
2) 先获取8-K链接，打开8-K获取附件链接，识别出贷款合同链接并保存文件。
3) 获取8-K，Python有已开发好的工具：https://py-sec-edgar.readthedocs.io/en/latest/readme.html 

> [!tip]
>
> 此链接过旧，建议阅读github首页README：[ryansmccoy/py-sec-edgar: Python application used to download, parse, and extract structured/unstructured data from filings in the SEC Edgar Database (including 10-K, 10-Q, 13-D, S-1, 8-K, etc.)](https://github.com/ryansmccoy/py-sec-edgar)

4) 一个小例子

8-K : https://www.sec.gov/Archives/edgar/data/1710155/000110465924087777/tm2421197d1_ex10-1.htm

附件文件页面:

https://www.sec.gov/Archives/edgar/data/1710155/000110465924087777/0001104659-24-087777-index.html

EXHIBIT 10.1后面的链接就是贷款合同文本:

https://www.sec.gov/Archives/edgar/data/1710155/000110465924087777/tm2421197d1_ex10-1.htm

一个疑问：保存成什么格式方便未来使用？



**具体操作：**

因为要求是2004年开始，**把setting.py里的第200行左右的代码里的时间改成8030天，即22年前开始**



因为我们要爬取的是8-k文件、任意公司等要求,就可以在uv run python......后面的语句改一下。

下载命令：

```cmd
uv run python -m py_sec_edgar workflows full-index --start-date 2004-01-01 --end-date 2004-03-31 --forms "8-K" --no-ticker-filter --download --extract
```

> [!tip]
>
> 这里的下载数据较慢，建议以季度为单位下载，预估花费若干小时
>
> 可能原因在于梯子链接不稳定

下载的文件结构如下

```
│data/
├── Archives/edgar/data/
│   └── 320193/                    # 公司的CIK
│       └── 000032019324000123/    # 特定filing
│           ├── 0001-aapl-20240930.htm  # 主要8-K文档（有时也可能是txt格式）
│           ├── 0002-(ex...).htm  #其他附件（也存在txt格式）
│           └── 
│		└── 000032019324000123.txt #主要8-K文档txt格式
```





### 2.  基于1中下载的Credit Agreement文本识别出含有供应链信息的句子

关键字符：supplier，customer，supply chain, supply-chain

例子：

https://www.sec.gov/Archives/edgar/data/1442236/000119380524000491/e663474_ex10-2.htm 

构建一个firm-contract-sentence level data set

| 公司ID | 公司名称 | 贷款合同ID | 贷款起效日期 | 含供应链信息句子 |
| ------ | -------- | ---------- | ------------ | ---------------- |
| A      | ABC      | 12345      | 2008-08-08   | 句子1            |
| A      | ABC      | 12345      | 2008-08-08   | 句子2            |
| B      | XXX      | 23456      | 2020-01-08   | 句子1            |
| B      | XXX      | 23456      | 2020-01-08   | 句子2            |
| B      | XXX      | 23456      | 2020-01-08   | 句子3            |
| c      | UU       | 45678      | 2009-08-08   | 句子1            |

 