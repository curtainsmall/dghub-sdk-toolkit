/**
 * WebSocket 连接管理器 —— 与 Python SDK 的 `dghub_sdk.agent.Agent` 功能一致。
 *
 * Node 版用 async/await 直连（ws 库），消息先入队，用户线程调用 `poll()`
 * 时再分发到各回调；`waitReady()` 返回 Promise 等待握手完成。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import WebSocket from "ws";

import { Codec, CodecMessage } from "./codec.js";
import { Action, Channel, CheckState, DeviceType, LogLevel, OpCode, StrengthMode } from "./enums.js";
import { envConfig, manifestDir, pluginRoot } from "./paths.js";

/** Agent 构造参数（对应 Python `Agent.__init__` 的命名参数）。 */
export interface AgentOptions {
  /** 包含 manifest.json 的目录；默认插件根（支持 DGHUB_MANIFEST_DIR 注入）。 */
  manifestDir?: string;
  /** WebSocket 连接的最大重试次数。 */
  maxRetries?: number;
  /** 每次发送操作的可选超时（秒）。undefined = 发完即返回。 */
  sendTimeout?: number;
  /** 握手成功后调用，传入 hello_ack 数据。 */
  onReady?: (data: Record<string, unknown>) => void;
  /** 握手后服务端推送一次全量配置时调用。 */
  onConfig?: (config: Record<string, unknown>) => void;
  /** 单个配置项变更时调用。 */
  onConfigChanged?: (key: string, value: boolean | number | string) => void;
  /** 设备状态变化时调用。签名：(connected, deviceType, maxA, maxB)。 */
  onDeviceInfo?: (connected: boolean, deviceType: DeviceType, maxA: number, maxB: number) => void;
  /** 服务端要求插件停止时调用。 */
  onStop?: (reason: string) => void;
  /** 收到服务端 ping 时调用，传入时间戳。 */
  onPing?: (t: number) => void;
}

/** 发送操作排队用的内部包装。 */
interface SendTask {
  raw: string;
  resolve: () => void;
  reject: (err: Error) => void;
}

export class Agent {
  // -- 公开回调 --
  onReady?: (data: Record<string, unknown>) => void;
  onConfig?: (config: Record<string, unknown>) => void;
  onConfigChanged?: (key: string, value: boolean | number | string) => void;
  onDeviceInfo?: (connected: boolean, deviceType: DeviceType, maxA: number, maxB: number) => void;
  onStop?: (reason: string) => void;
  onPing?: (t: number) => void;

  // -- 内部状态 --
  private _manifestDir: string;
  private _maxRetries: number;
  private _sendTimeout?: number;
  private _ws: WebSocket | null = null;
  private _token = "";
  private _manifest: Record<string, unknown> = {};
  private _pluginId = "";
  private _connected = false;
  private _stopped = false;
  private _readyResolve: (() => void) | null = null;
  private _readyReject: ((err: Error) => void) | null = null;
  private _startupException: Error | null = null;
  private _readyPromise: Promise<void> | null = null;
  private _queue: CodecMessage[] = [];
  private _errorQueue: Error[] = [];
  /** 发送任务队列：握手完成前缓冲，连接后按序发出。 */
  private _sendQueue: SendTask[] = [];
  private _sendFlush: (() => void) | null = null;

  // 启动检查状态
  private _checkTitle = "Startup Check";
  private _checkSteps = new Map<string, Record<string, unknown>>();

  constructor(options: AgentOptions = {}) {
    // --- 解析 manifest 目录（显式 → DGHUB_MANIFEST_DIR → 插件根） ---
    this._manifestDir = manifestDir(options.manifestDir);
    this._maxRetries = options.maxRetries ?? 5;
    this._sendTimeout = options.sendTimeout;

    this.onReady = options.onReady;
    this.onConfig = options.onConfig;
    this.onConfigChanged = options.onConfigChanged;
    this.onDeviceInfo = options.onDeviceInfo;
    this.onStop = options.onStop;
    this.onPing = options.onPing;
  }

  // -- 属性 ----------------------------------------------------------

  /** 是否已握手成功且连接中。 */
  get connected(): boolean {
    return this._connected;
  }

  /** manifest.json 中的插件 id。 */
  get pluginId(): string {
    return this._pluginId;
  }

  // -- 公开生命周期方法 --------------------------------------------------

