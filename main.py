import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog, Toplevel
from PIL import Image, ImageTk
import chess
import chess.pgn
import os
import threading
import queue
import io
import requests
import pygame
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from typing import Optional, Any, List, Dict
import random

from engine_handler import EngineHandler

BOARD_IMG_WIDTH = 600
BOARD_IMG_HEIGHT = 600
SQUARE_SIZE = BOARD_IMG_WIDTH // 8
INFO_PANEL_WIDTH = 450
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
    def __init__(self, root: tk.Tk) -> None:
        self.root: tk.Tk = root
        self.root.title("ChessAI")
        self.root.minsize(BOARD_IMG_WIDTH + 20, BOARD_IMG_HEIGHT + 120)

        self.piece_images: Dict[str, ImageTk.PhotoImage] = {}
        self.current_game_node: Optional[chess.pgn.GameNode] = None
        self.board_state: chess.Board = chess.Board()
        self.board_orientation_white_pov: bool = True

        self.is_animating: bool = False
        self.is_dragging: bool = False
        self.drag_from_square: Optional[int] = None
        self.drag_image_id: Optional[int] = None

        self.selected_square_for_move: Optional[int] = None
        self.game_mode: str = "analysis"
        self.user_color: Optional[bool] = None
        self.evaluation_history: List[float] = []

        self.init_sound()
        self.engine_skill_var = tk.IntVar(value=20)
        self.engine_multipv_var = tk.IntVar(value=3)
        self.engine_time_var = tk.IntVar(value=1200)

        self.engine: EngineHandler = EngineHandler(initial_skill_level=self.engine_skill_var.get())
        if not self.engine.process:
            messagebox.showwarning("Ошибка движка", f"Stockfish не найден. Анализ недоступен.")

        self.analysis_queue: queue.Queue = queue.Queue()
        self.threat_move_obj: Optional[chess.Move] = None

        self.load_assets()
        self.create_widgets()

        self.board_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.board_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.board_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.board_canvas.bind("<Motion>", self.on_mouse_move)
        self.board_canvas.bind("<Leave>", lambda e: self.board_canvas.configure(cursor="arrow"))

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.update_board_display()
        self.update_info_panel()
        self.process_analysis_queue()

        self.prompt_color_and_start()


    def init_sound(self) -> None:
        try:
            pygame.mixer.init()
            self.move_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "move.wav"))
            self.capture_sound = pygame.mixer.Sound(os.path.join(SOUND_DIR, "capture.wav"))
            self.sound_enabled = True
        except Exception as e:
            self.sound_enabled = False
            print(f"Ошибка инициализации звука: {e}")

    def load_assets(self) -> None:
        try:
            board_img_path = os.path.join(IMAGE_DIR, "board.png")
            pil_board_image = Image.open(board_img_path).resize((BOARD_IMG_WIDTH, BOARD_IMG_HEIGHT), Image.LANCZOS)
            self.board_bg_image = ImageTk.PhotoImage(pil_board_image)

            for symbol, filename in PIECE_SYMBOL_TO_FILE.items():
                color_folder = "white" if symbol.isupper() else "black"
                path = os.path.join(PIECE_DIR, color_folder, filename)
                img = Image.open(path).resize((SQUARE_SIZE, SQUARE_SIZE), Image.LANCZOS)
                self.piece_images[symbol] = ImageTk.PhotoImage(img)
        except Exception as e:
            messagebox.showerror("Ошибка загрузки ресурсов", f"Критическая ошибка: {e}")
            self.on_closing()


    def create_widgets(self) -> None:
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(self.main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        self.board_canvas = tk.Canvas(left_frame, width=BOARD_IMG_WIDTH, height=BOARD_IMG_HEIGHT)
        self.board_canvas.pack()
        if hasattr(self, 'board_bg_image'):
            self.board_canvas.create_image(0, 0, anchor=tk.NW, image=self.board_bg_image)

        self.create_board_controls(left_frame)

        self.info_panel = ttk.Frame(self.main_frame, width=INFO_PANEL_WIDTH)
        self.info_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.info_panel.pack_propagate(False)

        self.create_info_panel_widgets()

    def create_board_controls(self, parent):
        pgn_controls_frame = ttk.Frame(parent)
        pgn_controls_frame.pack(fill=tk.X, pady=5)

        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Загрузить PGN...", command=self.load_pgn)
        file_menu.add_command(label="Загрузить FEN...", command=self.load_fen_dialog)
        file_menu.add_command(label="Загрузить по URL (Lichess)...", command=self.load_from_url)
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить PGN с аннотациями...", command=self.save_pgn_with_annotations)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.on_closing)

        game_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Игра", menu=game_menu)
        game_menu.add_command(label="Новая игра с движком", command=self.start_new_game_vs_engine)

        self.prev_move_button = ttk.Button(pgn_controls_frame, text="<", command=self.prev_move_action, state=tk.DISABLED)
        self.prev_move_button.pack(side=tk.LEFT, padx=2)
        self.next_move_button = ttk.Button(pgn_controls_frame, text=">", command=self.next_move_action, state=tk.DISABLED)
        self.next_move_button.pack(side=tk.LEFT, padx=2)
        self.flip_board_button = ttk.Button(pgn_controls_frame, text="Перевернуть", command=self.flip_board)
        self.flip_board_button.pack(side=tk.LEFT, padx=5)
        self.copy_fen_button = ttk.Button(pgn_controls_frame, text="Копировать FEN", command=self.export_fen_to_clipboard)
        self.copy_fen_button.pack(side=tk.LEFT, padx=5)

        self.eval_bar_canvas = tk.Canvas(parent, height=EVAL_BAR_HEIGHT, bg="dim gray")
        self.eval_bar_canvas.pack(fill=tk.X, pady=(5, 0))
        self.eval_line = self.eval_bar_canvas.create_rectangle(0, 0, BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT, fill="white", outline="")
        self.eval_text = self.eval_bar_canvas.create_text(BOARD_IMG_WIDTH / 2, EVAL_BAR_HEIGHT / 2, text="0.0", fill="black", font=("Arial", 10, "bold"))

    def create_info_panel_widgets(self):
        self.notebook = ttk.Notebook(self.info_panel)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        analysis_tab = ttk.Frame(self.notebook)
        self.notebook.add(analysis_tab, text="Анализ")
        self.create_analysis_tab(analysis_tab)

        self.graph_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.graph_tab, text="График")
        self.create_graph_tab(self.graph_tab)

    def create_analysis_tab(self, parent):
        self.game_info_label = ttk.Label(parent, text="Партия не загружена", wraplength=INFO_PANEL_WIDTH - 20, justify=tk.LEFT)
        self.game_info_label.pack(anchor=tk.NW, pady=5, fill=tk.X, padx=5)

        moves_frame = ttk.Frame(parent)
        moves_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        self.moves_scrollbar = ttk.Scrollbar(moves_frame, orient=tk.VERTICAL)
        self.moves_listbox = tk.Listbox(moves_frame, yscrollcommand=self.moves_scrollbar.set, exportselection=False, font=("Courier", 10))
        self.moves_scrollbar.config(command=self.moves_listbox.yview)
        self.moves_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.moves_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.moves_listbox.bind('<<ListboxSelect>>', self.on_move_select_from_listbox)
        self.moves_listbox.bind('<Button-3>', self.show_annotation_menu)

        analysis_buttons_frame = ttk.Frame(parent)
        analysis_buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        self.analyze_game_button = ttk.Button(analysis_buttons_frame, text="Анализировать партию", command=self.start_full_game_analysis)
        self.analyze_game_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        self.threat_button = ttk.Button(analysis_buttons_frame, text="Показать угрозу", command=self.show_threat)
        self.threat_button.pack(side=tk.LEFT, expand=True, fill=tk.X)

        engine_settings_frame = ttk.LabelFrame(parent, text="Настройки движка", padding=5)
        engine_settings_frame.pack(fill=tk.X, padx=5, pady=5)

        skill_frame = ttk.Frame(engine_settings_frame)
        skill_frame.pack(fill=tk.X)
        ttk.Label(skill_frame, text="Сила (0-20):").pack(side=tk.LEFT)
        self.skill_scale = ttk.Scale(skill_frame, from_=0, to=20, orient=tk.HORIZONTAL, variable=self.engine_skill_var, command=self.update_engine_skill)
        self.skill_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(skill_frame, textvariable=self.engine_skill_var, width=2).pack(side=tk.LEFT)

        multipv_frame = ttk.Frame(engine_settings_frame)
        multipv_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(multipv_frame, text="Количество строк (1-5):").pack(side=tk.LEFT)
        self.multipv_spinbox = ttk.Spinbox(multipv_frame, from_=1, to=5, textvariable=self.engine_multipv_var, width=3, command=self.update_engine_multipv)
        self.multipv_spinbox.pack(side=tk.LEFT, padx=5)

        time_frame = ttk.Frame(engine_settings_frame)
        time_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(time_frame, text="Макс. время (мс):").pack(side=tk.LEFT)
        self.time_spinbox = ttk.Spinbox(time_frame, from_=200, to=10000, increment=100, textvariable=self.engine_time_var, width=8)
        self.time_spinbox.pack(side=tk.LEFT, padx=5)

        eval_frame = ttk.LabelFrame(parent, text="Оценка движка", padding=5)
        eval_frame.pack(fill=tk.X, padx=5, pady=5)

        columns = ('#1', '#2', '#3')
        self.eval_tree = ttk.Treeview(eval_frame, columns=columns, show='headings', height=4)
        self.eval_tree.heading('#1', text='№')
        self.eval_tree.column('#1', width=30, anchor='center')
        self.eval_tree.heading('#2', text='Ход')
        self.eval_tree.column('#2', width=100, anchor='w')
        self.eval_tree.heading('#3', text='Оценка')
        self.eval_tree.column('#3', width=80, anchor='w')
        self.eval_tree.pack(fill=tk.X, expand=True)

        self.game_status_label = ttk.Label(parent, text="", font=("Arial", 10, "bold"), foreground="blue")
        self.game_status_label.pack(anchor=tk.NW, fill=tk.X, pady=5, padx=5)

    def create_graph_tab(self, parent):
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Оценка партии")
        self.ax.set_xlabel("Номер хода")
        self.ax.set_ylabel("Оценка (сантипешки)")
        self.ax.grid(True)
        self.fig.tight_layout()

        self.graph_canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.graph_canvas.draw()
        self.graph_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.update_evaluation_graph()


    def prompt_color_and_start(self) -> None:
        """Диалог старта: Белые / Черные / Рандом / Только анализ."""
        win = Toplevel(self.root)
        win.title("Новая игра")
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text="Выберите сторону:").pack(padx=12, pady=(12, 6))

        choice = tk.StringVar(value="random")
        for text, val in (("Белыми", "white"), ("Черными", "black"), ("Случайно", "random"), ("Только анализ", "analysis")):
            ttk.Radiobutton(win, text=text, value=val, variable=choice).pack(anchor="w", padx=12)

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, pady=12, padx=12)
        ttk.Button(btns, text="OK", command=lambda: self._apply_start_choice(choice.get(), win)).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Отмена", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 6))

    def _apply_start_choice(self, val: str, dialog: Toplevel) -> None:
        dialog.destroy()
        if val == "analysis":
            self.reset_to_new_game(chess.pgn.Game())
            self.game_mode = "analysis"
            self.user_color = None
            return
        color = random.choice([chess.WHITE, chess.BLACK]) if val == "random" else (chess.WHITE if val == "white" else chess.BLACK)
        self.user_color = color
        game = chess.pgn.Game()
        game.headers["Event"] = "Игра против движка"
        game.headers["White"] = "Человек" if color == chess.WHITE else "Stockfish"
        game.headers["Black"] = "Stockfish" if color == chess.BLACK else "Человек"
        self.reset_to_new_game(game, preserve_orientation=True)
        self.board_orientation_white_pov = (self.user_color == chess.WHITE)
        self.update_board_display()
        self.game_mode = "play_engine"
        if self.board_state.turn != self.user_color:
            self.root.after(500, self.make_engine_move)


    def update_board_display(self, move_to_animate: Optional[chess.Move] = None, captured: bool = False,
                             is_reverse_animation: bool = False, animated_piece_symbol: Optional[str] = None) -> None:

        if self.is_animating:
            return
        self.board_canvas.delete("piece", "arrow", "threat_arrow")
        self.clear_highlighted_squares()
        self.threat_move_obj = None

        if move_to_animate and animated_piece_symbol:
            self.is_animating = True
            self.animate_move(move_to_animate, captured, is_reverse_animation, animated_piece_symbol)
        else:
            self._draw_all_pieces()
            self._draw_move_arrows()

    def _draw_all_pieces(self) -> None:
        self.board_canvas.delete("piece")
        for sq_idx in chess.SQUARES:
            if self.is_dragging and self.drag_from_square == sq_idx:
                continue
            piece = self.board_state.piece_at(sq_idx)
            if piece:
                symbol = piece.symbol()
                if symbol in self.piece_images:
                    x, y = self.get_square_coords(sq_idx)
                    self.board_canvas.create_image(x, y, anchor=tk.NW, image=self.piece_images[symbol],
                                                   tags=("piece", f"piece_at_{sq_idx}"))

    def _draw_move_arrows(self) -> None:
        self.board_canvas.delete("arrow")
        if self.current_game_node and self.current_game_node.move:
            move = self.current_game_node.move
            self.draw_arrow(move.from_square, move.to_square, color="#3366CC", width=3, tag="last_move_arrow")

        best_moves = self.get_best_moves_from_treeview()
        if best_moves:
            self.draw_arrow(best_moves[0].from_square, best_moves[0].to_square, color="#228B22", width=4, tag="best_move_arrow")
            for i, move in enumerate(best_moves[1:], start=1):
                self.draw_arrow(move.from_square, move.to_square, color="#FFA500", width=2, tag=f"alt_move_arrow_{i}")

        if self.threat_move_obj:
            self.draw_arrow(self.threat_move_obj.from_square, self.threat_move_obj.to_square, color="#FF0000", width=4, tag="threat_arrow")


    def update_info_panel(self) -> None:
        self.clear_evaluation_display()
        self.game_status_label.config(text="")

        if self.current_game_node:
            game_root_node = self.current_game_node.game()
            headers = game_root_node.headers
            info_text = f"Белые: {headers.get('White', '?')} ({headers.get('WhiteElo', 'Н/Д')})\n"
            info_text += f"Черные: {headers.get('Black', '?')} ({headers.get('BlackElo', 'Н/Д')})\n"
            info_text += f"Результат: {headers.get('Result', '*')}, Событие: {headers.get('Event', '?')}"
            self.game_info_label.config(text=info_text)

            self.populate_moves_listbox()
            self.check_game_status()

            if not self.board_state.is_game_over() and self.game_mode == "analysis":
                self.request_analysis_current_pos()
            else:
                self.update_eval_bar(None, None)
        else:
            self.game_info_label.config(text="Партия не загружена")
            self.moves_listbox.delete(0, tk.END)
            self.update_eval_bar(None, None)
            self.update_evaluation_graph()

    def populate_moves_listbox(self) -> None:
        self.moves_listbox.delete(0, tk.END)
        self.move_nodes_in_listbox = []

        game_root_node = self.current_game_node.game()
        board_for_san = game_root_node.board()

        self.moves_listbox.insert(tk.END, "--- Начало ---")
        self.move_nodes_in_listbox.append(game_root_node)

        for node in game_root_node.mainline():
            san_move = board_for_san.san(node.move)
            display_text = ""
            if board_for_san.turn == chess.WHITE:
                display_text = f"{board_for_san.fullmove_number}. {san_move}"
            else:
                display_text = f"{board_for_san.fullmove_number}... {san_move}"

            nag_symbols = {1: '!', 2: '?', 3: '!!', 4: '??', 5: '!?', 6: '?!'}
            nags = "".join([nag_symbols.get(nag, '') for nag in node.nags])
            if nags:
                display_text += f" {nags}"

            if "Зевок" in node.comment: display_text += " ??"
            elif "Ошибка" in node.comment: display_text += " ?"
            elif "Неточность" in node.comment: display_text += " ?!"

            self.moves_listbox.insert(tk.END, display_text)
            self.move_nodes_in_listbox.append(node)
            board_for_san.push(node.move)

        try:
            idx_to_select = self.move_nodes_in_listbox.index(self.current_game_node)
            self.moves_listbox.selection_clear(0, tk.END)
            self.moves_listbox.selection_set(idx_to_select)
            self.moves_listbox.see(idx_to_select)
        except (ValueError, tk.TclError):
            pass

    def update_evaluation_graph(self) -> None:
        self.ax.clear()
        self.ax.grid(True)
        self.ax.set_title("Оценка партии")
        self.ax.set_xlabel("Номер хода")
        self.ax.set_ylabel("Оценка (сантипешки)")

        if self.evaluation_history:
            plies = range(len(self.evaluation_history))
            self.ax.plot(plies, self.evaluation_history, marker='o', linestyle='-', markersize=4)
            self.ax.axhline(0, color='black', linewidth=0.8, linestyle='--')

            max_abs_eval = max(abs(e) for e in self.evaluation_history) if self.evaluation_history else 100
            display_max = min(max_abs_eval + 100, 1000)
            self.ax.set_ylim(-display_max, display_max)
        else:
            self.ax.text(0.5, 0.5, "Нет данных для графика.\nВыполните 'Анализировать партию'.",
                         horizontalalignment='center', verticalalignment='center', transform=self.ax.transAxes)

        self.fig.tight_layout()
        self.graph_canvas.draw()


    def load_pgn(self) -> None:
        filepath = filedialog.askopenfilename(title="Открыть PGN", filetypes=(("PGN files", "*.pgn"), ("All files", "*.*")))
        if not filepath:
            return

        try:
            with open(filepath, 'r', encoding='utf-8-sig') as pgn_file:
                pgn_text = pgn_file.read()

            pgn_io = io.StringIO(pgn_text)
            games = []
            while True:
                offset = pgn_io.tell()
                headers = chess.pgn.read_headers(pgn_io)
                if headers is None:
                    break
                games.append((headers, offset))

            if not games:
                messagebox.showerror("Ошибка PGN", "Не найдено ни одной партии в файле.")
                return

            if len(games) == 1:
                self.load_game_from_pgn(pgn_text, 0)
            else:
                self.show_pgn_selection_window(pgn_text, games)

        except Exception as e:
            messagebox.showerror("Ошибка загрузки PGN", f"Произошла ошибка: {e}")

    def show_pgn_selection_window(self, pgn_text: str, games: List[tuple[dict, int]]) -> None:
        win = Toplevel(self.root)
        win.title("Выберите партию")

        tree = ttk.Treeview(win, columns=('white', 'black', 'result'), show='headings')
        tree.heading('white', text='Белые')
        tree.heading('black', text='Черные')
        tree.heading('result', text='Результат')

        for i, (headers, offset) in enumerate(games):
            tree.insert('', 'end', values=(headers.get("White", "?"), headers.get("Black", "?"), headers.get("Result", "*")), iid=i)

        tree.pack(padx=10, pady=10, fill="both", expand=True)

        def on_load():
            selected_item = tree.selection()
            if selected_item:
                game_index = int(selected_item[0])
                offset = games[game_index][1]
                self.load_game_from_pgn(pgn_text, offset)
                win.destroy()

        load_button = ttk.Button(win, text="Загрузить", command=on_load)
        load_button.pack(pady=10)
        tree.bind("<Double-1>", lambda e: on_load())

    def load_game_from_pgn(self, pgn_text: str, offset: int) -> None:
        pgn_io = io.StringIO(pgn_text)
        pgn_io.seek(offset)
        game = chess.pgn.read_game(pgn_io)
        if game:
            self.reset_to_new_game(game, preserve_orientation=True)
        else:
            messagebox.showerror("Ошибка PGN", "Не удалось прочитать выбранную партию.")

    def load_fen_dialog(self) -> None:
        fen = simpledialog.askstring("Загрузить FEN", "Введите строку FEN:", parent=self.root)
        if fen:
            try:
                board = chess.Board(fen)
                game = chess.pgn.Game()
                game.setup(board)
                self.reset_to_new_game(game, preserve_orientation=True)
                self.game_mode = "puzzle"
                messagebox.showinfo("Режим Задачи", "Позиция загружена. Найдите лучший ход!")
            except ValueError:
                messagebox.showerror("Ошибка FEN", "Неверная строка FEN.")

    def load_from_url(self) -> None:
        url = simpledialog.askstring("Загрузить по URL", "Введите URL партии с Lichess:", parent=self.root)
        if not url or "lichess.org" not in url:
            if url:
                messagebox.showerror("Ошибка", "Поддерживаются только URL с lichess.org")
            return

        game_id = url.split('/')[-1].split('?')[0]
        if len(game_id) < 8:
            messagebox.showerror("Ошибка URL", "Неверный ID партии в URL.")
            return

        api_url = f"https://lichess.org/game/export/{game_id}"
        try:
            response = requests.get(api_url, headers={'Accept': 'application/x-chess-pgn'})
            response.raise_for_status()
            pgn_text = response.text
            self.load_game_from_pgn(pgn_text, 0)
        except requests.RequestException as e:
            messagebox.showerror("Ошибка сети", f"Не удалось загрузить партию: {e}")

    def save_pgn_with_annotations(self) -> None:
        if not self.current_game_node:
            messagebox.showwarning("Нет партии", "Сначала загрузите партию.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".pgn",
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")],
            title="Сохранить PGN как..."
        )
        if not filepath:
            return

        try:
            game = self.current_game_node.game()
            with open(filepath, 'w', encoding='utf-8') as f:
                exporter = chess.pgn.FileExporter(f)
                game.accept(exporter)
            messagebox.showinfo("Сохранено", f"Партия успешно сохранена в {filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файл: {e}")

    def export_fen_to_clipboard(self) -> None:
        fen = self.board_state.fen()
        self.root.clipboard_clear()
        self.root.clipboard_append(fen)
        messagebox.showinfo("FEN Скопирован", "Текущий FEN скопирован в буфер обмена.")


    def reset_to_new_game(self, game_node: chess.pgn.GameNode, preserve_orientation: bool = True) -> None:
        self.current_game_node = game_node
        self.board_state = game_node.board()
        if not preserve_orientation:
            self.board_orientation_white_pov = True
        self.game_mode = "analysis"
        self.selected_square_for_move = None
        self.is_dragging = False
        self.drag_from_square = None
        self.drag_image_id = None
        self.evaluation_history = []
        self.update_board_display()
        self.update_info_panel()
        self.update_navigation_buttons()
        self.update_evaluation_graph()

    def start_new_game_vs_engine(self) -> None:
        self.prompt_color_and_start()

    def make_user_move(self, move: chess.Move) -> None:
        if not self.board_state.is_legal(move):
            return

        if self.game_mode == "puzzle":
            self.check_puzzle_move(move)
            return

        captured = self.board_state.is_capture(move) or self.board_state.is_en_passant(move)
        animated_piece_symbol = self.get_animated_piece_symbol(move)

        if self.current_game_node is None:
            game = chess.pgn.Game()
            game.setup(self.board_state)
            self.current_game_node = game

        new_node = self.current_game_node.add_variation(move)

        self._set_active_node(new_node, is_forward_move=True, move_to_animate=move,
                              captured=captured, animated_piece_symbol=animated_piece_symbol)

        if self.game_mode == "play_engine" and not self.board_state.is_game_over():
            self.root.after(500, self.make_engine_move)

    def make_engine_move(self) -> None:
        if self.is_animating or self.board_state.is_game_over():
            return

        def find_and_make_move():
            _, best_move_uci = self.engine.get_analysis(movetime_ms=self.engine_time_var.get())
            if best_move_uci:
                move = chess.Move.from_uci(best_move_uci)
                if self.board_state.is_legal(move):
                    self.root.after(0, lambda: self.make_user_move(move))

        threading.Thread(target=find_and_make_move, daemon=True).start()

    def check_puzzle_move(self, user_move: chess.Move) -> None:
        def check_in_thread():
            _, best_move_uci = self.engine.get_analysis(movetime_ms=self.engine_time_var.get())
            best_move = chess.Move.from_uci(best_move_uci)

            def show_result():
                if user_move == best_move:
                    messagebox.showinfo("Правильно!", f"Отличный ход! {self.board_state.san(user_move)}")
                    self.make_user_move(user_move)
                else:
                    messagebox.showwarning("Неверно", f"Неправильный ход. Лучшим ходом был {self.board_state.san(best_move)}.")

            self.root.after(0, show_result)

        threading.Thread(target=check_in_thread, daemon=True).start()


    def start_full_game_analysis(self) -> None:
        if not self.current_game_node or not self.current_game_node.game().mainline():
            messagebox.showwarning("Нет партии", "Загрузите партию с ходами для анализа.")
            return

        self.analysis_progress_win = Toplevel(self.root)
        self.analysis_progress_win.title("Анализ")
        self.analysis_progress_win.transient(self.root)
        self.analysis_progress_win.grab_set()

        ttk.Label(self.analysis_progress_win, text="Идет анализ партии...").pack(padx=20, pady=10)
        self.progress_bar = ttk.Progressbar(self.analysis_progress_win, orient='horizontal', length=300, mode='determinate')
        self.progress_bar.pack(padx=20, pady=10)

        threading.Thread(target=self._run_full_game_analysis, daemon=True).start()

    def _run_full_game_analysis(self) -> None:
        game = self.current_game_node.game()
        nodes = list(game.mainline())
        total_moves = len(nodes)
        self.evaluation_history = []

        board = game.board()

        for i, node in enumerate(nodes):
            fen_before = board.fen()
            self.engine.set_position_from_fen(fen_before)
            analysis_before, _ = self.engine.get_analysis(movetime_ms=self.engine_time_var.get())

            if analysis_before and analysis_before[0].get('move_uci'):
                score_obj = analysis_before[0]
                score_cp = score_obj['score_cp']

                best_move_san = "N/A"
                try:
                    engine_move = chess.Move.from_uci(score_obj['move_uci'])
                    if board.is_legal(engine_move):
                        best_move_san = board.san(engine_move)
                except (ValueError, TypeError):
                    pass

                board.push(node.move)

                if score_cp is not None:
                    current_player_score = score_cp if board.turn != chess.WHITE else -score_cp
                    self.evaluation_history.append(current_player_score)

                    fen_after = board.fen()
                    self.engine.set_position_from_fen(fen_after)
                    analysis_after, _ = self.engine.get_analysis(movetime_ms=max(200, self.engine_time_var.get() // 4))

                    if analysis_after and analysis_after[0].get('score_cp') is not None:
                        score_after_cp = analysis_after[0]['score_cp']
                        next_player_score = score_after_cp if board.turn == chess.WHITE else -score_after_cp

                        eval_loss = current_player_score - (-next_player_score)

                        comment = f"[%eval {current_player_score/100.0:.2f}] Лучший ход был {best_move_san}."

                        if eval_loss > 250: comment += " (Зевок ??)"
                        elif eval_loss > 120: comment += " (Ошибка ?)"
                        elif eval_loss > 60: comment += " (Неточность ?!)"

                        node.comment = comment
                else:
                    mate_score = 10000 if score_obj.get('score_mate', 0) > 0 else -10000
                    self.evaluation_history.append(mate_score if board.turn != chess.WHITE else -mate_score)
            else:
                board.push(node.move)

            progress = (i + 1) / total_moves * 100
            self.root.after(0, lambda p=progress: self.progress_bar.config(value=p))

        def finish_analysis():
            self.analysis_progress_win.destroy()
            self.populate_moves_listbox()
            self.update_evaluation_graph()
            messagebox.showinfo("Анализ завершен", "Анализ партии окончен. Результаты добавлены в комментарии и на график.")

        self.root.after(0, finish_analysis)

    def show_threat(self) -> None:
        if self.is_animating or self.board_state.is_game_over():
            return

        def get_threat_in_thread():
            threat_uci = self.engine.get_threat(self.board_state.fen())
            if threat_uci:
                try:
                    self.threat_move_obj = self.board_state.parse_uci(threat_uci)
                    self.root.after(0, self._draw_move_arrows)
                except ValueError:
                    self.threat_move_obj = None

        threading.Thread(target=get_threat_in_thread, daemon=True).start()


    def on_mouse_move(self, event: tk.Event) -> None:
        if self.is_animating:
            return
        sq = self.get_square_from_coords(event.x, event.y)
        if sq is None:
            self.board_canvas.configure(cursor="arrow")
            return

        piece = self.board_state.piece_at(sq)
        can_move_now = (piece is not None and piece.color == self.board_state.turn)
        if self.game_mode == "play_engine":
            can_move_now = can_move_now and (self.user_color == self.board_state.turn)

        self.board_canvas.configure(cursor="hand2" if can_move_now else "arrow")

        if self.is_dragging and self.drag_image_id is not None:
            x = event.x - SQUARE_SIZE // 2
            y = event.y - SQUARE_SIZE // 2
            self.board_canvas.coords(self.drag_image_id, x, y)

    def on_mouse_down(self, event: tk.Event) -> None:
        if self.is_animating or self.board_state.is_game_over():
            return
        if self.game_mode == "play_engine" and self.board_state.turn != self.user_color:
            return

        sq = self.get_square_from_coords(event.x, event.y)
        if sq is None:
            return

        piece = self.board_state.piece_at(sq)
        if not piece or piece.color != self.board_state.turn:
            self._click_select_logic(sq)
            return

        self.is_dragging = True
        self.drag_from_square = sq
        self.highlight_legal_moves(sq)
        symbol = piece.symbol()
        img = self.piece_images.get(symbol)
        if img:
            x = event.x - SQUARE_SIZE // 2
            y = event.y - SQUARE_SIZE // 2
            self.drag_image_id = self.board_canvas.create_image(x, y, image=img, anchor=tk.NW, tags="dragging")
            self.board_canvas.delete(f"piece_at_{sq}")
        self.board_canvas.configure(cursor="hand2")

    def on_mouse_drag(self, event: tk.Event) -> None:
        if not self.is_dragging or self.drag_image_id is None:
            return
        x = event.x - SQUARE_SIZE // 2
        y = event.y - SQUARE_SIZE // 2
        self.board_canvas.coords(self.drag_image_id, x, y)

    def on_mouse_up(self, event: tk.Event) -> None:
        if self.is_dragging:
            to_sq = self.get_square_from_coords(event.x, event.y)
            from_sq = self.drag_from_square
            self._end_drag_visuals()
            if to_sq is not None and from_sq is not None:
                move = self.create_move_obj(from_sq, to_sq)
                if move and self.board_state.is_legal(move):
                    self.make_user_move(move)
                    return
            self.update_board_display()
            return

        sq = self.get_square_from_coords(event.x, event.y)
        if sq is not None:
            self._click_select_logic(sq)

    def _end_drag_visuals(self) -> None:
        self.is_dragging = False
        self.drag_from_square = None
        if self.drag_image_id is not None:
            self.board_canvas.delete(self.drag_image_id)
        self.drag_image_id = None
        self.clear_highlighted_squares()
        self.board_canvas.configure(cursor="arrow")

    def _click_select_logic(self, clicked_square: int) -> None:
        if self.selected_square_for_move is not None:
            move = self.create_move_obj(self.selected_square_for_move, clicked_square)
            self.selected_square_for_move = None
            self.clear_highlighted_squares()

            if move and self.board_state.is_legal(move):
                if self.game_mode == "play_engine" and self.board_state.turn != self.user_color:
                    return
                self.make_user_move(move)
            elif self.board_state.piece_at(clicked_square) and self.board_state.piece_at(clicked_square).color == self.board_state.turn:
                self.selected_square_for_move = clicked_square
                self.highlight_legal_moves(clicked_square)
        else:
            piece = self.board_state.piece_at(clicked_square)
            if piece and piece.color == self.board_state.turn:
                if self.game_mode == "play_engine" and self.board_state.turn != self.user_color:
                    return
                self.selected_square_for_move = clicked_square
                self.highlight_legal_moves(clicked_square)


    def next_move_action(self) -> None:
        if self.current_game_node and self.current_game_node.variations:
            target_node = self.current_game_node.variation(0)
            move = target_node.move
            captured = self.board_state.is_capture(move)
            animated_piece = self.get_animated_piece_symbol(move)
            self._set_active_node(target_node, is_forward_move=True, move_to_animate=move, captured=captured, animated_piece_symbol=animated_piece)

    def prev_move_action(self) -> None:
        if self.current_game_node and self.current_game_node.parent is not None:
            move_to_undo = self.current_game_node.move
            target_node = self.current_game_node.parent
            animated_piece = self.get_animated_piece_symbol(move_to_undo, is_undo=True)
            self._set_active_node(target_node, is_forward_move=False, move_to_animate=move_to_undo, animated_piece_symbol=animated_piece)

    def on_move_select_from_listbox(self, event: tk.Event) -> None:
        if self.is_animating or not event.widget.curselection():
            return

        selected_idx = event.widget.curselection()[0]
        if 0 <= selected_idx < len(self.move_nodes_in_listbox):
            target_node = self.move_nodes_in_listbox[selected_idx]
            if target_node != self.current_game_node:
                self._set_active_node(target_node)

    def show_annotation_menu(self, event: tk.Event) -> None:
        selection = self.moves_listbox.curselection()
        if not selection:
            return

        selected_idx = selection[0]
        if selected_idx == 0:
            return

        node_to_annotate = self.move_nodes_in_listbox[selected_idx]

        menu = tk.Menu(self.root, tearoff=0)
        nags = {
            "Хороший ход (!)": 1, "Ошибка (?)": 2, "Блестящий ход (!!)": 3,
            "Грубый зевок (??)": 4, "Интересный ход (!?)": 5, "Сомнительный ход (?!)": 6
        }
        for label, code in nags.items():
            menu.add_command(label=label, command=lambda c=code: self.add_nag_annotation(node_to_annotate, c))

        menu.add_separator()
        menu.add_command(label="Добавить/изменить комментарий...", command=lambda: self.add_text_comment(node_to_annotate))
        menu.add_command(label="Очистить аннотации", command=lambda: self.clear_annotations(node_to_annotate))

        menu.tk_popup(event.x_root, event.y_root)

    def add_nag_annotation(self, node: chess.pgn.GameNode, nag_code: int) -> None:
        node.nags.add(nag_code)
        self.populate_moves_listbox()

    def add_text_comment(self, node: chess.pgn.GameNode) -> None:
        comment = simpledialog.askstring("Комментарий", "Введите ваш комментарий:", initialvalue=node.comment, parent=self.root)
        if comment is not None:
            node.comment = comment
            self.populate_moves_listbox()

    def clear_annotations(self, node: chess.pgn.GameNode) -> None:
        node.nags.clear()
        node.comment = ""
        self.populate_moves_listbox()


    def request_analysis_current_pos(self) -> None:
        if self.is_animating or not self.engine.process or self.board_state.is_game_over():
            return

        self.clear_evaluation_display()
        current_fen = self.board_state.fen()
        threading.Thread(target=self._run_engine_analysis, args=(current_fen,), daemon=True).start()

    def _run_engine_analysis(self, fen_string: str) -> None:
        self.engine.set_position_from_fen(fen_string)
        analysis_lines, _ = self.engine.get_analysis(movetime_ms=self.engine_time_var.get())
        self.analysis_queue.put((analysis_lines, fen_string))

    def process_analysis_queue(self) -> None:
        try:
            analysis_lines, analyzed_fen = self.analysis_queue.get_nowait()

            if self.board_state.fen() != analyzed_fen or self.is_animating:
                self.root.after(100, self.process_analysis_queue); return

            if analysis_lines:
                for item in self.eval_tree.get_children():
                    self.eval_tree.delete(item)

                for line in analysis_lines:
                    move_uci = line.get('move_uci')
                    if not move_uci or move_uci == "(none)":
                        continue

                    try:
                        move = self.board_state.parse_uci(move_uci)
                        move_san = self.board_state.san(move)

                        eval_text = ""
                        if line['score_mate'] is not None:
                            mate_val = line['score_mate'] if self.board_state.turn == chess.WHITE else -line['score_mate']
                            eval_text = f"Мат в {abs(line['score_mate'])}"
                        elif line['score_cp'] is not None:
                            cp_val = line['score_cp'] if self.board_state.turn == chess.WHITE else -line['score_cp']
                            eval_text = f"{cp_val / 100.0:+.2f}"

                        self.eval_tree.insert('', 'end', values=(line['pv'], move_san, eval_text))
                    except (ValueError, IndexError):
                        continue

                first_line = analysis_lines[0]
                self.update_eval_bar(first_line['score_cp'], first_line['score_mate'])
                self._draw_move_arrows()

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_analysis_queue)


    def get_square_coords(self, square_index: int) -> tuple[int, int]:
        file = chess.square_file(square_index)
        rank = chess.square_rank(square_index)
        if self.board_orientation_white_pov:
            x, y = file * SQUARE_SIZE, (7 - rank) * SQUARE_SIZE
        else:
            x, y = (7 - file) * SQUARE_SIZE, rank * SQUARE_SIZE
        return x, y

    def get_square_from_coords(self, x: int, y: int) -> Optional[int]:
        file = int(x // SQUARE_SIZE)
        rank = int(y // SQUARE_SIZE)
        if self.board_orientation_white_pov:
            file, rank = file, 7 - rank
        else:
            file, rank = 7 - file, rank
        return chess.square(file, rank) if 0 <= file <= 7 and 0 <= rank <= 7 else None

    def _set_active_node(self, target_node: Optional[chess.pgn.GameNode], is_forward_move: Optional[bool] = None,
                         move_to_animate: Optional[chess.Move] = None, captured: bool = False,
                         animated_piece_symbol: Optional[str] = None) -> None:

        if self.is_animating or target_node is None:
            return

        self.current_game_node = target_node
        self.board_state = self.current_game_node.board()

        if move_to_animate:
            self.update_board_display(move_to_animate=move_to_animate, captured=captured,
                                      is_reverse_animation=(not is_forward_move),
                                      animated_piece_symbol=animated_piece_symbol)
        else:
            self.update_board_display()
            self.update_info_panel()
            self.update_navigation_buttons()

    def animate_move(self, move: chess.Move, captured: bool, is_reverse_animation: bool, piece_symbol: str) -> None:
        from_sq, to_sq = (move.to_square, move.from_square) if is_reverse_animation else (move.from_square, move.to_square)
        start_x, start_y = self.get_square_coords(from_sq)
        end_x, end_y = self.get_square_coords(to_sq)

        animated_image = self.piece_images.get(piece_symbol)
        if not animated_image:
            self._finalize_animation_and_update(); return

        animating_piece_id = self.board_canvas.create_image(start_x, start_y, anchor=tk.NW, image=animated_image, tags="anim_piece")
        self.board_canvas.tag_raise(animating_piece_id)

        self.board_canvas.delete(f"piece_at_{from_sq}")
        if not is_reverse_animation and captured:
            self.board_canvas.delete(f"piece_at_{to_sq}")

        dx, dy = (end_x - start_x) / ANIMATION_STEPS, (end_y - start_y) / ANIMATION_STEPS

        def animation_step(step):
            if step <= ANIMATION_STEPS:
                self.board_canvas.move(animating_piece_id, dx, dy)
                self.root.after(ANIMATION_DELAY, lambda: animation_step(step + 1))
            else:
                self.board_canvas.delete(animating_piece_id)
                self._finalize_animation_and_update(played_sound=is_reverse_animation, captured=captured)

        animation_step(1)

    def _finalize_animation_and_update(self, played_sound: bool = False, captured: bool = False) -> None:
        self.is_animating = False
        if not played_sound: self.play_sound(captured)
        self.update_board_display()
        self.update_info_panel()
        self.update_navigation_buttons()

    def play_sound(self, captured: bool) -> None:
        if not self.sound_enabled: return
        try:
            sound = self.capture_sound if captured else self.move_sound
            if sound: sound.play()
        except Exception as e:
            print(f"Ошибка воспроизведения звука: {e}")

    def draw_arrow(self, from_sq: int, to_sq: int, color: str, width: int, tag: str) -> None:
        x1, y1 = self.get_square_coords(from_sq)
        x2, y2 = self.get_square_coords(to_sq)
        center_offset = SQUARE_SIZE / 2
        self.board_canvas.create_line(x1 + center_offset, y1 + center_offset,
                                      x2 + center_offset, y2 + center_offset,
                                      arrow=tk.LAST, fill=color, width=width, tags=(tag, "arrow"))

    def update_navigation_buttons(self) -> None:
        if self.current_game_node:
            self.prev_move_button.config(state=tk.NORMAL if self.current_game_node.parent else tk.DISABLED)
            self.next_move_button.config(state=tk.NORMAL if self.current_game_node.variations else tk.DISABLED)
        else:
            self.prev_move_button.config(state=tk.DISABLED)
            self.next_move_button.config(state=tk.DISABLED)

    def flip_board(self) -> None:
        if self.is_animating: return
        self.board_orientation_white_pov = not self.board_orientation_white_pov
        self.clear_highlighted_squares()
        self.selected_square_for_move = None
        self.update_board_display()

    def highlight_legal_moves(self, from_square: int) -> None:
        self.clear_highlighted_squares()
        x, y = self.get_square_coords(from_square)
        self.board_canvas.create_rectangle(x, y, x + SQUARE_SIZE, y + SQUARE_SIZE, outline="#FFD700", width=4, tags="highlight_selected")

        for move in self.board_state.legal_moves:
            if move.from_square == from_square:
                to_x, to_y = self.get_square_coords(move.to_square)
                radius = SQUARE_SIZE / 6
                fill_color = "#FF6060" if self.board_state.is_capture(move) else "#A0A0A0"
                self.board_canvas.create_oval(to_x + SQUARE_SIZE/2 - radius, to_y + SQUARE_SIZE/2 - radius,
                                              to_x + SQUARE_SIZE/2 + radius, to_y + SQUARE_SIZE/2 + radius,
                                              fill=fill_color, outline="", tags="highlight")

    def clear_highlighted_squares(self) -> None:
        self.board_canvas.delete("highlight_selected", "highlight")

    def clear_evaluation_display(self) -> None:
        for item in self.eval_tree.get_children():
            self.eval_tree.delete(item)
        self.board_canvas.delete("best_move_arrow", "alt_move_arrow")

    def get_best_moves_from_treeview(self) -> List[chess.Move]:
        moves = []
        for item in self.eval_tree.get_children():
            move_san = self.eval_tree.item(item, 'values')[1]
            try:
                moves.append(self.board_state.parse_san(move_san))
            except (ValueError, IndexError):
                continue
        return moves

    def get_animated_piece_symbol(self, move: chess.Move, is_undo: bool = False) -> Optional[str]:
        if is_undo:
            piece = self.board_state.piece_at(move.to_square)
            if piece: return piece.symbol()
            if move.promotion:
                return 'P' if self.board_state.turn == chess.BLACK else 'p'
        else:
            if move.promotion:
                return chess.piece_symbol(move.promotion).upper() if self.board_state.turn == chess.WHITE else chess.piece_symbol(move.promotion).lower()

            piece = self.board_state.piece_at(move.from_square)

            if piece: return piece.symbol()
        return None

    def create_move_obj(self, from_sq: int, to_sq: int) -> Optional[chess.Move]:
        move = chess.Move(from_sq, to_sq)
        piece = self.board_state.piece_at(from_sq)
        if piece and piece.piece_type == chess.PAWN:
            if (chess.square_rank(to_sq) == 7 and piece.color == chess.WHITE) or \
               (chess.square_rank(to_sq) == 0 and piece.color == chess.BLACK):
                promo = simpledialog.askstring("Превращение", "В какую фигуру (q, r, b, n)?", initialvalue="q")
                if promo and promo.lower() in "qrbn":
                    move.promotion = chess.PIECE_SYMBOLS.index(promo.lower())
                else:
                    return None
        return move

    def check_game_status(self) -> None:
        status_text, color = "", "blue"
        if self.board_state.is_checkmate():
            winner = "Белые" if self.board_state.turn == chess.BLACK else "Черные"
            status_text, color = f"ШАХ И МАТ! {winner} победили.", "red"
        elif self.board_state.is_stalemate(): status_text = "ПАТ! Ничья."
        elif self.board_state.is_insufficient_material(): status_text = "Ничья (недостаточно материала)."
        elif self.board_state.is_seventyfive_moves(): status_text = "Ничья (правило 75 ходов)."
        elif self.board_state.is_fivefold_repetition(): status_text = "Ничья (5-кратное повторение)."
        self.game_status_label.config(text=status_text, foreground=color)

    def update_eval_bar(self, score_cp: Optional[int], score_mate: Optional[int], max_eval_cp: int = 1000) -> None:
        bar_width = self.eval_bar_canvas.winfo_width()
        if bar_width <= 1: bar_width = BOARD_IMG_WIDTH

        normalized_score, text = 0.5, "0.0"
        if self.board_state.is_checkmate():
            normalized_score = 0.0 if self.board_state.turn == chess.WHITE else 1.0
            text = "МАТ"
        elif score_mate is not None:
            normalized_score = 1.0 if score_mate > 0 else 0.0
            text = f"M{abs(score_mate)}"
        elif score_cp is not None:
            clamped_score = max(-max_eval_cp, min(max_eval_cp, score_cp))
            normalized_score = (clamped_score / max_eval_cp) * 0.5 + 0.5
            text = f"{score_cp / 100.0:+.2f}"

        white_width = bar_width * normalized_score
        self.eval_bar_canvas.coords(self.eval_line, 0, 0, white_width, EVAL_BAR_HEIGHT)
        self.eval_bar_canvas.delete("black_part")
        self.eval_bar_canvas.create_rectangle(white_width, 0, bar_width, EVAL_BAR_HEIGHT, fill="black", outline="", tags="black_part")
        self.eval_bar_canvas.coords(self.eval_text, bar_width / 2, EVAL_BAR_HEIGHT / 2)
        self.eval_bar_canvas.itemconfig(self.eval_text, text=text)
        self.eval_bar_canvas.tag_raise(self.eval_text)

    def update_engine_skill(self, event: Optional[Any] = None) -> None:
        if self.engine and self.engine.process:
            self.engine.set_skill_level(self.engine_skill_var.get())

    def update_engine_multipv(self, event: Optional[Any] = None) -> None:
        if self.engine and self.engine.process:
            self.engine.set_multi_pv(self.engine_multipv_var.get())
            self.request_analysis_current_pos()

    def on_closing(self) -> None:
        self.is_animating = False
        if self.engine and self.engine.process:
            self.engine.quit_engine()
        if hasattr(self, "sound_enabled") and self.sound_enabled and pygame.mixer.get_init():
            pygame.mixer.quit()
        self.root.destroy()

if __name__ == "__main__":
    if not os.path.exists(ASSETS_DIR):
        messagebox.showerror("Критическая ошибка", f"Директория с ресурсами '{ASSETS_DIR}' не найдена.")
    else:
        root = tk.Tk()
        app = ChessAnalyzerApp(root)
        root.mainloop()
