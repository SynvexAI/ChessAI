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

        try:
            pygame.mixer.init()
            self.move_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "move.wav"))
            self.capture_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "capture.wav"))
            self.sound_enabled = True
        except Exception as e:
            self.sound_enabled = False
            self.move_sound = None
            self.capture_sound = None
            print(f"Sound init error: {e}")

        self.piece_images = {}
        self.current_game_node = None
        self.board_state = chess.Board()
        self.board_orientation_white_pov = True
        
        self.engine_skill_var = tk.IntVar(value=20) # Default skill
        self.engine = EngineHandler(initial_skill_level=self.engine_skill_var.get())
        if not self.engine.process:
            messagebox.showwarning("Engine Error", f"Stockfish not found or failed to start from '{self.engine.engine_path}'. Analysis unavailable.")
        
        self.analysis_queue = queue.Queue()
        self.best_move_from_engine = None
        self.animating_piece_id = None
        self.is_animating = False

        self.selected_square_for_move = None
        self.highlighted_squares_ids = []

        self.load_assets()
        self.create_widgets()
        
        self.board_canvas.bind("<Button-1>", self.on_board_click)
        
        self.update_board_display()
        self.update_info_panel()
        self.process_analysis_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_assets(self):
        try:
            board_img_path = os.path.join(IMAGE_DIR, "board.png")
            pil_board_image = Image.open(board_img_path).resize((BOARD_IMG_WIDTH, BOARD_IMG_HEIGHT), Image.LANCZOS)
            self.board_bg_image = ImageTk.PhotoImage(pil_board_image)

            for symbol, filename in PIECE_SYMBOL_TO_FILE.items():
                path = os.path.join(PIECE_DIR, "white" if symbol.isupper() else "black", filename)
                try:
                    img = Image.open(path).resize((SQUARE_SIZE, SQUARE_SIZE), Image.LANCZOS)
                    self.piece_images[symbol] = ImageTk.PhotoImage(img)
                except FileNotFoundError:
                    self.piece_images[symbol] = None
        except Exception as e:
            messagebox.showerror("Asset Load Error", f"Critical asset error: {e}")
            if self.engine and self.engine.process: self.engine.quit_engine()
            self.root.quit()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.board_canvas = tk.Canvas(left_frame, width=BOARD_IMG_WIDTH, height=BOARD_IMG_HEIGHT, borderwidth=0, highlightthickness=0)
        self.board_canvas.pack()
        if hasattr(self, 'board_bg_image'):
             self.board_canvas.create_image(0, 0, anchor=tk.NW, image=self.board_bg_image, tags="board_bg")

        pgn_controls_frame = ttk.Frame(left_frame)
        pgn_controls_frame.pack(fill=tk.X, pady=5)
        self.load_pgn_button = ttk.Button(pgn_controls_frame, text="Load PGN", command=self.load_pgn)
        self.load_pgn_button.pack(side=tk.LEFT, padx=(0,5))
        self.prev_move_button = ttk.Button(pgn_controls_frame, text="< Prev", command=self.prev_move_action, state=tk.DISABLED)
        self.prev_move_button.pack(side=tk.LEFT, padx=5)
        self.next_move_button = ttk.Button(pgn_controls_frame, text="Next >", command=self.next_move_action, state=tk.DISABLED)
        self.next_move_button.pack(side=tk.LEFT, padx=5)
        self.flip_board_button = ttk.Button(pgn_controls_frame, text="Flip", command=self.flip_board)
        self.flip_board_button.pack(side=tk.LEFT, padx=5)
        
        fen_frame = ttk.Frame(left_frame)
        fen_frame.pack(fill=tk.X, pady=5)
        self.load_fen_button = ttk.Button(fen_frame, text="Load FEN", command=self.load_fen_dialog)
        self.load_fen_button.pack(side=tk.LEFT, padx=(0,5))
        self.export_fen_button = ttk.Button(fen_frame, text="Copy FEN", command=self.export_fen_to_clipboard)
        self.export_fen_button.pack(side=tk.LEFT, padx=5)

        self.eval_bar_canvas = tk.Canvas(left_frame, height=EVAL_BAR_HEIGHT, bg="dim gray")
        self.eval_bar_canvas.pack(fill=tk.X, pady=(5,0))
        self.eval_line = self.eval_bar_canvas.create_rectangle(0, 0, BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT, fill="white", outline="")
        self.eval_text = self.eval_bar_canvas.create_text(BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT / 2, text="0.0", fill="black", font=("Arial", 10, "bold"))

        self.info_panel = ttk.Frame(main_frame, width=INFO_PANEL_WIDTH, padding=5)
        self.info_panel.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.info_panel.pack_propagate(False)

        ttk.Label(self.info_panel, text="Game Info:", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        self.game_info_label = ttk.Label(self.info_panel, text="No game loaded", wraplength=INFO_PANEL_WIDTH - 10, justify=tk.LEFT)
        self.game_info_label.pack(anchor=tk.NW, pady=5, fill=tk.X)

        ttk.Label(self.info_panel, text="Moves:", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(10,0))
        moves_frame = ttk.Frame(self.info_panel)
        moves_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.moves_scrollbar = ttk.Scrollbar(moves_frame, orient=tk.VERTICAL)
        self.moves_listbox = tk.Listbox(moves_frame, yscrollcommand=self.moves_scrollbar.set, exportselection=False, font=("Courier", 10))
        self.moves_scrollbar.config(command=self.moves_listbox.yview)
        self.moves_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.moves_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.moves_listbox.bind('<<ListboxSelect>>', self.on_move_select_from_listbox)

        ttk.Label(self.info_panel, text="Current Move:", font=("Arial", 10)).pack(anchor=tk.W)
        self.current_move_label = ttk.Label(self.info_panel, text="-", font=("Arial", 10, "italic"))
        self.current_move_label.pack(anchor=tk.NW, fill=tk.X)

        self.analyze_button = ttk.Button(self.info_panel, text="Analyze Current Position", command=self.request_analysis_current_pos)
        self.analyze_button.pack(fill=tk.X, pady=(5,0))

        engine_skill_frame = ttk.Frame(self.info_panel)
        engine_skill_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Label(engine_skill_frame, text="Engine Skill (0-20):").pack(side=tk.LEFT)
        self.skill_scale = ttk.Scale(engine_skill_frame, from_=0, to=20, orient=tk.HORIZONTAL, variable=self.engine_skill_var, command=self.update_engine_skill)
        self.skill_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.skill_label_value = ttk.Label(engine_skill_frame, textvariable=self.engine_skill_var, width=2) # To display current value
        self.skill_label_value.pack(side=tk.LEFT)


        ttk.Label(self.info_panel, text="Engine Eval:", font=("Arial", 10)).pack(anchor=tk.W, pady=(5,0))
        self.evaluation_label = ttk.Label(self.info_panel, text="N/A", font=("Arial", 10, "italic"))
        self.evaluation_label.pack(anchor=tk.NW, fill=tk.X)
        
        ttk.Label(self.info_panel, text="Best Move:", font=("Arial", 10)).pack(anchor=tk.W, pady=(5,0))
        self.best_move_label = ttk.Label(self.info_panel, text="N/A", font=("Arial", 10, "italic"))
        self.best_move_label.pack(anchor=tk.NW, fill=tk.X)
        
        self.game_status_label = ttk.Label(self.info_panel, text="", font=("Arial", 10, "bold"), foreground="blue")
        self.game_status_label.pack(anchor=tk.NW, fill=tk.X, pady=(10,0))

    def update_engine_skill(self, event=None): # event is passed by Scale command
        if self.engine and self.engine.process:
            new_skill = self.engine_skill_var.get()
            self.engine.set_skill_level(new_skill)

    def get_square_coords(self, square_index):
        file = chess.square_file(square_index)
        rank = chess.square_rank(square_index)
        x = (file * SQUARE_SIZE) if self.board_orientation_white_pov else ((7 - file) * SQUARE_SIZE)
        y = ((7 - rank) * SQUARE_SIZE) if self.board_orientation_white_pov else (rank * SQUARE_SIZE)
        return x, y

    def get_square_from_coords(self, x, y):
        file = int(x // SQUARE_SIZE)
        rank = int(y // SQUARE_SIZE)
        if not self.board_orientation_white_pov:
            file = 7 - file
            rank = 7 - rank 
        else:
            rank = 7 - rank 
        if 0 <= file <= 7 and 0 <= rank <= 7:
            return chess.square(file, rank)
        return None

    def update_board_display(self, move_to_animate=None, captured=False, is_reverse_animation=False, animated_piece_symbol=None):
        if self.is_animating: return
        self.board_canvas.delete("piece")
        self.board_canvas.delete("arrow")
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
            self.draw_arrow(move.from_square, move.to_square, color="blue", width=3, tag="last_move_arrow")
        if self.best_move_from_engine and self.board_state.is_legal(self.best_move_from_engine):
            self.draw_arrow(self.best_move_from_engine.from_square, self.best_move_from_engine.to_square, color="green", width=4, tag="best_move_arrow")

    def animate_move(self, move, captured, is_reverse_animation, piece_symbol):
        from_sq_anim, to_sq_anim = (move.to_square, move.from_square) if is_reverse_animation else (move.from_square, move.to_square)
        start_x, start_y = self.get_square_coords(from_sq_anim)
        end_x, end_y = self.get_square_coords(to_sq_anim)

        if piece_symbol not in self.piece_images or not self.piece_images[piece_symbol]:
            self._finalize_animation_and_update(move, captured, is_reverse_animation)
            return
            
        animated_image = self.piece_images[piece_symbol]
        self.animating_piece_id = self.board_canvas.create_image(start_x, start_y, anchor=tk.NW, image=animated_image, tags="anim_piece")
        self.board_canvas.tag_raise(self.animating_piece_id)
        self.board_canvas.delete("piece")
        
        board_for_static_pieces = None
        if is_reverse_animation:
            board_for_static_pieces = self.board_state # State we are going to
        else: # Forward animation
            if self.current_game_node and self.current_game_node.parent:
                board_for_static_pieces = self.current_game_node.parent.board()
            else: # E.g. first user move from initial setup or FEN
                 temp_board = chess.Board(self.board_state.fen())
                 if self.board_state.move_stack: # If the board_state is already *after* the move
                     try: temp_board.pop() # Get state before
                     except IndexError: pass
                 board_for_static_pieces = temp_board

        if board_for_static_pieces:
            for sq_idx in chess.SQUARES:
                if sq_idx == from_sq_anim : continue 
                piece_on_sq = board_for_static_pieces.piece_at(sq_idx)
                if piece_on_sq:
                    symbol_static = piece_on_sq.symbol()
                    if symbol_static in self.piece_images and self.piece_images[symbol_static]:
                        x_static, y_static = self.get_square_coords(sq_idx)
                        if not (not is_reverse_animation and captured and sq_idx == to_sq_anim):
                             self.board_canvas.create_image(x_static, y_static, anchor=tk.NW, image=self.piece_images[symbol_static], tags=("piece", f"piece_at_{sq_idx}"))
        
        self._draw_move_arrows()
        dx = (end_x - start_x) / ANIMATION_STEPS
        dy = (end_y - start_y) / ANIMATION_STEPS

        def animation_step(current_step):
            if current_step <= ANIMATION_STEPS:
                self.board_canvas.coords(self.animating_piece_id, start_x + dx * current_step, start_y + dy * current_step)
                self.root.after(ANIMATION_DELAY, lambda: animation_step(current_step + 1))
            else:
                self.board_canvas.delete(self.animating_piece_id)
                self.animating_piece_id = None
                self._finalize_animation_and_update(move, captured, is_reverse_animation)
        animation_step(1)

    def _finalize_animation_and_update(self, move, captured, is_reverse_animation):
        self.is_animating = False
        if not is_reverse_animation: 
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
            print(f"Sound playback error: {e}")

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
            info_text = f"W: {headers.get('White', '?')} ({headers.get('WhiteElo', '')}) B: {headers.get('Black', '?')} ({headers.get('BlackElo', '')})\n"
            info_text += f"Res: {headers.get('Result', '*')} Evt: {headers.get('Event', '?')} ({headers.get('Site', '')}, {headers.get('Date', '?')})"
            self.game_info_label.config(text=info_text)

            self.moves_listbox.delete(0, tk.END)
            self.move_nodes_in_listbox = []
            
            self.moves_listbox.insert(tk.END, "--- Start ---")
            self.move_nodes_in_listbox.append(game_root_node)

            board_for_san = game_root_node.board() # Initial board for SAN generation
            for node in game_root_node.mainline_nodes():
                if node.move is None: # This is the root node itself, already handled.
                    if node == game_root_node: continue
                    # This case (None move not at root in mainline_nodes) should ideally not happen.
                    # If it does, it means a node without a move, which is unusual for mainline.
                    # We'll just skip adding it to listbox and nodes list if no move.
                    continue 
                
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
                except Exception as e: # Should not happen if PGN is valid
                    print(f"Error pushing move for SAN: {node.move} on board {board_for_san.fen()} - {e}")
                    break # Stop processing moves if board state becomes inconsistent

            try:
                if self.current_game_node in self.move_nodes_in_listbox:
                    idx_to_select = self.move_nodes_in_listbox.index(self.current_game_node)
                    self.moves_listbox.selection_clear(0, tk.END)
                    self.moves_listbox.selection_set(idx_to_select)
                    self.moves_listbox.see(idx_to_select)
                elif not self.current_game_node.move: # If it's the root node
                    self.moves_listbox.selection_set(0)
                    self.moves_listbox.see(0)

            except (ValueError, tk.TclError): pass


            if self.current_game_node.move:
                parent_board = self.current_game_node.parent.board() if self.current_game_node.parent else chess.Board()
                self.current_move_label.config(text=parent_board.san(self.current_game_node.move))
            else:
                self.current_move_label.config(text="Initial Position")
            
            self.check_game_status()
            if not self.board_state.is_game_over():
                self.request_analysis_current_pos()
            else:
                self.evaluation_label.config(text="Game Over")
                self.best_move_label.config(text="-")
                self.update_eval_bar(None, None)
                self.best_move_from_engine = None
                self._draw_move_arrows()
        else:
            self.game_info_label.config(text="No game loaded")
            self.moves_listbox.delete(0, tk.END)
            self.current_move_label.config(text="-")
            self.evaluation_label.config(text="N/A")
            self.best_move_label.config(text="N/A")
            self.game_status_label.config(text="")
            self.update_eval_bar(None, None)
            
    def check_game_status(self):
        status_text, color = "", "blue"
        if self.board_state.is_checkmate():
            winner = "White" if self.board_state.turn == chess.BLACK else "Black"
            status_text, color = f"CHECKMATE! {winner} wins.", "red"
        elif self.board_state.is_stalemate(): status_text = "STALEMATE! Draw."
        elif self.board_state.is_insufficient_material(): status_text = "Draw (insufficient material)."
        elif self.board_state.is_seventyfive_moves(): status_text = "Draw (75-move rule)."
        elif self.board_state.is_fivefold_repetition(): status_text = "Draw (5-fold repetition)."
        self.game_status_label.config(text=status_text, foreground=color)

    def update_eval_bar(self, score_cp, score_mate, max_eval_cp=1000):
        bar_width = self.eval_bar_canvas.winfo_width()
        if bar_width <= 1: bar_width = BOARD_IMG_WIDTH
        text_to_display, normalized_score = "N/A", 0.5

        if self.board_state.is_checkmate():
            normalized_score = 1.0 if self.board_state.turn == chess.BLACK else 0.0
            text_to_display = "M+" if self.board_state.turn == chess.BLACK else "M-"
        elif score_mate is not None:
            effective_mate_score = score_mate if self.board_state.turn == chess.WHITE else -score_mate
            text_to_display_mate_val = score_mate if self.board_state.turn == chess.WHITE else -score_mate
            text_to_display = f"M{'+' if text_to_display_mate_val > 0 else ''}{text_to_display_mate_val}"
            normalized_score = 1.0 if effective_mate_score > 0 else 0.0
        elif score_cp is not None:
            actual_score_cp = score_cp if self.board_state.turn == chess.WHITE else -score_cp
            clamped_score = max(-max_eval_cp, min(max_eval_cp, actual_score_cp))
            normalized_score = (clamped_score / max_eval_cp) * 0.5 + 0.5
            text_to_display = f"{actual_score_cp / 100.0:+.2f}"
        
        white_width = bar_width * normalized_score
        self.eval_bar_canvas.coords(self.eval_line, 0, 0, white_width, EVAL_BAR_HEIGHT)
        self.eval_bar_canvas.itemconfig(self.eval_line, fill="white")
        black_rect_id = self.eval_bar_canvas.find_withtag("black_eval_part")
        if black_rect_id: self.eval_bar_canvas.delete(black_rect_id)
        self.eval_bar_canvas.create_rectangle(white_width, 0, bar_width, EVAL_BAR_HEIGHT, fill="black", outline="", tags="black_eval_part")
        self.eval_bar_canvas.tag_raise(self.eval_text)
        self.eval_bar_canvas.coords(self.eval_text, bar_width / 2, EVAL_BAR_HEIGHT / 2)
        self.eval_bar_canvas.itemconfig(self.eval_text, text=text_to_display)

    def load_pgn(self):
        if self.is_animating: return
        filepath = filedialog.askopenfilename(title="Open PGN", filetypes=(("PGN files", "*.pgn"), ("All files", "*.*")))
        if not filepath: return
        try:
            with open(filepath, encoding='utf-8-sig') as pgn_file: game = chess.pgn.read_game(pgn_file)
            if game is None:
                messagebox.showerror("PGN Error", "Failed to read PGN file.")
                return
            self.current_game_node = game 
            self.board_state = game.board()
            self.board_orientation_white_pov = True
            self._draw_all_pieces() 
            self._draw_move_arrows()
            self.update_info_panel() 
            self.update_navigation_buttons()
        except Exception as e:
            messagebox.showerror("PGN Load Error", f"Error: {e}")

    def load_fen_dialog(self):
        if self.is_animating: return
        fen = simpledialog.askstring("Load FEN", "Enter FEN string:", parent=self.root)
        if fen:
            try:
                new_board = chess.Board(fen)
                game = chess.pgn.Game()
                game.setup(new_board) 
                self.current_game_node = game 
                self.board_state = new_board
                self._draw_all_pieces()
                self._draw_move_arrows()
                self.update_info_panel() 
                self.update_navigation_buttons()
            except ValueError:
                messagebox.showerror("FEN Error", "Invalid FEN string.")

    def export_fen_to_clipboard(self):
        if self.is_animating: return
        fen = self.board_state.fen()
        self.root.clipboard_clear()
        self.root.clipboard_append(fen)
        messagebox.showinfo("FEN Exported", "Current FEN copied to clipboard.")

    def _navigate_to_node(self, target_node, is_forward_move=None, is_reverse_animation=False, 
                          move_to_animate_override=None, animated_piece_symbol_override=None):
        if self.is_animating or target_node is None: return
        move_to_animate = move_to_animate_override
        animated_piece_symbol = animated_piece_symbol_override
        captured = False
        if move_to_animate:
            if is_forward_move and target_node.parent:
                board_before_move = target_node.parent.board()
                captured = board_before_move.is_capture(move_to_animate) or board_before_move.is_en_passant(move_to_animate)
        self.current_game_node = target_node
        self.board_state = self.current_game_node.board()
        self.update_board_display(move_to_animate=move_to_animate, captured=captured, 
                                  is_reverse_animation=is_reverse_animation, 
                                  animated_piece_symbol=animated_piece_symbol)
            
    def next_move_action(self):
        if self.current_game_node and self.current_game_node.variations:
            target_node = self.current_game_node.variation(0)
            move_to_animate = target_node.move
            animated_piece_symbol = None
            piece_obj = target_node.board().piece_at(move_to_animate.to_square)
            if piece_obj: animated_piece_symbol = piece_obj.symbol()
            elif move_to_animate.promotion: 
                animated_piece_symbol = chess.Piece(move_to_animate.promotion, not target_node.board().turn).symbol() # Color of piece just promoted
            self._navigate_to_node(target_node, is_forward_move=True, 
                                   move_to_animate_override=move_to_animate, 
                                   animated_piece_symbol_override=animated_piece_symbol)

    def prev_move_action(self):
        if self.current_game_node and self.current_game_node.parent is not None:
            move_being_undone = self.current_game_node.move
            target_node = self.current_game_node.parent
            animated_piece_symbol = None
            piece_obj_on_dest_sq_before_undo = self.current_game_node.board().piece_at(move_being_undone.to_square)
            if piece_obj_on_dest_sq_before_undo: 
                animated_piece_symbol = piece_obj_on_dest_sq_before_undo.symbol()
            elif move_being_undone.promotion:
                 pawn_color = target_node.board().turn # The pawn's color that was promoted
                 animated_piece_symbol = chess.Piece(chess.PAWN, pawn_color).symbol()
            self._navigate_to_node(target_node, is_forward_move=False, is_reverse_animation=True,
                                   move_to_animate_override=move_being_undone,
                                   animated_piece_symbol_override=animated_piece_symbol)

    def on_move_select_from_listbox(self, event):
        if self.is_animating: return
        selection = event.widget.curselection()
        if not selection: return
        selected_listbox_idx = selection[0]
        
        if 0 <= selected_listbox_idx < len(self.move_nodes_in_listbox):
            target_node = self.move_nodes_in_listbox[selected_listbox_idx]
            if target_node == self.current_game_node: return

            is_forward, is_reverse = False, False
            current_ply = self.current_game_node.ply() if self.current_game_node.move else -1
            target_ply = target_node.ply() if target_node.move else -1
            if target_ply > current_ply: is_forward = True
            elif target_ply < current_ply: is_reverse = True
            
            move_payload, anim_symbol = None, None
            if is_forward:
                move_payload = target_node.move
                p_obj = target_node.board().piece_at(move_payload.to_square)
                if p_obj: anim_symbol = p_obj.symbol()
                elif move_payload.promotion: anim_symbol = chess.Piece(move_payload.promotion, not target_node.board().turn).symbol()
            elif is_reverse:
                move_payload = self.current_game_node.move
                p_obj = self.current_game_node.board().piece_at(move_payload.to_square)
                if p_obj: anim_symbol = p_obj.symbol()
                elif move_payload.promotion:
                    p_color = target_node.board().turn 
                    anim_symbol = chess.Piece(chess.PAWN, p_color).symbol()
            
            self._navigate_to_node(target_node, is_forward_move=is_forward, is_reverse_animation=is_reverse,
                                   move_to_animate_override=move_payload, animated_piece_symbol_override=anim_symbol)

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
        self._draw_all_pieces()
        self._draw_move_arrows()

    def on_board_click(self, event):
        if self.is_animating or self.board_state.is_game_over(): return
        clicked_square = self.get_square_from_coords(event.x, event.y)
        if clicked_square is None: return

        if self.selected_square_for_move is not None:
            move = chess.Move(self.selected_square_for_move, clicked_square)
            piece = self.board_state.piece_at(self.selected_square_for_move)
            if piece and piece.piece_type == chess.PAWN:
                if (piece.color == chess.WHITE and chess.square_rank(clicked_square) == 7) or \
                   (piece.color == chess.BLACK and chess.square_rank(clicked_square) == 0):
                    promo_char = simpledialog.askstring("Promotion", "Promote to (q, r, b, n)?", parent=self.root, initialvalue="q")
                    if promo_char and promo_char.lower() in ['q', 'r', 'b', 'n']:
                        move.promotion = chess.PIECE_SYMBOLS.index(promo_char.lower())
                    else: 
                        self.selected_square_for_move = None
                        self.clear_highlighted_squares()
                        return 
            current_selected_sq = self.selected_square_for_move
            self.selected_square_for_move = None 
            self.clear_highlighted_squares()
            if self.board_state.is_legal(move):
                self.make_user_move(move)
            else: 
                new_piece_at_click = self.board_state.piece_at(clicked_square)
                if new_piece_at_click and new_piece_at_click.color == self.board_state.turn and clicked_square != current_selected_sq :
                    self.selected_square_for_move = clicked_square
                    self.highlight_legal_moves(clicked_square)
        else: 
            piece_at_click = self.board_state.piece_at(clicked_square)
            if piece_at_click and piece_at_click.color == self.board_state.turn:
                self.selected_square_for_move = clicked_square
                self.highlight_legal_moves(clicked_square)
            else:
                self.clear_highlighted_squares()

    def make_user_move(self, move):
        if not self.board_state.is_legal(move): return
        captured = self.board_state.is_capture(move) or self.board_state.is_en_passant(move)
        new_node = None
        if self.current_game_node:
            try: new_node = self.current_game_node.add_main_variation(move)
            except Exception: 
                try: new_node = self.current_game_node.add_variation(move, promote=True)
                except Exception as e_var: return 
        else: 
            new_game = chess.pgn.Game()
            new_game.setup(self.board_state) 
            new_node = new_game.add_main_variation(move)

        if new_node:
            self.current_game_node = new_node
            self.board_state = self.current_game_node.board()
        else: self.board_state.push(move)

        animated_piece_symbol = None
        p_obj = self.board_state.piece_at(move.to_square) # Piece is now at destination
        if p_obj: animated_piece_symbol = p_obj.symbol()
        elif move.promotion: animated_piece_symbol = chess.Piece(move.promotion, not self.board_state.turn).symbol() # Color of the piece that just promoted

        self.update_board_display(move_to_animate=move, captured=captured, animated_piece_symbol=animated_piece_symbol)

    def highlight_legal_moves(self, from_square):
        self.clear_highlighted_squares()
        piece = self.board_state.piece_at(from_square)
        if not piece or piece.color != self.board_state.turn: return
        x, y = self.get_square_coords(from_square)
        rect_id = self.board_canvas.create_rectangle(x, y, x + SQUARE_SIZE, y + SQUARE_SIZE, outline="#FFD700", width=3, tags="highlight_selected")
        for move in self.board_state.legal_moves:
            if move.from_square == from_square:
                to_x, to_y = self.get_square_coords(move.to_square)
                radius = SQUARE_SIZE / 7
                fill_color = "#A0A0A0" if not self.board_state.is_capture(move) else "#FF6060"
                self.board_canvas.create_oval(to_x + SQUARE_SIZE/2 - radius, to_y + SQUARE_SIZE/2 - radius, to_x + SQUARE_SIZE/2 + radius, to_y + SQUARE_SIZE/2 + radius, fill=fill_color, outline="", tags="highlight")

    def clear_highlighted_squares(self):
        self.board_canvas.delete("highlight_selected")
        self.board_canvas.delete("highlight")

    def request_analysis_current_pos(self):
        if self.is_animating:
            self.root.after(ANIMATION_STEPS * ANIMATION_DELAY + 200, self.request_analysis_current_pos)
            return
        if not self.engine or not self.engine.process or self.board_state.is_game_over():
            if self.board_state.is_game_over():
                self.evaluation_label.config(text="Game Over"); self.best_move_label.config(text="-")
            elif not self.engine or not self.engine.process:
                self.evaluation_label.config(text="Engine Inactive"); self.best_move_label.config(text="N/A")
            self.update_eval_bar(None, None); self.best_move_from_engine = None; self._draw_move_arrows()
            return
        self.evaluation_label.config(text="Analyzing..."); self.best_move_label.config(text="Analyzing...")
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
                self.evaluation_label.config(text=f"Mate in {abs(score_mate)} ({'+' if actual_mate_val > 0 else '-'})")
            elif score_cp is not None:
                actual_score_cp = score_cp if self.board_state.turn == chess.WHITE else -score_cp
                self.evaluation_label.config(text=f"{actual_score_cp / 100.0:+.2f}")
            else: self.evaluation_label.config(text="N/A")
            
            self.update_eval_bar(score_cp, score_mate)
            new_best_move_obj = None
            if best_move_uci and best_move_uci != "(none)":
                try:
                    move = self.board_state.parse_uci(best_move_uci)
                    if self.board_state.is_legal(move): new_best_move_obj = move; self.best_move_label.config(text=self.board_state.san(move))
                    else: self.best_move_label.config(text=f"Illegal: {best_move_uci}")
                except ValueError: self.best_move_label.config(text=f"UCI Err: {best_move_uci}")
            elif self.board_state.is_game_over(): self.best_move_label.config(text="Game Over")
            else: self.best_move_label.config(text="N/A (no move)")
            
            if self.best_move_from_engine != new_best_move_obj:
                self.best_move_from_engine = new_best_move_obj; self._draw_move_arrows()
        except queue.Empty: pass
        finally: self.root.after(100, self.process_analysis_queue)

    def on_closing(self):
        self.is_animating = False
        if self.engine and self.engine.process : self.engine.quit_engine()
        if self.sound_enabled and pygame.mixer.get_init(): pygame.mixer.quit()
        self.root.destroy()

if __name__ == "__main__":
    if not os.path.exists(ASSETS_DIR): print(f"Asset directory '{ASSETS_DIR}' not found.")
    root = tk.Tk()
    app = ChessAnalyzerApp(root)
    root.mainloop()