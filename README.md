# Markdown-Feishu Sync

> 任意路径下 markdown 文件 ↔ 飞书文档的双向同步工具。

把飞书写在文档里的思考同步到你的 **Obsidian vault**、**博客仓库**、**项目文档**……任何 `.md` 文件都可以。

## 为什么需要这个？

**没有同步工具时：**
- 飞书文档想归档到本地？手动复制粘贴，格式全乱
- 本地笔记想分享给团队？导出 Markdown，上传飞书，再调整格式
- 博客草稿在本地写，却要在飞书协作？两边改来改去不知道哪个最新
- 表格格式不兼容？飞书表格变成乱码
- 图片链接失效？飞书图片在编辑器里显示不出来

**有了同步工具：**
- 一条命令：飞书文档 → 本地 `.md` 文件，自动添加同步标识
- 一条命令：本地 `.md` 文件 → 飞书文档，团队立即可见
- 已建立同步关系的文档，自动检测冲突并智能合并
- 表格自动转换：飞书 `<lark-table>` ↔ Markdown 表格
- 图片自动同步：飞书图片下载到本地 / 本地图片上传到飞书
- 支持任意目录：Obsidian vault、博客项目、文档仓库……不限位置

## 特性

- ✅ **任意 markdown 文件** - 不再限定 Obsidian vault，支持任何路径下的 `.md` 文件
- ✅ **双向同步** - 飞书 → 本地，本地 → 飞书，自由选择方向
- ✅ **路径无关** - 文件移动/重命名不影响同步关系（通过 frontmatter 追踪）
- ✅ **Base Directory** - `--base-dir` 参数切换工作目录，省去写绝对路径的麻烦
- ✅ **表格转换** - 飞书表格 ↔ Markdown 表格自动转换
- ✅ **图片同步** - 飞书图片下载到 `attachments/` / 本地图片上传到飞书
- ✅ **安全删除** - 同步关系移除不删除文件，两端互不影响
- ✅ **冲突检测** - 双向同步时自动检测冲突，智能合并
- ✅ **状态可视** - 查看所有同步关系，文件存在与否一目了然
- ✅ **扫描发现** - 扫描目录树中所有含 `feishu_doc_id` frontmatter 的文件

## 安装

### Hermes Agent

```bash
hermes skills install https://github.com/Igloo302/obsidian-feishu-sync.git
```

### 手动安装

```bash
git clone https://github.com/Igloo302/obsidian-feishu-sync.git
cd obsidian-feishu-sync
cp -r . ~/.hermes/skills/obsidian-feishu-sync/
```

## 使用

### 自然语言交互（Hermes Agent）

| 你说 | 效果 |
|------|------|
| `把这个飞书文档同步到本地` | 下载到 Inbox，建立同步关系 |
| `把 blog/posts/hello.md 同步到飞书` | 创建/更新飞书文档 |
| `查看所有同步关系` | 列出已同步的文档 |
| `停止同步 xxx` | 移除同步关系，保留文档 |
| `扫描 ~/docs 目录里的同步关系` | 探索式发现 |

### 命令行

```bash
# 从飞书同步到本地（默认 Obsidian vault）
python sync.py sync-from-feishu "https://xxx.feishu.cn/docx/xxx"

# 从飞书同步到指定路径
python sync.py sync-from-feishu "https://xxx.feishu.cn/docx/xxx" --path ~/blog/posts/draft.md

# 用 base-dir 切换项目目录，省去写绝对路径
python sync.py --base-dir ~/Projects/thoughts-public sync-to-feishu posts/hello.md --create

# 绝对路径也支持
python sync.py sync-to-feishu /Users/me/projects/docs/note.md --create

# 查看同步状态
python sync.py sync-status

# 同步所有已建立关系的文档
python sync.py sync-all

# 扫描目录中已存在的同步关系（只读）
python sync.py scan ~/Documents/my-project

# 扫描 base-dir
python sync.py --base-dir ~/blog scan

# 修复/重建同步状态
python sync.py sync-repair ~/Documents  # 扫描指定目录重建
```

## 前置要求

- Python 3.11+
- [lark-cli](https://github.com/we-dcode/lark-cli) — 飞书 CLI 工具
- 已配置飞书应用权限（文档读写、图片上传）

## Base Directory 概念

`--base-dir` 决定了相对路径的解析起点：

- **未指定** → 默认 Obsidian vault（`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianVault/`）
- **`--base-dir ~/Projects/blog`** → 相对路径 `posts/note.md` 解析为 `~/Projects/blog/posts/note.md`
- **环境变量** `SYNC_BASE_DIR` 也可设置

绝对路径（以 `/` 开头）始终直接使用，不受 base-dir 影响。

## 同步流程

### 飞书 → 本地

1. 解析飞书文档 URL，提取文档 ID
2. 调用 lark-cli 获取文档内容
3. **转换表格**：`<lark-table>` → Markdown 表格
4. **下载图片**：飞书图片 → `attachments/<doc_id>/`
5. 写入文件，添加 frontmatter 标识

### 本地 → 飞书

1. 读取文件，提取 frontmatter 中的飞书文档 ID
2. **上传图片**：本地图片 → 飞书云存储
3. **转换表格**：Markdown 表格 → `<lark-table>`
4. 调用 lark-cli 更新飞书文档
5. 更新 frontmatter 时间戳

## Frontmatter 格式

同步的文档会自动添加以下 YAML frontmatter：

```yaml
---
feishu_doc_id: MvRkdLdazoPElDxlh2GcHcDNnJe
feishu_title: 文档标题
last_sync: 2024-01-15T10:30:00
---
```

**这就是同步关系的核心** — 无论文件在哪个目录、叫什么名字，只要 frontmatter 在，就能找回同步关系。

## 项目结构

```
obsidian-feishu-sync/
├── SKILL.md              # Hermes Agent 技能定义
├── scripts/
│   ├── sync.py           # 核心同步脚本（CLI）
│   ├── converter.py      # 表格/图片格式转换
│   └── state_manager.py  # 同步状态管理
└── LICENSE
```

## 注意事项

- 表格转换支持基本格式，复杂表格（合并单元格）可能不完全兼容
- 图片同步需要飞书应用有 `drive:drive:readonly` 权限
- 大量图片同步可能耗时较长
- 同步状态存储于 `~/.hermes/obsidian-feishu-sync/sync_state.json`

## 对比其他方案

| 特性 | 本工具 | 手动操作 |
|------|--------|---------|
| 同步方向 | 双向自动 | 单向手动 |
| 格式保留 | 表格/图片/链接 | 容易丢失 |
| 冲突处理 | 自动检测+智能合并 | 手动对比 |
| 文件路径 | 任意位置 | 仅 Obsidian |
| 同步关系 | Frontmatter 持久化 | 无 |

## License

MIT
