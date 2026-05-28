---
name: obsidian-feishu-sync
description: 任意 markdown 文件 ↔ 飞书文档双向同步工具
triggers:
  - 同步.*飞书
  - 飞书.*同步
  - sync.*feishu
  - 同步.*markdown
  - markdown.*同步
  - sync-from-feishu
  - sync-to-feishu
  - sync-status
  - sync-remove
  - sync-repair
  - scan.*同步.*状态
---

# Markdown-Feishu Sync Skill

实现**任意路径下 markdown 文件**与飞书文档的双向同步。不再限定于 Obsidian vault —— 任何 `.md` 文件均可同步。

## 核心功能

1. **从飞书同步到本地** - 飞书文档 → 本地 `.md` 文件（任意路径）
2. **从本地同步到飞书** - 本地 `.md` 文件 → 飞书文档（任意路径）
3. **自动双向同步** - 通过 `sync-all` 一键同步所有已建立关系的文档
4. **安全的删除处理** - `sync-remove` 只移除同步关系，不删除文件
5. **路径无关同步** - 通过 frontmatter 存储飞书文档 ID，移动/重命名文件不影响同步关系
6. **全路径支持** - 支持绝对路径、相对路径（可配置 `--base-dir`）
7. **向后兼容** - 默认 base_dir 为 Obsidian vault，旧版同步状态自动迁移
8. **扫描发现** - `scan` 命令扫描目录树中所有含 `feishu_doc_id` frontmatter 的文件

## 核心功能

1. **从飞书同步到 Obsidian** - 用户提供飞书链接，同步到 Obsidian 的 Inbox 目录
2. **从 Obsidian 同步到飞书** - 用户提供 Obsidian 内容，同步到飞书文档
3. **自动双向同步** - 建立同步关系的文档自动双向同步
4. **安全的删除处理** - 删除一份文档，停止同步但不删除另一份
5. **路径无关同步** - 通过 frontmatter 存储飞书文档 ID，移动/重命名文件不影响同步关系
6. **表格转换** - 飞书 `<lark-table>` ↔ Markdown 表格自动转换
7. **图片同步** - 飞书图片下载到 `attachments/` 目录 / 本地图片上传到飞书

## 基础路径（Base Directory）概念

`--base-dir` 是本次扩展的核心特性。它决定了相对路径的解析起点：

- **指定 base-dir**：`--base-dir ~/Projects/thoughts-public`
- **未指定**：默认使用 Obsidian vault 路径（向后兼容）
- **环境变量**：可通过 `SYNC_BASE_DIR` 设置

**路径解析规则**：
- 绝对路径（以 `/` 开头）→ 直接使用
- 相对路径（如 `Notes/note.md`）→ 解析为 `{base-dir}/{路径}`

## 命令

### 全局选项

所有命令均支持以下全局选项：

- `--base-dir <目录>`: 设置基础目录（解析相对路径用），默认 Obsidian vault

### sync-from-feishu

从飞书链接同步文档到本地 markdown 文件。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-from-feishu <feishu_url>
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py --base-dir ~/Projects sync-from-feishu <feishu_url>
```

参数:
- `feishu_url`: 飞书文档链接，支持格式:
  - `https://xxx.feishu.cn/docx/xxx`
  - `https://xxx.larksuite.com/docx/xxx`

选项:
- `--path <path>`: 保存路径（绝对或相对路径，默认: {base-dir}/Inbox/文档标题.md）

### sync-to-feishu

从本地 markdown 文件同步到飞书文档。

```bash
# 使用绝对路径
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-to-feishu /Users/igloo/Projects/my-doc.md --create

# 使用相对路径（相对于 base-dir）
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-to-feishu Notes/meeting.md --create

# 指定 base-dir（在 blog 仓库中同步）
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py --base-dir ~/Projects/thoughts-public sync-to-feishu posts/new-post.md --create
```

参数:
- `markdown_path`: 本地 markdown 文件路径（绝对路径或相对路径）

选项:
- `--create`: 如果飞书文档不存在，创建新文档
- `--folder <folder_token>`: 指定飞书文档保存的文件夹 token

### sync-status

查看所有同步关系。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-status
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py --base-dir ~/Projects sync-status
```

输出格式:
```
飞书文档 ID           飞书标题      本地文件路径                         最后同步        状态
──────────────────────────────────────────────────────────────────────────────────────────────
doxcnXXXXXX           项目计划      ObsidianVault/Inbox/项目计划.md      2024-01-15 10:30 ✓
doxcnYYYYYY           会议记录      Notes/会议记录.md                   2024-01-14 15:20 ✓
doxcnZZZZZZ           博客草稿      /Users/igloo/Projects/blog/draft.md  2024-01-14 12:00 ✓
```

### sync-remove

移除同步关系（不删除文档）。

```bash
# 通过飞书文档 ID 移除
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-remove doxcnXXXXXX

# 通过本地文件路径移除（支持绝对和相对路径）
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-remove /Users/igloo/Projects/my-doc.md
```

参数:
- `identifier`: 飞书文档 ID 或本地文件路径

### sync-all

同步所有已建立关系的文档。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-all
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-all --direction to-feishu
```

选项:
- `--direction <direction>`: 同步方向 `to-feishu` | `to-obsidian` | `bidirectional`（默认）

### sync-repair

根据 frontmatter 重建 sync_state.json（用于修复断开的同步关系）。

```bash
# 扫描 base_dir（默认 Obsidian vault）
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-repair

# 扫描指定目录
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py --base-dir ~/Projects/thoughts-public sync-repair
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-repair ~/Documents/my-md-project
```

