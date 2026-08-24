import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

# In-memory registries
GAMES: Dict[int, 'GameBase'] = {}           # chat_id -> active game
PENDING: Dict[int, dict] = {}               # chat_id -> pending challenge


@dataclass
class GameBase:
    chat_id: int
    players: List[int]          # [player1_id, player2_id]
    turn: int = 0               # 0 or 1
    board: List = field(default_factory=list)
    message_id: Optional[int] = None
    game_id: str = field(default_factory=lambda: ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6)))

    def current_player(self) -> int:
        return self.players[self.turn]

    def next_turn(self):
        self.turn ^= 1

    def render_keyboard(self) -> InlineKeyboardMarkup:
        raise NotImplementedError

    def check_winner(self) -> Optional[int]:   # 0, 1, -1 (draw), None
        raise NotImplementedError

    def make_move(self, pos: int, player_idx: int) -> bool:
        raise NotImplementedError

    def get_status_text(self) -> str:
        p1 = f"<a href='tg://user?id={self.players[0]}'>Player 1</a>"
        p2 = f"<a href='tg://user?id={self.players[1]}'>Player 2</a>"
        current = p1 if self.turn == 0 else p2
        return f"{p1} ❌ vs {p2} ⭕\nTurn: {current}"


class TicTacToe(GameBase):
    def __init__(self, chat_id: int, players: List[int]):
        super().__init__(chat_id, players)
        self.board = [None] * 9

    def render_keyboard(self) -> InlineKeyboardMarkup:
        rows = []
        for row in range(3):
            buttons = []
            for col in range(3):
                idx = row * 3 + col
                val = self.board[idx]
                text = " " if val is None else ("❌" if val == 0 else "⭕")
                buttons.append(InlineKeyboardButton(
                    text, callback_data=f"ttt:{self.game_id}:{idx}"
                ))
            rows.append(buttons)
        return InlineKeyboardMarkup(rows)

    def make_move(self, pos: int, player_idx: int) -> bool:
        if self.board[pos] is not None or self.turn != player_idx:
            return False
        self.board[pos] = player_idx
        return True

    def check_winner(self) -> Optional[int]:
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a,b,c in wins:
            if self.board[a] is not None and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        if all(v is not None for v in self.board):
            return -1
        return None


class Connect4(GameBase):
    ROWS = 6
    COLS = 7

    def __init__(self, chat_id: int, players: List[int]):
        super().__init__(chat_id, players)
        self.board = [[None for _ in range(self.COLS)] for _ in range(self.ROWS)]

    def render_keyboard(self) -> InlineKeyboardMarkup:
        rows = []
        # Column selector (top row)
        col_buttons = []
        for col in range(self.COLS):
            full = self.board[0][col] is not None
            text = f"{col+1}" if not full else "⛔"
            col_buttons.append(InlineKeyboardButton(text, callback_data=f"c4:{self.game_id}:{col}"))
        rows.append(col_buttons)
        # Visual board rows
        for row in range(self.ROWS):
            btn_row = []
            for col in range(self.COLS):
                val = self.board[row][col]
                text = "⚪" if val is None else ("🔴" if val == 0 else "🟡")
                btn_row.append(InlineKeyboardButton(text, callback_data="ignore"))
            rows.append(btn_row)
        return InlineKeyboardMarkup(rows)

    def make_move(self, col: int, player_idx: int) -> bool:
        if self.turn != player_idx or col < 0 or col >= self.COLS:
            return False
        if self.board[0][col] is not None:
            return False
        for row in range(self.ROWS - 1, -1, -1):
            if self.board[row][col] is None:
                self.board[row][col] = player_idx
                return True
        return False

    def check_winner(self) -> Optional[int]:
        dirs = [(0,1),(1,0),(1,1),(1,-1)]
        for r in range(self.ROWS):
            for c in range(self.COLS):
                val = self.board[r][c]
                if val is None:
                    continue
                for dr, dc in dirs:
                    cnt = 1
                    for i in range(1, 4):
                        nr, nc = r + dr*i, c + dc*i
                        if 0 <= nr < self.ROWS and 0 <= nc < self.COLS and self.board[nr][nc] == val:
                            cnt += 1
                        else:
                            break
                    if cnt >= 4:
                        return val
        if all(self.board[0][c] is not None for c in range(self.COLS)):
            return -1
        return None


