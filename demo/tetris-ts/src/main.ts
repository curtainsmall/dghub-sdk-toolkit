/**
 * 俄罗斯方块（TypeScript/Node 终端版）主程序。
 * 与 Python 版 `demo/tetris-py/src/main.py` 功能对齐：
 * Agent 生命周期、activated / delta_pct 配置回调、Game Over 惩罚触发、
 * 暂停覆盖层、DAS 连发与软降加速。
 */

import { Agent, Action, LogLevel } from "dghub-sdk";
import { Tetris } from "./game.js";
import { render, pauseOverlay } from "./render.js";

let activated = false;
let deltaPct = 20;

function onConfigChanged(key: string, value: boolean | number | string): void {
  if (key === "activated") {
    activated = Boolean(value);
  } else if (key === "delta_pct") {
    deltaPct = Number(value);
  }
}

function onConfig(configs: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(configs)) {
    onConfigChanged(key, value as boolean | number | string);
  }
}

/** 终端原始模式：逐键读取（对齐 pygame 事件循环）；非 TTY（SEA/管道）跳过。 */
function setupInput(onKey: (key: string) => void): void {
  const stdin = process.stdin;
  if (!stdin.isTTY) {
    return; // 无交互终端（如 DGHub 管道启动）：不注册键盘
  }
  stdin.setRawMode(true);
  stdin.resume();
  stdin.setEncoding("utf8");
  stdin.on("data", (chunk: string) => {
    // 转义序列：\x1b[D 左 / \x1b[C 右 / \x1b[A 上 / \x1b[B 下
    if (chunk === "\u001b[D") onKey("left");
    else if (chunk === "\u001b[C") onKey("right");
    else if (chunk === "\u001b[A") onKey("up");
    else if (chunk === "\u001b[B") onKey("down");
    else if (chunk === " ") onKey("space");
    else if (chunk.toLowerCase() === "r") onKey("r");
    else if (chunk === "\u0003") onKey("quit"); // Ctrl+C
  });
}

function restoreInput(): void {
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
    process.stdin.pause();
  }
}

function main(): void {
  const agent = new Agent({ onConfig, onConfigChanged });
  agent.start();

  // 隐藏光标 + 清屏
  process.stdout.write("\x1b[?25l\x1b[2J\x1b[H");

  let running = true;

  const onKey = (key: string): void => {
    switch (key) {
      case "quit":
        running = false;
        break;
      case "r":
        game.restart();
        break;
      case "left":
        game.move(-1, 0);
        dasDir = -1;
        dasTimer = 0.0;
        dasCharged = false;
        break;
      case "right":
        game.move(1, 0);
        dasDir = 1;
        dasTimer = 0.0;
        dasCharged = false;
        break;
      case "down":
        softDrop = true;
        break;
      case "up":
        game.rotate();
        break;
      case "space":
        game.hardDrop();
        break;
    }
  };
  setupInput(onKey);

  // 退出清理（Agent 停止 + 终端恢复）
  const shutdown = (): void => {
    restoreInput();
    process.stdout.write("\x1b[?25h\x1b[2J\x1b[H");
    agent.stop();
    process.exit(0);
  };
  process.on("exit", shutdown);

  const game = new Tetris();

  // DAS 连发状态（对齐 Python 版）
  const dasDelay = 0.15;
  const dasRepeat = 0.05;
  let dasDir = 0;
  let dasTimer = 0.0;
  let dasCharged = false;
  let softDrop = false;
  let punished = true;
  let lastFrame = Date.now();

  // 等待握手（不阻塞输入，连接失败由 getException 查询）
  agent.waitReady(10)
    .then(() => agent.sendLog(LogLevel.INFO, "tetris-ts started"))
    .catch(() => {
      // 连接失败时仍允许本地游玩（打印错误不退出）
      agent.getException();
    });

  const FPS = 30;
  const frameMs = 1000 / FPS;

  const loop = (): void => {
    if (!running) {
      shutdown();
      return;
    }
    const now = Date.now();
    const dt = Math.min((now - lastFrame) / 1000, 0.1);
    lastFrame = now;

    agent.poll();
    while (agent.getException() !== null) {
      // 排空后台异常（连接失败等）
    }

    // 暂停：插件开关关闭时，仅允许关闭与键盘复位
    if (!activated) {
      // 丢弃瞬时输入，避免恢复时卡住移动
      dasDir = 0;
      dasTimer = 0.0;
      dasCharged = false;
      softDrop = false;
      process.stdout.write("\x1b[2J\x1b[H" + render(game) + "\n" + pauseOverlay() + "\n");
      setTimeout(loop, frameMs);
      return;
    }

    // Game Over 惩罚触发（每次新游戏重新武装）
    if (game.gameOver) {
      if (!punished) {
        agent.sendTrigger({ action: Action.STRENGTH, deltaPct, durationS: 5 });
        punished = true;
      }
    } else {
      punished = false;
    }

    // DAS 自动连发
    if (dasDir !== 0) {
      dasTimer += dt;
      if (!dasCharged && dasTimer >= dasDelay) {
        dasCharged = true;
        dasTimer = 0.0;
      } else if (dasCharged && dasTimer >= dasRepeat) {
        game.move(dasDir, 0);
        dasTimer = 0.0;
      }
    }

    // 软降加速
    game.dropInterval = softDrop && !game.gameOver ? 0.05 : 0.5;

    game.update(dt);
    process.stdout.write("\x1b[2J\x1b[H" + render(game) + "\n");
    setTimeout(loop, frameMs);
  };

  loop();
}

main();
