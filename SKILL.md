---
name: obsidian-feishu-sync
description: Obsidian 和飞书文档的双向同步工具
triggers:
  - obsidian.*同步.*飞书
  - 飞书.*同步.*obsidian
  - sync.*feishu
  - sync.*obsidian
  - sync-from-feishu
  - sync-to-feishu
  - sync-status
  - sync-remove
  - sync-repair
---

# Obsidian-Feishu Sync Skill

实现 Obsidian 和飞书文档的双向同步。

## 核心功能

1. **从飞书同步到 Obsidian** - 用户提供飞书链接，同步到 Obsidian 的 Inbox 目录
2. **从 Obsidian 同步到飞书** - 用户提供 Obsidian 内容，同步到飞书文档
3. **自动双向同步** - 建立同步关系的文档自动双向同步
4. **安全的删除处理** - 删除一份文档，停止同步但不删除另一份
5. **路径无关同步** - 通过 frontmatter 存储飞书文档 ID，移动/重命名文件不影响同步关系

## 命令

### sync-from-feishu

从飞书链接同步文档到 Obsidian Inbox 目录。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-from-feishu <feishu_url>
```

参数:
- `feishu_url`: 飞书文档链接，支持格式:
  - `https://xxx.feishu.cn/docx/xxx`
  - `https://xxx.larksuite.com/docx/xxx`

选项:
- `--path <obsidian_path>`: 指定 Obsidian 保存路径（默认: Inbox/文档标题.md）

### sync-to-feishu

从 Obsidian 同步内容到飞书文档。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-to-feishu <obsidian_path>
```

参数:
- `obsidian_path`: Obsidian 文档相对路径（如 `Notes/my-note.md`）

选项:
- `--create`: 如果飞书文档不存在，创建新文档
- `--folder <folder_token>`: 指定飞书文档保存的文件夹 token

### sync-status

查看所有同步关系。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-status
```

输出格式:
```
飞书文档                          Obsidian 路径           最后同步时间
─────────────────────────────────────────────────────────────────────
项目计划文档                      Inbox/项目计划.md       2024-01-15 10:30
会议记录                          Notes/会议记录.md       2024-01-14 15:20
```

### sync-remove

移除同步关系（不删除文档）。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-remove <identifier>
```

参数:
- `identifier`: 可以是飞书文档 ID 或 Obsidian 路径

### sync-all

同步所有已建立关系的文档。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-all
```

选项:
- `--direction <direction>`: 同步方向 `to-feishu` | `to-obsidian` | `bidirectional`（默认）

### sync-repair

根据 frontmatter 重建 sync_state.json（用于修复断开的同步关系）。

```bash
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-repair
```

适用场景：
- sync_state.json 丢失或损坏
- 文件被移动/重命名后需要更新路径
- 手动修改了 frontmatter 后需要同步状态

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

### 示例 1: 从飞书同步新文档

```
用户: 把这个飞书文档同步到 Obsidian: https://xxx.feishu.cn/docx/doxcnXXXXXX
助手: [调用 sync-from-feishu 命令]
已将「项目计划文档」同步到 Obsidian: Inbox/项目计划.md
```

### 示例 2: 从 Obsidian 同步到飞书

```
用户: 把 Obsidian 的 Notes/会议记录.md 同步到飞书
助手: [调用 sync-to-feishu 命令]
已将「会议记录」同步到飞书文档
```

### 示例 3: 查看同步状态

```
用户: 查看所有同步关系
助手: [调用 sync-status 命令]
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

- Obsidian vault: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianVault/`
- 同步状态: `~/.hermes/obsidian-feishu-sync/sync_state.json`
- Skill 目录: `~/.hermes/skills/obsidian-feishu-sync/`

## 注意事项

1. 需要先配置飞书 CLI 认证（`lark-cli auth login`）
2. 飞书文档需要 API 访问权限
3. 大文档同步可能需要较长时间
4. 图片和附件会单独处理并保持引用
