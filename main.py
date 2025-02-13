import tkinter as tk
from PIL import Image, ImageTk

# Настройки пути к изображениям
board_path = 'ChessAI/assets/images/board.png'
pieces_path = {
    'black_bishop': 'ChessAI/assets/images/pieces/black/bb.png',
    'black_king': 'ChessAI/assets/images/pieces/black/bk.png',
    'black_knight': 'ChessAI/assets/images/pieces/black/bn.png',
    'black_pawn': 'ChessAI/assets/images/pieces/black/bp.png',
    'black_queen': 'ChessAI/assets/images/pieces/black/bq.png',
    'black_rook': 'ChessAI/assets/images/pieces/black/br.png',
    'white_bishop': 'ChessAI/assets/images/pieces/white/wb.png',
    'white_king': 'ChessAI/assets/images/pieces/white/wk.png',
    'white_knight': 'ChessAI/assets/images/pieces/white/wn.png',
    'white_pawn': 'ChessAI/assets/images/pieces/white/wp.png',
    'white_queen': 'ChessAI/assets/images/pieces/white/wq.png',
    'white_rook': 'ChessAI/assets/images/pieces/white/wr.png',
}

# Настройка основного окна
root = tk.Tk()
root.title("Chess Analyzer")

# Загрузка и масштабирование шахматной доски
board_img = Image.open(board_path)
board_img = board_img.resize((600, 600))
board_photo = ImageTk.PhotoImage(board_img)

# Отображение шахматной доски
canvas = tk.Canvas(root, width=600, height=600)
canvas.pack()
canvas.create_image(0, 0, anchor=tk.NW, image=board_photo)

# Загрузка и отображение фигур
pieces_images = {}
for name, path in pieces_path.items():
    img = Image.open(path)
    img = img.resize((75, 75))  # Масштабирование фигур до 75x75
    pieces_images[name] = ImageTk.PhotoImage(img)

# Пример отображения фигур на стартовых позициях
# Королевская пешка на е2 (белая пешка)
canvas.create_image(300, 450, anchor=tk.NW, image=pieces_images['white_pawn'])
# Белый ферзь на d1
canvas.create_image(225, 525, anchor=tk.NW, image=pieces_images['white_queen'])
# Черный король на e8
canvas.create_image(300, 0, anchor=tk.NW, image=pieces_images['black_king'])

# Запуск главного цикла
root.mainloop()
