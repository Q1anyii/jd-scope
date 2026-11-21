"""通用技术词表：用于 JD 结构化抽取与简历覆盖度比对。

词表只包含公开的技术名词，不含任何个人信息。
每个词条：canonical（规范名）、aliases（检索别名，已做小写去空格归一）、
domain（所属领域，用于「部分覆盖」判定）。
"""

from __future__ import annotations


def normalize(text: str) -> str:
    """检索归一：小写、去空白、去常见标点。"""
    if not text:
        return ""
    out = []
    for ch in text.lower():
        if ch.isalnum() or ch in ("+", "#"):
            out.append(ch)
        # 其余（空格、标点、括号、制表）一律丢弃
    return "".join(out)


# domain 常量
BACKEND = "后端"
FRONTEND = "前端"
LANG = "编程语言"
DB = "数据存储"
MQ = "消息与中间件"
OPS = "运维与部署"
AI = "人工智能"
ARCH = "架构与工程化"
TEST = "测试与质量"
SOFT = "通用能力"

RAW_TERMS = [
    # ---- 编程语言 ----
    ("Java", ["java", "jdk"], LANG),
    ("Python", ["python", "py3"], LANG),
    ("Go", ["golang", "go语言"], LANG),
    ("C++", ["c++", "cpp"], LANG),
    ("C#", ["c#", "csharp", ".net"], LANG),
    ("JavaScript", ["javascript", "js"], LANG),
    ("TypeScript", ["typescript", "ts"], LANG),
    ("Rust", ["rust"], LANG),
    ("Kotlin", ["kotlin"], LANG),
    ("PHP", ["php"], LANG),
    ("SQL", ["sql"], LANG),
    ("Shell", ["shell", "bash脚本", "shell脚本"], OPS),

    # ---- 后端框架 ----
    ("Spring", ["spring"], BACKEND),
    ("Spring Boot", ["springboot", "spring-boot"], BACKEND),
    ("Spring Cloud", ["springcloud", "spring-cloud"], BACKEND),
    ("Spring MVC", ["springmvc"], BACKEND),
    ("MyBatis", ["mybatis", "mybatisplus"], BACKEND),
    ("FastAPI", ["fastapi"], BACKEND),
    ("Django", ["django"], BACKEND),
    ("Flask", ["flask"], BACKEND),
    ("Node.js", ["nodejs", "node.js"], BACKEND),
    ("Express", ["express"], BACKEND),
    ("NestJS", ["nestjs"], BACKEND),
    ("gRPC", ["grpc"], BACKEND),
    ("RESTful", ["restful", "restapi"], BACKEND),

    # ---- 前端 ----
    ("React", ["react", "reactjs"], FRONTEND),
    ("Vue", ["vue", "vue3", "vue2"], FRONTEND),
    ("Angular", ["angular"], FRONTEND),
    ("Next.js", ["nextjs", "next.js"], FRONTEND),
    ("Vite", ["vite"], FRONTEND),
    ("Webpack", ["webpack"], FRONTEND),
    ("HTML/CSS", ["html", "css", "html5"], FRONTEND),

    # ---- 数据存储 ----
    ("MySQL", ["mysql"], DB),
    ("PostgreSQL", ["postgresql", "postgres", "pgsql"], DB),
    ("Oracle", ["oracle"], DB),
    ("SQL Server", ["sqlserver", "mssql"], DB),
    ("SQLite", ["sqlite"], DB),
    ("Redis", ["redis"], DB),
    ("MongoDB", ["mongodb", "mongo"], DB),
    ("Elasticsearch", ["elasticsearch", "es搜索"], DB),
    ("ClickHouse", ["clickhouse"], DB),
    ("HBase", ["hbase"], DB),
    ("向量数据库", ["向量数据库", "vectordb", "向量库"], DB),
    ("Milvus", ["milvus"], DB),
    ("FAISS", ["faiss"], DB),
    ("pgvector", ["pgvector"], DB),

    # ---- 消息与中间件 ----
    ("Kafka", ["kafka"], MQ),
    ("RabbitMQ", ["rabbitmq"], MQ),
    ("RocketMQ", ["rocketmq"], MQ),
    ("消息队列", ["消息队列", "mq"], MQ),
    ("Nginx", ["nginx"], MQ),
    ("Tomcat", ["tomcat"], MQ),
    ("ZooKeeper", ["zookeeper", "zk"], MQ),
    ("Nacos", ["nacos"], MQ),
    ("Gateway", ["gateway", "网关"], MQ),

    # ---- 运维与部署 ----
    ("Linux", ["linux", "centos", "ubuntu", "麒麟"], OPS),
    ("Docker", ["docker", "容器化"], OPS),
    ("Kubernetes", ["kubernetes", "k8s"], OPS),
    ("CI/CD", ["ci/cd", "cicd", "持续集成", "流水线"], OPS),
    ("Jenkins", ["jenkins"], OPS),
    ("GitLab CI", ["gitlabci"], OPS),
    ("GitHub Actions", ["githubactions"], OPS),
    ("监控告警", ["监控", "告警", "prometheus", "grafana"], OPS),
    ("灰度发布", ["灰度", "蓝绿", "滚动发布"], OPS),
    ("回滚", ["回滚", "rollback"], OPS),
    ("负载均衡", ["负载均衡", "反向代理"], OPS),
    ("HTTPS/证书", ["https", "ssl", "证书", "tls"], OPS),
    ("备份恢复", ["备份", "恢复", "rsync", "容灾"], OPS),
    ("日志排查", ["日志", "排障", "定位问题"], OPS),

    # ---- 人工智能 ----
    ("大模型", ["大模型", "llm", "大语言模型"], AI),
    ("Agent", ["agent", "智能体", "multi-agent"], AI),
    ("RAG", ["rag", "检索增强"], AI),
    ("MCP", ["mcp", "modelcontextprotocol"], AI),
    ("LangChain", ["langchain"], AI),
    ("LangGraph", ["langgraph"], AI),
    ("Prompt", ["prompt", "提示词"], AI),
    ("Function Calling", ["functioncalling", "工具调用", "tool calling"], AI),
    ("Embedding", ["embedding", "向量化", "bge"], AI),
    ("重排", ["重排", "rerank", "reranker"], AI),
    ("微调", ["微调", "lora", "sft", "finetune"], AI),
    ("多模态", ["多模态", "multimodal", "视觉模型"], AI),
    ("模型评测", ["评测", "evaluation", "评测集", "benchmark"], AI),
    ("上下文管理", ["上下文", "context", "记忆", "memory"], AI),
    ("推理优化", ["推理优化", "量化", "vllm", "推理加速"], AI),
    ("语音识别", ["语音识别", "asr", "tts"], AI),
    ("计算机视觉", ["计算机视觉", "cv", "ocr"], AI),

    # ---- 架构与工程化 ----
    ("微服务", ["微服务", "microservice"], ARCH),
    ("分布式", ["分布式", "distributed"], ARCH),
    ("高并发", ["高并发", "高可用", "ha"], ARCH),
    ("缓存设计", ["缓存", "cache", "多级缓存"], ARCH),
    ("事务", ["事务", "acid", "一致性"], ARCH),
    ("分库分表", ["分库分表", "sharding"], ARCH),
    ("性能优化", ["性能优化", "调优", "压测", "jmeter"], ARCH),
    ("限流熔断", ["限流", "熔断", "降级"], ARCH),
    ("幂等", ["幂等", "idempotent"], ARCH),
    ("设计模式", ["设计模式", "重构"], ARCH),
    ("Git", ["git", "版本控制"], ARCH),

    # ---- 测试与质量 ----
    ("单元测试", ["单元测试", "unittest", "junit", "pytest"], TEST),
    ("接口测试", ["接口测试", "postman", "自动化测试"], TEST),
    ("UI 自动化", ["selenium", "playwright", "ui自动化"], TEST),
    ("代码评审", ["代码评审", "code review"], TEST),

    # ---- 通用能力 ----
    ("需求分析", ["需求分析", "需求梳理"], SOFT),
    ("项目管理", ["项目管理", "进度管理"], SOFT),
    ("交付实施", ["交付", "实施", "上线部署", "驻场"], SOFT),
    ("技术支持", ["技术支持", "客户支持", "售后支持"], SOFT),
    ("文档写作", ["文档写作", "技术文档", "需求文档", "手册", "sop"], SOFT),
    ("跨团队协作", ["跨团队", "协作", "沟通"], SOFT),
]

