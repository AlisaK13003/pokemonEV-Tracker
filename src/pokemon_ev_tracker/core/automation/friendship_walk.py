"""Frame-counted bidirectional walk controller for Friendship Walk."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

BLOCKED_TIMEOUT_FRAMES = 36
REVERSAL_GRACE_FRAMES = 20
MIN_MOVES_AFTER_REVERSAL = 2


class WalkAxis(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class WalkDirection(str, Enum):
    LEFT = "Left"
    RIGHT = "Right"
    UP = "Up"
    DOWN = "Down"


class WalkStatus(str, Enum):
    IDLE = "Idle"
    STARTING = "Starting — waiting for Lua acknowledgement"
    WALKING_LEFT = "Walking Left"
    WALKING_RIGHT = "Walking Right"
    WALKING_UP = "Walking Up"
    WALKING_DOWN = "Walking Down"
    BLOCKED_REVERSING = "Blocked — reversing"
    MOVING_UNCONFIRMED = "Moving — confirming direction"
    PAUSED_BATTLE = "Paused — Battle"
    PAUSED_RAM = "Paused — RAM connection lost"
    PAUSED_COORDINATES = "Paused — Position unavailable"
    PAUSED_MANUAL = "Paused — Manual input"
    PAUSED_COMMAND = "Paused — Movement command channel unavailable"
    PAUSED_COMMAND_LOST = "Paused — Movement command channel lost"


@dataclass(frozen=True)
class WalkUpdate:
    status: WalkStatus
    direction: WalkDirection | None
    successful_moves: int
    active: bool
    direction_changed: bool = False
    send_stop: bool = False


class FriendshipWalkController:
    """Chooses directions using game-frame deltas, never wall-clock delays."""

    def __init__(
        self,
        blocked_timeout_frames: int = BLOCKED_TIMEOUT_FRAMES,
        grace_frames: int = REVERSAL_GRACE_FRAMES,
        min_moves_after_reversal: int = MIN_MOVES_AFTER_REVERSAL,
    ) -> None:
        if blocked_timeout_frames < 1 or grace_frames < 0 or min_moves_after_reversal < 1:
            raise ValueError("Timeout must be positive; grace and minimum moves must be valid.")
        self.blocked_timeout_frames = blocked_timeout_frames
        self.grace_frames = grace_frames
        self.min_moves_after_reversal = min_moves_after_reversal
        self.axis = WalkAxis.HORIZONTAL
        self.status = WalkStatus.IDLE
        self.direction: WalkDirection | None = None
        self.successful_moves = 0
        self.active = False
        self._last_frame: int | None = None
        self._last_axis_value: int | None = None
        self._last_position_change_frame: int | None = None
        self._direction_started_frame: int | None = None
        self._reversal_grace_until_frame: int | None = None
        self.previous_direction: WalkDirection | None = None
        self.reversal_start_frame: int | None = None
        self.reversal_start_coordinate: int | None = None
        self.successful_moves_since_reversal = 0
        self.movement_confirmed_after_reversal = True
        self.wall_detection_armed = False

    @property
    def current_frame(self) -> int | None:
        return self._last_frame

    @property
    def relevant_axis_value(self) -> int | None:
        return self._last_axis_value

    @property
    def last_position_change_frame(self) -> int | None:
        return self._last_position_change_frame

    @property
    def frames_since_axis_change(self) -> int | None:
        if self._last_frame is None or self._last_position_change_frame is None:
            return None
        return max(0, self._last_frame - self._last_position_change_frame)

    @property
    def reversal_grace_remaining_frames(self) -> int:
        if self._last_frame is None or self._reversal_grace_until_frame is None:
            return 0
        return max(0, self._reversal_grace_until_frame - self._last_frame)

    @property
    def debug_state(self) -> str:
        if not self.active:
            return "IDLE" if self.status is WalkStatus.IDLE else "PAUSED"
        if self.status is WalkStatus.BLOCKED_REVERSING:
            return "REVERSING"
        if not self.wall_detection_armed:
            return "MOVING_UNCONFIRMED"
        if self.frames_since_axis_change is not None and (
            self.frames_since_axis_change >= self.blocked_timeout_frames
        ):
            return "BLOCKED"
        return "MOVING_CONFIRMED"

    def start(self, axis: str | WalkAxis, frame: int, x: int, y: int) -> WalkUpdate:
        self.axis = WalkAxis(axis)
        self.direction = (
            WalkDirection.LEFT if self.axis is WalkAxis.HORIZONTAL else WalkDirection.UP
        )
        self.status = _walking_status(self.direction)
        self.successful_moves = 0
        self.active = True
        self._last_frame = int(frame)
        self._last_axis_value = int(x if self.axis is WalkAxis.HORIZONTAL else y)
        self._last_position_change_frame = int(frame)
        self._direction_started_frame = int(frame)
        self._reversal_grace_until_frame = None
        self.previous_direction = None
        self.reversal_start_frame = None
        self.reversal_start_coordinate = None
        self.successful_moves_since_reversal = 0
        self.movement_confirmed_after_reversal = True
        self.wall_detection_armed = True
        return self._result(direction_changed=True)

    def stop(self) -> WalkUpdate:
        self.active = False
        self.direction = None
        self.status = WalkStatus.IDLE
        return self._result(send_stop=True)

    def pause(self, status: WalkStatus) -> WalkUpdate:
        if status not in {
            WalkStatus.PAUSED_BATTLE,
            WalkStatus.PAUSED_RAM,
            WalkStatus.PAUSED_COORDINATES,
            WalkStatus.PAUSED_MANUAL,
            WalkStatus.PAUSED_COMMAND,
            WalkStatus.PAUSED_COMMAND_LOST,
        }:
            raise ValueError("Pause requires a paused status.")
        self.active = False
        self.direction = None
        self.status = status
        return self._result(send_stop=True)

    def update(
        self,
        frame: int,
        x: int | None,
        y: int | None,
        *,
        connected: bool = True,
        battle_active: bool = False,
        manual_input: bool = False,
    ) -> WalkUpdate:
        if not self.active:
            return self._result()
        if not connected:
            return self.pause(WalkStatus.PAUSED_RAM)
        if battle_active:
            return self.pause(WalkStatus.PAUSED_BATTLE)
        if not _valid_coord(x) or not _valid_coord(y):
            return self.pause(WalkStatus.PAUSED_COORDINATES)
        if manual_input:
            return self.pause(WalkStatus.PAUSED_MANUAL)

        frame = int(frame)
        if self._last_frame is not None and frame < self._last_frame:
            self._last_frame = frame
            self._last_axis_value = x if self.axis is WalkAxis.HORIZONTAL else y
            self._last_position_change_frame = frame
            self._direction_started_frame = frame
            if not self.wall_detection_armed:
                self.reversal_start_frame = frame
                self.reversal_start_coordinate = self._last_axis_value
                self.successful_moves_since_reversal = 0
                self.movement_confirmed_after_reversal = False
                self._reversal_grace_until_frame = frame + self.grace_frames
            else:
                self._reversal_grace_until_frame = None
            return self._result()
        if frame == self._last_frame:
            return self._result()

        axis_value = x if self.axis is WalkAxis.HORIZONTAL else y
        self._last_frame = frame
        if axis_value != self._last_axis_value:
            self.successful_moves += 1
            self._last_axis_value = axis_value
            self._last_position_change_frame = frame
            self._direction_started_frame = frame
            if not self.wall_detection_armed:
                self.successful_moves_since_reversal += 1
                self.movement_confirmed_after_reversal = (
                    self.successful_moves_since_reversal >= self.min_moves_after_reversal
                )
                self._try_arm_wall_detection(frame)
                self._refresh_unconfirmed_status(frame)
            else:
                self.status = _walking_status(self.direction)
            return self._result()

        if not self.wall_detection_armed:
            self._try_arm_wall_detection(frame)
            self._refresh_unconfirmed_status(frame)
            return self._result()

        if (
            self._last_position_change_frame is not None
            and frame - self._last_position_change_frame >= self.blocked_timeout_frames
        ):
            self.previous_direction = self.direction
            self.direction = _reverse(self.direction)
            self.status = WalkStatus.BLOCKED_REVERSING
            self._direction_started_frame = frame
            self._last_position_change_frame = frame
            self._reversal_grace_until_frame = frame + self.grace_frames
            self.reversal_start_frame = frame
            self.reversal_start_coordinate = axis_value
            self.successful_moves_since_reversal = 0
            self.movement_confirmed_after_reversal = False
            self.wall_detection_armed = False
            return self._result(direction_changed=True)
        return self._result()

    def _try_arm_wall_detection(self, frame: int) -> None:
        grace_elapsed = (
            self._reversal_grace_until_frame is None
            or frame >= self._reversal_grace_until_frame
        )
        if (
            not self.wall_detection_armed
            and grace_elapsed
            and self.movement_confirmed_after_reversal
        ):
            self.wall_detection_armed = True
            self._last_position_change_frame = frame
            self._direction_started_frame = frame
            self._reversal_grace_until_frame = None
            self.status = _walking_status(self.direction)

    def _refresh_unconfirmed_status(self, frame: int) -> None:
        if self.wall_detection_armed:
            return
        grace_elapsed = (
            self._reversal_grace_until_frame is None
            or frame >= self._reversal_grace_until_frame
        )
        if grace_elapsed:
            self.status = WalkStatus.MOVING_UNCONFIRMED
        else:
            self.status = WalkStatus.BLOCKED_REVERSING

    def acknowledge_remote_pause(self, reason: str | None) -> WalkUpdate:
        statuses = {
            "battle": WalkStatus.PAUSED_BATTLE,
            "connection": WalkStatus.PAUSED_COMMAND_LOST,
            "command_stale": WalkStatus.PAUSED_COMMAND_LOST,
            "coordinates": WalkStatus.PAUSED_COORDINATES,
            "manual": WalkStatus.PAUSED_MANUAL,
            "command": WalkStatus.PAUSED_COMMAND,
        }
        return self.pause(statuses.get(reason, WalkStatus.PAUSED_COMMAND))

    def _result(self, *, direction_changed: bool = False, send_stop: bool = False) -> WalkUpdate:
        return WalkUpdate(
            self.status,
            self.direction,
            self.successful_moves,
            self.active,
            direction_changed,
            send_stop,
        )


def _valid_coord(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -0x8000 <= value <= 0x7FFF


def _reverse(direction: WalkDirection | None) -> WalkDirection:
    return {
        WalkDirection.LEFT: WalkDirection.RIGHT,
        WalkDirection.RIGHT: WalkDirection.LEFT,
        WalkDirection.UP: WalkDirection.DOWN,
        WalkDirection.DOWN: WalkDirection.UP,
    }[direction or WalkDirection.LEFT]


def _walking_status(direction: WalkDirection | None) -> WalkStatus:
    return {
        WalkDirection.LEFT: WalkStatus.WALKING_LEFT,
        WalkDirection.RIGHT: WalkStatus.WALKING_RIGHT,
        WalkDirection.UP: WalkStatus.WALKING_UP,
        WalkDirection.DOWN: WalkStatus.WALKING_DOWN,
    }[direction or WalkDirection.LEFT]
