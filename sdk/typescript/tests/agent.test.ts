/**
 * Agent 基础测试 —— 构造/选项/属性（不连真实 DGHub）。
 * 生命周期与网络行为需真实服务端，见 Python `tests/test_agent_lifecycle.py`。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { Agent } from "../dist/agent.js";
import { LogLevel } from "../dist/enums.js";

test("Agent 构造传递回调与选项", () => {
  let readyData: Record<string, unknown> | undefined;
  const agent = new Agent({
    maxRetries: 3,
    sendTimeout: 5,
    onReady: (data) => { readyData = data; },
    onConfig: () => {},
    onConfigChanged: () => {},
    onDeviceInfo: () => {},
    onStop: () => {},
    onPing: () => {},
  });
  assert.equal(typeof agent.onReady, "function");
  assert.equal(typeof agent.onStop, "function");
  assert.equal(agent.connected, false);
  assert.equal(agent.pluginId, "");
  // 未 start 时 waitReady 拒绝
  assert.rejects(() => agent.waitReady(), /has not been started/);
});

test("Agent 发送方法在未连接时不抛错（排队/静默）", () => {
  const agent = new Agent();
  // 未连接时发送：SDK 缓冲（不崩溃）
  agent.sendLog(LogLevel.INFO, "test");
  agent.sendTrigger({ preset: "wave" });
  assert.equal(agent.connected, false);
});

test("Agent getException 无异常返回 null", () => {
  const agent = new Agent();
  assert.equal(agent.getException(), null);
});
