"""
俄罗斯方块 —— 纯独立游戏，仅依赖 pygame-ce。

Tetris — pure standalone game, no external dependencies beyond pygame-ce.
"""
import random
import pygame
import dghub_sdk
from typing import Any

# ── 常量 ────────────────────────────────────────────────────────────────

COLS = 10  # 棋盘列数
ROWS = 20  # 棋盘行数
CELL = 30  # 每格像素
SIDE = 200  # 侧边栏宽度
WIDTH = COLS * CELL + SIDE  # 窗口宽
HEIGHT = ROWS * CELL  # 窗口高
FPS = 60  # 帧率

# 七种方块颜色（RGB）
COLORS = [
    (0, 240, 240),   # I  青色
    (240, 240, 0),   # O  黄色
    (160, 0, 240),   # T  紫色
    (0, 240, 0),     # S  绿色
    (240, 0, 0),     # Z  红色
    (0, 0, 240),     # J  蓝色
    (240, 160, 0),   # L  橙色
]

# 七种标准方块的矩阵掩码（7 种 Tetromino）
SHAPES = [
    [[0, 0, 0, 0],   # I
     [1, 1, 1, 1],
     [0, 0, 0, 0],
     [0, 0, 0, 0]],
    [[1, 1],          # O
     [1, 1]],
    [[0, 1, 0],       # T
     [1, 1, 1],
     [0, 0, 0]],
    [[0, 1, 1],       # S
     [1, 1, 0],
     [0, 0, 0]],
    [[1, 1, 0],       # Z
     [0, 1, 1],
     [0, 0, 0]],
    [[1, 0, 0],       # J
     [1, 1, 1],
     [0, 0, 0]],
    [[0, 0, 1],       # L
     [1, 1, 1],
     [0, 0, 0]],
]


# ── Piece 方块 ──────────────────────────────────────────────────────────

class Piece:
    """表示一个当前活动的方块（Tetromino）。"""

    def __init__(self, shape_idx: int):
        """用形状索引初始化方块。

        Args:
            shape_idx: SHAPES 列表中的索引（0=I, 1=O, 2=T, ...）
        """
        self.shape = SHAPES[shape_idx]
        self.color = COLORS[shape_idx]
        self.x = COLS // 2 - len(self.shape[0]) // 2
        self.y = 0

    def rotated(self) -> list[list[int]]:
        """返回顺时针旋转 90 度后的形状矩阵（不修改自身）。

        Returns:
            新的形状矩阵
        """
        rows, cols = len(self.shape), len(self.shape[0])
        return [[self.shape[rows - 1 - j][i] for j in range(rows)] for i in range(cols)]


# ── Game 游戏 ───────────────────────────────────────────────────────────

