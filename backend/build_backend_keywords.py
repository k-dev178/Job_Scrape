"""모든공고md 코퍼스에서 웹 집계용 백엔드 키워드 파일을 생성한다."""

import json
import re
from pathlib import Path


PROJECT_DIR = Path(__file__).parent.parent
CORPUS_DIR = PROJECT_DIR / "모든공고md"
OUTPUT_FILE = Path(__file__).parent / "data" / "backend" / "backend_keywords.json"

# 후보군은 백엔드 기술로 한정한다. 실제 코퍼스에 등장한 후보만 결과 JSON에 저장된다.
KEYWORD_CANDIDATES = (
    # 언어
    ("Java", "언어", r"\bjava\b(?!script)"),
    ("Python", "언어", r"\bpython\b"),
    ("Kotlin", "언어", r"\bkotlin\b"),
    ("Go", "언어", r"\bgolang\b|(?<![A-Za-z])(?-i:Go)(?![A-Za-z])"),
    ("TypeScript", "언어", r"\btypescript\b"),
    ("JavaScript", "언어", r"\bjavascript\b"),
    ("C#", "언어", r"c#"),
    ("C++", "언어", r"c\+\+"),
    ("C", "언어", r"(?<![A-Za-z0-9+#])c(?![A-Za-z0-9+#])"),
    ("PHP", "언어", r"\bphp\b"),
    ("Rust", "언어", r"\brust\b"),
    ("Ruby", "언어", r"\bruby\b(?!\s*on)"),
    ("Scala", "언어", r"\bscala\b"),
    # JVM
    ("Spring", "JVM", r"\bspring\b(?!\s*(?:boot|cloud|security|batch|data|mvc))"),
    ("Spring Boot", "JVM", r"\bspring\s*boot\b"),
    ("Spring Cloud", "JVM", r"\bspring\s*cloud\b"),
    ("Spring Batch", "JVM", r"\bspring\s*batch\b"),
    ("Spring Data", "JVM", r"\bspring\s*data\b"),
    ("Spring Security", "JVM", r"\bspring\s*security\b"),
    ("Spring MVC", "JVM", r"\bspring\s*mvc\b"),
    ("JPA", "JVM", r"\bjpa\b"),
    ("Hibernate", "JVM", r"\bhibernate\b"),
    ("MyBatis", "JVM", r"\bmybatis\b"),
    ("QueryDSL", "JVM", r"\bquerydsl\b"),
    ("WebFlux", "JVM", r"\bwebflux\b"),
    ("Netty", "JVM", r"\bnetty\b"),
    ("Gradle", "JVM", r"\bgradle\b"),
    ("Maven", "JVM", r"\bmaven\b"),
    ("Flyway", "JVM", r"\bflyway\b"),
    ("Liquibase", "JVM", r"\bliquibase\b"),
    # Python
    ("Django", "Python", r"\bdjango\b"),
    ("DRF", "Python", r"\bdrf\b|\bdjango\s*rest\s*framework\b"),
    ("FastAPI", "Python", r"\bfastapi\b"),
    ("Flask", "Python", r"\bflask\b"),
    ("Celery", "Python", r"\bcelery\b"),
    ("Airflow", "Python", r"\bairflow\b"),
    ("SQLAlchemy", "Python", r"\bsqlalchemy\b"),
    ("Pydantic", "Python", r"\bpydantic\b"),
    ("Gunicorn", "Python", r"\bgunicorn\b"),
    ("Uvicorn", "Python", r"\buvicorn\b"),
    ("pytest", "Python", r"\bpytest\b"),
    # Node.js
    ("Node.js", "Node.js", r"\bnode\.?js\b"),
    ("NestJS", "Node.js", r"\bnest\.?js\b"),
    ("Express", "Node.js", r"\bexpress(?:\.?js)?\b"),
    ("Fastify", "Node.js", r"\bfastify\b"),
    ("Koa", "Node.js", r"\bkoa(?:\.js)?\b"),
    ("Bun", "Node.js", r"\bbun(?:js|\.js)?\b"),
    ("TypeORM", "Node.js", r"\btypeorm\b"),
    ("Prisma", "Node.js", r"\bprisma\b"),
    ("Sequelize", "Node.js", r"\bsequelize\b"),
    ("Mongoose", "Node.js", r"\bmongoose\b"),
    ("BullMQ", "Node.js", r"\bbullmq\b"),
    # 기타 프레임워크
    ("Rails", "프레임워크", r"\b(?:ruby\s*on\s*rails|rails)\b"),
    ("ASP.NET", "프레임워크", r"\basp\.?net\b"),
    (".NET", "프레임워크", r"\.net\b"),
    ("Laravel", "프레임워크", r"\blaravel\b"),
    ("Gin", "프레임워크", r"\bgin\b"),
    ("Fiber", "프레임워크", r"\bfiber\b"),
    ("Echo", "프레임워크", r"\becho\b"),
    ("Actix", "프레임워크", r"\bactix\b"),
    ("Axum", "프레임워크", r"\baxum\b"),
    # 데이터베이스/검색/캐시
    ("MySQL", "데이터베이스", r"\bmysql\b"),
    ("PostgreSQL", "데이터베이스", r"\b(?:postgresql|postgres)\b"),
    ("MariaDB", "데이터베이스", r"\bmariadb\b"),
    ("Oracle", "데이터베이스", r"\boracle\b"),
    ("MSSQL", "데이터베이스", r"\b(?:mssql|sql\s*server)\b"),
    ("SQLite", "데이터베이스", r"\bsqlite\b"),
    ("MongoDB", "데이터베이스", r"\bmongodb\b"),
    ("DynamoDB", "데이터베이스", r"\bdynamodb\b"),
    ("Cassandra", "데이터베이스", r"\bcassandra\b"),
    ("CockroachDB", "데이터베이스", r"\bcockroachdb\b"),
    ("Redis", "캐시", r"\bredis\b"),
    ("Memcached", "캐시", r"\bmemcached\b"),
    ("Elasticsearch", "검색", r"\belasticsearch\b"),
    ("OpenSearch", "검색", r"\bopensearch\b"),
    ("ClickHouse", "데이터베이스", r"\bclickhouse\b"),
    ("Neo4j", "데이터베이스", r"\bneo4j\b"),
    ("BigQuery", "데이터베이스", r"\bbigquery\b"),
    ("Snowflake", "데이터베이스", r"\bsnowflake\b"),
    ("Redshift", "데이터베이스", r"\bredshift\b"),
    ("Aurora", "데이터베이스", r"\baurora\b"),
    ("InfluxDB", "데이터베이스", r"\binfluxdb\b"),
    ("TimescaleDB", "데이터베이스", r"\btimescaledb\b"),
    ("Milvus", "벡터DB", r"\bmilvus\b"),
    ("Pinecone", "벡터DB", r"\bpinecone\b"),
    ("Weaviate", "벡터DB", r"\bweaviate\b"),
    ("Qdrant", "벡터DB", r"\bqdrant\b"),
    ("pgvector", "벡터DB", r"\bpgvector\b"),
    # 메시징/데이터 처리
    ("Kafka", "메시징", r"\bkafka\b"),
    ("RabbitMQ", "메시징", r"\brabbitmq\b"),
    ("NATS", "메시징", r"\bnats\b"),
    ("ActiveMQ", "메시징", r"\bactivemq\b"),
    ("Kinesis", "메시징", r"\bkinesis\b"),
    ("SQS", "메시징", r"\bsqs\b"),
    ("SNS", "메시징", r"\bsns\b"),
    ("Pub/Sub", "메시징", r"\bpub\s*/\s*sub\b|\bgoogle\s+pubsub\b"),
    ("Temporal", "메시징", r"\btemporal\b"),
    ("Spark", "데이터처리", r"\bspark\b"),
    ("Flink", "데이터처리", r"\bflink\b"),
    ("Hadoop", "데이터처리", r"\bhadoop\b"),
    ("dbt", "데이터처리", r"\bdbt\b"),
    ("Trino", "데이터처리", r"\btrino\b"),
    # 클라우드
    ("AWS", "클라우드", r"\baws\b|\bamazon\s+web\s+services\b"),
    ("GCP", "클라우드", r"\bgcp\b|\bgoogle\s+cloud\b"),
    ("Azure", "클라우드", r"\bazure\b"),
    ("Naver Cloud", "클라우드", r"\b(?:ncp|naver\s*cloud)\b|네이버\s*클라우드"),
    ("EC2", "AWS", r"\bec2\b"),
    ("S3", "AWS", r"\bs3\b"),
    ("Lambda", "AWS", r"\b(?:aws\s*)?lambda\b"),
    ("RDS", "AWS", r"\brds\b"),
    ("ECS", "AWS", r"\becs\b"),
    ("EKS", "AWS", r"\beks\b"),
    ("ECR", "AWS", r"\becr\b"),
    ("Fargate", "AWS", r"\bfargate\b"),
    ("CloudFront", "AWS", r"\bcloudfront\b"),
    ("CloudWatch", "AWS", r"\bcloudwatch\b"),
    ("ElastiCache", "AWS", r"\belasticache\b"),
    ("API Gateway", "AWS", r"\bapi\s*gateway\b"),
    ("EventBridge", "AWS", r"\beventbridge\b"),
    ("IAM", "AWS", r"\biam\b"),
    ("Cloud Run", "GCP", r"\bcloud\s*run\b"),
    ("Cloud Functions", "GCP", r"\bcloud\s*functions?\b"),
    # 인프라/배포
    ("Linux", "인프라", r"\blinux\b"),
    ("Embedded Linux", "시스템SW", r"\bembedded\s+linux\b|임베디드\s*리눅스"),
    ("RTOS", "시스템SW", r"\brtos\b|\breal[\s-]*time\s+os\b"),
    ("FreeRTOS", "시스템SW", r"\bfreertos\b"),
    ("Qt", "시스템SW", r"\bqt\b"),
    ("MCU", "시스템SW", r"\bmcu\b|마이크로컨트롤러"),
    ("STM32", "시스템SW", r"\bstm32\b"),
    ("Yocto", "시스템SW", r"\byocto\b"),
    ("AUTOSAR", "시스템SW", r"\bautosar\b"),
    ("ROS", "시스템SW", r"\bros\s*2?\b"),
    ("POSIX", "시스템SW", r"\bposix\b"),
    ("MFC", "시스템SW", r"\bmfc\b"),
    ("Nginx", "인프라", r"\bnginx\b"),
    ("Tomcat", "인프라", r"\btomcat\b"),
    ("Envoy", "인프라", r"\benvoy\b"),
    ("Docker", "컨테이너", r"\bdocker\b"),
    ("Kubernetes", "컨테이너", r"\b(?:kubernetes|k8s)\b"),
    ("Helm", "컨테이너", r"\bhelm\b"),
    ("Istio", "컨테이너", r"\bistio\b"),
    ("Jenkins", "CI/CD", r"\bjenkins\b"),
    ("GitHub Actions", "CI/CD", r"\bgithub\s*actions\b"),
    ("GitLab CI", "CI/CD", r"\bgitlab\s*(?:ci|ci/cd)\b"),
    ("CircleCI", "CI/CD", r"\bcircleci\b"),
    ("ArgoCD", "CI/CD", r"\bargo\s*cd\b|\bargocd\b"),
    ("Terraform", "IaC", r"\bterraform\b"),
    ("Ansible", "IaC", r"\bansible\b"),
    # 관측성
    ("Grafana", "관측성", r"\bgrafana\b"),
    ("Prometheus", "관측성", r"\bprometheus\b"),
    ("Datadog", "관측성", r"\bdatadog\b"),
    ("New Relic", "관측성", r"\bnew\s*relic\b"),
    ("Sentry", "관측성", r"\bsentry\b"),
    ("ELK", "관측성", r"\belk\b"),
    ("Kibana", "관측성", r"\bkibana\b"),
    ("OpenTelemetry", "관측성", r"\bopentelemetry\b|\botel\b"),
    ("Loki", "관측성", r"\bloki\b"),
    ("Jaeger", "관측성", r"\bjaeger\b"),
    # API/인증/아키텍처
    ("REST API", "API", r"\brest(?:ful)?[\s-]*api\b"),
    ("GraphQL", "API", r"\bgraphql\b"),
    ("gRPC", "API", r"\bgrpc\b"),
    ("WebSocket", "API", r"\bweb\s*socket\b|\bwebsocket\b"),
    ("Socket.IO", "API", r"\bsocket\.io\b"),
    ("Swagger", "API", r"\bswagger\b"),
    ("OpenAPI", "API", r"\bopenapi\b"),
    ("JWT", "인증", r"\bjwt\b"),
    ("OAuth", "인증", r"\boauth2?\b"),
    ("OIDC", "인증", r"\boidc\b|\bopen\s*id\s*connect\b"),
    ("MSA", "아키텍처", r"\bmsa\b|\bmicroservices?\b|마이크로서비스"),
    ("DDD", "아키텍처", r"\bddd\b|도메인\s*주도\s*설계"),
    ("CQRS", "아키텍처", r"\bcqrs\b"),
    ("Event Driven", "아키텍처", r"\bevent[\s-]*driven\b|이벤트\s*기반"),
    # 테스트/AI
    ("JUnit", "테스트", r"\bjunit\b"),
    ("Mockito", "테스트", r"\bmockito\b"),
    ("Jest", "테스트", r"\bjest\b"),
    ("PyTorch", "AI", r"\bpytorch\b"),
    ("OpenAI", "AI", r"\bopenai\b"),
    ("LangChain", "AI", r"\blangchain\b"),
    ("LangGraph", "AI", r"\blanggraph\b"),
    ("LlamaIndex", "AI", r"\bllamaindex\b"),
)


