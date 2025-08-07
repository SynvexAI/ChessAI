import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import chess
import chess.pgn
import os
import threading
import queue
import time
import pygame

from engine_handler import EngineHandler

BOARD_IMG_WIDTH = 600
BOARD_IMG_HEIGHT = 600
SQUARE_SIZE = BOARD_IMG_WIDTH // 8
INFO_PANEL_WIDTH = 400
EVAL_BAR_HEIGHT = 30
COMPACT_MODE_THRESHOLD = BOARD_IMG_WIDTH + 50

ASSETS_DIR = "assets"
IMAGE_DIR = os.path.join(ASSETS_DIR, "images")
PIECE_DIR = os.path.join(IMAGE_DIR, "pieces")
SOUND_DIR = os.path.join(ASSETS_DIR, "sounds")

PIECE_SYMBOL_TO_FILE = {
    'P': 'wp.png', 'N': 'wn.png', 'B': 'wb.png', 'R': 'wr.png', 'Q': 'wq.png', 'K': 'wk.png',
    'p': 'bp.png', 'n': 'bn.png', 'b': 'bb.png', 'r': 'br.png', 'q': 'bq.png', 'k': 'bk.png'
}

ANIMATION_STEPS = 10
ANIMATION_DELAY = 15

class ChessAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Ультимативный Анализатор Шахматных Партий")
        self.root.minsize(BOARD_IMG_WIDTH, BOARD_IMG_HEIGHT + 120)

        try:
            pygame.mixer.init()
            self.move_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "move.wav"))
            self.capture_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "capture.wav"))
            self.sound_enabled = True
        except Exception as e:
            self.sound_enabled = False
            self.move_sound = None
            self.capture_sound = None
            print(f"Ошибка инициализации звука: {e}")

        self.piece_images = {}
        self.current_game_node = None
        self.board_state = chess.Board()
        self.board_orientation_white_pov = True
        self.is_compact_mode = False
        
        self.engine_skill_var = tk.IntVar(value=20)
        self.engine = EngineHandler(initial_skill_level=self.engine_skill_var.get())
        if not self.engine.process:
            messagebox.showwarning("Ошибка движка", f"Stockfish не найден или не удалось запустить из '{self.engine.engine_path}'. Анализ недоступен.")
        
        self.analysis_queue = queue.Queue()
        self.best_move_from_engine = None
        self.animating_piece_id = None
        self.is_animating = False

        self.selected_square_for_move = None
        self.highlighted_squares_ids = []

        self.load_assets()
        self.create_widgets()
        
        self.board_canvas.bind("<Button-1>", self.on_board_click)
        self.root.bind("<Configure>", self.handle_resize)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.update_board_display()
        self.update_info_panel()
        self.process_analysis_queue()

    def load_assets(self):
        try:
            board_img_path = os.path.join(IMAGE_DIR, "board.png")
            pil_board_image = Image.open(board_img_path).resize((BOARD_IMG_WIDTH, BOARD_IMG_HEIGHT), Image.LANCZOS)
            self.board_bg_image = ImageTk.PhotoImage(pil_board_image)

            for symbol, filename in PIECE_SYMBOL_TO_FILE.items():
                color_folder = "white" if symbol.isupper() else "black"
                path = os.path.join(PIECE_DIR, color_folder, filename)
                try:
                    img = Image.open(path).resize((SQUARE_SIZE, SQUARE_SIZE), Image.LANCZOS)
                    self.piece_images[symbol] = ImageTk.PhotoImage(img)
                except FileNotFoundError:
                    print(f"Warning: Asset not found at {path}")
                    self.piece_images[symbol] = None
        except Exception as e:
            messagebox.showerror("Ошибка загрузки ресурсов", f"Критическая ошибка ресурсов: {e}")
            if self.engine and self.engine.process: self.engine.quit_engine()
            self.root.quit()

    def create_widgets(self):
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(self.main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.board_canvas = tk.Canvas(left_frame, width=BOARD_IMG_WIDTH, height=BOARD_IMG_HEIGHT, borderwidth=0, highlightthickness=0)
        self.board_canvas.pack()
        if hasattr(self, 'board_bg_image'):
             self.board_canvas.create_image(0, 0, anchor=tk.NW, image=self.board_bg_image, tags="board_bg")


        # ТОПОРНЫЙ БЛОК КОДА
        pgn_controls_frame = ttk.Frame(left_frame)
        pgn_controls_frame.pack(fill=tk.X, pady=5)
        self.load_pgn_button = ttk.Button(pgn_controls_frame, text="Загрузить PGN", command=self.load_pgn)
        self.load_pgn_button.pack(side=tk.LEFT, padx=(0,5))
        self.prev_move_button = ttk.Button(pgn_controls_frame, text="< Назад", command=self.prev_move_action, state=tk.DISABLED)
        self.prev_move_button.pack(side=tk.LEFT, padx=5)
        self.next_move_button = ttk.Button(pgn_controls_frame, text="Вперед >", command=self.next_move_action, state=tk.DISABLED)
        self.next_move_button.pack(side=tk.LEFT, padx=5)
        self.flip_board_button = ttk.Button(pgn_controls_frame, text="Перевернуть", command=self.flip_board)
        self.flip_board_button.pack(side=tk.LEFT, padx=5)
        
        fen_frame = ttk.Frame(left_frame)
        fen_frame.pack(fill=tk.X, pady=5)
        self.load_fen_button = ttk.Button(fen_frame, text="Загрузить FEN", command=self.load_fen_dialog)
        self.load_fen_button.pack(side=tk.LEFT, padx=(0,5))
        self.export_fen_button = ttk.Button(fen_frame, text="Копировать FEN", command=self.export_fen_to_clipboard)
        self.export_fen_button.pack(side=tk.LEFT, padx=5)

        self.eval_bar_canvas = tk.Canvas(left_frame, height=EVAL_BAR_HEIGHT, bg="dim gray")
        self.eval_bar_canvas.pack(fill=tk.X, pady=(5,0))
        self.eval_line = self.eval_bar_canvas.create_rectangle(0, 0, BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT, fill="white", outline="")
        self.eval_text = self.eval_bar_canvas.create_text(BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT / 2, text="0.0", fill="black", font=("Arial", 10, "bold"))

        self.info_panel = ttk.LabelFrame(self.main_frame, text="Информация и Анализ", width=INFO_PANEL_WIDTH, padding=10)
        self.info_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.info_panel.pack_propagate(False)

        self.game_info_label = ttk.Label(self.info_panel, text="Партия не загружена", wraplength=INFO_PANEL_WIDTH - 20, justify=tk.LEFT)
        self.game_info_label.pack(anchor=tk.NW, pady=5, fill=tk.X)

        ttk.Label(self.info_panel, text="Ходы:", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(10,0))
        moves_frame = ttk.Frame(self.info_panel)
        moves_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.moves_scrollbar = ttk.Scrollbar(moves_frame, orient=tk.VERTICAL)
        self.moves_listbox = tk.Listbox(moves_frame, yscrollcommand=self.moves_scrollbar.set, exportselection=False, font=("Courier", 10))
        self.moves_scrollbar.config(command=self.moves_listbox.yview)
        self.moves_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.moves_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.moves_listbox.bind('<<ListboxSelect>>', self.on_move_select_from_listbox)

        self.analyze_button = ttk.Button(self.info_panel, text="Анализировать Позицию", command=self.request_analysis_current_pos)
        self.analyze_button.pack(fill=tk.X, pady=(5,0))

        engine_skill_frame = ttk.Frame(self.info_panel)
        engine_skill_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Label(engine_skill_frame, text="Сила движка (0-20):").pack(side=tk.LEFT)
        self.skill_scale = ttk.Scale(engine_skill_frame, from_=0, to=20, orient=tk.HORIZONTAL, variable=self.engine_skill_var, command=self.update_engine_skill)
        self.skill_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.skill_label_value = ttk.Label(engine_skill_frame, textvariable=self.engine_skill_var, width=2)
        self.skill_label_value.pack(side=tk.LEFT)

        ttk.Label(self.info_panel, text="Оценка движка:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5,0))
        self.evaluation_label = ttk.Label(self.info_panel, text="N/A", font=("Arial", 10, "italic"))
        self.evaluation_label.pack(anchor=tk.NW, fill=tk.X)
        
        ttk.Label(self.info_panel, text="Лучший ход:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5,0))
        self.best_move_label = ttk.Label(self.info_panel, text="N/A", font=("Arial", 10, "italic"))
        self.best_move_label.pack(anchor=tk.NW, fill=tk.X)
        
        self.game_status_label = ttk.Label(self.info_panel, text="", font=("Arial", 10, "bold"), foreground="blue")
        self.game_status_label.pack(anchor=tk.NW, fill=tk.X, pady=(10,0))

    def update_engine_skill(self, event=None):
        if self.engine and self.engine.process:
            new_skill = self.engine_skill_var.get()
            self.engine.set_skill_level(new_skill)

    def get_square_coords(self, square_index):
        file = chess.square_file(square_index)
        rank = chess.square_rank(square_index)
        if self.board_orientation_white_pov:
            x = file * SQUARE_SIZE
            y = (7 - rank) * SQUARE_SIZE
        else:
            x = (7 - file) * SQUARE_SIZE
            y = rank * SQUARE_SIZE
        return x, y

    def get_square_from_coords(self, x, y):
        file_coord = int(x // SQUARE_SIZE)
        rank_coord = int(y // SQUARE_SIZE)
        
        if self.board_orientation_white_pov:
            file = file_coord
            rank = 7 - rank_coord
        else:
            file = 7 - file_coord
            rank = rank_coord
            
        if 0 <= file <= 7 and 0 <= rank <= 7:
            return chess.square(file, rank)
        return None

    def update_board_display(self, move_to_animate=None, captured=False, is_reverse_animation=False, animated_piece_symbol=None):
        if self.is_animating: return
        self.board_canvas.delete("piece", "arrow")
        self.clear_highlighted_squares()

        if move_to_animate and animated_piece_symbol:
            self.is_animating = True
            self.animate_move(move_to_animate, captured, is_reverse_animation, animated_piece_symbol)
        else:
            self._draw_all_pieces()
            self._draw_move_arrows()

    def _draw_all_pieces(self):
        self.board_canvas.delete("piece")
        for sq_idx in chess.SQUARES:
            piece = self.board_state.piece_at(sq_idx)
            if piece:
                symbol = piece.symbol()
                if symbol in self.piece_images and self.piece_images[symbol]:
                    x, y = self.get_square_coords(sq_idx)
                    self.board_canvas.create_image(x, y, anchor=tk.NW, image=self.piece_images[symbol], tags=("piece", f"piece_at_{sq_idx}"))

    def _draw_move_arrows(self):
        self.board_canvas.delete("arrow")
        if self.current_game_node and self.current_game_node.move:
            move = self.current_game_node.move
            self.draw_arrow(move.from_square, move.to_square, color="#3366CC", width=3, tag="last_move_arrow")
        if self.best_move_from_engine and self.board_state.is_legal(self.best_move_from_engine):
            self.draw_arrow(self.best_move_from_engine.from_square, self.best_move_from_engine.to_square, color="#228B22", width=4, tag="best_move_arrow")

    def animate_move(self, move, captured, is_reverse_animation, piece_symbol):
        from_sq_anim, to_sq_anim = (move.to_square, move.from_square) if is_reverse_animation else (move.from_square, move.to_square)
        start_x, start_y = self.get_square_coords(from_sq_anim)
        end_x, end_y = self.get_square_coords(to_sq_anim)

        if piece_symbol not in self.piece_images or not self.piece_images[piece_symbol]:
            self._finalize_animation_and_update()
            return
            
        animated_image = self.piece_images[piece_symbol]
        self.animating_piece_id = self.board_canvas.create_image(start_x, start_y, anchor=tk.NW, image=animated_image, tags="anim_piece")
        self.board_canvas.tag_raise(self.animating_piece_id)
        
        self.board_canvas.delete(f"piece_at_{from_sq_anim}")
        if not is_reverse_animation and captured:
            self.board_canvas.delete(f"piece_at_{to_sq_anim}")

        dx = (end_x - start_x) / ANIMATION_STEPS
        dy = (end_y - start_y) / ANIMATION_STEPS

        def animation_step(current_step):
            if current_step <= ANIMATION_STEPS:
                self.board_canvas.move(self.animating_piece_id, dx, dy)
                self.root.after(ANIMATION_DELAY, lambda: animation_step(current_step + 1))
            else:
                self.board_canvas.delete(self.animating_piece_id)
                self.animating_piece_id = None
                self._finalize_animation_and_update(played_sound=is_reverse_animation, captured=captured)
        
        animation_step(1)

    def _finalize_animation_and_update(self, played_sound=False, captured=False):
        self.is_animating = False
        if not played_sound: 
            self.play_sound(captured)
        self._draw_all_pieces()
        self._draw_move_arrows()
        self.update_info_panel()
        self.update_navigation_buttons()

    def play_sound(self, captured):
        if not self.sound_enabled: return
        try:
            sound_to_play = self.capture_sound if captured and self.capture_sound else self.move_sound
            if sound_to_play: sound_to_play.play()
        except Exception as e:
            print(f"Ошибка воспроизведения звука: {e}")

    def draw_arrow(self, from_square, to_square, color="green", width=3, tag="arrow"):
        x1_abs, y1_abs = self.get_square_coords(from_square)
        x2_abs, y2_abs = self.get_square_coords(to_square)
        x1, y1 = x1_abs + SQUARE_SIZE / 2, y1_abs + SQUARE_SIZE / 2
        x2, y2 = x2_abs + SQUARE_SIZE / 2, y2_abs + SQUARE_SIZE / 2
        self.board_canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, fill=color, width=width, tags=(tag, "arrow"))

    def update_info_panel(self):
        self.best_move_from_engine = None
        self.best_move_label.config(text="N/A")
        self.game_status_label.config(text="")

        if self.current_game_node:
            game_root_node = self.current_game_node.game()
            headers = game_root_node.headers
            info_text = f"Белые: {headers.get('White', '?')} ({headers.get('WhiteElo', 'N/A')})\n"
            info_text += f"Черные: {headers.get('Black', '?')} ({headers.get('BlackElo', 'N/A')})\n"
            info_text += f"Результат: {headers.get('Result', '*')}, Событие: {headers.get('Event', '?')}"
            self.game_info_label.config(text=info_text)

            self.moves_listbox.delete(0, tk.END)
            self.move_nodes_in_listbox = []
            
            path_to_current = []
            node = self.current_game_node
            while node is not None:
                path_to_current.append(node)
                node = node.parent
            path_to_current.reverse()

            board_for_san = game_root_node.board()
            self.moves_listbox.insert(tk.END, "--- Начало ---")
            self.move_nodes_in_listbox.append(game_root_node)

            for node in path_to_current:
                if not node.move: continue
                
                san_move = board_for_san.san(node.move)
                display_text = ""
                if board_for_san.turn == chess.WHITE:
                    display_text = f"{board_for_san.fullmove_number}. {san_move}"
                else:
                    display_text = f"{board_for_san.fullmove_number}... {san_move}"
                
                self.moves_listbox.insert(tk.END, display_text)
                self.move_nodes_in_listbox.append(node)
                
                try:
                    board_for_san.push(node.move)
                except Exception as e: 
                    print(f"Ошибка применения хода для SAN: {node.move} на доске {board_for_san.fen()} - {e}")
                    break 

            try:
                idx_to_select = self.move_nodes_in_listbox.index(self.current_game_node)
                self.moves_listbox.selection_clear(0, tk.END)
                self.moves_listbox.selection_set(idx_to_select)
                self.moves_listbox.see(idx_to_select)
            except (ValueError, tk.TclError): pass
            
            self.check_game_status()
            if not self.board_state.is_game_over():
                self.request_analysis_current_pos()
            else:
                self.evaluation_label.config(text="Игра окончена")
                self.best_move_label.config(text="-")
                self.update_eval_bar(None, None)
                self.best_move_from_engine = None
                self._draw_move_arrows()
        else:
            self.game_info_label.config(text="Партия не загружена")
            self.moves_listbox.delete(0, tk.END)
            self.evaluation_label.config(text="N/A")
            self.best_move_label.config(text="N/A")
            self.game_status_label.config(text="")
            self.update_eval_bar(None, None)
            
    def check_game_status(self):
        status_text, color = "", "blue"
        if self.board_state.is_checkmate():
            winner = "Белые" if self.board_state.turn == chess.BLACK else "Черные"
            status_text, color = f"ШАХ И МАТ! {winner} победили.", "red"
        elif self.board_state.is_stalemate(): status_text = "ПАТ! Ничья."
        elif self.board_state.is_insufficient_material(): status_text = "Ничья (недостаточно материала)."
        elif self.board_state.is_seventyfive_moves(): status_text = "Ничья (правило 75 ходов)."
        elif self.board_state.is_fivefold_repetition(): status_text = "Ничья (5-кратное повторение)."
        self.game_status_label.config(text=status_text, foreground=color)

    def update_eval_bar(self, score_cp, score_mate, max_eval_cp=1000):
        bar_width = self.eval_bar_canvas.winfo_width()
        if bar_width <= 1: bar_width = BOARD_IMG_WIDTH
        text_to_display, normalized_score = "N/A", 0.5

        if self.board_state.is_checkmate():
            normalized_score = 1.0 if self.board_state.turn == chess.BLACK else 0.0
            text_to_display = "MАТ"
        elif score_mate is not None:
            effective_mate_score = score_mate if self.board_state.turn == chess.WHITE else -score_mate
            text_to_display = f"M{effective_mate_score}"
            normalized_score = 1.0 if effective_mate_score > 0 else 0.0
        elif score_cp is not None:
            actual_score_cp = score_cp if self.board_state.turn == chess.WHITE else -score_cp
            clamped_score = max(-max_eval_cp, min(max_eval_cp, actual_score_cp))
            normalized_score = (clamped_score / max_eval_cp) * 0.5 + 0.5
            text_to_display = f"{actual_score_cp / 100.0:+.2f}"
        
        white_width = bar_width * normalized_score
        self.eval_bar_canvas.coords(self.eval_line, 0, 0, white_width, EVAL_BAR_HEIGHT)
        self.eval_bar_canvas.itemconfig(self.eval_line, fill="white")
        
        self.eval_bar_canvas.delete("black_eval_part")
        self.eval_bar_canvas.create_rectangle(white_width, 0, bar_width, EVAL_BAR_HEIGHT, fill="black", outline="", tags="black_eval_part")
        
        self.eval_bar_canvas.tag_raise(self.eval_text)
        self.eval_bar_canvas.coords(self.eval_text, bar_width / 2, EVAL_BAR_HEIGHT / 2)
        self.eval_bar_canvas.itemconfig(self.eval_text, text=text_to_display)

    def load_pgn(self):
        if self.is_animating: return
        filepath = filedialog.askopenfilename(title="Открыть PGN", filetypes=(("PGN files", "*.pgn"), ("All files", "*.*")))
        if not filepath: return
        try:
            with open(filepath, encoding='utf-8-sig') as pgn_file: 
                game = chess.pgn.read_game(pgn_file)
            if game is None:
                messagebox.showerror("Ошибка PGN", "Не удалось прочитать PGN файл. Возможно, он пуст или имеет неверный формат.")
                return
            self.current_game_node = game 
            self.board_state = game.board()
            self.board_orientation_white_pov = True
            self.update_board_display() 
            self.update_info_panel() 
            self.update_navigation_buttons()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки PGN", f"Произошла ошибка: {e}")

    def load_fen_dialog(self):
        if self.is_animating: return
        fen = simpledialog.askstring("Загрузить FEN", "Введите строку FEN:", parent=self.root)
        if fen:
            try:
                new_board = chess.Board(fen)
                game = chess.pgn.Game()
                game.setup(new_board) 
                self.current_game_node = game 
                self.board_state = new_board
                self.update_board_display()
                self.update_info_panel() 
                self.update_navigation_buttons()
            except ValueError:
                messagebox.showerror("Ошибка FEN", "Неверная строка FEN.")

    def export_fen_to_clipboard(self):
        if self.is_animating: return
        fen = self.board_state.fen()
        self.root.clipboard_clear()
        self.root.clipboard_append(fen)
        messagebox.showinfo("FEN Экспортирован", "Текущий FEN скопирован в буфер обмена.")

    def _set_active_node(self, target_node, is_forward_move=None, move_to_animate=None):
        if self.is_animating or target_node is None: return

        animated_piece_symbol = None
        captured = False

        if move_to_animate:
            if is_forward_move:
                piece_obj = target_node.board().piece_at(move_to_animate.to_square)
                if piece_obj: animated_piece_symbol = piece_obj.symbol()
                elif move_to_animate.promotion: 
                    animated_piece_symbol = chess.Piece(move_to_animate.promotion, not target_node.board().turn).symbol()
                
                if target_node.parent:
                    board_before_move = target_node.parent.board()
                    captured = board_before_move.is_capture(move_to_animate) or board_before_move.is_en_passant(move_to_animate)
            else:
                piece_obj = self.board_state.piece_at(move_to_animate.to_square)
                if piece_obj: animated_piece_symbol = piece_obj.symbol()
                elif move_to_animate.promotion:
                    pawn_color = target_node.board().turn
                    animated_piece_symbol = chess.Piece(chess.PAWN, pawn_color).symbol()

        self.current_game_node = target_node
        self.board_state = self.current_game_node.board()
        self.update_board_display(move_to_animate=move_to_animate, captured=captured, 
                                  is_reverse_animation=(not is_forward_move), 
                                  animated_piece_symbol=animated_piece_symbol)
            
    def next_move_action(self):
        if self.current_game_node and self.current_game_node.variations:
            target_node = self.current_game_node.variation(0)
            self._set_active_node(target_node, is_forward_move=True, move_to_animate=target_node.move)

    def prev_move_action(self):
        if self.current_game_node and self.current_game_node.parent is not None:
            move_to_undo = self.current_game_node.move
            target_node = self.current_game_node.parent
            self._set_active_node(target_node, is_forward_move=False, move_to_animate=move_to_undo)

    def on_move_select_from_listbox(self, event):
        if self.is_animating: return
        selection = event.widget.curselection()
        if not selection: return
        
        selected_idx = selection[0]
        if 0 <= selected_idx < len(self.move_nodes_in_listbox):
            target_node = self.move_nodes_in_listbox[selected_idx]
            if target_node == self.current_game_node: return

            self.current_game_node = target_node
            self.board_state = target_node.board()
            self.update_board_display()
            self.update_info_panel()
            self.update_navigation_buttons()

    def update_navigation_buttons(self):
        if self.current_game_node:
            self.prev_move_button.config(state=tk.NORMAL if self.current_game_node.parent is not None else tk.DISABLED)
            self.next_move_button.config(state=tk.NORMAL if self.current_game_node.variations else tk.DISABLED)
        else:
            self.prev_move_button.config(state=tk.DISABLED)
            self.next_move_button.config(state=tk.DISABLED)

    def flip_board(self):
        if self.is_animating: return
        self.board_orientation_white_pov = not self.board_orientation_white_pov
        self.clear_highlighted_squares()
        self.selected_square_for_move = None
        self.update_board_display()

    def on_board_click(self, event):
        if self.is_animating or self.board_state.is_game_over(): return
        clicked_square = self.get_square_from_coords(event.x, event.y)
        if clicked_square is None: return

        if self.selected_square_for_move is not None:
            from_sq = self.selected_square_for_move
            to_sq = clicked_square
            
            move = chess.Move(from_sq, to_sq)
            piece = self.board_state.piece_at(from_sq)
            if piece and piece.piece_type == chess.PAWN:
                is_white_promo = (piece.color == chess.WHITE and chess.square_rank(to_sq) == 7)
                is_black_promo = (piece.color == chess.BLACK and chess.square_rank(to_sq) == 0)
                if is_white_promo or is_black_promo:
                    promo_char = simpledialog.askstring("Превращение", "Превратить в (q, r, b, n)?", parent=self.root, initialvalue="q")
                    if promo_char and promo_char.lower() in ['q', 'r', 'b', 'n']:
                        move.promotion = chess.PIECE_SYMBOLS.index(promo_char.lower())
                    else:
                        self.selected_square_for_move = None
                        self.clear_highlighted_squares()
                        return
            
            self.selected_square_for_move = None 
            self.clear_highlighted_squares()

            if self.board_state.is_legal(move):
                self.make_user_move(move)
            elif self.board_state.piece_at(to_sq) and self.board_state.piece_at(to_sq).color == self.board_state.turn:
                self.selected_square_for_move = to_sq
                self.highlight_legal_moves(to_sq)
        else: 
            piece_at_click = self.board_state.piece_at(clicked_square)
            if piece_at_click and piece_at_click.color == self.board_state.turn:
                self.selected_square_for_move = clicked_square
                self.highlight_legal_moves(clicked_square)

    def make_user_move(self, move):
        if not self.board_state.is_legal(move): return
        
        captured = self.board_state.is_capture(move) or self.board_state.is_en_passant(move)
        
        new_node = None
        if self.current_game_node:
            new_node = self.current_game_node.add_variation(move)
        else:
            game = chess.pgn.Game()
            game.setup(self.board_state)
            new_node = game.add_main_variation(move)

        self.current_game_node = new_node
        self.board_state = self.current_game_node.board()

        animated_piece_symbol = None
        p_obj = self.board_state.piece_at(move.to_square)
        if p_obj: 
            animated_piece_symbol = p_obj.symbol()
        elif move.promotion: 
            animated_piece_symbol = chess.Piece(move.promotion, not self.board_state.turn).symbol()

        self.update_board_display(move_to_animate=move, captured=captured, animated_piece_symbol=animated_piece_symbol)

    def highlight_legal_moves(self, from_square):
        self.clear_highlighted_squares()
        x, y = self.get_square_coords(from_square)
        self.board_canvas.create_rectangle(x, y, x + SQUARE_SIZE, y + SQUARE_SIZE, outline="#FFD700", width=4, tags="highlight_selected")
        
        for move in self.board_state.legal_moves:
            if move.from_square == from_square:
                to_x, to_y = self.get_square_coords(move.to_square)
                radius = SQUARE_SIZE / 6
                fill_color_solid = "#A0A0A0" if not self.board_state.is_capture(move) else "#FF6060"
                self.board_canvas.create_oval(to_x + SQUARE_SIZE/2 - radius, to_y + SQUARE_SIZE/2 - radius, 
                                            to_x + SQUARE_SIZE/2 + radius, to_y + SQUARE_SIZE/2 + radius, 
                                            fill=fill_color_solid, outline="", tags="highlight")

    def clear_highlighted_squares(self):
        self.board_canvas.delete("highlight_selected", "highlight")

    def request_analysis_current_pos(self):
        if self.is_animating:
            self.root.after(ANIMATION_STEPS * ANIMATION_DELAY + 200, self.request_analysis_current_pos)
            return
        if not self.engine or not self.engine.process or self.board_state.is_game_over():
            return
        
        self.evaluation_label.config(text="Анализ...")
        self.best_move_label.config(text="Анализ...")
        current_fen = self.board_state.fen()
        threading.Thread(target=self._run_engine_analysis, args=(current_fen,), daemon=True).start()

    def _run_engine_analysis(self, fen_string):
        if not self.engine or not self.engine.process: return
        self.engine.set_position_from_fen(fen_string)
        score_cp, score_mate, best_move_uci = self.engine.get_evaluation_and_best_move(movetime_ms=1000)
        self.analysis_queue.put((score_cp, score_mate, best_move_uci, fen_string))

    def process_analysis_queue(self):
        try:
            score_cp, score_mate, best_move_uci, analyzed_fen = self.analysis_queue.get_nowait()
            
            if self.board_state.fen() != analyzed_fen or self.is_animating:
                self.root.after(100, self.process_analysis_queue); return

            if score_mate is not None:
                actual_mate_val = score_mate if self.board_state.turn == chess.WHITE else -score_mate
                self.evaluation_label.config(text=f"Мат в {abs(score_mate)} ({'+' if actual_mate_val > 0 else ''})")
            elif score_cp is not None:
                actual_score_cp = score_cp if self.board_state.turn == chess.WHITE else -score_cp
                self.evaluation_label.config(text=f"{actual_score_cp / 100.0:+.2f}")
            else: self.evaluation_label.config(text="N/A")
            
            self.update_eval_bar(score_cp, score_mate)
            new_best_move_obj = None
            if best_move_uci and best_move_uci != "(none)":
                try:
                    move = self.board_state.parse_uci(best_move_uci)
                    if self.board_state.is_legal(move): 
                        new_best_move_obj = move
                        self.best_move_label.config(text=self.board_state.san(move))
                    else: self.best_move_label.config(text=f"Нелегальный ход: {best_move_uci}")
                except ValueError: self.best_move_label.config(text=f"Ошибка UCI: {best_move_uci}")
            else: self.best_move_label.config(text="-" if self.board_state.is_game_over() else "N/A")
            
            if self.best_move_from_engine != new_best_move_obj:
                self.best_move_from_engine = new_best_move_obj
                self._draw_move_arrows()
        except queue.Empty: pass
        finally: self.root.after(100, self.process_analysis_queue)

    def handle_resize(self, event):
        if event.widget != self.root:
            return
            
        current_width = self.root.winfo_width()
        
        if current_width < COMPACT_MODE_THRESHOLD and not self.is_compact_mode:
            self.info_panel.pack_forget()
            self.is_compact_mode = True
        elif current_width >= COMPACT_MODE_THRESHOLD and self.is_compact_mode:
            self.info_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
            self.is_compact_mode = False

    def on_closing(self):
        self.is_animating = False
        if self.engine and self.engine.process : self.engine.quit_engine()
        if self.sound_enabled and pygame.mixer.get_init(): pygame.mixer.quit()
        self.root.destroy()

if __name__ == "__main__":
    if not os.path.exists(ASSETS_DIR):
        print(f"Критическая ошибка: Директория с ресурсами '{ASSETS_DIR}' не найдена.")
        print("Убедитесь, что программа запускается из правильной папки, и все ресурсы на месте.")
    else:
        root = tk.Tk()
        app = ChessAnalyzerApp(root)
        root.mainloop()