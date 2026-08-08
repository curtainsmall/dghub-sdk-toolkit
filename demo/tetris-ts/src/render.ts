/**
 * SDL2 渲染层 —— pygame 绘制逻辑的对应实现（@kmamal/sdl + @napi-rs/canvas）。
 * canvas 2D 绘制（色块/网格/侧边栏文字/遮罩）→ getImageData → window.render 上屏。
 * 视觉对齐 Python 版：圆角色块 + 高光边缘、TETRIS 标题、Score、控制说明、
 * GAME OVER / PAUSED 覆盖层。
 */

import sdl from "@kmamal/sdl";
import { createCanvas } from "@napi-rs/canvas";
import { COLORS, COLS, ROWS, Tetris } from "./game.js";

export const CELL = 30;   // 每格像素（同 Python 版）
export const SIDE = 200;  // 侧边栏宽度
export const WIDTH = COLS * CELL + SIDE;   // 500
export const HEIGHT = ROWS * CELL;          // 600

const BOARD_W = COLS * CELL;  // 棋盘区宽度 300
const SX = BOARD_W + 20;      // 侧边栏文字起点（pygame sx = CELL*COLS+20）

type RGB = [number, number, number];

const rgb = ([r, g, b]: RGB): string => `rgb(${r},${g},${b})`;

/** @kmamal/sdl + canvas 渲染器：canvas 绘制 → 像素上屏。 */
export class SdlRenderer {
  /** SDL 窗口（main.ts 注册键盘/关闭事件）。 */
  window;
  private canvas;
  private ctx;
  private buffer: Buffer;

  constructor() {
    this.window = sdl.video.createWindow({
      title: "Tetris",
      width: WIDTH,
      height: HEIGHT,
    });
    this.canvas = createCanvas(WIDTH, HEIGHT);
    this.ctx = this.canvas.getContext("2d");
    this.buffer = Buffer.alloc(WIDTH * HEIGHT * 4); // rgba32
  }

  /** 绘制一个方块格：圆角 + 高光边缘（对齐 pygame _draw_cell）。 */
  private drawCell(cx: number, cy: number, color: RGB): void {
    const c = this.ctx;
    const x = cx * CELL + 1;
    const y = cy * CELL + 1;
    c.fillStyle = rgb(color);
    c.beginPath();
    c.roundRect(x, y, CELL - 2, CELL - 2, 4);
    c.fill();
    // 高光：上/左边线提亮（pygame 的 lighter 边缘）
    const lighter = rgb([
      Math.min(color[0] + 40, 255),
      Math.min(color[1] + 40, 255),
      Math.min(color[2] + 40, 255),
    ]);
    c.strokeStyle = lighter;
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(x + 2, y + 2);
    c.lineTo(x + CELL - 3, y + 2);
    c.moveTo(x + 2, y + 2);
    c.lineTo(x + 2, y + CELL - 3);
    c.stroke();
  }

  /** 绘制完整画面并上屏；分数/状态进侧边栏与窗口标题。 */
  render(game: Tetris, paused: boolean): void {
    const c = this.ctx;

    // 窗口底色 + 棋盘底
    c.fillStyle = "rgb(18,18,24)";
    c.fillRect(0, 0, WIDTH, HEIGHT);
    c.fillStyle = "rgb(30,30,40)";
    c.fillRect(0, 0, BOARD_W, HEIGHT);

    // 网格线
    c.strokeStyle = "rgb(45,45,55)";
    c.lineWidth = 1;
    for (let i = 0; i <= COLS; i++) {
      c.beginPath();
      c.moveTo(i * CELL, 0);
      c.lineTo(i * CELL, HEIGHT);
      c.stroke();
    }
    for (let i = 0; i <= ROWS; i++) {
      c.beginPath();
      c.moveTo(0, i * CELL);
      c.lineTo(BOARD_W, i * CELL);
      c.stroke();
    }

    // 已落方块
    for (let r = 0; r < ROWS; r++) {
      for (let col = 0; col < COLS; col++) {
        const cell = game.board[r][col];
        if (cell !== null) {
          this.drawCell(col, r, cell);
        }
      }
    }

    // 当前方块
    for (let r = 0; r < game.piece.shape.length; r++) {
      for (let col = 0; col < game.piece.shape[r].length; col++) {
        if (game.piece.shape[r][col]) {
          const py = game.piece.y + r;
          if (py >= 0) {
            this.drawCell(game.piece.x + col, py, game.piece.color);
          }
        }
      }
    }

    // 侧边栏：标题 / 分数 / 控制说明（对齐 pygame 布局与配色）
    c.textBaseline = "top";
    c.font = "bold 32px Consolas";
    c.fillStyle = "white";
    c.fillText("TETRIS", SX, 30);
    c.font = "22px Consolas";
    c.fillStyle = "rgb(200,200,200)";
    c.fillText(`Score: ${game.score}`, SX, 80);
    const controls = [
      "← → : Move",
      "↑   : Rotate",
      "↓   : Soft drop",
      "Space: Hard drop",
      "R   : Restart",
    ];
    c.font = "16px Consolas";
    c.fillStyle = "rgb(140,140,160)";
    controls.forEach((line, i) => c.fillText(line, SX, 140 + i * 24));

    // 棋盘区边框（pygame board_rect 外框）
    c.strokeStyle = "rgb(80,80,100)";
    c.lineWidth = 2;
    c.strokeRect(0, 0, BOARD_W, HEIGHT);

    // 遮罩层（pygame overlay 半透明黑 140/255）
    if (game.gameOver || paused) {
      c.fillStyle = "rgba(0,0,0,0.55)";
      c.fillRect(0, 0, BOARD_W, HEIGHT);
    }
    c.textAlign = "center";
    if (game.gameOver) {
      c.font = "bold 32px Consolas";
      c.fillStyle = "rgb(255,60,60)";
      c.fillText("GAME OVER", BOARD_W / 2, HEIGHT / 2 - 15);
      c.font = "22px Consolas";
      c.fillStyle = "rgb(200,200,200)";
      c.fillText("Press R to restart", BOARD_W / 2, HEIGHT / 2 + 20);
    } else if (paused) {
      c.font = "bold 32px Consolas";
      c.fillStyle = "white";
      c.fillText("PAUSED", BOARD_W / 2, HEIGHT / 2 - 15);
    }
    c.textAlign = "left";

    // 像素上屏
    const img = c.getImageData(0, 0, WIDTH, HEIGHT);
    Buffer.from(img.data.buffer).copy(this.buffer);
    this.window.render(WIDTH, HEIGHT, WIDTH * 4, "rgba32", this.buffer);
    this.window.setTitle(
      `${game.gameOver ? "GAME OVER  " : paused ? "PAUSED  " : ""}` +
      `Tetris - Score: ${game.score}`);
  }

  destroy(): void {
    this.window.destroy();
  }
}

/** 颜色常量导出（与 Python COLORS 对齐）。 */
export { COLORS };
