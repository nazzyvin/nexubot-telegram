import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from services import storage

# In-memory registries
GAMES: Dict[int, 'GameBase'] = {}           # chat_id -> active game
PENDING: Dict[int, dict] = {}               # chat_id -> pending challenge

CHALLENGE_TIMEOUT_SECONDS = 5 * 60  # auto-expire an unanswered challenge after 5 minutes
BOARD_BUMP_THRESHOLD = 7            # re-post (vs. edit in place) once this many other messages land in the chat

@dataclass
class GameBase:
    chat_id: int
    players: List[int]          # [player1_id, player2_id]
    turn: int = 0               # 0 or 1
    board: List = field(default_factory=list)
    message_id: Optional[int] = None
    messagge_since_board: int = 0   # chat messages seen since the board was last (re)posted
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

    def render_keyboard(self, show_forfeit: bool = True) -> InlineKeyboardMarkup:
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
        if show_forfeit:
            rows.append([InlineKeyboardButton("🏳️ Forfeit", callback_data=f"forfeit:{self.game_id}")])
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

    def render_keyboard(self, show_forfeit: bool = True) -> InlineKeyboardMarkup:
        rows = []
        # Column selector (top row)
        col_buttons = []
        for col in range(self.COLS):
            full = self.board[0][col] is not None
            text = f"{col+1}" if not full else "⛔"
            col_buttons.append(InlineKeyboardButton(text, callback_data=f"c4:{self.game_id}:{col}"))
        rows.append(col_buttons)
        # Visual board rows — every cell in a column shares the column's
        # callback_data, so tapping anywhere in the column drops a piece there
        # (not just the small number button up top).
        for row in range(self.ROWS):
            btn_row = []
            for col in range(self.COLS):
                val = self.board[row][col]
                text = "⚪" if val is None else ("🔴" if val == 0 else "🟡")
                btn_row.append(InlineKeyboardButton(text, callback_data=f"c4:{self.game_id}:{col}"))
            rows.append(btn_row)
        if show_forfeit:
            rows.append([InlineKeyboardButton("🏳️ Forfeit", callback_data=f"forfeit:{self.game_id}")])
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


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = await storage.get_leaderboard(chat_id)
    if not rows:
        await update.message.reply_text("No game results recorded yet in this chat. Go play some /ttt or /connect4!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Leaderboard</b>"]
    for i, (name, wins, losses, draws) in enumerate(rows):
        prefix = medals[i] if i < len(medals) else f"{i+1}."
        lines.append(f"{prefix} {name} — {wins}W {losses}L {draws}D")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ---------- Internals ----------

async def _start_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, gtype: str, GameClass):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id in GAMES or chat_id in PENDING:
        await update.message.reply_text("A game is already pending/active here.")
        return

    opponent_id = None
    opponent_username = None
    opponent_display = None  # what we show in the "X challenged Y" message

    # Prefer a real mention entity — works for tagged users with or without a
    # public @username. text_mention carries the actual User object (has .id);
    # plain mention only carries "@username" text, so we fall back to that.
    for entity in (update.message.entities or []):
        if entity.type == "text_mention" and entity.user is not None:
            opponent_id = entity.user.id
            opponent_username = (entity.user.username or "").lower() or None
            opponent_display = entity.user.full_name
            break
        if entity.type == "mention":
            mention_text = update.message.parse_entity(entity)  # e.g. "@someuser"
            opponent_username = mention_text.lstrip('@').lower()
            opponent_display = mention_text
            break

    # Fallback: plain "@username" typed as the first arg (no entity attached,
    # e.g. copy-pasted text).
    if opponent_id is None and opponent_username is None:
        if context.args and context.args[0].startswith('@'):
            opponent_username = context.args[0][1:].lower()
            opponent_display = f"@{opponent_username}"

    if opponent_id is None and opponent_username is None:
        await update.message.reply_text(
            f"Usage: /{gtype} @opponent (tag a user, or type their @username)"
        )
        return

    if opponent_id == user.id:
        await update.message.reply_text("You can't challenge yourself.")
        return

    challenger_id = user.id

    # Store pending challenge
    PENDING[chat_id] = {
        'challenger_id': challenger_id,
        'opponent_id': opponent_id,              # set if we got a real text_mention
        'opponent_username': opponent_username,   # fallback match key
        'gtype': gtype,
        'GameClass': GameClass,
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Join Game", callback_data=f"join:{gtype}"),
        InlineKeyboardButton("❌ Decline", callback_data="decline"),
    ]])
    
    sent = await update.message.reply_text(
        f"{user.first_name} challenged {opponent_display} to {gtype.upper()}!\n"
        f"Tap \"Join Game\" to accept.",
        reply_markup=keyboard
    )

    PENDING[chat_id]['message_id'] = sent.message_id

    if context.job_queue is not None:
        job = context.job_queue.run_once(
            _expire_challenge,
            CHALLENGE_TIMEOUT_SECONDS,
            chat_id=chat_id,
            data={'chat_id': chat_id, 'message_id': sent.message_id},
        )
        PENDING[chat_id]['timeout_job'] = job


