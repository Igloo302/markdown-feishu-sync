# Obsidian-Feishu Sync

> Obsidian 和飞书文档的双向同步工具，让知识在两个平台间自由流动。

## 为什么需要这个？

**没有同步工具时：**
- 飞书文档想归档到 Obsidian？手动复制粘贴，格式全乱
- Obsidian 笔记想分享给团队？导出 Markdown，上传飞书，再调整格式
- 两边都有修改？不知道该以哪个为准
- 表格格式不兼容？飞书表格变成乱码
- 图片链接失效？飞书图片在 Obsidian 里显示不出来

**有了同步工具：**
- 一条命令：飞书文档 → Obsidian Inbox，自动添加同步标识
- 一条命令：Obsidian 笔记 → 飞书文档，团队立即可见
- 已建立同步关系的文档，自动检测冲突并智能合并
- 表格自动转换：飞书 `<lark-table>` ↔ Markdown 表格
- 图片自动同步：飞书图片下载到本地 / 本地图片上传到飞书

## 特性

- ✅ **双向同步** - 飞书 ↔ Obsidian，自由选择方向
- ✅ **路径无关** - 文件移动/重命名不影响同步关系（通过 frontmatter 追踪）
- ✅ **表格转换** - 飞书表格 ↔ Markdown 表格自动转换
- ✅ **图片同步** - 飞书图片下载到 `attachments/` / 本地图片上传到飞书
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
```

## 前置要求

- Python 3.11+
- [lark-cli](https://github.com/we-dcode/lark-cli) - 飞书 CLI 工具
- 已配置飞书应用权限（文档读写、图片上传）

## 配置

编辑 `scripts/config.py`：

```python
OBSIDIAN_VAULT_PATH = Path("~/path/to/your/obsidian/vault").expanduser()
DEFAULT_INBOX_DIR = "0-Inbox"  # 默认同步目标目录
```

## 同步流程

### 飞书 → Obsidian

1. 解析飞书文档 URL，提取文档 ID
2. 调用 lark-cli 获取文档内容
3. **转换表格**：`<lark-table>` → Markdown 表格
4. **下载图片**：飞书图片 → `attachments/<doc_id>/`
5. 写入 Obsidian，添加 frontmatter 标识

### Obsidian → 飞书

1. 读取 Obsidian 文档，提取 frontmatter
2. **上传图片**：本地图片 → 飞书云存储
3. **转换表格**：Markdown 表格 → `<lark-table>`
4. 调用 lark-cli 更新飞书文档
5. 更新 frontmatter 时间戳

## Frontmatter 格式

```yaml
---
feishu_doc_id: MvRkdLdazoPElDxlh2GcHcDNnJe
feishu_title: 文档标题
last_sync: 2024-01-15T10:30:00
---
```

## 注意事项

- 表格转换支持基本格式，复杂表格（合并单元格）可能不完全兼容
- 图片同步需要飞书应用有 `drive:drive:readonly` 权限
- 大量图片同步可能耗时较长

## License

MIT
