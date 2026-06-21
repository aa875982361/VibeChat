# VibeChat

VibeChat 是一个 AI 驱动的匿名情绪聊天室。用户输入当下想说的话后，系统会识别主情绪、复合情绪、情绪强度、表达意图和安全风险，并自动匹配到相近情绪的匿名房间，让“不想发朋友圈”的瞬间也能被温柔接住。

- 线上演示地址：https://vibechat.nisonfuture.cn/
- GitHub 仓库：https://github.com/aa875982361/VibeChat

## 功能亮点

- 情绪输入：用户用自然语言描述当前状态，不需要选择固定标签。
- AI 情绪识别：支持 OpenAI 标准接口、Anthropic 标准接口，也支持 DeepSeek 这类 OpenAI 兼容接口。
- 自动匹配：根据主情绪、强度、表达意图、倾向、唤醒度和复合情绪生成同频聊天室。
- 匿名聊天：自动生成匿名身份，进入房间后通过 WebSocket 实时聊天。
- 安全兜底：识别高风险表达时不会进入普通聊天室，会展示安全提示。
- 房间保留：用户可回到已匹配过的聊天室，继续匿名表达。

## 技术栈

- 前端：Next.js 15、React 19、TypeScript、Tailwind CSS、lucide-react
- 后端：FastAPI、Pydantic、SQLite、WebSocket
- AI 接口：OpenAI Responses API、OpenAI Moderation API、Anthropic Messages API、OpenAI-compatible Chat Completions API
- 部署：Docker、Docker Compose、Nginx/HTTPS 反向代理
- 测试：pytest、TypeScript typecheck

## Docker 一键部署（推荐）

准备环境变量：

```bash
cp .env.example .env
```

如需启用真实 AI 情绪识别，先在 `.env` 中填写 OpenAI、Anthropic 或 DeepSeek 配置；未填写 API Key 时，后端会使用本地规则兜底，方便无密钥环境下快速体验基本流程。

一键启动前后端：

```bash
docker compose up --build
```

访问地址：

- 前端：http://localhost:3000
- 后端：http://localhost:8058
- 健康检查：http://localhost:8058/api/health

后台运行：

```bash
docker compose up -d --build
```

停止服务：

```bash
docker compose down
```

SQLite 数据默认写入 `vibechat-data` Docker volume。

腾讯云部署时可启用 BuildKit 复用依赖缓存：

```bash
DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose build
docker compose up -d
```

Docker 构建默认使用腾讯云 PyPI 镜像和 npmmirror。需要切回官方源时：

```bash
PIP_INDEX_URL=https://pypi.org/simple NPM_CONFIG_REGISTRY=https://registry.npmjs.org docker compose build
```

## 本地开发运行

如果需要分别调试前后端，可使用本地开发模式。

先复制环境变量示例：

```bash
cp .env.example .env
```

安装根目录依赖：

```bash
npm install
```

启动后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8058
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

也可以在根目录同时启动前后端：

```bash
npm run dev
```

## OpenAI 标准接口配置

在 `.env` 中设置：

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=
OPENAI_MODERATION_MODEL=omni-moderation-latest
NEXT_PUBLIC_API_URL=http://localhost:8058
```

说明：

- `AI_PROVIDER=openai` 会使用 OpenAI Responses API 做情绪理解。
- `OPENAI_MODERATION_MODEL` 用于安全审核和风险兜底。
- `OPENAI_BASE_URL` 可留空；如使用网关或代理，可填写兼容 OpenAI SDK 的 base URL。

## Anthropic 标准接口配置

在 `.env` 中设置：

```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_BASE_URL=
NEXT_PUBLIC_API_URL=http://localhost:8058
```

说明：

- `AI_PROVIDER=anthropic` 会使用 Anthropic Messages API 做情绪理解。
- `ANTHROPIC_BASE_URL` 可留空；如使用 Anthropic API 网关或代理，可填写对应 base URL。
- Anthropic 模式下仍保留本地安全关键词兜底。

## OpenAI 兼容接口示例：DeepSeek

DeepSeek 走 OpenAI-compatible Chat Completions API：

```bash
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
NEXT_PUBLIC_API_URL=http://localhost:8058
```

## API 概览

- `GET /api/health`：健康检查
- `POST /api/sessions`：创建匿名会话
- `POST /api/emotions/analyze`：分析情绪并推荐聊天室
- `POST /api/rooms/join`：进入安全可加入的推荐房间
- `POST /api/rooms/rejoin`：回到已加入过的房间
- `GET /api/rooms`：查看聊天室和在线人数
- `POST /api/messages/report`：记录消息举报
- `WebSocket /ws/rooms/{room_id}?session_id=...`：实时聊天室消息流

## 测试

后端测试：

```bash
npm run test:backend
```

前端类型检查：

```bash
npm run test:frontend
```

## 提交信息

- 项目 GitHub 链接：https://github.com/aa875982361/VibeChat
- 线上演示地址：https://vibechat.nisonfuture.cn/
- 100 字以内产品介绍：

  VibeChat 是一个 AI 匿名情绪聊天室：输入当下心情后，系统识别情绪与表达意图，自动匹配同频房间，让不想公开发布的情绪也能被安全接住。
