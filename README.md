# Obsidian-Feishu Sync

> Obsidian 和飞书文档的双向同步工具，让知识在两个平台间自由流动。

## 为什么需要这个？

**没有同步工具时：**
- 飞书文档想归档到 Obsidian？手动复制粘贴，格式全乱
- Obsidian 笔记想分享给团队？导出 Markdown，上传飞书，再调整格式
- 两边都有修改？不知道该以哪个为准

**有了同步工具：**
- 一条命令：飞书文档 → Obsidian Inbox，自动添加同步标识
- 一条命令：Obsidian 笔记 → 飞书文档，团队立即可见
- 已建立同步关系的文档，自动检测冲突并智能合并

## 特性

- ✅ **双向同步** - 飞书 ↔ Obsidian，自由选择方向
- ✅ **路径无关** - 文件移动/重命名不影响同步关系（通过 frontmatter 追踪）
- ✅ **安全删除** - 删除一份文档，同步停止但另一份保留
- ✅ **冲突检测** - 双向同步时自动检测冲突，智能合并
- ✅ **状态可视** - 查看所有同步关系，一目了然

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

| 你说 | 效果 |
|------|------|
| `把这个飞书文档同步到 Obsidian: <URL>` | 下载到 Inbox，建立同步关系 |
| `把 Obsidian 的 Notes/xxx.md 同步到飞书` | 创建/更新飞书文档 |
| `查看所有同步关系` | 列出已同步的文档 |
| `停止同步 xxx.md` | 移除同步关系，保留文档 |

### 命令行

```bash
# 从飞书同步到 Obsidian
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-from-feishu "https://xxx.feishu.cn/docx/xxx"

# 从 Obsidian 同步到飞书
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-to-feishu "Notes/my-note.md" --create

# 查看同步状态
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-status

# 同步所有已建立关系的文档
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-all

# 修复断开的同步关系
python ~/.hermes/skills/obsidian-feishu-sync/scripts/sync.py sync-repair
```

## 工作原理

```
┌─────────────┐                    ┌─────────────┐
│   飞书文档   │◄────── 同步 ──────►│  Obsidian   │
└─────────────┘                    └─────────────┘
       │                                  │
       │  doc_id + frontmatter            │
       ▼                                  ▼
┌─────────────────────────────────────────────────┐
│              sync_state.json                    │
│  (记录同步关系、最后同步时间、内容哈希)          │
└─────────────────────────────────────────────────┘
```

**同步标识（Frontmatter）：**

```yaml
---
feishu_doc_id: doxcnXXXXXX
feishu_title: 原始标题
last_sync: 2024-01-15T10:30:00Z
---
```

即使文件被移动或重命名，通过 frontmatter 也能追踪同步关系。

## 依赖

- [lark-cli](https://github.com/nicepkg/lark-cli) - 飞书文档操作
- Obsidian vault 路径：`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianVault/`

## License

MIT