async def _expire_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scheduled ~5 minutes after a challenge is posted. No-ops if the challenge was already joined/declined, or replaced by a newer one."""
    job = context.job
    chat_id = job.chat_id
    message_id = job.data.get('message_id')

    pending = PENDING.get(chat_id)
    if not pending or pending.get('message_id') != message_id:
        return  # already resolve, or this is a stale job for an old challenge

    del PENDING[chat_id]
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⌛ Challenge expired — no response within 5 minutes.",
        )
    except Exception:
        pass


async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id
    user = query.from_user

    if data == "decline":
        pending = PENDING.get(chat_id)
        if pending:
            job = pending.get('timeout_job')
            if job is not None:
                job.schedule_removal()
            del PENDING[chat_id]
        await query.edit_message_text("Challenge declined.")
        return

    if data not in ("join:ttt", "join:c4"):
        return

    pending = PENDING.get(chat_id)
    if not pending:
        await query.answer("No pending challenge.")
        return

    # Verify it's the opponent — prefer an exact user-id match (from a
    # text_mention challenge, which works even without a public username).
    # Fall back to username comparison for the plain "@username" path, and
    # guard against user.username being None (not everyone sets one).
    opponent_id = pending.get('opponent_id')
    opponent_username = pending.get('opponent_username')

    if opponent_id is not None:
        is_opponent = (user.id == opponent_id)
    elif opponent_username is not None:
        is_opponent = (user.username or "").lower() == opponent_username
    else:
        is_opponent = False

    if not is_opponent:
        await query.answer("This challenge isn't for you.")
        return

    # Start the game
    gtype = pending['gtype']
    GameClass = pending['GameClass']
    challenger_id = pending['challenger_id']
    opponent_id = user.id

    # Clean up pending
    timeout_job = pending.get('timeout_job')
    if timeout_job is not None:
        timeout_job.schedule_removal()
    del PENDING[chat_id]

    # Create game
    game = GameClass(chat_id, [challenger_id, opponent_id])
    game.message_id = query.message.message_id
    GAMES[chat_id] = game

    # Send game board
    text = game.get_status_text()
    keyboard = game.render_keyboard()
    
    await query.edit_message_text(
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def _display_name(context: ContextTypes.DEFAULT_TYPE, chat_id: int, uid: int) -> str:
    try:
        member = await context.bot.get_chat_member(chat_id, uid)
        return member.user.full_name
    except Exception:
        return f"Player {uid}"


async def _finish_game(chat_id: int, game: GameBase, winner: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Builds the end-of-game text and records the result to Postgres.
    Never lets a stats-recording failure block the game-over message."""
    p0_id, p1_id = game.players

    try:
        if winner == -1:
            name0 = await _display_name(context, chat_id, p0_id)
            name1 = await _display_name(context, chat_id, p1_id)
            await storage.record_result(chat_id, p0_id, name0, 'draw')
            await storage.record_result(chat_id, p1_id, name1, 'draw')
            return "🤝 It's a draw!"
        else:
            winner_id = game.players[winner]
            loser_id = game.players[1 - winner]
            winner_name = await _display_name(context, chat_id, winner_id)
            loser_name = await _display_name(context, chat_id, loser_id)
            await storage.record_result(chat_id, winner_id, winner_name, 'win')
            await storage.record_result(chat_id, loser_id, loser_name, 'loss')
            return f"🎉 {winner_name} wins!"
    except Exception:
        # Stats recording is best-effort — a DB hiccup shouldn't break the game.
        if winner == -1:
            return "🤝 It's a draw!"
        return f"🎉 Player {winner+1} wins!"


