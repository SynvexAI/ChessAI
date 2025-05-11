import subprocess
import time
import platform

STOCKFISH_PATH_WINDOWS = "./stockfish.exe"
STOCKFISH_PATH_LINUX_MACOS = "./stockfish"

class EngineHandler:
    def __init__(self, engine_path=None, initial_skill_level=20):
        if engine_path is None:
            if platform.system() == "Windows":
                self.engine_path = STOCKFISH_PATH_WINDOWS
            else:
                self.engine_path = STOCKFISH_PATH_LINUX_MACOS
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
            while True:
                line = self._read_output()
                if "uciok" in line:
                    self.is_ready = True
                    break
            self.set_skill_level(self.skill_level)
            self._send_command("isready")
            while True:
                line = self._read_output()
                if "readyok" in line:
                    break
        except FileNotFoundError:
            print(f"ERROR: Engine file not found: {self.engine_path}")
            self.process = None
        except Exception as e:
            print(f"ERROR starting Stockfish: {e}")
            self.process = None

    def _send_command(self, command):
        if self.process and self.process.stdin:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

    def _read_output(self):
        if self.process and self.process.stdout:
            line = self.process.stdout.readline().strip()
            return line
        return ""

    def set_skill_level(self, level):
        if not self.process or not self.is_ready : return
        level = max(0, min(20, int(level)))
        self.skill_level = level
        self._send_command(f"setoption name Skill Level value {self.skill_level}")

    def set_position_from_fen(self, fen_string):
        if not self.process: return
        self._send_command(f"position fen {fen_string}")

    def set_position_from_moves(self, moves_list):
        if not self.process: return
        if not moves_list:
            self._send_command("position startpos")
        else:
            self._send_command(f"position startpos moves {' '.join(moves_list)}")

    def get_evaluation_and_best_move(self, movetime_ms=1000):
        if not self.process or not self.is_ready:
            return None, None, None

        self._send_command(f"go movetime {movetime_ms}")
        
        best_move_uci = None
        score_cp = None
        score_mate = None

        while True:
            line = self._read_output()
            if line.startswith("info"):
                parts = line.split()
                try:
                    if "score" in parts:
                        score_idx = parts.index("score")
                        if parts[score_idx + 1] == "cp":
                            score_cp = int(parts[score_idx + 2])
                            score_mate = None
                        elif parts[score_idx + 1] == "mate":
                            score_mate = int(parts[score_idx + 2])
                            score_cp = None
                except (ValueError, IndexError):
                    pass

            elif line.startswith("bestmove"):
                parts = line.split()
                if len(parts) > 1:
                    best_move_uci = parts[1]
                break
            elif not line and self.process.poll() is not None:
                print("Engine process terminated unexpectedly.")
                return None, None, None
        
        if best_move_uci == "(none)":
            best_move_uci = None 

        return score_cp, score_mate, best_move_uci

    def get_board_uci_moves(self, game_node):
        moves = []
        current = game_node
        while current.move:
            moves.append(current.move.uci())
            current = current.parent
        return list(reversed(moves))

    def quit_engine(self):
        if self.process:
            self._send_command("quit")
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.is_ready = False