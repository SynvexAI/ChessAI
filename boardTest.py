import tkinter as tk
from tkinter import filedialog
import chess
import chess.engine
from PIL import Image, ImageTk

# Размеры доски
BOARD_SIZE = 600

# Инициализация главного окна
root = tk.Tk()
root.title("Chess Analyzer")

# Создание холста для доски
canvas = tk.Canvas(root, width=BOARD_SIZE, height=BOARD_SIZE)
canvas.grid(row=0, column=0)

# Загрузка и изменение размера текстуры доски
board_image = Image.open("assets/images/board.png")
board_image = board_image.resize((BOARD_SIZE, BOARD_SIZE), Image.ANTIALIAS)
board_photo = ImageTk.PhotoImage(board_image)

# Отображение доски на холсте
canvas.create_image(0, 0, anchor=tk.NW, image=board_photo)

# Загрузка и отображение фигур
pieces = {}
piece_filenames = {
    "P": "wp.png", "N": "wn.png", "B": "wb.png", "R": "wr.png", "Q": "wq.png", "K": "wk.png",
    "p": "bp.png", "n": "bn.png", "b": "bb.png", "r": "br.png", "q": "bq.png", "k": "bk.png"
}

for piece, filename in piece_filenames.items():
    image = Image.open(f"assets/images/pieces/white/{filename}" if piece.isupper() else f"assets/images/pieces/black/{filename}")
    image = image.resize((75, 75), Image.ANTIALIAS)  # Размеры фигур 75x75
    pieces[piece] = ImageTk.PhotoImage(image)

# Функция для отображения фигур на доске
def draw_pieces(board):
    canvas.delete("piece")
    square_size = BOARD_SIZE // 8
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            x = (square % 8) * square_size
            y = (7 - square // 8) * square_size
            canvas.create_image(x, y, anchor=tk.NW, image=pieces[piece.symbol()], tags="piece")

# Инициализация доски и отображение начальной позиции
board = chess.Board()
draw_pieces(board)

# Запуск главного цикла
root.mainloop()