  /** 在后台启动 WebSocket 连接，不阻塞。 */
  start(): void {
    this._stopped = false;
    this._connected = false;
    this._startupException = null;
    this._queue = [];
    this._errorQueue = [];
    this._readyPromise = new Promise<void>((resolve, reject) => {
      this._readyResolve = resolve;
      this._readyReject = reject;
    });
    void this._connectAndLoop();
  }

  /** 等待握手成功；超时抛 TimeoutError。应在 start() 后调用。 */
  waitReady(timeout?: number): Promise<void> {
    if (!this._readyPromise) {
      return Promise.reject(new Error("Agent has not been started"));
    }
    return new Promise<void>((resolve, reject) => {
      const timer = timeout === undefined
        ? undefined
        : setTimeout(() => reject(new Error("Agent did not become ready before timeout")), timeout * 1000);
      this._readyPromise!
        .then(() => {
          if (timer) clearTimeout(timer);
          if (this._connected) {
            resolve();
          } else if (this._startupException) {
            reject(this._startupException);
          } else {
            reject(new Error("Agent stopped before handshake completed"));
          }
        })
        .catch((err: Error) => {
          if (timer) clearTimeout(timer);
          reject(err);
        });
    });
  }

  /** 一次性检查握手是否已完成（不阻塞）。 */
  isReady(): boolean {
    return this._connected;
  }

  /** 处理已接收的消息，在当前线程上调用回调。timeout 秒内最多阻塞取一条。 */
  poll(timeout?: number): void {
    if (timeout === undefined) {
      while (this._queue.length > 0) {
        const msg = this._queue.shift()!;
        this._invoke(msg);
      }
      return;
    }
    const deadline = Date.now() + timeout * 1000;
    while (this._queue.length === 0 && Date.now() < deadline) {
      // 忙等：等待接收循环入队（Node 事件循环不阻塞时消息即到）
      this._sleep(5);
    }
    if (this._queue.length > 0) {
      this._invoke(this._queue.shift()!);
    }
  }

