/**
 * 俄罗斯方块游戏核心逻辑 —— 与 Python 版 `demo/tetris-py/src/main.py`
 * 的 Piece / Tetris 类一一对应（7-bag、碰撞、消行计分、旋转 Wall Kick）。
 */

export const COLS = 10;
export const ROWS = 20;

// 七种方块颜色（RGB）—— ANSI 渲染用索引映射
export const COLORS: Array<[number, number, number]> = [
  [0, 240, 240],   // I  青色
  [240, 240, 0],   // O  黄色
  [160, 0, 240],   // T  紫色
  [0, 240, 0],     // S  绿色
  [240, 0, 0],     // Z  红色
  [0, 0, 240],     // J  蓝色
  [240, 160, 0],   // L  橙色
];

// 七种标准方块的矩阵掩码（7 种 Tetromino）
export const SHAPES: number[][][] = [
  [[0, 0, 0, 0],   // I
   [1, 1, 1, 1],
   [0, 0, 0, 0],
   [0, 0, 0, 0]],
  [[1, 1],          // O
   [1, 1]],
  [[0, 1, 0],       // T
   [1, 1, 1],
   [0, 0, 0]],
  [[0, 1, 1],       // S
   [1, 1, 0],
   [0, 0, 0]],
  [[1, 1, 0],       // Z
   [0, 1, 1],
   [0, 0, 0]],
  [[1, 0, 0],       // J
   [1, 1, 1],
   [0, 0, 0]],
  [[0, 0, 1],       // L
   [1, 1, 1],
   [0, 0, 0]],
];

/** 棋盘格颜色（RGB）或 null = 空格。 */
export type Cell = [number, number, number] | null;

/** 当前活动的方块（Tetromino）。 */
export class Piece {
  shape: number[][];
  color: [number, number, number];
  x: number;
  y: number;

  constructor(shapeIdx: number) {
    this.shape = SHAPES[shapeIdx].map((row) => [...row]);
    this.color = COLORS[shapeIdx];
    this.x = Math.floor(COLS / 2) - Math.floor(this.shape[0].length / 2);
    this.y = 0;
  }

  /** 返回顺时针旋转 90 度后的形状矩阵（不修改自身）。 */
  rotated(): number[][] {
    const rows = this.shape.length;
    const cols = this.shape[0].length;
    const result: number[][] = [];
    for (let i = 0; i < cols; i++) {
      const row: number[] = [];
      for (let j = 0; j < rows; j++) {
        row.push(this.shape[rows - 1 - j][i]);
      }
      result.push(row);
    }
    return result;
  }
}

/** 俄罗斯方块游戏（对齐 Python 版全部核心逻辑）。 */
export class Tetris {
  board: Cell[][];
  score: number;
  gameOver: boolean;
  bag: number[];
  piece: Piece;
  dropInterval = 0.5; // 秒
  dropTimer = 0.0;

  constructor() {
    this.board = Array.from({ length: ROWS }, () => Array<Cell>(COLS).fill(null));
    this.score = 0;
    this.gameOver = false;
    this.bag = [];
    this.piece = this._spawn();
  }

  private _refillBag(): void {
    const bag = SHAPES.map((_, i) => i);
    // Fisher–Yates shuffle
    for (let i = bag.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [bag[i], bag[j]] = [bag[j], bag[i]];
    }
    this.bag.push(...bag);
  }

  private _spawn(): Piece {
    if (this.bag.length < 1) {
      this._refillBag();
    }
    return new Piece(this.bag.pop()!);
  }

  private _valid(piece: Piece, dx = 0, dy = 0, shape?: number[][]): boolean {
    const s = shape ?? piece.shape;
    for (let r = 0; r < s.length; r++) {
      for (let c = 0; c < s[r].length; c++) {
        if (!s[r][c]) {
          continue;
        }
        const nx = piece.x + c + dx;
        const ny = piece.y + r + dy;
        if (nx < 0 || nx >= COLS || ny >= ROWS) {
          return false;
        }
        if (ny >= 0 && this.board[ny][nx] !== null) {
          return false;
        }
      }
    }
    return true;
  }

  private _lock(): void {
    let aboveBoard = false;
    for (let r = 0; r < this.piece.shape.length; r++) {
      for (let c = 0; c < this.piece.shape[r].length; c++) {
        if (this.piece.shape[r][c]) {
          const y = this.piece.y + r;
          const x = this.piece.x + c;
          if (y < 0) {
            aboveBoard = true;
          } else {
            this.board[y][x] = this.piece.color;
          }
        }
      }
    }
    if (aboveBoard) {
      this._onGameOver();
      return;
    }
    this._clearLines();
    this.piece = this._spawn();
    if (!this._valid(this.piece)) {
      this._onGameOver();
    }
  }

  private _clearLines(): void {
    let cleared = 0;
    const newBoard: Cell[][] = [];
    for (const row of this.board) {
      if (row.every((c) => c !== null)) {
        cleared += 1;
      } else {
        newBoard.push(row);
      }
    }
    for (let i = 0; i < cleared; i++) {
      newBoard.unshift(Array<Cell>(COLS).fill(null));
    }
    this.board = newBoard;
    this.score += [0, 100, 300, 500, 800][cleared];
  }

  private _onGameOver(): void {
    this.gameOver = true;
    console.log(`[Tetris] Game Over! Score: ${this.score}`);
  }

  // ── 输入 ──

  /** 尝试移动当前方块；返回是否移动成功。 */
  move(dx: number, dy: number): boolean {
    if (this.gameOver) {
      return false;
    }
    if (this._valid(this.piece, dx, dy)) {
      this.piece.x += dx;
      this.piece.y += dy;
      return true;
    }
    return false;
  }

  /** 尝试顺时针旋转，含 Wall Kick 补偿（左右各试一次）。 */
  rotate(): void {
    if (this.gameOver) {
      return;
    }
    const r = this.piece.rotated();
    if (this._valid(this.piece, 0, 0, r)) {
      this.piece.shape = r;
    } else if (this._valid(this.piece, 1, 0, r)) {
      this.piece.x += 1;
      this.piece.shape = r;
    } else if (this._valid(this.piece, -1, 0, r)) {
      this.piece.x -= 1;
      this.piece.shape = r;
    }
  }

  /** 硬降：将方块直接落到底部并固定。 */
  hardDrop(): void {
    if (this.gameOver) {
      return;
    }
    while (this._valid(this.piece, 0, 1)) {
      this.piece.y += 1;
    }
    this._lock();
  }

  /** 重置游戏状态。 */
  restart(): void {
    this.board = Array.from({ length: ROWS }, () => Array<Cell>(COLS).fill(null));
    this.score = 0;
    this.gameOver = false;
    this.bag = [];
    this.piece = this._spawn();
    this.dropTimer = 0.0;
  }

  // ── 更新 ──

  /** 按帧更新下落计时器，触发自动下落。 */
  update(dt: number): void {
    if (this.gameOver) {
      return;
    }
    this.dropTimer += dt;
    if (this.dropTimer >= this.dropInterval) {
      this.dropTimer = 0.0;
      if (!this.move(0, 1)) {
        this._lock();
      }
    }
  }
}