适用场景：
- sync_state.json 丢失或损坏
- 文件被移动/重命名后需要更新路径
- 手动修改了 frontmatter 后需要同步状态
- 迁移到新目录后重建同步关系

### scan

扫描目录树中所有包含 `feishu_doc_id` frontmatter 的 markdown 文件，列出发现的同步关系（只读，不修改状态）。

```bash
# 扫描 base_dir
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py scan

# 扫描指定目录
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py scan ~/Documents/my-project
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py --base-dir ~/Projects scan
```

## Frontmatter 同步标识

同步的 Obsidian 文档会自动添加 frontmatter：

```yaml
---
feishu_doc_id: doxcnXXXXXX
feishu_title: 原始标题
last_sync: 2024-01-15T10:30:00Z
---
```

**优势**：
- 文件移动或重命名后，`sync_all` 会自动通过 frontmatter 找到文件
- `sync_repair` 可以根据 frontmatter 重建同步状态
- 即使 sync_state.json 丢失，也能恢复同步关系

## 同步状态存储

同步状态存储在 `~/.hermes/obsidian-feishu-sync/sync_state.json`:

```json
{
  "doxcnXXXXXX": {
    "obsidian_path": "Inbox/项目计划.md",
    "feishu_title": "项目计划文档",
    "last_sync_time": "2024-01-15T10:30:00Z",
    "obsidian_hash": "abc123",
    "feishu_hash": "def456"
  }
}
```

## 使用示例

### 示例 1: 从飞书同步新文档（保存到 Obsidian vault，默认 base_dir）

```
用户: 把这个飞书文档同步到本地: https://xxx.feishu.cn/docx/doxcnXXXXXX
助手: [调用 sync-from-feishu 命令]
已将「项目计划文档」同步到本地: Inbox/项目计划.md
```

### 示例 2: 从飞书同步到指定路径（任意目录）

```
用户: 把飞书文档同步到我的博客仓库
助手: [调用 sync-from-feishu --path ~/Projects/thoughts-public/blog/idea.md]
已将「AI 趋势分析」同步到本地: ~/Projects/thoughts-public/blog/idea.md
```

### 示例 3: 从本地 markdown 同步到飞书

```
用户: 把 Projects/meeting-notes.md 同步到飞书
助手: [调用 sync-to-feishu ~/Projects/meeting-notes.md --create]
已将「会议记录」同步到飞书文档 (doxcnYYYYYY)
```

### 示例 4: 在项目目录中使用 base-dir

```
用户: 把博客 repo 里的 posts/draft.md 同步到飞书
助手: [调用 sync-to-feishu --base-dir ~/Projects/thoughts-public posts/draft.md --create]
已将「博客草稿」同步到飞书文档 (doxcnZZZZZZ)
```

### 示例 5: 扫描目录发现同步关系

```
用户: 看看我的 docs 目录里有哪些文件已经同步到飞书了
助手: [调用 scan ~/Documents/my-project]
在 /Users/igloo/Documents/my-project 中找到 3 个同步关系:
  doxcnAAAAAA             架构设计            docs/arch.md
  doxcnBBBBBB             API 接口说明        docs/api.md
  doxcnCCCCCC             部署指南            docs/deploy.md
```

### 示例 6: 查看所有同步状态

```
用户: 查看所有同步关系
助手: [调用 sync-status]
```

### 示例 4: 移除同步关系

```
用户: 停止同步 Inbox/项目计划.md
助手: [调用 sync-remove 命令]
已移除同步关系，文档保留在原位置
```

## 技术细节

### 依赖的 Skills

- `lark-doc`: 飞书文档操作（读取、创建、更新）
- `lark-shared`: 飞书认证和配置
- `obsidian`: Obsidian vault 操作

### 冲突处理

当双向同步检测到冲突时:
1. 比较最后修改时间
2. 较新的内容覆盖较旧的
3. 如果修改时间相近（5分钟内），保留两个版本并标记冲突

### 内容转换

- 飞书文档 → Obsidian: 转换为 Markdown 格式
- Obsidian → 飞书文档: 转换为飞书文档块格式

### 文件路径

- **默认 base_dir（向后兼容）**: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianVault/`
- **自定义 base_dir**: 通过 `--base-dir` 参数或 `SYNC_BASE_DIR` 环境变量设置
- **绝对路径**: 任何以 `/` 开头的路径直接使用，不依赖 base_dir
- **同步状态存储**: `~/.hermes/obsidian-feishu-sync/sync_state.json`
- **Skill 目录**: `~/.hermes/skills/obsidian-feishu-sync/`
- **附件目录**: `attachments/{doc_id}/`（位于 Markdown 文件同级目录下，以确保 Markdown 相对路径引用的正确渲染与预览，支持子目录结构）

## 注意事项

1. 需要先配置飞书 CLI 认证（`lark-cli auth login`）
2. 飞书文档需要 API 访问权限
3. 大文档同步可能需要较长时间
4. **图片和附件的处理**：
   - 飞书下载的图片及媒体文件使用 `lark-cli docs +media-download` 获取，并以标准 Markdown 语法 `![图片](attachments/{doc_id}/img_{token}.png)` 插入本地文档。
   - `lark-cli` 要求 `--output` 路径必须为当前工作目录下的相对路径，脚本在执行下载时会自动将本地绝对路径转换为相对于当前工作目录的相对路径，以避免触发 Lark CLI 的安全检查报错。
   - 本地图片同步上传至飞书使用 `lark-cli docs +media-insert` 并动态绑定到文档块，本地相对图片路径会被重写为飞书图片 Token 结构。