def build_backend_keywords(
    corpus_dir: Path = CORPUS_DIR,
    output_file: Path = OUTPUT_FILE,
) -> dict:
    paths = sorted(corpus_dir.glob("*.md"))
    documents = [
        re.sub(
            r"(?m)^- 기술:.*$",
            "",
            path.read_text(encoding="utf-8", errors="ignore"),
        )
        for path in paths
    ]
    keywords = []

    for name, category, pattern_text in KEYWORD_CANDIDATES:
        pattern = re.compile(pattern_text, re.IGNORECASE)
        document_count = sum(bool(pattern.search(document)) for document in documents)
        if document_count == 0:
            continue
        occurrence_count = sum(len(pattern.findall(document)) for document in documents)
        keywords.append({
            "name": name,
            "category": category,
            "pattern": pattern_text,
            "document_count": document_count,
            "occurrence_count": occurrence_count,
            "enabled": True,
        })

    payload = {
        "schema_version": 1,
        "generated_from": "모든공고md/*.md",
        "excluded_lines": ["- 기술: ..."],
        "document_count": len(documents),
        "keyword_count": len(keywords),
        "keywords": keywords,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    result = build_backend_keywords()
    print(
        f"{result['document_count']}개 문서에서 "
        f"{result['keyword_count']}개 백엔드 키워드를 저장했습니다: {OUTPUT_FILE}"
    )