TERMS = []
for canonical, aliases, domain in RAW_TERMS:
    norm = set()
    for a in aliases:
        norm.add(normalize(a))
    norm.add(normalize(canonical))
    TERMS.append({"term": canonical, "aliases": sorted(norm), "domain": domain})

# canonical -> domain
TERM_DOMAIN = {t["term"]: t["domain"] for t in TERMS}
# 全部规范名
ALL_TERMS = [t["term"] for t in TERMS]
# domain -> 该领域全部规范名
DOMAIN_TERMS: dict[str, list[str]] = {}
for t in TERMS:
    DOMAIN_TERMS.setdefault(t["domain"], []).append(t["term"])


def find_terms(text: str) -> list[str]:
    """在一段文本中找出命中的规范术语。

    采用「最长匹配优先 + 区间不重叠」：`MySQL` 命中时不再额外报 `SQL`，
    `Spring Boot` 命中时不再单独报 `Spring`，避免同义词互相抬分。
    """
    norm_text = normalize(text)
    if not norm_text:
        return []
    cands: list[tuple[int, int, str]] = []
    for t in TERMS:
        for alias in t["aliases"]:
            if not alias:
                continue
            start = norm_text.find(alias)
            while start != -1:
                cands.append((start, start + len(alias), t["term"]))
                start = norm_text.find(alias, start + 1)
    cands.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken: list[tuple[int, int]] = []
    chosen: list[tuple[int, str]] = []
    for start, end, term in cands:
        if any(not (end <= s or start >= e) for s, e in taken):
            continue
        taken.append((start, end))
        chosen.append((start, term))
    chosen.sort()
    out: list[str] = []
    for _, term in chosen:
        if term not in out:
            out.append(term)
    return out


# 城市候选（用于 JD 地点识别，只影响展示，不参与硬性条件打分之外的判断）
CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "武汉",
    "西安", "长沙", "南昌", "合肥", "郑州", "天津", "重庆", "厦门", "福州",
    "青岛", "济南", "大连", "沈阳", "无锡", "东莞", "佛山", "珠海", "宁波",
    "常州", "嘉兴", "昆山", "惠州", "中山", "石家庄", "太原", "昆明", "贵阳",
    "南宁", "海口", "兰州", "银川", "西宁", "乌鲁木齐", "呼和浩特", "温州",
    "绍兴", "台州", "金华", "泉州", "烟台", "潍坊", "徐州", "南通", "扬州",
]

DEGREES = [
    ("博士", 5), ("硕士", 4), ("研究生", 4), ("本科", 3),
    ("大专", 2), ("专科", 2), ("中专", 1), ("高中", 1),
]
# 用户档案里的学历 -> 等级
EDU_LEVEL = {
    "博士": 5, "硕士": 4, "研究生": 4, "本科": 3,
    "大专": 2, "专科": 2, "中专": 1, "高中": 1, "": 0,
}
