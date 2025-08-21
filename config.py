import os

# Визуальные константы
BOARD_IMG_WIDTH = 600
BOARD_IMG_HEIGHT = 600
SQUARE_SIZE = BOARD_IMG_WIDTH // 8

# Панель информации справа
INFO_PANEL_WIDTH = 420
EVAL_BAR_HEIGHT = 28

# Ассеты
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
IMAGE_DIR = os.path.join(ASSETS_DIR, "images")
PIECE_DIR = os.path.join(IMAGE_DIR, "pieces")
SOUND_DIR = os.path.join(ASSETS_DIR, "sound")
PIECE_SYMBOL_TO_FILE = {
    'P': 'wp.png', 'N': 'wn.png', 'B': 'wb.png', 'R': 'wr.png', 'Q': 'wq.png', 'K': 'wk.png',
    'p': 'bp.png', 'n': 'bn.png', 'b': 'bb.png', 'r': 'br.png', 'q': 'bq.png', 'k': 'bk.png'
}

# Анимация
ANIMATION_STEPS = 10
ANIMATION_DELAY = 0

# Engine defaults
DEFAULT_ENGINE_SKILL = 20
DEFAULT_ENGINE_MULTIPV = 3
DEFAULT_ENGINE_MOVETIME_MS = 2000

# Путь к stockfish
STOCKFISH_PATH_WINDOWS = "./stockfish.exe"
STOCKFISH_PATH_UNIX = "./stockfish"

# Подсказки, показываемые в режиме "только доска"
BOARD_ONLY_HINTS = [
    "Подсказки:",
    "← / → : перемотка по ходам",
    "F : перевернуть доску",
    "A : проанализировать позицию",
    "T : показать угрозу",
    "Space : включить/выключить режим только доски"
]
