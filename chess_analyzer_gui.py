import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk
import chess
import chess.pgn
import os
import threading
import queue
import time # Для анимации
import pygame # Для звуков

from engine_handler import EngineHandler

# --- Константы ---
BOARD_IMG_WIDTH = 600
BOARD_IMG_HEIGHT = 600
SQUARE_SIZE = BOARD_IMG_WIDTH // 8
INFO_PANEL_WIDTH = 350 # Немного увеличим для доп. кнопок
EVAL_BAR_HEIGHT = 30
# WINDOW_WIDTH = BOARD_IMG_WIDTH + INFO_PANEL_WIDTH # Закомментируем, пусть Tkinter сам решает
# WINDOW_HEIGHT = BOARD_IMG_HEIGHT + EVAL_BAR_HEIGHT

ASSETS_DIR = "assets"
IMAGE_DIR = os.path.join(ASSETS_DIR, "images")
PIECE_DIR = os.path.join(IMAGE_DIR, "pieces")
SOUND_DIR = os.path.join(ASSETS_DIR, "sounds")

PIECE_SYMBOL_TO_FILE = {
    'P': 'wp.png', 'N': 'wn.png', 'B': 'wb.png', 'R': 'wr.png', 'Q': 'wq.png', 'K': 'wk.png',
    'p': 'bp.png', 'n': 'bn.png', 'b': 'bb.png', 'r': 'br.png', 'q': 'bq.png', 'k': 'bk.png'
}

# Анимация
ANIMATION_STEPS = 10  # Количество шагов для анимации
ANIMATION_DELAY = 15  # Задержка между шагами в мс

class ChessAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Продвинутый Анализатор Шахматных Партий")

        # --- Инициализация Pygame для звука ---
        try:
            pygame.mixer.init()
            self.move_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "move.wav"))
            self.capture_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "capture.wav"))
            self.sound_enabled = True
        except Exception as e:
            print(f"Ошибка инициализации звука (pygame): {e}. Звук будет отключен.")
            messagebox.showwarning("Ошибка звука", f"Не удалось загрузить звуковые файлы или инициализировать pygame.mixer: {e}\nЗвук будет отключен.")
            self.sound_enabled = False
            self.move_sound = None
            self.capture_sound = None


        self.piece_images = {}
        self.current_game_node = None
        self.board_state = chess.Board()
        self.board_orientation_white_pov = True # True - белые внизу, False - черные внизу

        self.engine = EngineHandler()
        if not self.engine.process:
            messagebox.showwarning("Движок не найден",
                                   f"Stockfish не был найден или не удалось его запустить.\n"
                                   f"Проверьте наличие файла '{self.engine.engine_path}' "
                                   f"или укажите корректный путь в engine_handler.py.\n"
                                   "Анализ будет недоступен.")
        
        self.analysis_queue = queue.Queue()
        self.best_move_from_engine = None
        self.animating_piece_id = None # ID элемента Canvas для анимируемой фигуры
        self.is_animating = False

        self.load_assets()
        self.create_widgets()
        self.update_board_display()
        self.update_info_panel()
        self.process_analysis_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_assets(self):
        try:
            board_img_path = os.path.join(IMAGE_DIR, "board.png")
            pil_board_image = Image.open(board_img_path)
            pil_board_image = pil_board_image.resize((BOARD_IMG_WIDTH, BOARD_IMG_HEIGHT), Image.LANCZOS)
            self.board_bg_image = ImageTk.PhotoImage(pil_board_image)

            for symbol, filename in PIECE_SYMBOL_TO_FILE.items():
                color_folder = "white" if symbol.isupper() else "black"
                path = os.path.join(PIECE_DIR, color_folder, filename)
                try:
                    img = Image.open(path)
                    img = img.resize((SQUARE_SIZE, SQUARE_SIZE), Image.LANCZOS)
                    self.piece_images[symbol] = ImageTk.PhotoImage(img)
                except FileNotFoundError:
                    print(f"Предупреждение: Файл фигуры не найден: {path}")
                    self.piece_images[symbol] = None
        except FileNotFoundError as e:
            messagebox.showerror("Ошибка загрузки ассетов", f"Не найден критический файл: {e}\nПроверьте пути в 'assets'.")
            if self.engine: self.engine.quit_engine()
            self.root.quit()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки ассетов", f"Произошла ошибка: {e}")
            if self.engine: self.engine.quit_engine()
            self.root.quit()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Левая часть: Доска, управление, оценка ---
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.board_canvas = tk.Canvas(left_frame, width=BOARD_IMG_WIDTH, height=BOARD_IMG_HEIGHT, borderwidth=0, highlightthickness=0)
        self.board_canvas.pack()
        if hasattr(self, 'board_bg_image'):
             self.board_canvas.create_image(0, 0, anchor=tk.NW, image=self.board_bg_image, tags="board_bg")

        # Панель управления PGN и навигацией
        pgn_controls_frame = ttk.Frame(left_frame)
        pgn_controls_frame.pack(fill=tk.X, pady=5)

        self.load_pgn_button = ttk.Button(pgn_controls_frame, text="Загрузить PGN", command=self.load_pgn)
        self.load_pgn_button.pack(side=tk.LEFT, padx=(0,5))

        self.prev_move_button = ttk.Button(pgn_controls_frame, text="< Назад", command=self.prev_move_action, state=tk.DISABLED)
        self.prev_move_button.pack(side=tk.LEFT, padx=5)

        self.next_move_button = ttk.Button(pgn_controls_frame, text="Вперёд >", command=self.next_move_action, state=tk.DISABLED)
        self.next_move_button.pack(side=tk.LEFT, padx=5)

        self.flip_board_button = ttk.Button(pgn_controls_frame, text="Перевернуть", command=self.flip_board)
        self.flip_board_button.pack(side=tk.LEFT, padx=5)


        # Линия оценки
        self.eval_bar_canvas = tk.Canvas(left_frame, height=EVAL_BAR_HEIGHT, bg="dim gray")
        self.eval_bar_canvas.pack(fill=tk.X, pady=(5,0))
        self.eval_line = self.eval_bar_canvas.create_rectangle(
            0, 0, BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT, fill="white", outline=""
        )
        self.eval_text = self.eval_bar_canvas.create_text(
            BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT / 2, text="0.0", fill="black", font=("Arial", 10, "bold")
        )


        # --- Правая часть: Информация, ходы, анализ ---
        self.info_panel = ttk.Frame(main_frame, width=INFO_PANEL_WIDTH, padding=5)
        self.info_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.info_panel.pack_propagate(False)

        ttk.Label(self.info_panel, text="Информация о партии:", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.game_info_label = ttk.Label(self.info_panel, text="Партия не загружена", wraplength=INFO_PANEL_WIDTH - 10, justify=tk.LEFT)
        self.game_info_label.pack(anchor=tk.NW, pady=5, fill=tk.X)

        ttk.Label(self.info_panel, text="Ходы:", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(10,0))
        
        # Фрейм для Listbox и Scrollbar
        moves_frame = ttk.Frame(self.info_panel)
        moves_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.moves_scrollbar = ttk.Scrollbar(moves_frame, orient=tk.VERTICAL)
        self.moves_listbox = tk.Listbox(moves_frame, yscrollcommand=self.moves_scrollbar.set, exportselection=False) # exportselection=False важно
        self.moves_scrollbar.config(command=self.moves_listbox.yview)
        
        self.moves_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.moves_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.moves_listbox.bind('<<ListboxSelect>>', self.on_move_select_from_listbox)


        ttk.Label(self.info_panel, text="Текущий ход:", font=("Arial", 10)).pack(anchor=tk.W)
        self.current_move_label = ttk.Label(self.info_panel, text="-", font=("Arial", 10, "italic"))
        self.current_move_label.pack(anchor=tk.NW, fill=tk.X)

        self.analyze_button = ttk.Button(self.info_panel, text="Анализ текущей позиции", command=self.request_analysis_current_pos)
        self.analyze_button.pack(fill=tk.X, pady=(10,0))

        ttk.Label(self.info_panel, text="Оценка (Stockfish):", font=("Arial", 10)).pack(anchor=tk.W, pady=(10,0))
        self.evaluation_label = ttk.Label(self.info_panel, text="N/A", font=("Arial", 10, "italic"))
        self.evaluation_label.pack(anchor=tk.NW, fill=tk.X)
        
        ttk.Label(self.info_panel, text="Лучший ход:", font=("Arial", 10)).pack(anchor=tk.W, pady=(5,0))
        self.best_move_label = ttk.Label(self.info_panel, text="N/A", font=("Arial", 10, "italic"))
        self.best_move_label.pack(anchor=tk.NW, fill=tk.X)
        
        self.game_status_label = ttk.Label(self.info_panel, text="", font=("Arial", 10, "bold"), foreground="blue")
        self.game_status_label.pack(anchor=tk.NW, fill=tk.X, pady=(10,0))

    def get_square_coords(self, square_index):
        """Преобразует индекс клетки (0-63) в координаты x, y на холсте,
           учитывая ориентацию доски."""
        file = chess.square_file(square_index)
        rank = chess.square_rank(square_index)

        if self.board_orientation_white_pov:
            # Белые внизу
            x = file * SQUARE_SIZE
            y = (7 - rank) * SQUARE_SIZE
        else:
            # Черные внизу
            x = (7 - file) * SQUARE_SIZE
            y = rank * SQUARE_SIZE
        return x, y

    def update_board_display(self, move_to_animate=None, captured=False):
        if self.is_animating: # Не обновляем доску, пока идет анимация другого хода
            return

        self.board_canvas.delete("piece")
        self.board_canvas.delete("arrow")

        if move_to_animate:
            self.is_animating = True
            self.animate_move(move_to_animate, captured)
        else:
            self._draw_all_pieces()
            self._draw_move_arrows()


    def _draw_all_pieces(self):
        """Вспомогательная функция для отрисовки всех фигур на текущей board_state."""
        self.board_canvas.delete("piece") # Удаляем только фигуры
        for sq_idx in chess.SQUARES:
            piece = self.board_state.piece_at(sq_idx)
            if piece:
                symbol = piece.symbol()
                if symbol in self.piece_images and self.piece_images[symbol]:
                    x, y = self.get_square_coords(sq_idx)
                    self.board_canvas.create_image(x, y, anchor=tk.NW,
                                                   image=self.piece_images[symbol], tags=("piece", f"piece_at_{sq_idx}"))

    def _draw_move_arrows(self):
        """Вспомогательная функция для отрисовки стрелок последнего и лучшего хода."""
        self.board_canvas.delete("arrow") # Удаляем только стрелки
        # Стрелка последнего сделанного хода
        if self.current_game_node and self.current_game_node.move:
            move = self.current_game_node.move
            self.draw_arrow(move.from_square, move.to_square, color="blue", width=3, tag="last_move_arrow")

        # Стрелка лучшего хода от движка
        if self.best_move_from_engine:
             # Убедимся, что лучший ход валиден для текущей позиции
            if self.board_state.is_legal(self.best_move_from_engine):
                self.draw_arrow(self.best_move_from_engine.from_square,
                                self.best_move_from_engine.to_square,
                                color="green", width=4, tag="best_move_arrow")
            else: # Если ход нелегален (например, позиция изменилась быстрее, чем пришел ответ)
                self.best_move_from_engine = None # Сбрасываем
                self.best_move_label.config(text="N/A (ход устарел)")



    def animate_move(self, move, captured):
        from_sq = move.from_square
        to_sq = move.to_square
        
        piece_to_move = self.board_state.piece_at(to_sq) # Фигура уже на конечной клетке в board_state
        if not piece_to_move: # Если это был кастлинг, то фигура короля могла быть не той, что формально двигалась
            if move.promotion: # Если это превращение пешки
                 piece_to_move = chess.Piece(chess.PAWN, self.board_state.turn) # Берем пешку, которая превратилась
            elif self.board_state.is_castling(move):
                 # Для кастлинга, двигаем короля. board_state уже обновился.
                 # Фигура короля уже на своем месте. Анимируем короля.
                 king_square = self.board_state.king(not self.board_state.turn) # Король, который сделал ход
                 if king_square == to_sq or king_square == chess.square(chess.square_file(to_sq)-1, chess.square_rank(to_sq)) or \
                    king_square == chess.square(chess.square_file(to_sq)+1, chess.square_rank(to_sq)): # Упрощенная проверка на короля
                     piece_to_move = self.board_state.piece_at(king_square)

        if not piece_to_move: # Если всё еще не нашли фигуру (маловероятно, но для безопасности)
            print(f"Ошибка анимации: не найдена фигура для хода {move.uci()}")
            self._finalize_animation_and_update(move, captured)
            return

        piece_symbol = piece_to_move.symbol()
        
        # Начальные и конечные экранные координаты
        start_x, start_y = self.get_square_coords(from_sq)
        end_x, end_y = self.get_square_coords(to_sq)

        # Создаем копию изображения фигуры для анимации
        if piece_symbol in self.piece_images and self.piece_images[piece_symbol]:
            animated_image = self.piece_images[piece_symbol]
            self.animating_piece_id = self.board_canvas.create_image(start_x, start_y, anchor=tk.NW, image=animated_image, tags="anim_piece")
            self.board_canvas.tag_raise(self.animating_piece_id) # Поднять поверх других фигур
        else:
            self._finalize_animation_and_update(move, captured) # Нечего анимировать
            return

        # Удаляем статическую фигуру с начальной клетки (если она там была нарисована)
        # self.board_canvas.delete(f"piece_at_{from_sq}") # Это удалит ее до анимации
        # Вместо этого, полная перерисовка будет после анимации.

        # Рассчитываем шаги анимации
        dx = (end_x - start_x) / ANIMATION_STEPS
        dy = (end_y - start_y) / ANIMATION_STEPS

        def animation_step(current_step):
            if current_step <= ANIMATION_STEPS:
                current_x = start_x + dx * current_step
                current_y = start_y + dy * current_step
                self.board_canvas.coords(self.animating_piece_id, current_x, current_y)
                self.root.after(ANIMATION_DELAY, lambda: animation_step(current_step + 1))
            else:
                # Анимация завершена
                self.board_canvas.delete(self.animating_piece_id)
                self.animating_piece_id = None
                self._finalize_animation_and_update(move, captured)
        
        # Перед началом анимации, отрисуем все фигуры КРОМЕ той, что будет анимироваться с from_sq
        self.board_canvas.delete("piece")
        for sq_idx in chess.SQUARES:
            if sq_idx == from_sq: # Пропускаем клетку, с которой анимируем
                 continue
            piece_on_sq = self.current_game_node.parent.board().piece_at(sq_idx) # Берем из предыдущего состояния
            if piece_on_sq: # Если на клетке была фигура (до хода)
                symbol = piece_on_sq.symbol()
                if symbol in self.piece_images and self.piece_images[symbol]:
                    x, y = self.get_square_coords(sq_idx)
                    # Не рисуем фигуру на to_sq, если это взятие, т.к. она исчезнет
                    if captured and sq_idx == to_sq:
                        pass
                    else:
                        self.board_canvas.create_image(x, y, anchor=tk.NW,
                                                       image=self.piece_images[symbol], tags=("piece", f"piece_at_{sq_idx}"))
        
        self._draw_move_arrows() # Рисуем стрелки сразу
        animation_step(1) # Запускаем анимацию


    def _finalize_animation_and_update(self, move, captured):
        self.is_animating = False
        self.play_sound(captured)
        self._draw_all_pieces() # Перерисовываем все фигуры в финальной позиции
        self._draw_move_arrows() # Обновляем стрелки
        self.update_info_panel() # Обновляем инфопанель, включая запрос анализа
        self.update_navigation_buttons()


    def play_sound(self, captured):
        if not self.sound_enabled:
            return
        try:
            if captured:
                if self.capture_sound: self.capture_sound.play()
            else:
                if self.move_sound: self.move_sound.play()
        except Exception as e:
            print(f"Ошибка воспроизведения звука: {e}")


    def draw_arrow(self, from_square, to_square, color="green", width=3, tag="arrow"):
        # Учитываем ориентацию доски для стрелок
        x1_abs, y1_abs = self.get_square_coords(from_square)
        x2_abs, y2_abs = self.get_square_coords(to_square)
        
        # Центр клетки
        x1 = x1_abs + SQUARE_SIZE / 2
        y1 = y1_abs + SQUARE_SIZE / 2
        x2 = x2_abs + SQUARE_SIZE / 2
        y2 = y2_abs + SQUARE_SIZE / 2

        self.board_canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, fill=color, width=width, tags=(tag, "arrow"))

    def update_info_panel(self):
        # ... (остальная часть update_info_panel почти без изменений, но нужно немного поправить логику списка ходов)
        self.best_move_from_engine = None
        self.best_move_label.config(text="N/A")
        self.game_status_label.config(text="") # Сброс статуса игры

        if self.current_game_node:
            headers = self.current_game_node.game().headers
            info_text = f"Белые: {headers.get('White', 'N/A')} ({headers.get('WhiteElo', '')})\n"
            info_text += f"Черные: {headers.get('Black', 'N/A')} ({headers.get('BlackElo', '')})\n"
            info_text += f"Результат: {headers.get('Result', 'N/A')}\n"
            info_text += f"Событие: {headers.get('Event', 'N/A')} ({headers.get('Site', '')}, {headers.get('Date', 'N/A')})"
            self.game_info_label.config(text=info_text)

            # --- Обновление списка ходов ---
            selected_index_before_update = self.moves_listbox.curselection()
            
            self.moves_listbox.delete(0, tk.END)
            game_start_node = self.current_game_node.game()
            self.move_nodes_in_listbox = [] # Список для GameNode объектов

            # Добавляем начальную позицию
            self.moves_listbox.insert(tk.END, "   --- Начало партии ---")
            self.move_nodes_in_listbox.append(game_start_node)

            current_board_for_san = game_start_node.board() # Начинаем с начальной доски
            for node_index, node in enumerate(game_start_node.mainline()): # node это GameNode
                if node.move is None: continue

                move_num_str = ""
                if node.ply() % 2 == 1: # Ход белых
                    move_num_str = f"{node.ply() // 2 + 1}. "
                
                san_move = current_board_for_san.san(node.move)
                current_board_for_san.push(node.move) # Применяем ход к временной доске для следующего SAN
                
                if node.ply() % 2 == 1: # Ход белых, новая строка
                    self.moves_listbox.insert(tk.END, f"{move_num_str}{san_move}")
                else: # Ход черных, добавляем к последней строке
                    last_entry_index = self.moves_listbox.size() -1
                    if last_entry_index >=0:
                        last_entry_text = self.moves_listbox.get(last_entry_index)
                        self.moves_listbox.delete(last_entry_index)
                        self.moves_listbox.insert(tk.END, f"{last_entry_text}  {san_move}") # Два пробела для разделения
                    else:
                         self.moves_listbox.insert(tk.END, f" {san_move}") # На всякий случай

                self.move_nodes_in_listbox.append(node)
            
            # Восстановление выделения, если возможно, или выделение текущего узла
            try:
                idx_to_select = self.move_nodes_in_listbox.index(self.current_game_node)
                self.moves_listbox.selection_set(idx_to_select)
                self.moves_listbox.see(idx_to_select)
            except ValueError: # Если текущий узел не найден (не должно быть, но для надежности)
                if selected_index_before_update:
                    try:
                        self.moves_listbox.selection_set(selected_index_before_update[0])
                        self.moves_listbox.see(selected_index_before_update[0])
                    except tk.TclError: pass # Индекс мог измениться

            # --- Отображение текущего хода и статуса игры ---
            if self.current_game_node.move:
                san_move = self.current_game_node.parent.board().san(self.current_game_node.move)
                self.current_move_label.config(text=san_move)
            else:
                self.current_move_label.config(text="Начальная позиция")
            
            self.check_game_status() # Проверка на мат/пат
            if not self.board_state.is_game_over(): # Запрашиваем анализ, только если игра не окончена
                self.request_analysis_current_pos()
            else: # Если игра окончена, сбрасываем оценку и лучший ход
                self.evaluation_label.config(text="Игра окончена")
                self.best_move_label.config(text="-")
                self.update_eval_bar(None, None) # Сброс eval bar
                self.best_move_from_engine = None # Убираем стрелку лучшего хода
                self._draw_move_arrows() # Перерисовать стрелки (убрать лучшую)

        else: # Партия не загружена
            self.game_info_label.config(text="Партия не загружена")
            self.moves_listbox.delete(0, tk.END)
            self.current_move_label.config(text="-")
            self.evaluation_label.config(text="N/A")
            self.best_move_label.config(text="N/A")
            self.game_status_label.config(text="")
            self.update_eval_bar(None, None)

    def check_game_status(self):
        if self.board_state.is_checkmate():
            winner = "Белые" if self.board_state.turn == chess.BLACK else "Черные" # Мат поставили предыдущим ходом
            self.game_status_label.config(text=f"МАТ! {winner} победили.", foreground="red")
            self.evaluation_label.config(text="Мат")
            self.best_move_label.config(text="-")
        elif self.board_state.is_stalemate():
            self.game_status_label.config(text="ПАТ! Ничья.", foreground="blue")
        elif self.board_state.is_insufficient_material():
            self.game_status_label.config(text="Ничья (недостаточно материала).", foreground="blue")
        elif self.board_state.is_seventyfive_moves():
            self.game_status_label.config(text="Ничья (правило 75 ходов).", foreground="blue")
        elif self.board_state.is_fivefold_repetition():
            self.game_status_label.config(text="Ничья (пятикратное повторение).", foreground="blue")
        # Можно добавить is_variant_draw, is_variant_loss, is_variant_win если работаете с вариантами шахмат
        else:
            self.game_status_label.config(text="") # Нет особого статуса

    def update_eval_bar(self, score_cp, score_mate, max_eval_cp=1000):
        # ... (без изменений)
        bar_width = self.eval_bar_canvas.winfo_width()
        if bar_width <= 1: bar_width = BOARD_IMG_WIDTH
        
        text_to_display = "N/A"
        normalized_score = 0.5 # Нейтрально по умолчанию

        if self.board_state.is_checkmate():
            # Если мат, то оценка должна быть максимальной в пользу победителя
            if self.board_state.turn == chess.BLACK: # Мат белым (ход черных, но мат уже стоит)
                normalized_score = 1.0 
                text_to_display = "M+" # Белые выиграли
            else: # Мат черным
                normalized_score = 0.0
                text_to_display = "M-" # Черные выиграли
        elif score_mate is not None:
            # Оценка в матах от движка
            # Учитываем, чей ход для интерпретации мата от движка
            # Если движок говорит M+X и ход белых, это мат белым в X ходов.
            # Если движок говорит M+X и ход черных, это мат черным в X ходов (движок видит мат за себя)
            effective_mate_score = score_mate if self.board_state.turn == chess.WHITE else -score_mate
            if effective_mate_score > 0: 
                normalized_score = 1.0
                text_to_display = f"M{abs(score_mate)}"
            else: 
                normalized_score = 0.0
                text_to_display = f"M{-abs(score_mate)}"
        elif score_cp is not None:
            # Оценка в сантипешках
            # Приводим к перспективе белых: score_cp > 0 - преимущество белых
            actual_score_cp = score_cp if self.board_state.turn == chess.WHITE else -score_cp
            
            clamped_score = max(-max_eval_cp, min(max_eval_cp, actual_score_cp))
            normalized_score = (clamped_score / max_eval_cp) * 0.5 + 0.5
            text_to_display = f"{actual_score_cp / 100.0:+.2f}"
        
        white_width = bar_width * normalized_score
        self.eval_bar_canvas.coords(self.eval_line, 0, 0, white_width, EVAL_BAR_HEIGHT)
        self.eval_bar_canvas.itemconfig(self.eval_line, fill="white")
        
        black_rect_id = self.eval_bar_canvas.find_withtag("black_eval_part")
        if black_rect_id: self.eval_bar_canvas.delete(black_rect_id)
        
        self.eval_bar_canvas.create_rectangle(
            white_width, 0, bar_width, EVAL_BAR_HEIGHT, fill="black", outline="", tags="black_eval_part"
        )
        self.eval_bar_canvas.tag_raise(self.eval_text)
        self.eval_bar_canvas.coords(self.eval_text, bar_width / 2, EVAL_BAR_HEIGHT / 2)
        self.eval_bar_canvas.itemconfig(self.eval_text, text=text_to_display)


    def load_pgn(self):
        if self.is_animating: return
        # ... (без изменений)
        filepath = filedialog.askopenfilename(
            title="Открыть PGN файл",
            filetypes=(("PGN files", "*.pgn"), ("All files", "*.*"))
        )
        if not filepath: return

        try:
            with open(filepath, encoding='utf-8-sig') as pgn_file: 
                game = chess.pgn.read_game(pgn_file)
            if game is None:
                messagebox.showerror("Ошибка PGN", "Не удалось прочитать PGN файл. Возможно, он пустой или некорректный.")
                return

            self.current_game_node = game 
            self.board_state = game.board()
            self.board_orientation_white_pov = True # Сброс ориентации при загрузке новой партии
            
            # Не вызываем анимацию при загрузке, просто обновляем доску
            self._draw_all_pieces() 
            self._draw_move_arrows()
            self.update_info_panel() 
            self.update_navigation_buttons()

        except Exception as e:
            messagebox.showerror("Ошибка загрузки PGN", f"Произошла ошибка: {e}")


    def _navigate_to_node(self, target_node, is_forward_move=None):
        if self.is_animating or target_node is None:
            return

        move_to_animate = None
        captured = False

        # Определяем, был ли ход вперед или назад для анимации и звука
        if is_forward_move is not None:
            if is_forward_move and target_node.move: # Движение вперед
                move_to_animate = target_node.move
                # Проверяем, было ли это взятие, на ДОСКЕ ПЕРЕД ЭТИМ ХОДОМ
                board_before_move = target_node.parent.board()
                captured = board_before_move.is_capture(move_to_animate)
                if board_before_move.is_en_passant(move_to_animate): # Взятие на проходе тоже capture
                    captured = True

            elif not is_forward_move and self.current_game_node.move: # Движение назад
                # Для движения назад, "анимируем" отмену хода
                # move_to_animate = self.current_game_node.move
                # # Проверяем, было ли это взятие, которое отменяется (сложнее, т.к. фигура "возвращается")
                # # captured = self.current_game_node.parent.board().is_capture(move_to_animate) # Не совсем корректно для звука "отмены"
                # # Для упрощения, звук только для ходов вперед.
                pass # Пока без анимации и звука для хода назад


        self.current_game_node = target_node
        self.board_state = self.current_game_node.board() # Обновляем состояние доски

        # Обновляем отображение (с анимацией, если нужно)
        if move_to_animate:
            self.update_board_display(move_to_animate=move_to_animate, captured=captured)
            # update_info_panel и update_navigation_buttons будут вызваны в _finalize_animation_and_update
        else:
            self._draw_all_pieces()
            self._draw_move_arrows()
            self.update_info_panel()
            self.update_navigation_buttons()
            
    def next_move_action(self):
        if self.current_game_node and self.current_game_node.variations:
            self._navigate_to_node(self.current_game_node.variation(0), is_forward_move=True)

    def prev_move_action(self):
        if self.current_game_node and self.current_game_node.parent is not None:
             self._navigate_to_node(self.current_game_node.parent, is_forward_move=False)

    def on_move_select_from_listbox(self, event):
        if self.is_animating: return
        
        widget = event.widget
        selection = widget.curselection()
        if not selection:
            return
        
        selected_idx = selection[0]
        if 0 <= selected_idx < len(self.move_nodes_in_listbox):
            target_node = self.move_nodes_in_listbox[selected_idx]
            
            # Определяем направление для анимации (упрощенно)
            is_forward = False
            if self.current_game_node and target_node:
                # Сравниваем глубину (ply) узлов
                current_ply = self.current_game_node.ply() if self.current_game_node.move else -1 # -1 для начальной позиции
                target_ply = target_node.ply() if target_node.move else -1
                if target_ply > current_ply:
                    is_forward = True
            
            self._navigate_to_node(target_node, is_forward_move=is_forward if target_node != self.current_game_node else None)


    def update_navigation_buttons(self):
        # ... (без изменений)
        if self.current_game_node:
            self.prev_move_button.config(state=tk.NORMAL if self.current_game_node.parent is not None else tk.DISABLED)
            self.next_move_button.config(state=tk.NORMAL if self.current_game_node.variations else tk.DISABLED)
        else:
            self.prev_move_button.config(state=tk.DISABLED)
            self.next_move_button.config(state=tk.DISABLED)

    def flip_board(self):
        if self.is_animating: return
        self.board_orientation_white_pov = not self.board_orientation_white_pov
        self._draw_all_pieces() # Перерисовать фигуры с новой ориентацией
        self._draw_move_arrows() # Перерисовать стрелки

    # --- Логика анализа движком --- (почти без изменений)
    def request_analysis_current_pos(self):
        if self.is_animating: # Не запускаем анализ, пока идет анимация
            # Запланировать анализ после завершения анимации
            self.root.after(ANIMATION_STEPS * ANIMATION_DELAY + 100, self.request_analysis_current_pos)
            return

        if not self.engine or not self.engine.process or self.board_state.is_game_over():
            if self.board_state.is_game_over():
                self.evaluation_label.config(text="Игра окончена")
                self.best_move_label.config(text="-")
            elif not self.engine or not self.engine.process:
                self.evaluation_label.config(text="Движок не активен")
                self.best_move_label.config(text="N/A")
            self.update_eval_bar(None, None)
            self.best_move_from_engine = None
            self._draw_move_arrows() # Обновить доску (убрать стрелку лучшего хода)
            return

        self.evaluation_label.config(text="Анализ...")
        self.best_move_label.config(text="Анализ...")
        # self.best_move_from_engine = None # Не сбрасываем здесь, чтобы стрелка не мигала, если анализ быстрый
        # self.update_board_display() # Не нужно полное обновление, только стрелки, если изменится

        current_fen = self.board_state.fen()
        threading.Thread(target=self._run_engine_analysis, args=(current_fen,), daemon=True).start()

    def _run_engine_analysis(self, fen_string):
        # ... (без изменений)
        if not self.engine or not self.engine.process: return
        self.engine.set_position_from_fen(fen_string)
        score_cp, score_mate, best_move_uci = self.engine.get_evaluation_and_best_move(movetime_ms=1000)
        self.analysis_queue.put((score_cp, score_mate, best_move_uci, fen_string))


    def process_analysis_queue(self):
        # ... (небольшие правки для отображения лучшего хода)
        try:
            score_cp, score_mate, best_move_uci, analyzed_fen = self.analysis_queue.get_nowait()

            if self.board_state.fen() != analyzed_fen or self.is_animating:
                self.root.after(100, self.process_analysis_queue)
                return

            if score_mate is not None:
                # Приводим мат к перспективе белых для текстового отображения
                actual_mate_val = score_mate if self.board_state.turn == chess.WHITE else -score_mate
                self.evaluation_label.config(text=f"Мат в {abs(score_mate)} ({'+' if actual_mate_val > 0 else '-'})")
            elif score_cp is not None:
                # Приводим оценку к перспективе белых
                actual_score_cp = score_cp if self.board_state.turn == chess.WHITE else -score_cp
                self.evaluation_label.config(text=f"{actual_score_cp / 100.0:+.2f}")
            else:
                self.evaluation_label.config(text="N/A")
            
            self.update_eval_bar(score_cp, score_mate)

            new_best_move_obj = None
            if best_move_uci and best_move_uci != "(none)":
                try:
                    move = self.board_state.parse_uci(best_move_uci)
                    if self.board_state.is_legal(move): # Дополнительная проверка
                        new_best_move_obj = move
                        self.best_move_label.config(text=self.board_state.san(move))
                    else:
                         self.best_move_label.config(text=f"Нелегальный ход: {best_move_uci}")
                except ValueError:
                    self.best_move_label.config(text=f"Ошибка UCI: {best_move_uci}")
            elif self.board_state.is_game_over():
                 self.best_move_label.config(text="Игра окончена")
            else:
                self.best_move_label.config(text="N/A (нет хода)")
            
            if self.best_move_from_engine != new_best_move_obj:
                self.best_move_from_engine = new_best_move_obj
                self._draw_move_arrows() # Перерисовываем стрелки, если лучший ход изменился

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_analysis_queue)

    def on_closing(self):
        print("Закрытие приложения...")
        self.is_animating = False # Остановить любую текущую анимацию
        if self.engine:
            self.engine.quit_engine()
        if self.sound_enabled and pygame.mixer.get_init():
            pygame.mixer.quit()
        self.root.destroy()

if __name__ == "__main__":
    if not os.path.exists(ASSETS_DIR):
        print(f"Ошибка: Директория ассетов '{ASSETS_DIR}' не найдена.")
    
    root = tk.Tk()
    app = ChessAnalyzerApp(root)
    root.mainloop()