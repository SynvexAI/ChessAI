import subprocess
import platform
import chess

STOCKFISH_PATH_WINDOWS = "./stockfish.exe"
STOCKFISH_PATH_LINUX_MACOS = "./stockfish"

class EngineHandler:
    def __init__(self, engine_path=None, initial_skill_level=20):
        if engine_path is None:
            self.engine_path = STOCKFISH_PATH_WINDOWS if platform.system() == "Windows" else STOCKFISH_PATH_LINUX_MACOS
        else:
            self.engine_path = engine_path
        
        self.process = None
        self.is_ready = False
        self.skill_level = initial_skill_level
        self._start_engine()

    def _start_engine(self):
        try:
            self.process = subprocess.Popen(
                self.engine_path,
                universal_newlines=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1
            )
            self._send_command("uci")
            while "uciok" not in self._read_output():
                pass
            self.set_skill_level(self.skill_level)
            self.set_multi_pv(3)
            self._send_command("isready")
            while "readyok" not in self._read_output():
                pass
            self.is_ready = True
        except FileNotFoundError:
            print(f"ОШИБКА: Файл движка не найден: {self.engine_path}")
            self.process = None
        except Exception as e:
            print(f"ОШИБКА при запуске Stockfish: {e}")
            self.process = None

    def _send_command(self, command):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                print("Ошибка: Канал для записи в движок закрыт.")
                self.process = None

    def _read_output(self):
        if self.process and self.process.stdout:
            try:
                line = self.process.stdout.readline().strip()
                return line
            except (IOError, ValueError):
                return ""
        return ""

    def set_skill_level(self, level):
        if not self.process or not self.is_ready: return
        level = max(0, min(20, int(level)))
        self.skill_level = level
        self._send_command(f"setoption name Skill Level value {self.skill_level}")

    def set_multi_pv(self, num_pvs):
        if not self.process or not self.is_ready: return
        num_pvs = max(1, min(5, int(num_pvs)))
        self._send_command(f"setoption name MultiPV value {num_pvs}")

    def set_position_from_fen(self, fen_string):
        if not self.process: return
        self._send_command(f"position fen {fen_string}")

    def get_analysis(self, movetime_ms=1000):
        if not self.process or not self.is_ready:
            return [], None

        self._send_command(f"go movetime {movetime_ms}")
        
        lines = []
        best_move_uci = None
        
        while True:
            line = self._read_output()
            if line.startswith("info"):
                parts = line.split()
                try:
                    pv_index = parts.index("multipv") + 1
                    pv = int(parts[pv_index])
                    
                    score_cp, score_mate = None, None
                    if "score" in parts:
                        score_idx = parts.index("score")
                        if parts[score_idx + 1] == "cp":
                            score_cp = int(parts[score_idx + 2])
                        elif parts[score_idx + 1] == "mate":
                            score_mate = int(parts[score_idx + 2])
                    
                    move_uci = None
                    if "pv" in parts:
                        move_uci = parts[parts.index("pv") + 1]

                    lines.append({'pv': pv, 'score_cp': score_cp, 'score_mate': score_mate, 'move_uci': move_uci})
                except (ValueError, IndexError):
                    continue

            elif line.startswith("bestmove"):
                best_move_uci = line.split()[1]
                break
            elif not line and self.process and self.process.poll() is not None:
                print("Процесс движка неожиданно завершился.")
                return [], None
        
        lines.sort(key=lambda x: x['pv'])
        return lines, best_move_uci

    def get_threat(self, fen_string, movetime_ms=500):
        if not self.process or not self.is_ready:
            return None
        
        try:
            board = chess.Board(fen_string)
            if board.is_game_over(): return None
            
            parts = fen_string.split()
            parts[1] = 'b' if parts[1] == 'w' else 'w'
            if parts[3] != '-':
                parts[3] = '-'
            threat_fen = " ".join(parts)
            
            self.set_position_from_fen(threat_fen)
            _, best_move_uci = self.get_analysis(movetime_ms)
            return best_move_uci
        except Exception as e:
            print(f"Ошибка при анализе угрозы: {e}")
            return None

    def quit_engine(self):
        if self.process:
            self._send_command("quit")
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.is_ready = False