class Tetris:
    """俄罗斯方块游戏核心逻辑。

    管理棋盘状态、方块生成、碰撞检测、消行计分、下落计时等。
    """

    def __init__(self):
        """初始化游戏：清空棋盘、重置分数、生成第一个方块。"""
        self.board: list[list[tuple[int, int, int] | None]] = [[None] * COLS for _ in range(ROWS)]
        self.score = 0
        self.game_over = False
        self.bag: list[int] = []
        self.piece = self._spawn()
        self.drop_interval = 0.5  # 秒
        self.drop_timer = 0.0

    def _refill_bag(self) -> None:
        """向 7-bag 随机序列补充一组形状索引（Fisher–Yates shuffle）。"""
        bag = list(range(len(SHAPES)))
        random.shuffle(bag)
        self.bag.extend(bag)

    def _spawn(self) -> Piece:
        """从 bag 中取出下一个形状生成新方块。

        Returns:
            新的 Piece 实例
        """
        if len(self.bag) < 1:
            self._refill_bag()
        return Piece(self.bag.pop())

    def _valid(self, piece: Piece, dx: int = 0, dy: int = 0,
               shape: list[list[int]] | None = None) -> bool:
        """检查方块在给定偏移和形状下是否合法（不越界、不碰撞）。

        Args:
            piece: 要检查的方块
            dx: 水平偏移量
            dy: 垂直偏移量
            shape: 可选的替代形状（用于旋转检测），默认用 piece.shape

        Returns:
            True 表示位置合法
        """
        s = shape or piece.shape
        for r, row in enumerate(s):
            for c, v in enumerate(row):
                if not v:
                    continue
                nx = piece.x + c + dx
                ny = piece.y + r + dy
                if nx < 0 or nx >= COLS or ny >= ROWS:
                    return False
                if ny >= 0 and self.board[ny][nx] is not None:
                    return False
        return True

    def _lock(self) -> None:
        """将当前方块固定到棋盘上，然后消行并生成下一个方块。

        如果方块落在棋盘上方则游戏结束。
        """
        above_board = False
        for r, row in enumerate(self.piece.shape):
            for c, v in enumerate(row):
                if v:
                    y = self.piece.y + r
                    x = self.piece.x + c
                    if y < 0:
                        above_board = True
                    else:
                        self.board[y][x] = self.piece.color
        if above_board:
            self._on_game_over()
            return
        self._clear_lines()
        self.piece = self._spawn()
        if not self._valid(self.piece):
            self._on_game_over()

    def _clear_lines(self) -> None:
        """检测并消除满行，更新分数。

        消除 1/2/3/4 行分别得 100/300/500/800 分。
        """
        cleared = 0
        new_board: list[list[tuple[int, int, int] | None]] = []
        for row in self.board:
            if all(c is not None for c in row):
                cleared += 1
            else:
                new_board.append(row)
        for _ in range(cleared):
            new_board.insert(0, [None] * COLS)
        self.board = new_board
        self.score += [0, 100, 300, 500, 800][cleared]

    def _on_game_over(self) -> None:
        """处理游戏结束：设置标志并打印分数。"""
        self.game_over = True
        print(f"[Tetris] Game Over! Score: {self.score}")

    # ── 输入 ──

    def move(self, dx: int, dy: int) -> bool:
        """尝试移动当前方块。

        Args:
            dx: 水平偏移（负=左，正=右）
            dy: 垂直偏移（正=下）

        Returns:
            是否移动成功
        """
        if self.game_over:
            return False
        if self._valid(self.piece, dx, dy):
            self.piece.x += dx
            self.piece.y += dy
            return True
        return False

    def rotate(self) -> None:
        """尝试顺时针旋转当前方块，含 Wall Kick 补偿（左右各试一次）。"""
        if self.game_over:
            return
        r = self.piece.rotated()
        if self._valid(self.piece, shape=r):
            self.piece.shape = r
        elif self._valid(self.piece, dx=1, shape=r):
            self.piece.x += 1
            self.piece.shape = r
        elif self._valid(self.piece, dx=-1, shape=r):
            self.piece.x -= 1
            self.piece.shape = r

    def hard_drop(self) -> None:
        """硬降：将方块直接落到底部并固定。"""
        if self.game_over:
            return
        while self._valid(self.piece, 0, 1):
            self.piece.y += 1
        self._lock()

    def restart(self) -> None:
        """重置游戏状态。"""
        self.board = [[None] * COLS for _ in range(ROWS)]
        self.score = 0
        self.game_over = False
        self.bag = []
        self.piece = self._spawn()
        self.drop_timer = 0.0

    # ── 更新 ──

    def update(self, dt: float) -> None:
        """按帧更新下落计时器，触发自动下落。

        Args:
            dt: 本帧经过的秒数
        """
        if self.game_over:
            return
        self.drop_timer += dt
        if self.drop_timer >= self.drop_interval:
            self.drop_timer = 0.0
            if not self.move(0, 1):
                self._lock()

    # ── 绘制 ──

    def draw(self, surface: pygame.Surface) -> None:
        """绘制完整游戏画面：棋盘、当前方块、侧边栏、Game Over 覆盖层。

        Args:
            surface: 目标 pygame 表面
        """
        surface.fill((18, 18, 24))

        board_rect = pygame.Rect(0, 0, CELL * COLS, CELL * ROWS)
        pygame.draw.rect(surface, (30, 30, 40), board_rect)

        for c in range(COLS + 1):
            pygame.draw.line(surface, (45, 45, 55),
                             (c * CELL, 0), (c * CELL, CELL * ROWS))
        for r in range(ROWS + 1):
            pygame.draw.line(surface, (45, 45, 55),
                             (0, r * CELL), (CELL * COLS, r * CELL))

        for r in range(ROWS):
            for c in range(COLS):
                if self.board[r][c]:
                    self._draw_cell(surface, c, r, self.board[r][c])

        for r, row in enumerate(self.piece.shape):
            for c, v in enumerate(row):
                if v:
                    py = self.piece.y + r
                    if py >= 0:
                        self._draw_cell(surface, self.piece.x + c, py,
                                        self.piece.color)

        # 侧边栏
        sx = CELL * COLS + 20
        font = pygame.font.SysFont("consolas", 22)
        big_font = pygame.font.SysFont("consolas", 32, bold=True)

        title = big_font.render("TETRIS", True, (255, 255, 255))
        surface.blit(title, (sx, 30))

        score_label = font.render(f"Score: {self.score}", True, (200, 200, 200))
        surface.blit(score_label, (sx, 80))

        controls = [
            "← → : Move",
            "↑   : Rotate",
            "↓   : Soft drop",
            "Space: Hard drop",
            "R   : Restart",
        ]
        y = 140
        small_font = pygame.font.SysFont("consolas", 16)
        for line in controls:
            txt = small_font.render(line, True, (140, 140, 160))
            surface.blit(txt, (sx, y))
            y += 24

        if self.game_over:
            # 半透明覆盖层
            overlay = pygame.Surface((CELL * COLS, CELL * ROWS), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            surface.blit(overlay, (0, 0))

            cx = CELL * COLS // 2
            cy = CELL * ROWS // 2

            go_text = big_font.render("GAME OVER", True, (255, 60, 60))
            rect = go_text.get_rect(center=(cx, cy - 15))
            surface.blit(go_text, rect)

            hint = font.render("Press R to restart", True, (200, 200, 200))
            rect2 = hint.get_rect(center=(cx, cy + 20))
            surface.blit(hint, rect2)

        pygame.draw.rect(surface, (80, 80, 100), board_rect, 2)

    def _draw_cell(self, surface: pygame.Surface, x: int, y: int,
                   color: tuple[int, int, int]) -> None:
        """绘制单个方块格子，带高光边缘。

        Args:
            surface: 目标表面
            x: 格子列坐标
            y: 格子行坐标
            color: RGB 颜色元组
        """
        rect = pygame.Rect(x * CELL + 1, y * CELL + 1, CELL - 2, CELL - 2)
        pygame.draw.rect(surface, color, rect, border_radius=4)
        lighter = tuple(min(c + 40, 255) for c in color)
        pygame.draw.line(surface, lighter, (rect.x + 2, rect.y + 2),
                         (rect.right - 3, rect.y + 2))
        pygame.draw.line(surface, lighter, (rect.x + 2, rect.y + 2),
                         (rect.x + 2, rect.bottom - 3))


activated = False
strength = 20
def on_config_changed_callback(key: str, value: Any):
    global activated, strength
    match key:
        case "switch":
            activated = value
        case "strength":
            strength = value

def on_config_callback(configs: dict[str, Any]):
    global activated, strength
    for key, value in configs.items():
        match key:
            case "switch":
                activated = value
            case "strength":
                strength = value

# ── Main ───────────────────────────────────────────────────────────────

def _draw_pause_overlay(surface: pygame.Surface) -> None:
    """在当前画面上叠加半透明「已暂停」提示（插件开关关闭时）。"""
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    surface.blit(overlay, (0, 0))
    font = pygame.font.Font(None, 48)
    text = font.render("PAUSED", True, (240, 240, 240))
    rect = text.get_rect(center=(surface.get_width() // 2,
                                 surface.get_height() // 2))
    surface.blit(text, rect)


def main() -> None:
    """俄罗斯方块主函数。

    初始化 pygame 窗口、创建游戏实例、运行主循环（含 DAS 自动连发处理），
    退出时调用 pygame.quit()。
    """
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Tetris")
    clock = pygame.time.Clock()

    game = Tetris()

    das_delay = 0.15
    das_repeat = 0.05
    das_dir = 0
    das_timer = 0.0
    das_charged = False
    soft_drop = False

    punished = True

    global activated, strength
    with dghub_sdk.Agent() as agent:
        agent.on_config = on_config_callback
        agent.on_config_changed = on_config_changed_callback

        running = True
        while running:
            dt = clock.tick(FPS) / 1000.0

            agent.poll()
            while e := agent.get_exception():
                pass

            # -- paused when the plugin switch is off --
            if not activated:
                # keep the window responsive; only allow closing
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                # drop transient input so movement won't resume stuck
                das_dir = 0
                das_timer = 0.0
                das_charged = False
                soft_drop = False
                game.draw(screen)
                _draw_pause_overlay(screen)
                pygame.display.flip()
                continue

            if game.game_over:
                if not punished:
                    agent.send_trigger(
                        action=dghub_sdk.Action.STRENGTH,
                        delta_pct=strength,
                        duration_s=5
                    )
                    punished = True
            else:
                # re-arm once a new game starts (e.g. after restart)
                punished = False

            for event in pygame.event.get():
                match event.type:
                    case pygame.QUIT:
                        running = False

                    case pygame.KEYDOWN:
                        match event.key:
                            case pygame.K_r:
                                game.restart()
                            case pygame.K_LEFT:
                                game.move(-1, 0)
                                das_dir = -1
                                das_timer = 0.0
                                das_charged = False
                            case pygame.K_RIGHT:
                                game.move(1, 0)
                                das_dir = 1
                                das_timer = 0.0
                                das_charged = False
                            case pygame.K_DOWN:
                                soft_drop = True
                            case pygame.K_UP:
                                game.rotate()
                            case pygame.K_SPACE:
                                game.hard_drop()

                    case pygame.KEYUP:
                        match event.key:
                            case pygame.K_LEFT | pygame.K_RIGHT:
                                das_dir = 0
                            case pygame.K_DOWN:
                                soft_drop = False

            # DAS
            if das_dir != 0:
                das_timer += dt
                if not das_charged and das_timer >= das_delay:
                    das_charged = True
                    das_timer = 0.0
                elif das_charged and das_timer >= das_repeat:
                    game.move(das_dir, 0)
                    das_timer = 0.0

            # soft drop speed
            if soft_drop and not game.game_over:
                game.drop_interval = 0.05
            else:
                game.drop_interval = 0.5

            game.update(dt)
            game.draw(screen)
            pygame.display.flip()

        pygame.quit()


if __name__ == "__main__":
    main()
