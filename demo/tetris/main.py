import random

import pygame

# ── constants ──────────────────────────────────────────────────────────

COLS = 10
ROWS = 20
CELL = 30
SIDE = 200
WIDTH = COLS * CELL + SIDE
HEIGHT = ROWS * CELL
FPS = 60

# piece colors (RGB)
COLORS = [
    (0, 240, 240),   # I  cyan
    (240, 240, 0),   # O  yellow
    (160, 0, 240),   # T  purple
    (0, 240, 0),     # S  green
    (240, 0, 0),     # Z  red
    (0, 0, 240),     # J  blue
    (240, 160, 0),   # L  orange
]

# 7 standard tetrominoes as matrix bitmasks
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


# ── Piece ──────────────────────────────────────────────────────────────

class Piece:
    def __init__(self, shape_idx: int):
        self.shape = [row[:] for row in SHAPES[shape_idx]]
        self.color = COLORS[shape_idx]
        self.x = COLS // 2 - len(self.shape[0]) // 2
        self.y = 0

    def rotated(self) -> list[list[int]]:
        rows, cols = len(self.shape), len(self.shape[0])
        return [[self.shape[rows - 1 - j][i] for j in range(rows)] for i in range(cols)]


# ── Game ───────────────────────────────────────────────────────────────

class Tetris:
    def __init__(self):
        self.board: list[list[tuple[int, int, int] | None]] = [[None] * COLS for _ in range(ROWS)]
        self.score = 0
        self.game_over = False
        self.bag: list[int] = []
        self.piece = self._spawn()
        self.drop_interval = 0.5
        self.drop_timer = 0.0

    def _refill_bag(self) -> None:
        bag = list(range(len(SHAPES)))
        random.shuffle(bag)
        self.bag.extend(bag)

    def _spawn(self) -> Piece:
        if len(self.bag) < 1:
            self._refill_bag()
        return Piece(self.bag.pop())

    def _valid(self, piece: Piece, dx: int = 0, dy: int = 0,
               shape: list[list[int]] | None = None) -> bool:
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
        self.game_over = True
        print(f"[Tetris] Game Over! Score: {self.score}")

    # ── input ──

    def move(self, dx: int, dy: int) -> bool:
        if self.game_over:
            return False
        if self._valid(self.piece, dx, dy):
            self.piece.x += dx
            self.piece.y += dy
            return True
        return False

    def rotate(self) -> None:
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
        if self.game_over:
            return
        while self._valid(self.piece, 0, 1):
            self.piece.y += 1
        self._lock()

    def restart(self) -> None:
        self.board = [[None] * COLS for _ in range(ROWS)]
        self.score = 0
        self.game_over = False
        self.bag = []
        self.piece = self._spawn()
        self.drop_timer = 0.0

    # ── update ──

    def update(self, dt: float) -> None:
        if self.game_over:
            return
        self.drop_timer += dt
        if self.drop_timer >= self.drop_interval:
            self.drop_timer = 0.0
            if not self.move(0, 1):
                self._lock()

    # ── draw ──

    def draw(self, surface: pygame.Surface) -> None:
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

        # sidebar
        sx = CELL * COLS + 20
        font = pygame.font.SysFont("consolas", 22)
        big_font = pygame.font.SysFont("consolas", 32, bold=True)

        title = big_font.render("TETRIS", True, (255, 255, 255))
        surface.blit(title, (sx, 30))

        score_label = font.render(f"Score: {self.score}", True, (200, 200, 200))
        surface.blit(score_label, (sx, 80))

        controls = [
            "\u2190 \u2192 : Move",
            "\u2191   : Rotate",
            "\u2193   : Soft drop",
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
            # semi-transparent overlay
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
        rect = pygame.Rect(x * CELL + 1, y * CELL + 1, CELL - 2, CELL - 2)
        pygame.draw.rect(surface, color, rect, border_radius=4)
        lighter = tuple(min(c + 40, 255) for c in color)
        pygame.draw.line(surface, lighter, (rect.x + 2, rect.y + 2),
                         (rect.right - 3, rect.y + 2))
        pygame.draw.line(surface, lighter, (rect.x + 2, rect.y + 2),
                         (rect.x + 2, rect.bottom - 3))


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
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

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    game.restart()
                elif event.key == pygame.K_LEFT:
                    game.move(-1, 0)
                    das_dir = -1
                    das_timer = 0.0
                    das_charged = False
                elif event.key == pygame.K_RIGHT:
                    game.move(1, 0)
                    das_dir = 1
                    das_timer = 0.0
                    das_charged = False
                elif event.key == pygame.K_DOWN:
                    soft_drop = True
                elif event.key == pygame.K_UP:
                    game.rotate()
                elif event.key == pygame.K_SPACE:
                    game.hard_drop()

            elif event.type == pygame.KEYUP:
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    das_dir = 0
                if event.key == pygame.K_DOWN:
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
