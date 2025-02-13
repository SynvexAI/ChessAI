from PIL import Image, ImageTk

# Размер шахматной доски и клеток
BOARD_SIZE = 600
SQUARE_SIZE = BOARD_SIZE // 8

# Функция для загрузки и масштабирования фигуры
def load_and_resize_piece(piece_name):
    image = Image.open(f"ChessAI/assets/images/pieces/{piece_name[0]}/{piece_name}.png")
    resized_image = image.resize((SQUARE_SIZE, SQUARE_SIZE), Image.LANCZOS)
    return ImageTk.PhotoImage(resized_image)

# Пример использования для загрузки фигуры
piece_image = load_and_resize_piece("bb")  # Черный слон
canvas.create_image(x, y, image=piece_image, anchor=tk.NW)
