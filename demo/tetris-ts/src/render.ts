/**
 * ANSI 终端渲染 —— pygame 绘制逻辑的终端对应物。
 * 棋盘格子用双字符宽色块（背景色 + 空格）保持比例，侧边栏显示分数与操作说明。
 */

import { COLORS, COLS, ROWS, Tetris } from "./game.js";

/** RGB → ANSI 256 色近似索引（216 色立方）。 */
function ansi256(rgb: [number, number, number]): number {
  const r = Math.round((rgb[0] / 255) * 5);
  const g = Math.round((rgb[1] / 255) * 5);
  const b = Math.round((rgb[2] / 255) * 5);
  return 16 + 36 * r + 6 * g + b;
}

/** 用背景色渲染一个双字符宽的空格色块。 */
function block(rgb: [number, number, number]): string {
  return `\x1b[48;5;${ansi256(rgb)}m  \x1b[0m`;
}

/** 空格的暗底色。 */
const EMPTY = "\x1b[48;5;236m  \x1b[0m";

/** 渲染完整游戏画面（棋盘 + 当前方块 + 侧边栏 + Game Over 覆盖）。 */
export function render(game: Tetris): string {
  const lines: string[] = [];
  // 先构建棋盘行（含当前方块）
  const rows: string[][] = [];
  for (let r = 0; r < ROWS; r++) {
    const row: string[] = [];
    for (let c = 0; c < COLS; c++) {
      const cell = game.board[r][c];
      row.push(cell !== null ? block(cell) : EMPTY);
    }
    rows.push(row);
  }
  // 覆盖当前方块
  for (let r = 0; r < game.piece.shape.length; r++) {
    for (let c = 0; c < game.piece.shape[r].length; c++) {
      if (game.piece.shape[r][c]) {
        const py = game.piece.y + r;
        if (py >= 0 && py < ROWS) {
          rows[py][game.piece.x + c] = block(game.piece.color);
        }
      }
    }
  }

  const boardWidth = COLS * 2;
  const title = "TETRIS";
  const scoreText = `Score: ${game.score}`;
  const controls = [
    "← → : Move",
    "↑   : Rotate",
    "↓   : Soft drop",
    "Space: Hard drop",
    "R   : Restart",
  ];
  const side = [
    `\x1b[1m${title}\x1b[0m`,
    "",
    scoreText,
    "",
    ...controls,
  ];

  for (let r = 0; r < ROWS; r++) {
    const boardPart = rows[r].join("");
    const sidePart = side[r] ?? "";
    lines.push(boardPart + "  " + sidePart);
  }

  // 底部边界
  lines.push("\x1b[47m" + " ".repeat(boardWidth) + "\x1b[0m");

  if (game.gameOver) {
    lines.push("");
    lines.push("\x1b[1;31mGAME OVER\x1b[0m  Press R to restart");
  }
  return lines.join("\n");
}

/** 渲染暂停覆盖（插件开关关闭时，保留窗口可交互性）。 */
export function pauseOverlay(): string {
  return "\x1b[1;37m==== PAUSED ====\x1b[0m";
}

/** 保留颜色常量导出（与 Python COLORS 对齐）。 */
export { COLORS };
