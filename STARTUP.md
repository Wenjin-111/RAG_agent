# Argus RAG Platform — 启动教程

## 1. 环境要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Docker Desktop | 最新 | 运行 PostgreSQL、MinIO、Elasticsearch |
| Conda | 最新 | Python 虚拟环境管理 |
| Node.js | 18+ | 前端构建 |
| Git | — | 可选 |

## 2. 启动基础设施

```bash
cd D:\AI_code\RAG2.0
docker compose up -d
```

等待所有服务 healthy（首次启动 ES 约 1-2 分钟）：

```bash
docker compose ps
```

预期输出：三个容器都是 `(healthy)` 状态。

| 服务 | 端口 | 账号/密码 |
|------|------|----------|
| PostgreSQL 16 + pgvector | `5432` | postgres / postgres |
| MinIO S3 API | `9000` | minioadmin / minioadmin |
| MinIO Web Console | `9001` | minioadmin / minioadmin |
| Elasticsearch 8.15 | `9200` | 无认证 |

> **注意**：如果本机已安装 PostgreSQL 并占用 5432 端口，需先停掉本机 PG 服务，否则 Docker 端口映射会静默失败。

## 3. 配置 Python 后端

### 3.1 创建 Conda 环境

```bash
conda create -n argus python=3.12 -y
conda activate argus
```

### 3.2 安装依赖

```bash
cd D:\AI_code\RAG2.0\Argus-python
pip install -r requirements.txt
```

### 3.3 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，修改 API Key：

```env
# 聊天大模型（DeepSeek）
CHAT_API_KEY=sk-your-deepseek-key
CHAT_MODEL_NAME=deepseek-chat
CHAT_BASE_URL=https://api.deepseek.com/v1

# 嵌入模型（阿里云）
EMBEDDING_API_KEY=sk-your-dashscope-key
EMBEDDING_MODEL_NAME=text-embedding-v4
EMBEDDING_DIMENSIONS=1024
```

其余配置已匹配 Docker 默认值，无需修改。

> 管理员登录后可在 **系统设置 → 添加模型** 中管理多个模型配置并快捷切换，无需手动改 `.env`。

### 3.4 初始化数据库

```bash
python init_db.py
```

输出：
```
INFO:init_db:pgvector extension enabled
INFO:init_db:All tables created
INFO:init_db:Admin seeded: admin@argus.local / Admin@123456
```

## 4. 启动后端

```bash
uvicorn app.main:app --host 0.0.0.0 --port 10001 --reload
```

启动成功后访问 `http://localhost:10001/docs` 查看 API 文档。

后端启动时会自动：
- 创建数据库表（如果不存在）
- 初始化 ES 索引
- 启动文档 ETI Worker（后台异步处理文档向量化）
- 创建默认管理员账号（如果不存在）

## 5. 启动前端

打开新终端：

```bash
cd D:\AI_code\RAG2.0\Argus-frontend
npm install
npm run dev
```

前端运行在 `http://localhost:5173`，Vite 代理自动将 `/api` 转发到 `http://localhost:10001`。

## 6. 首次使用

1. 访问 `http://localhost:5173`
2. 管理员登录：`admin` / `Admin@123456`
3. 创建协作小组（知识库）
4. 上传文档（PDF / DOCX / TXT / MD）
5. 等待文档状态变为"就绪"（ETI Worker 自动处理，约 5-10 秒）
6. 在 **知识库问答** 页面提问，或使用 **AI 助手** 的 KB_SEARCH 模式

## 7. 常用命令

```bash
# Docker 服务管理
docker compose ps                    # 查看状态
docker compose logs -f postgres      # 查看 PG 日志
docker compose down                  # 停止（数据保留）
docker compose down -v               # 停止并清除数据

# 数据库
docker exec -it argus-pg psql -U postgres -d new_rag  # 进入 PG
python init_db.py                                      # 重新初始化

# MinIO Console
# 浏览器打开 http://localhost:9001

# ES 索引
curl http://localhost:9200/_cat/indices
```

## 8. 故障排查

| 问题 | 解决 |
|------|------|
| 端口 5432 被占用 | 停掉本机 PostgreSQL 服务，重启 Docker 容器 |
| ES 启动失败 | 容器内网络不通导致 IK 插件下载失败，已从 docker-compose 移除自动安装 |
| `init_db.py` 连接失败 | 确认 `127.0.0.1` 而非 `localhost`（避免 IPv6 延迟） |
| 文档上传 15 秒超时 | `.env` 中所有地址改为 `127.0.0.1`（MinIO、ES） |
| 登录后刷新跳回登录页 | 清除浏览器缓存重新登录 |
| QA 回答截断 | DeepSeek JSON 输出换行问题，已切换为分隔符格式 |
| 向量化一直失败 | 确认 embedding API Key 有效，且模型名正确 |
