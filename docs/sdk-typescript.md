# DGHub SDK TypeScript 使用指南

社区 TypeScript SDK（npm `dghub-sdk`），为 DGHub 插件提供 WebSocket 通信封装。
协议细节请参考 [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)。

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [插件根目录与资源文件](#插件根目录与资源文件)
- [配置监听](#配置监听)
- [强度触发](#强度触发)
- [状态上报](#状态上报)
- [错误处理](#错误处理)
- [手动接入（调试）](#手动接入调试)
- [更多](#更多)

---

## 安装

从 npm 安装：

```bash
npm install dghub-sdk
```

> 依赖：Node.js 20+（SEA 打包要求）、`ws`（会自动安装）。

## 快速开始

```ts
import { Agent } from "dghub-sdk";

let running = true;

const agent = new Agent({
  onStop: (reason) => { running = false; },
});
agent.start();
await agent.waitReady(10);   // 等待握手完成
while (running) {
  agent.poll();
  // 你的游戏 / 业务逻辑
}
```

`start()` 不等待握手完成。在首次调用 `poll()` 或发送消息前，应显式
`await waitReady()` 确认握手完成：

```ts
const agent = new Agent();
agent.start();
await agent.waitReady(10);
```

需要非阻塞的单次检查时，可用 `isReady()`：

```ts
if (agent.isReady()) {
  agent.sendStatusField("score", score);
}
```

连接或握手失败会由 `waitReady()` 的 Promise 拒绝抛出，
运行期间的后台异常仍可通过 `getException()` 读取。

`poll()` 从内部消息队列取出已收到的服务端消息，在调用线程上依次触发回调。
默认非阻塞（立即清空队列），传入 `timeout` 参数可阻塞等待。

## 插件根目录与资源文件

`pluginRoot()` 返回插件根目录，源码与打包形态自动一致：

- **exe（Packer 产物）**：exe 所在目录（SEA onedir 布局下 exe 与
  manifest.json、资源同级于插件根）
- **源码（开发调试）**：调用该函数的文件所在目录
- **`DGHUB_PLUGIN_ROOT`**：服务端/调试器注入插件根时优先使用（约定绝对路径）

```ts
import { pluginRoot } from "dghub-sdk";
import { join } from "node:path";

const icon = join(pluginRoot(), "assets", "icon.png");   // 读资源统一相对插件根
```

`Agent` 的 `manifestDir` 构造参数解析三档：

1. 显式传入——绝对原样；相对以调用方文件目录为基准
2. `DGHUB_MANIFEST_DIR` 环境变量——Packer 调试注入（约定绝对路径）
3. 均未提供——直接用 `pluginRoot()` 的插件根（Packer 用户
   `new Agent()` 零参数）

手动运行源码且插件根没有 manifest.json 时，握手会失败
（插件根 manifest 是构建产物；未使用 Packer 的项目需自行维护）。

## 配置监听

DGHub 通过两个时机推送配置：

| 回调 | 触发时机 | 签名 |
|------|----------|------|
| `onConfig` | 握手完成后，推送全量配置 | `(config: Record<string, unknown>) => void` |
| `onConfigChanged` | 用户在前端修改单个字段 | `(key: string, value: boolean \| number \| string) => void` |

典型用法：

```ts
import { Agent } from "dghub-sdk";

const config: Record<string, unknown> = {};

const agent = new Agent({
  onConfig: (cfg) => {
    // 握手后收到全量配置，初始化本地状态
    Object.assign(config, cfg);
  },
  onConfigChanged: (key, value) => {
    // 用户修改了一个配置项，增量更新
    config[key] = value;
  },
});
agent.start();
await agent.waitReady(10);
```

### config 的内容与边界

`config` 是当前插件 ID 下的"配置值快照"，不是 `config_schema` 本身。它通常包含：

- 已经持久化的 `config_schema` 字段值
- 插件通过 `sendSetConfig` 写入的自定义字段
- DGHub 管理的公开字段，例如 `target_id`、运行中产生的 `idle_strength`

边界约定：

- `config_schema.default` 不保证自动出现在 `config` 中，尚未保存的字段可能缺失，
  插件应使用 schema 的默认值兜底
- `enabled` 和 `_` 开头的内部字段不会下发
- `target_id` 由 DGHub 管理，插件不能通过 `sendSetConfig` 修改
- 握手后收到一次全量 `config`，之后用户修改配置会收到单字段 `config_changed`
- `sendSetConfig` 发送后不会回推 `config_changed`，插件应在发送后同步更新自己的本地缓存

## 强度触发

`sendTrigger` 是推荐的核心方法——一条调用同时控制强度、波形、通道：

```ts
agent.sendTrigger({
  action: Action.BOTH,            // 默认 "both"
  deltaPct: 0,                    // 默认 0
  strengthMode: StrengthMode.ROLLBACK,  // 默认 "rollback"
  durationS: 1.0,                 // 默认 1.0
  preset: "",                     // 含波形时必填
  channel: Channel.BOTH,          // 默认 "both"
  label: "受击",
  username: "player",
  name: "BOSS 守卫",
  cause: "强度值下降",
  pulseName: "脉冲",
  targetId: "target-1",
});
```

### Rollback（临时）

强度临时偏移 baseline，duration 结束后自动回正：

```ts
agent.sendTrigger({
  action: Action.BOTH,
  deltaPct: 50,
  strengthMode: StrengthMode.ROLLBACK,
  durationS: 1.5,
  preset: "CS2-受伤",
  label: "受击",
});
```

### Permanent（永久）

永久修改 baseline：

```ts
agent.sendTrigger({
  action: Action.STRENGTH,
  deltaPct: 10,
  strengthMode: StrengthMode.PERMANENT,
});
```

### 仅波形

不改强度，只播放一段触感反馈：

```ts
agent.sendTrigger({
  action: Action.WAVEFORM,
  preset: "振动-短",
  durationS: 0.5,
});
```

### SDK 1.1 事件信息

`sendTrigger()` 可通过 `name`、`cause`、`pulseName` 补充事件的具体内容、
触发原因和实际波形名。`sendEvent()` 还支持 `fromPct`、`toPct`、
`deltaPct`，用于让 DGHub 界面完整展示事件前后的强度变化。

### V4 多设备目标

V4 设备信息会以 `DeviceType.V4` 传给 `onDeviceInfo`。通常插件不需要自己
选设备，省略 `targetId` 时 DGHub 会使用插件默认目标；只有一次行为需要明确
发给另一台 V4 设备时，才传消息级目标：

```ts
agent.sendPulse("振动-短", Channel.A, "target-1");
```

`sendTrigger()`、`sendEvent()`、`sendPulse()`、`sendSetStrength()` 和
`sendAdjustStrength()` 都支持可选的 `targetId`。省略时不会在 JSON 中发送
该字段，因此 V2/V3 和旧调用方式保持不变。`targetId` 仍由 DGHub 管理，
不要用 `sendSetConfig()` 修改它。

## 状态上报

SDK 提供多个便捷方法上报插件状态：

### sendStartupCheck —— 启动检查

内部维护 steps 状态，每次调用更新或新增对应 step 并自动发送：

```ts
import { CheckState } from "dghub-sdk";

// 初始化时批量设置 steps（不发送）
agent.sendStartupCheck("plugin", "插件连接", CheckState.IDLE, { dontSend: true });
agent.sendStartupCheck("game", "游戏连接", CheckState.IDLE, { dontSend: true });
// 最后一个调用触发发送
agent.sendStartupCheck("device", "设备连接", CheckState.IDLE,
  { displayStatus: "初始化中" });

// 之后逐步更新，每次自动发送
agent.sendStartupCheck("plugin", "插件连接", CheckState.OK, { detail: "已连接 DGHub" });
agent.sendStartupCheck("game", "游戏连接", CheckState.OK,
  { detail: "已连接", displayStatus: "运行中" });
```

面板标题默认为 `"Startup Check"`，可通过 `setStartupCheckTitle()` 修改。

`state` 可选值定义在 `CheckState` 枚举中：`idle` / `pending` / `ok` / `warn` / `fail`。

### sendDisplayStatus —— 显示状态

```ts
agent.sendDisplayStatus("运行中");
```

### sendStatusField —— 单字段上报

```ts
agent.sendStatusField("tick", 42);
```

### sendStatus —— 底层 API

以上方法底层均调用 `sendStatus(fields)`，可直接使用：

```ts
agent.sendStatus({ custom_field: 42 });
```

## 错误处理

后台连接中的异常不会直接抛出，而是被收集到内部队列。
在主循环中调用 `getException()` 检查：

```ts
while (running) {
  agent.poll();

  let exc = agent.getException();
  while (exc !== null) {
    console.error(`[错误] ${exc}`);
    exc = agent.getException();
    // 根据严重程度决定是否退出
  }
}
```

## 手动接入（调试）

正常情况下 DGHub 会自动 spawn 你的插件进程并设置环境变量。
调试时可以手动启动插件，只需提前设置环境变量：

```bash
set DGHUB_HOST=127.0.0.1
set DGHUB_PORT=27020
set DGHUB_TOKEN=<从 GET /api/plugins/_session_token 获取>
node dist/main.js
```

Token 可从 DGHub 运行时通过 `GET http://127.0.0.1:27020/api/plugins/_session_token` 获取。

## 构建与测试

```bash
cd sdk/typescript
npm install
npm run build     # tsc 编译到 dist/
npm test          # node:test 单元测试
```

---

## 更多

- 完整协议字段定义：[PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md)
- API 签名与参数说明：参见源码中的 Google-style docstrings
