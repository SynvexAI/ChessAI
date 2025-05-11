# engine_handler.py
import subprocess
import time
import platform # Для определения ОС и путей

STOCKFISH_PATH_WINDOWS = "./stockfish.exe" # Ожидаем stockfish.exe в той же папке
STOCKFISH_PATH_LINUX_MACOS = "./stockfish" # Ожидаем stockfish в той же папке

class EngineHandler:
    def __init__(self, engine_path=None):
        if engine_path is None:
            if platform.system() == "Windows":
                self.engine_path = STOCKFISH_PATH_WINDOWS
            else:
                self.engine_path = STOCKFISH_PATH_LINUX_MACOS # Для Linux/macOS
        else:
            self.engine_path = engine_path
        
        self.process = None
        self.is_ready = False
        self._start_engine()

    def _start_engine(self):
        try:
            self.process = subprocess.Popen(
                self.engine_path,
                universal_newlines=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, # Можно для отладки
                bufsize=1 # Line buffering
            )
            self._send_command("uci")
            while True:
                line = self._read_output()
                if "uciok" in line:
                    self.is_ready = True
                    break
            self._send_command("isready")
            while True:
                line = self._read_output()
                if "readyok" in line:
                    break
            # print("Stockfish запущен и готов.")
        except FileNotFoundError:
            print(f"ОШИБКА: Файл движка не найден по пути: {self.engine_path}")
            print("Пожалуйста, скачайте Stockfish и поместите его в папку проекта или укажите правильный путь.")
            self.process = None # Указываем, что процесс не запущен
        except Exception as e:
            print(f"ОШИБКА при запуске Stockfish: {e}")
            self.process = None

    def _send_command(self, command):
        if self.process and self.process.stdin:
            # print(f"GUI -> Engine: {command}")
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def _read_output(self):
        if self.process and self.process.stdout:
            line = self.process.stdout.readline().strip()
            # print(f"Engine -> GUI: {line}")
            return line
        return ""

    def set_position_from_fen(self, fen_string):
        if not self.process: return
        self._send_command(f"position fen {fen_string}")

    def set_position_from_moves(self, moves_list): # moves_list - список ходов в UCI формате, например ['e2e4', 'e7e5']
        if not self.process: return
        if not moves_list:
            self._send_command("position startpos")
        else:
            self._send_command(f"position startpos moves {' '.join(moves_list)}")

    def get_evaluation_and_best_move(self, movetime_ms=1000):
        if not self.process or not self.is_ready:
            return None, None, None # Оценка (cp), оценка (mate), лучший ход

        self._send_command(f"go movetime {movetime_ms}")
        
        last_info_line = ""
        best_move_uci = None
        score_cp = None
        score_mate = None

        while True:
            line = self._read_output()
            if line.startswith("info"):
                last_info_line = line # Сохраняем последнюю info строку
                parts = line.split()
                try:
                    if "score" in parts:
                        score_idx = parts.index("score")
                        if parts[score_idx + 1] == "cp":
                            score_cp = int(parts[score_idx + 2])
                            score_mate = None # Сбрасываем мат, если пришла оценка в пешках
                        elif parts[score_idx + 1] == "mate":
                            score_mate = int(parts[score_idx + 2])
                            score_cp = None # Сбрасываем пешки, если пришел мат
                except (ValueError, IndexError):
                    pass # Не удалось распарсить info

            elif line.startswith("bestmove"):
                parts = line.split()
                if len(parts) > 1:
                    best_move_uci = parts[1]
                break # Выход из цикла после получения bestmove
            elif not line and self.process.poll() is not None: # Процесс завершился
                print("Процесс движка неожиданно завершился.")
                return None, None, None
        
        # Если лучший ход - (none), это может быть мат или пат
        if best_move_uci == "(none)":
            best_move_uci = None 

        return score_cp, score_mate, best_move_uci


    def get_board_uci_moves(self, game_node):
        """Возвращает список UCI ходов от начала игры до текущего узла"""
        moves = []
        current = game_node
        while current.move:
            moves.append(current.move.uci())
            current = current.parent
        return list(reversed(moves))

    def quit_engine(self):
        if self.process:
            print("Остановка движка...")
            self._send_command("quit")
            try:
                self.process.wait(timeout=2) # Ждем завершения процесса
            except subprocess.TimeoutExpired:
                print("Движок не ответил на команду quit, принудительное завершение.")
                self.process.kill()
            self.process = None
            self.is_ready = False
            print("Движок остановлен.")

if __name__ == '__main__':
    # Тестирование EngineHandler
    engine = EngineHandler()
    if engine.process: # Проверяем, запустился ли движок
        print("Тест EngineHandler:")
        
        # Начальная позиция
        engine.set_position_from_moves([])
        cp, mate, best_move = engine.get_evaluation_and_best_move(movetime_ms=500)
        print(f"Startpos: Eval cp: {cp}, Mate: {mate}, Best move: {best_move}")

        # После e2e4
        engine.set_position_from_moves(['e2e4'])
        cp, mate, best_move = engine.get_evaluation_and_best_move(movetime_ms=500)
        print(f"After e2e4: Eval cp: {cp}, Mate: {mate}, Best move: {best_move}")

        # Из FEN
        fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2" # После 1. e4 e5
        engine.set_position_from_fen(fen)
        cp, mate, best_move = engine.get_evaluation_and_best_move(movetime_ms=500)
        print(f"FEN ({fen}): Eval cp: {cp}, Mate: {mate}, Best move: {best_move}")
        
        engine.quit_engine()
    else:
        print("Не удалось запустить движок для теста.")