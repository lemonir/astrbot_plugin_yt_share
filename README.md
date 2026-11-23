<div align="center">

# 外网视频解析

_只认外网站点的视频解析插件，下载后连卡片一起发进群_

</div>

## 为什么做这个

国内平台（B站、抖音、小红书、快手……）的解析插件已经很成熟了，但它们的平台列表里通常没有 YouTube、Twitter/X、TikTok 这些。

这个插件只干一件事：**外网链接交给我，国内的留给别的插件**，两边不打架。

## 支持范围

YouTube、YouTube Shorts、Twitter/X、TikTok、Instagram、Facebook、Twitch、Vimeo、Reddit、Dailymotion、niconico、SoundCloud、bilibili.tv。

实际能力取决于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 支持哪些站点，上面这些是默认启用的白名单。

## 工作流程

```
群里出现外网链接
      │
      ├─ 命中白名单 → URL 去重（同链接 10 分钟一次）→ 同群冷却 30 秒
      │
      ├─ yt-dlp 取元数据 → 绘制卡片（封面 + 标题 + 作者 + 时长 + 播放/点赞）
      │
      ├─ 按画质上限下载（默认 720P）→ 体积超限则丢弃文件
      │
      └─ 发送：卡片 + 视频；没下成默认安静跳过，打开 fallback 开关才补链接
```

## 安装

1. 把插件目录放进 `data/plugins/astrbot_plugin_yt_share/`
2. 确保容器里装了 **yt-dlp** 和 **ffmpeg**：

```sh
pip install -U yt-dlp
apt-get install -y ffmpeg   # 音视频分流需要它来合并
```

3. 重启 AstrBot 或在面板扫描插件。

## 配置项

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `enable` | `true` | 总开关。关掉后所有链接都不处理，下面那些站点开关一并失效。 |
| `parse_bot_messages` | `false` | 也解析机器人自己发的链接，用于和资讯类插件联动。默认关，避免解析完发出去又触发解析。 |
| `url_dedup_minutes` | `10` | 同一条链接多久内只解析一次。这是「开了上面那个开关也不会死循环」的保险，不建议设 0。 |
| `site_youtube` 等 12 个 | `true` | 每个外网站点一个独立开关：YouTube、Twitter/X、TikTok、Instagram、Facebook、Twitch、Vimeo、Reddit、Dailymotion、niconico、SoundCloud、bilibili.tv。只影响自己那一家，关掉别的照常解析；总开关关掉时全部失效。 |
| `send_card` | `true` | 解析成功后先发一张卡片（本地绘制，不依赖外部渲染服务）。 |
| `send_video` | `true` | 下载并发送视频本体。关掉就只发卡片和链接。 |
| `max_height` | `720` | 画质上限。480 最省流量，1080 以上体积明显变大。 |
| `max_size_mb` | `50` | 视频体积上限，超了不发文件，避免传一半断掉。 |
| `fallback_link_on_fail` | `false` | 下载失败或超体积时，要不要补发原链接。默认关——群里多数人没代理，给了也点不开。 |
| `cooldown_seconds` | `30` | 同群两次解析的最短间隔。 |
| `download_timeout_seconds` | `180` | 单次下载超时，避免任务一直挂着。 |
| `proxy` | 空 | 留空跟随环境变量。YouTube、Twitter 通常必须挂代理。 |

## 出处与授权

- **取流内核**：[yt-dlp](https://github.com/yt-dlp/yt-dlp)，Unlicense 许可。本插件不复制它的代码，只把它当依赖调用。
- **链接识别、调度、体积控制、卡片绘制、消息发送**：本插件自己实现，MIT 许可。
- **卡片信息**：来自各平台对外公开的元数据（标题、作者、时长、封面、播放量），不抓取正文，也不绕过任何登录限制。
- 本插件与上述各平台无隶属关系，相关商标归各自权利人所有。

## 已知限制

- **YouTube 的高清格式需要一个 JS 运行时**。新版 yt-dlp 建议装 [Deno](https://deno.com/)，没装时会少部分格式、偶尔只能拿到较低画质。
- **代理断了就全废**，这类站点没有直连的余地。
- **时长超过默认超时的视频**会被放弃，可以先调大 `download_timeout_seconds`。
- 大体积、高画质的视频发到 QQ 容易失败，这也是默认 720P + 50MB 的原因。

## 更新日志

- **v0.3.0**：新增 `parse_bot_messages`（默认关）和 `url_dedup_minutes`（默认 10 分钟），可以接住机器人自己在群里发的链接，靠去重断掉循环。
- **v0.2.3**：把「失败补发原链接」做成开关 `fallback_link_on_fail`，默认关闭。
- **v0.2.2**：失败时不再发提示语，只保留日志，避免在群里刷屏。
- **v0.2.1**：失败时不再补发原链接——群里大多数人没有代理环境，给链接也点不开。
- **v0.2.0**：每个外网站点拆出独立开关（12 个），全部挂在总开关下，总开关关掉时一律失效。
- **v0.1.0**：首版。外网白名单、元数据卡片、按画质与体积限制下载、超限补链接。

## 许可

MIT
