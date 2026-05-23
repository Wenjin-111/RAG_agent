<div align="center">

<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12"/>
<img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
<img src="https://img.shields.io/badge/Vue-3.5-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue 3.5"/>
<img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL 16"/>
<img src="https://img.shields.io/badge/Elasticsearch-8.x-005571?style=for-the-badge&logo=elasticsearch&logoColor=white" alt="Elasticsearch 8.x"/>
<img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License MIT"/>

</div>

<br/>

<h1 align="center">Argus — RAG 知识库平台</h1>

<p align="center">
  <strong>融合 RAG 与 AI Agent 技术的企业级智能知识平台</strong>
</p>

<p align="center">
  文档上传 · 智能解析 · 混合检索 · AI 对话 · 引用溯源
</p>

---

## 项目简介

**Argus** 是一个从底层构建的 **RAG（检索增强生成）知识库平台**，将企业私有文档与大语言模型深度融合，解决 LLM 在垂直领域应用中的三大核心痛点：

| 痛点 | Argus 的解决方案 |
|------|-----------------|
| 幻觉编造 | 向量 + ES 混合检索 + 四级证据评估，证据不足时主动拒答 |
| 知识割裂 | 文档上传 → 解析 → 切片 → 向量化 → ES 索引，全链路自动化 |
| 无记忆对话 | ReactAgent + 短期记忆，支持跨轮次上下文感知对话 |

## 技术栈

### 后端
- **Python 3.12** / **FastAPI** — 异步 Web 框架
- **SQLAlchemy 2.0 async** + **asyncpg** — 异步 ORM
- **PostgreSQL 16 + pgvector** — HNSW 向量索引
- **Elasticsearch 8.x** — 关键词检索 + IK 中文分词
- **MinIO** — S3 兼容对象存储
- **LangGraph** — AI Agent 框架
- **Pydantic v2** — 配置与数据验证

### 前端
- **Vue 3** (Composition API) + **TypeScript** + **Vite 8**
- **Pinia** — 状态管理
- **Element Plus** — UI 组件库
- **Axios** — HTTP 客户端

### AI 模型
- **DeepSeek** — 聊天大模型（可配置）
- **阿里云 text-embedding-v4** — 嵌入模型（可配置）
- 管理员可在系统设置中切换模型，无需改配置文件

## 核心功能

### 知识库问答（RAG QA）
```
用户提问 → 查询规划（LLM） → 混合检索（向量 + ES）
    → RRF 融合排序 → 证据评估 → LLM 生成 → 引用溯源
```

### AI 智能助手
- ReactAgent 图执行引擎，自主决定是否调用检索工具
- 会话管理 + 短期记忆 + 自动标题生成
- SSE 流式输出，打字机效果
- 支持账户快捷切换

### 文档管理
- 直接上传 + 分片上传（断点续传/秒传）
- 多格式支持：PDF / DOCX / MD / TXT
- 自动 ETI 流水线：解析 → 清洗 → 切片 → 向量化 → ES 索引
- 同群组内 SHA-256 去重

### 协作小组
- 创建群组、邀请成员、加入申请/审批
- 群组级数据隔离（向量检索和 ES 检索均过滤 group_id）
- 待审批申请实时角标提醒

### 系统管理
- 用户管理（CRUD + 状态变更 + 密码重置）
- LLM 用量统计（调用次数、Token、费用、趋势图、排行）
- 模型配置管理（聊天/嵌入模型独立切换）

## 快速开始

详见 **[STARTUP.md](STARTUP.md)**

```bash
# 1. 启动基础设施
docker compose up -d

# 2. 配置后端
cd Argus-python
cp .env.example .env   # 编辑 API Key
pip install -r requirements.txt
python init_db.py

# 3. 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 10001 --reload

# 4. 启动前端
cd Argus-frontend
npm install && npm run dev
```

访问 `http://localhost:5173`，默认管理员：`admin` / `Admin@123456`

## 项目结构

```
RAG2.0/
├── docker-compose.yml              # PostgreSQL + MinIO + Elasticsearch
├── Argus-python/                   # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py                 #   入口 + 生命周期
│   │   ├── config.py               #   配置（.env 加载）
│   │   ├── auth/                   #   认证授权
│   │   ├── user/                   #   用户管理
│   │   ├── group/                  #   群组协作
│   │   ├── document/               #   文档管理
│   │   ├── ingestion/              #   ETI 流水线
│   │   ├── qa/                     #   知识库问答
│   │   ├── assistant/              #   AI 助手 Agent
│   │   ├── metrics/                #   用量统计
│   │   ├── models_config/          #   模型配置管理
│   │   └── engine/                 #   基础设施（PG/ES/MinIO）
│   ├── init_db.py                  #   数据库初始化
│   └── .env.example                #   环境变量模板
└── Argus-frontend/                 # Vue 3 前端
    └── src/
        ├── api/                    #   后端 API 封装
        ├── views/                  #   页面组件
        │   ├── documents/          #     文档管理
        │   ├── qa/                 #     知识库问答
        │   ├── assistant/          #     AI 助手
        │   ├── groups/             #     协作小组
        │   ├── admin/              #     用户管理 + 使用统计
        │   └── settings/           #     系统设置
        ├── stores/                 #   Pinia 状态
        └── components/             #   公共组件
```

## License

MIT