# ---------- Public command handlers ----------

async def tictactoe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_challenge(update, context, 'ttt', TicTacToe)


async def connect4_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_challenge(update, context, 'c4', Connect4)


async def games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in GAMES:
        g = GAMES[chat_id]
        await update.message.reply_text(f"Active: {type(g).__name__} (ID: {g.game_id})", parse_mode="HTML")
    else:
        await update.message.reply_text("No active game.")


# ---------- Internals ----------

async def _start_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, gtype: str, GameClass):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id in GAMES or chat_id in PENDING:
        await update.message.reply_text("A game is already pending/active here.")
        return

    if not context.args or not context.args[0].startswith('@'):
        await update.message.reply_text(f"Usage: /{gtype} @opponent")
        return

    opponent_username = context.args[0][1:].lower()
    challenger_id = user.id

    # Store pending challenge
    PENDING[chat_id] = {
        'challenger_id': challenger_id,
        'opponent_username': opponent_username,
        'gtype': gtype,
        'GameClass': GameClass,
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Join Game", callback_data=f"join:{gtype}"),
        InlineKeyboardButton("❌ Decline", callback_data="decline"),
    ]])
    
    await update.message.reply_text(
        f"{user.first_name} challenged @{opponent_username} to {gtype.upper()}!\n"
        f"Tap \"Join Game\" to accept.",
        reply_markup=keyboard
    )


async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id
    user = query.from_user

    if data == "decline":
        if chat_id in PENDING:
            del PENDING[chat_id]
        await query.edit_message_text("Challenge declined.")
        return

    if data not in ("join:ttt", "join:c4"):
        return

    pending = PENDING.get(chat_id)
    if not pending:
        await query.answer("No pending challenge.")
        return

    # Verify it's the opponent
    if user.username.lower() != pending['opponent_username']:
        await query.answer("This challenge isn't for you.")
        return

    # Start the game
    gtype = pending['gtype']
    GameClass = pending['GameClass']
    challenger_id = pending['challenger_id']
    opponent_id = user.id

    # Clean up pending
    del PENDING[chat_id]

    # Create game
    game = GameClass(chat_id, [challenger_id, opponent_id])
    GAMES[chat_id] = game

    # Send game board
    text = game.get_status_text()
    keyboard = game.render_keyboard()
    
    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "ignore":
        return

    parts = data.split(':')
    if len(parts) != 3:
        return

    prefix, game_id, pos_str = parts
    chat_id = query.message.chat_id

    game = GAMES.get(chat_id)
    if not game or game.game_id != game_id:
        await query.answer("Game not found or expired.")
        return

    try:
        pos = int(pos_str)
    except ValueError:
        return

    user_id = query.from_user.id
    player_idx = 0 if game.players[0] == user_id else (1 if game.players[1] == user_id else -1)
    if player_idx == -1:
        await query.answer("Not your game.")
        return

    if prefix == "ttt":
        if game.make_move(pos, player_idx):
            winner = game.check_winner()
            if winner is not None:
                if winner == -1:
                    text = "🤝 It's a draw!"
                else:
                    text = f"🎉 Player {winner+1} wins!"
                await query.edit_message_text(text, parse_mode="HTML")
                del GAMES[chat_id]
            else:
                game.next_turn()
                await query.edit_message_text(
                    game.get_status_text(),
                    reply_markup=game.render_keyboard(),
                    parse_mode="HTML"
                )
    elif prefix == "c4":
        if game.make_move(pos, player_idx):
            winner = game.check_winner()
            if winner is not None:
                if winner == -1:
                    text = "🤝 It's a draw!"
                else:
                    text = f"🎉 Player {winner+1} wins!"
                await query.edit_message_text(text, parse_mode="HTML")
                del GAMES[chat_id]
            else:
                game.next_turn()
                await query.edit_message_text(
                    game.get_status_text(),
                    reply_markup=game.render_keyboard(),
                    parse_mode="HTML"
                )


def get_game_handlers():
    return [
        CommandHandler('ttt', tictactoe_command),
        CommandHandler('connect4', connect4_command),
        CommandHandler('games', games_command),
        CallbackQueryHandler(join_callback, pattern=r'^join:(ttt|c4)$|^decline$'),
        CallbackQueryHandler(game_callback, pattern=r'^(ttt|c4):'),
    ]