  /** 通知后台循环停止并断开连接。 */
  stop(): void {
    this._stopped = true;
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      try {
        this._ws.close();
      } catch {
        // 忽略关闭异常
      }
      this._ws = null;
    }
  }

  /** 等待连接循环退出（可选项；Promise 在循环结束后 resolve）。 */
  async waitThreadingExit(timeout?: number): Promise<void> {
    // ws 连接关闭后循环自然退出；此处给事件循环一个退出的机会
    await this._sleep(timeout ?? 0.1);
  }

  // -- 公开发送方法（均为同步，立即调度） ----------------------------------

  /** 通过 WebSocket 发送原始 JSON 字符串。 */
  send(raw: string): void {
    this._scheduleSend(raw);
  }

  /** 向设备发送强度/波形触发（action 含波形时 preset 必填）。 */
  sendTrigger(options: {
    action?: Action;
    deltaPct?: number;
    strengthMode?: StrengthMode;
    durationS?: number;
    preset?: string;
    channel?: Channel;
    label?: string | null;
    username?: string | null;
    name?: string | null;
    cause?: string | null;
    pulseName?: string | null;
    targetId?: string | null;
  }): void {
    this._scheduleSend(Codec.trigger(options));
  }

  /** 发送一次性命名事件。 */
  sendEvent(label: string, name: string, options: {
    username?: string | null;
    strengthPct?: number | null;
    duration?: number;
    eventId?: string | null;
    cause?: string | null;
    pulseName?: string | null;
    fromPct?: number | null;
    toPct?: number | null;
    deltaPct?: number | null;
    targetId?: string | null;
  } = {}): void {
    this._scheduleSend(Codec.event(label, name, options));
  }

  /** 发送仅波形的脉冲（不改变强度）。 */
  sendPulse(preset: string, channel: Channel = Channel.BOTH, targetId?: string | null): void {
    this._scheduleSend(Codec.pulse(preset, channel, targetId));
  }

  /** 设置指定通道的绝对强度（0–100）。 */
  sendSetStrength(channel: Channel, pct: number, targetId?: string | null): void {
    this._scheduleSend(Codec.setStrength(channel, pct, targetId));
  }

  /** 按相对增量调整强度（-100 到 100）。 */
  sendAdjustStrength(channel: Channel, deltaPct: number, targetId?: string | null): void {
    this._scheduleSend(Codec.adjustStrength(channel, deltaPct, targetId));
  }

  /** 向服务端上报插件状态（如 startup_check 结果）。 */
  sendStatus(fields: Record<string, unknown>): void {
    this._scheduleSend(Codec.status(fields));
  }

  /** 向服务端发送日志，展示在 DGHub 控制台中。 */
  sendLog(level: LogLevel, message: string): void {
    this._scheduleSend(Codec.log(level, message));
  }

  /** 更新一个启动检查步骤，并可选地发送全量状态。 */
  sendStartupCheck(
    key: string,
    title: string,
    state: CheckState,
    options: {
      detail?: string | null;
      hint?: string | null;
      displayStatus?: string | null;
      dontSend?: boolean;
    } = {},
  ): void {
    const step: Record<string, unknown> = { key, title, state };
    if (options.detail !== undefined && options.detail !== null) {
      step.detail = options.detail;
    }
    if (options.hint !== undefined && options.hint !== null) {
      step.hint = options.hint;
    }
    this._checkSteps.set(key, step);

    if (options.dontSend) {
      return;
    }
    const fields: Record<string, unknown> = {};
    if (options.displayStatus !== undefined && options.displayStatus !== null) {
      fields.display_status = options.displayStatus;
    }
    fields.startup_check = {
      title: this._checkTitle,
      steps: [...this._checkSteps.values()],
    };
    this.sendStatus(fields);
  }

  /** 设置启动检查面板的标题（不发送）。 */
  setStartupCheckTitle(title: string): void {
    this._checkTitle = title;
  }

  /** 向服务端发送 display_status 更新。 */
  sendDisplayStatus(text: string): void {
    this.sendStatus({ display_status: text });
  }

  /** 向服务端发送单个状态字段。 */
  sendStatusField(key: string, value: unknown): void {
    this.sendStatus({ [key]: value });
  }

  /** 将插件自有的配置键持久化到服务端。 */
  sendSetConfig(key: string, value: unknown): void {
    this._scheduleSend(Codec.setConfig(key, value));
  }

  // -- 公开异常查询 ------------------------------------------------------

  /** 返回后台捕获的一个异常，无则返回 null（应循环获取直到 null）。 */
  getException(): Error | null {
    return this._errorQueue.shift() ?? null;
  }

  // -- 内部：连接与接收循环 --------------------------------------------------

  private async _connectAndLoop(): Promise<void> {
    try {
      // ---- 解析 manifest ----
      const manifestPath = join(this._manifestDir, "manifest.json");
      const raw = readFileSync(manifestPath, "utf-8");
      this._manifest = JSON.parse(raw) as Record<string, unknown>;
      this._pluginId = String(this._manifest.id ?? "");

      // ---- 环境变量 ----
      const { host, port, token } = envConfig();
      if (!token) {
        throw new Error("DGHUB_TOKEN environment variable is not set");
      }
      this._token = token;
      const url = `ws://${host}:${port}/ws/plugin?token=${encodeURIComponent(token)}`;

      // ---- 带重试的连接 ----
      for (let attempt = 0; attempt <= this._maxRetries; attempt++) {
        if (this._stopped) {
          throw new Error("Agent stopped before connection established");
        }
        try {
          this._ws = await this._openSocket(url);
          break;
        } catch (err) {
          if (attempt < this._maxRetries) {
            const delay = Math.min(2 ** attempt, 30);
            await this._sleepSliced(delay);
          } else {
            throw err;
          }
        }
      }

      // ---- 握手 ----
      const ws = this._ws!;
      ws.send(Codec.hello(this._token, this._manifest));
      const ackRaw = await this._recvOnce(ws);
      const ack = JSON.parse(ackRaw) as Record<string, unknown>;
      if (!ack.accepted) {
        throw new Error(`hello rejected: ${ack.reason ?? "unknown"}`);
      }

      this._connected = true;
      this._queue.push({
        op: OpCode.HELLO_ACK,
        data: {
          accepted: ack.accepted,
          reason: ack.reason,
          sdk_version: ack.sdk_version,
        },
      });
      this._readyResolve?.();

      // ---- 接收循环 ----
      ws.on("message", (data) => {
        if (this._stopped) {
          return;
        }
        const msg = Codec.parse(data.toString());
        if (msg.op === OpCode.PING) {
          try {
            ws.send(JSON.stringify({ op: "pong", t: msg.t }));
          } catch {
            // 连接可能已关闭
          }
          this._queue.push(msg);
        } else {
          this._queue.push(msg);
          if (msg.op === OpCode.STOP) {
            this.stop();
          }
        }
      });
      ws.on("close", () => {
        this._connected = false;
        this._readyReject?.(new Error("Agent stopped before handshake completed"));
      });
      ws.on("error", (err) => {
        this._errorQueue.push(err instanceof Error ? err : new Error(String(err)));
      });

      // 连接就绪后冲刷缓冲的发送任务
      this._flushSendQueue();
    } catch (err) {
      const exc = err instanceof Error ? err : new Error(String(err));
      if (!this._connected) {
        this._startupException = exc;
      }
      this._errorQueue.push(exc);
      this._readyReject?.(exc);
    } finally {
      this._connected = false;
    }
  }

  /** 建立 WebSocket 连接（Promise 化）。 */
  private _openSocket(url: string): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      const onOpen = (): void => {
        ws.off("error", onError);
        resolve(ws);
      };
      const onError = (err: Error): void => {
        ws.off("open", onOpen);
        reject(err);
      };
      ws.once("open", onOpen);
      ws.once("error", onError);
    });
  }

  /** 等待单条消息（用于握手 ack）。 */
  private _recvOnce(ws: WebSocket): Promise<string> {
    return new Promise((resolve, reject) => {
      const onMessage = (data: WebSocket.RawData): void => {
        ws.off("message", onMessage);
        ws.off("error", onError);
        resolve(data.toString());
      };
      const onError = (err: Error): void => {
        ws.off("message", onMessage);
        reject(err);
      };
      ws.once("message", onMessage);
      ws.once("error", onError);
    });
  }

  // -- 内部：发送 ----------------------------------------------------------

  /** 调度发送：未连接时入队缓冲，连接后立即发送。 */
  private _scheduleSend(raw: string): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      try {
        this._ws.send(raw);
        return;
      } catch (err) {
        this._errorQueue.push(err instanceof Error ? err : new Error(String(err)));
      }
    }
    // 握手未完成或发送失败：入队等待冲刷
    if (!this._connected) {
      this._sendQueue.push({ raw, resolve: () => {}, reject: () => {} });
    }
  }

  /** 握手成功后冲刷缓冲队列。 */
  private _flushSendQueue(): void {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
      return;
    }
    for (const task of this._sendQueue) {
      try {
        this._ws.send(task.raw);
        task.resolve();
      } catch (err) {
        task.reject(err instanceof Error ? err : new Error(String(err)));
      }
    }
    this._sendQueue = [];
  }

  // -- 内部：分发 ----------------------------------------------------------

  private _invoke(msg: CodecMessage): void {
    switch (msg.op) {
      case OpCode.HELLO_ACK:
        if (this.onReady && msg.data) {
          this.onReady(msg.data);
        }
        break;
      case OpCode.CONFIG:
        if (this.onConfig) {
          this.onConfig(msg.data ?? {});
        }
        break;
      case OpCode.CONFIG_CHANGED:
        if (this.onConfigChanged) {
          this.onConfigChanged(msg.key ?? "", msg.value ?? "");
        }
        break;
      case OpCode.DEVICE_INFO:
        if (this.onDeviceInfo && msg.connected !== undefined
          && msg.deviceType !== undefined
          && msg.maxStrengthA !== undefined
          && msg.maxStrengthB !== undefined) {
          this.onDeviceInfo(
            msg.connected, msg.deviceType,
            msg.maxStrengthA, msg.maxStrengthB,
          );
        }
        break;
      case OpCode.STOP:
        if (this.onStop) {
          this.onStop(msg.reason ?? "");
        }
        break;
      case OpCode.PING:
        if (this.onPing) {
          this.onPing(msg.t ?? 0);
        }
        break;
      default:
        break;
    }
  }

  private _sleep(seconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
  }

  /** 分片等待：stop() 可在 0.5s 内中断退避重试（同 Python 语义）。 */
  private async _sleepSliced(seconds: number): Promise<void> {
    const slices = Math.floor(seconds / 0.5);
    for (let i = 0; i < slices; i++) {
      if (this._stopped) {
        throw new Error("Agent stopped before connection established");
      }
      await this._sleep(0.5);
    }
  }
}

// 模块级便利函数（对齐 Python `dghub_sdk.agent.plugin_root`）
export { pluginRoot } from "./paths.js";
