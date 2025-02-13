import pygame
import os

# Параметры
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 800
BOARD_SIZE = 800
SQUARE_SIZE = BOARD_SIZE // 8
PIECE_SIZE = SQUARE_SIZE  # Размеры изображений фигур

# Путь к ресурсам
IMAGE_PATH = "ChessAI/assets/images/"

# Инициализация Pygame
pygame.init()
screen = pygame.display.set_mode((BOARD_SIZE, BOARD_SIZE))
pygame.display.set_caption('Test Chess Board')

# Загрузка изображений
def load_images():
    images = {}
    piece_paths = {
        'wq': 'white/wq.png', 'wr': 'white/wr.png', 'wb': 'white/wb.png', 'wn': 'white/wn.png', 'wk': 'white/wk.png', 'wp': 'white/wp.png',
        'bq': 'black/bq.png', 'br': 'black/br.png', 'bb': 'black/bb.png', 'bn': 'black/bn.png', 'bk': 'black/bk.png', 'bp': 'black/bp.png'
    }

    for piece, path in piece_paths.items():
        image_path = os.path.join(IMAGE_PATH, path)
        try:
            print(f"Loading image: {image_path}")  # Отладочный вывод
            image = pygame.image.load(image_path)
            image = pygame.transform.scale(image, (PIECE_SIZE, PIECE_SIZE))
            images[piece] = image
        except pygame.error as e:
            print(f"Error loading image for {piece}: {e}")
    
    return images

images = load_images()

def draw_board():
    # Очистка экрана
    screen.fill((255, 255, 255))

    # Нарисовать клетки доски
    for i in range(8):
        for j in range(8):
            color = (255, 255, 255) if (i + j) % 2 == 0 else (0, 0, 0)
            pygame.draw.rect(screen, color, pygame.Rect(j * SQUARE_SIZE, i * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE))
    
    # Отображение начальной расстановки фигур
    start_position = [
        ('wr', 0, 0), ('wn', 1, 0), ('wb', 2, 0), ('wq', 3, 0), ('wk', 4, 0), ('wb', 5, 0), ('wn', 6, 0), ('wr', 7, 0),
        ('wp', 0, 1), ('wp', 1, 1), ('wp', 2, 1), ('wp', 3, 1), ('wp', 4, 1), ('wp', 5, 1), ('wp', 6, 1), ('wp', 7, 1),
        ('bp', 0, 6), ('bp', 1, 6), ('bp', 2, 6), ('bp', 3, 6), ('bp', 4, 6), ('bp', 5, 6), ('bp', 6, 6), ('bp', 7, 6),
        ('br', 0, 7), ('bn', 1, 7), ('bb', 2, 7), ('bq', 3, 7), ('bk', 4, 7), ('bb', 5, 7), ('bn', 6, 7), ('br', 7, 7)
    ]

    for piece, x, y in start_position:
        if piece in images:
            piece_image = images[piece]
            screen.blit(piece_image, (x * SQUARE_SIZE, y * SQUARE_SIZE))
        else:
            print(f"Missing image for piece: {piece}")  # Отладочный вывод
    
    pygame.display.flip()

def main_loop():
    # Запуск основного цикла Pygame
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        pygame.display.flip()
    
    pygame.quit()

# Запуск функции отрисовки и основного цикла
draw_board()
main_loop()
