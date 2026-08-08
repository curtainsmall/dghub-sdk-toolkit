/**
 * codec 编解码测试 —— 对齐 Python SDK `tests/test_codec.py`。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { Action, Channel, DeviceType, LogLevel, OpCode, StrengthMode } from "../dist/enums.js";
import { Codec } from "../dist/codec.js";

const payload = (raw: string): Record<string, unknown> => JSON.parse(raw);

test("parse 接受 v4 device_info", () => {
  const msg = Codec.parse(JSON.stringify({
    op: "device_info",
    connected: true,
    device_type: "v4",
    max_strength_a: 100,
    max_strength_b: 100,
  }));
  assert.equal(msg.op, OpCode.DEVICE_INFO);
  assert.equal(msg.deviceType, DeviceType.V4);
  assert.equal(msg.maxStrengthA, 100);
});

test("trigger 序列化元数据与 target 字段", () => {
  const msg = payload(Codec.trigger({
    action: Action.STRENGTH,
    deltaPct: 25,
    label: "惩罚",
    username: "player",
    name: "BOSS 守卫",
    cause: "强度值下降",
    pulseName: "脉冲",
    targetId: "target-1",
  }));
  assert.equal(msg.action, "strength");
  assert.equal(msg.delta_pct, 25);
  assert.equal(msg.name, "BOSS 守卫");
  assert.equal(msg.cause, "强度值下降");
  assert.equal(msg.pulse_name, "脉冲");
  assert.equal(msg.target_id, "target-1");
});

test("event 序列化元数据与 target 字段", () => {
  const msg = payload(Codec.event("惩罚", "BOSS 守卫", {
    username: "player",
    strengthPct: 40,
    cause: "强度值下降",
    pulseName: "脉冲",
    fromPct: 20,
    toPct: 40,
    deltaPct: 20,
    targetId: "target-1",
  }));
  assert.equal(msg.cause, "强度值下降");
  assert.equal(msg.pulse_name, "脉冲");
  assert.equal(msg.from_pct, 20);
  assert.equal(msg.to_pct, 40);
  assert.equal(msg.delta_pct, 20);
  assert.equal(msg.target_id, "target-1");
});

test("trigger 含波形时必须提供 preset", () => {
  assert.throws(() => Codec.trigger({ action: Action.BOTH }), /preset is required/);
  assert.throws(() => Codec.trigger({ action: Action.WAVEFORM }), /preset is required/);
});

test("setStrength 校验 0-100", () => {
  assert.throws(() => Codec.setStrength(Channel.A, -1), /pct must be 0-100/);
  assert.throws(() => Codec.setStrength(Channel.A, 101), /pct must be 0-100/);
});

test("adjustStrength 校验 -100 到 100", () => {
  assert.throws(() => Codec.adjustStrength(Channel.B, -101), /-100 to 100/);
  assert.throws(() => Codec.adjustStrength(Channel.B, 101), /-100 to 100/);
});

test("pulse 必须提供 preset", () => {
  assert.throws(() => Codec.pulse(""), /preset is required/);
});

test("event 必填 label/name", () => {
  assert.throws(() => Codec.event("", "n"), /label is required/);
  assert.throws(() => Codec.event("l", ""), /name is required/);
});

test("hello 必须提供 token", () => {
  assert.throws(() => Codec.hello("", {}), /token is required/);
});

test("parse 服务端消息类型", () => {
  const cfg = Codec.parse('{"op":"config","data":{"a":1}}');
  assert.equal(cfg.op, OpCode.CONFIG);
  assert.deepEqual(cfg.data, { a: 1 });

  const changed = Codec.parse('{"op":"config_changed","key":"k","value":5}');
  assert.equal(changed.op, OpCode.CONFIG_CHANGED);
  assert.equal(changed.key, "k");
  assert.equal(changed.value, 5);

  const ping = Codec.parse('{"op":"ping","t":123.5}');
  assert.equal(ping.op, OpCode.PING);
  assert.equal(ping.t, 123.5);

  const stop = Codec.parse('{"op":"stop","reason":"bye"}');
  assert.equal(stop.op, OpCode.STOP);
  assert.equal(stop.reason, "bye");

  const ack = Codec.parse('{"op":"hello_ack","accepted":true}');
  assert.equal(ack.op, OpCode.HELLO_ACK);
  assert.deepEqual(ack.data, { accepted: true });
});

test("parse 未知 op 抛错", () => {
  assert.throws(() => Codec.parse('{"op":"nope"}'), /Unknown op: nope/);
});

test("serialize 往返一致", () => {
  const msg = Codec.parse(
    '{"op":"device_info","connected":true,"device_type":"v3","max_strength_a":90,"max_strength_b":80}');
  const raw = Codec.serialize(msg);
  const back = Codec.parse(raw);
  assert.equal(back.op, OpCode.DEVICE_INFO);
  assert.equal(back.deviceType, DeviceType.V3);
  assert.equal(back.maxStrengthA, 90);
  assert.equal(back.maxStrengthB, 80);
});

test("status/log/setConfig 结构", () => {
  const st = payload(Codec.status({ display_status: "ok" }));
  assert.equal(st.op, "status");
  assert.deepEqual(st.fields, { display_status: "ok" });

  const lg = payload(Codec.log(LogLevel.WARNING, "warn msg"));
  assert.equal(lg.op, "log");
  assert.equal(lg.level, "warning");
  assert.equal(lg.message, "warn msg");

  const sc = payload(Codec.setConfig("k", 42));
  assert.equal(sc.op, "set_config");
  assert.equal(sc.key, "k");
  assert.equal(sc.value, 42);
});

test("trigger 默认值", () => {
  const msg = payload(Codec.trigger({ preset: "wave" }));
  assert.equal(msg.action, Action.BOTH);
  assert.equal(msg.delta_pct, 0);
  assert.equal(msg.strength_mode, StrengthMode.ROLLBACK);
  assert.equal(msg.duration_s, 1.0);
  assert.equal(msg.channel, Channel.BOTH);
});