async def _finish_forfeit(chat_id: int, game: GameBase, forfeiting_idx: int, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Same idea as _finish_game, but for a player bailing out early.
    The other player is credited a win, the forfeiter a loss."""
    winner_idx = 1 - forfeiting_idx
    winner_id = game.players[winner_idx]
    loser_id = game.players[forfeiting_idx]

    winner_name = await _display_name(context, chat_id, winner_id)
    loser_name = await _display_name(context, chat_id, loser_id)

    try:
        await storage.record_result(chat_id, winner_id, winner_name, 'win')
        await storage.record_result(chat_id, loser_id, loser_name, 'loss')
    except Exception:
        pass  # stats recording is best-effort — don't block the forfeit message

    return f"🏳️ {loser_name} forfeited. {winner_name} wins by default!"


async def _update_board(context: ContextTypes.DEFAULT_TYPE, chat_id: int, game: GameBase, text: str, keyboard: InlineKeyboardMarkup, force_repost: bool = False):
    """Updates the board message. If the chat's been quiet since the last
    board post, this just edits it in place (cheap, no extra clutter). If
    BOARD_BUMP_THRESHOLD other messages have landed since then — or
    force_repost is set, e.g. for the final win/draw/forfeit message — it
    strips the old message's buttons and posts a fresh one instead, so the
    board bumps back to the bottom of the chat where people are looking."""
    should_repost = (
        force_repost
        or game.message_id is None
        or game.messages_since_board >= BOARD_BUMP_THRESHOLD
    )

    if not should_repost:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=game.message_id,
                text=text, reply_markup=keyboard, parse_mode="HTML",
            )
            return
        except Exception:
            pass  # old message gone/uneditable — fall through to a fresh repost

    old_message_id = game.message_id
    if old_message_id is not None:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=old_message_id, reply_markup=None
            )
        except Exception:
            pass  # old message may be too old / already gone — not fatal

    sent = await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML"
    )
    game.message_id = sent.message_id
    game.messages_since_board = 0


async def _track_chat_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Counts other chat messages while a game is active, so _update_board
    knows when the chat's been busy enough to warrant bumping the board back
    to the bottom instead of a quiet in-place edit."""
    chat = update.effective_chat
    if chat is None:
        return
    game = GAMES.get(chat.id)
    if game is not None:
        game.messages_since_board += 1


def get_activity_tracker_handler():
    return MessageHandler(filters.ALL, _track_chat_activity)

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
                text = await _finish_game(chat_id, game, winner, context)
                await _update_board(context, chat_id, game, text, game.render_keyboard(show_forfeit=False))
                del GAMES[chat_id]
            else:
                game.next_turn()
                await _update_board(context, chat_id, game, game.get_status_text(), game.render_keyboard())
        else:
            if game.turn != player_idx:
                await query.answer("Not your turn.")
            else:
                await query.answer("That square is taken.")
    elif prefix == "c4":
        if game.make_move(pos, player_idx):
            winner = game.check_winner()
            if winner is not None:
                text = await _finish_game(chat_id, game, winner, context)
                await _update_board(context, chat_id, game, text, game.render_keyboard(show_forfeit=False))
                del GAMES[chat_id]
            else:
                game.next_turn()
                await _update_board(context, chat_id, game, game.get_status_text(), game.render_keyboard())
        else:
            if game.turn != player_idx:
                await query.answer("Not your turn.")
            else:
                await query.answer("That column is full — pick another.")


async def forfeit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 🏳️ Forfeit button on the game keyboard."""
    query = update.callback_query
    await query.answer()

    data = query.data
    game_id = data.split(':', 1)[1] if ':' in data else None
    chat_id = query.message.chat_id

    game = GAMES.get(chat_id)
    if not game or game.game_id != game_id:
        await query.answer("Game not found or expired.")
        return

    user_id = query.from_user.id
    player_idx = 0 if game.players[0] == user_id else (1 if game.players[1] == user_id else -1)
    if player_idx == -1:
        await query.answer("Not your game.")
        return

    text = await _finish_forfeit(chat_id, game, player_idx, context)
    await query.edit_message_text(context, chat_id, game, text, reply_markup=game.render_keyboard(show_forfeit=False))
    del GAMES[chat_id]


async def forfeit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /forfeit and /quit — lets a player bail without hunting for the button."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    game = GAMES.get(chat_id)
    if not game:
        await update.message.reply_text("No active game in this chat.")
        return

    player_idx = 0 if game.players[0] == user.id else (1 if game.players[1] == user.id else -1)
    if player_idx == -1:
        await update.message.reply_text("You're not part of the active game here.")
        return

    text = await _finish_forfeit(chat_id, game, player_idx, context)
    final_keyboard = game.render_keyboard(show_forfeit=False)
    await _update_board(context, chat_id, game, text, final_keyboard)
    del GAMES[chat_id]

def get_game_handlers():
    return [
        CommandHandler('ttt', tictactoe_command),
        CommandHandler('connect4', connect4_command),
        CommandHandler('c4', connect4_command),
        CommandHandler('games', games_command),
        CommandHandler('leaderboard', leaderboard_command),
        CommandHandler('lb', leaderboard_command),
        CommandHandler('forfeit', forfeit_command),
        CommandHandler('quit', forfeit_command),
        CallbackQueryHandler(join_callback, pattern=r'^join:(ttt|c4)$|^decline$'),
        CallbackQueryHandler(game_callback, pattern=r'^(ttt|c4):'),
        CallbackQueryHandler(forfeit_callback, pattern=r'^forfeit:'),
    ]