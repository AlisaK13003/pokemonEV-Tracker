from __future__ import annotations

import pytest

from pokemon_ev_tracker.core.automation.friendship_walk import (
    BLOCKED_TIMEOUT_FRAMES,
    MIN_MOVES_AFTER_REVERSAL,
    REVERSAL_GRACE_FRAMES,
    FriendshipWalkController,
    WalkAxis,
    WalkDirection,
    WalkStatus,
)


@pytest.mark.parametrize(
    ("axis", "initial", "reverse", "coordinate", "irrelevant_coordinate"),
    [
        (WalkAxis.HORIZONTAL, WalkDirection.LEFT, WalkDirection.RIGHT, (8, 12), (8, 99)),
        (WalkAxis.VERTICAL, WalkDirection.UP, WalkDirection.DOWN, (8, 12), (99, 12)),
    ],
)
def test_wall_reverses_then_requires_grace_and_two_axis_changes_to_rearm(
    axis, initial, reverse, coordinate, irrelevant_coordinate
) -> None:
    walk = FriendshipWalkController()
    start_x, start_y = coordinate
    walk.start(axis, frame=100, x=start_x, y=start_y)
    assert walk.direction is initial
    assert walk.wall_detection_armed

    blocked = walk.update(100 + BLOCKED_TIMEOUT_FRAMES, *coordinate)
    assert blocked.direction is reverse
    assert blocked.status is WalkStatus.BLOCKED_REVERSING
    assert walk.previous_direction is initial
    assert walk.reversal_start_coordinate == (start_x if axis is WalkAxis.HORIZONTAL else start_y)
    assert walk.successful_moves_since_reversal == 0
    assert not walk.wall_detection_armed
    assert walk.last_position_change_frame == 100 + BLOCKED_TIMEOUT_FRAMES
    assert walk.frames_since_axis_change == 0
    assert walk.reversal_grace_remaining_frames == REVERSAL_GRACE_FRAMES
    assert walk.debug_state == "REVERSING"

    reversal_frame = walk.current_frame
    grace_end = reversal_frame + REVERSAL_GRACE_FRAMES
    still_stuck = walk.update(grace_end, *coordinate)
    assert still_stuck.direction is reverse
    assert still_stuck.status is WalkStatus.MOVING_UNCONFIRMED
    assert not walk.wall_detection_armed
    assert walk.successful_moves_since_reversal == 0
    assert walk.reversal_grace_remaining_frames == 0
    assert walk.debug_state == "MOVING_UNCONFIRMED"

    first_coordinate = (
        (start_x + 1, irrelevant_coordinate[1])
        if axis is WalkAxis.HORIZONTAL
        else (irrelevant_coordinate[0], start_y + 1)
    )
    first_move = walk.update(grace_end + 1, *first_coordinate)
    assert first_move.direction is reverse
    assert first_move.status is WalkStatus.MOVING_UNCONFIRMED
    assert walk.successful_moves_since_reversal == 1
    assert not walk.wall_detection_armed
    assert walk.debug_state == "MOVING_UNCONFIRMED"

    # A long stationary interval still cannot trigger another reverse before
    # the minimum number of relevant-axis changes has been observed.
    stalled_unconfirmed = walk.update(grace_end + 100, *first_coordinate)
    assert stalled_unconfirmed.direction is reverse
    assert stalled_unconfirmed.status is WalkStatus.MOVING_UNCONFIRMED
    assert not walk.wall_detection_armed

    second_coordinate = (
        first_coordinate[0] + 1,
        first_coordinate[1],
    ) if axis is WalkAxis.HORIZONTAL else (
        first_coordinate[0],
        first_coordinate[1] + 1,
    )
    confirmed = walk.update(grace_end + 101, *second_coordinate)
    assert confirmed.status is _walking_status_for(reverse)
    assert walk.successful_moves_since_reversal == MIN_MOVES_AFTER_REVERSAL
    assert walk.movement_confirmed_after_reversal
    assert walk.wall_detection_armed
    assert walk.debug_state == "MOVING_CONFIRMED"

    before_wall_timeout = walk.update(
        grace_end + 100 + BLOCKED_TIMEOUT_FRAMES,
        *second_coordinate,
    )
    assert before_wall_timeout.direction is reverse
    assert walk.wall_detection_armed

    second_wall = walk.update(
        grace_end + 101 + BLOCKED_TIMEOUT_FRAMES,
        *second_coordinate,
    )
    assert second_wall.direction is initial
    assert second_wall.status is WalkStatus.BLOCKED_REVERSING
    assert walk.previous_direction is reverse


def _walking_status_for(direction: WalkDirection) -> WalkStatus:
    return {
        WalkDirection.LEFT: WalkStatus.WALKING_LEFT,
        WalkDirection.RIGHT: WalkStatus.WALKING_RIGHT,
        WalkDirection.UP: WalkStatus.WALKING_UP,
        WalkDirection.DOWN: WalkStatus.WALKING_DOWN,
    }[direction]


def test_frames_stationary_before_reversal_do_not_carry_into_new_direction() -> None:
    walk = FriendshipWalkController()
    walk.start("horizontal", frame=200, x=20, y=5)
    reversal_frame = 200 + BLOCKED_TIMEOUT_FRAMES
    walk.update(reversal_frame, 20, 5)

    after_twenty_frames = walk.update(reversal_frame + REVERSAL_GRACE_FRAMES, 20, 5)

    assert after_twenty_frames.direction is WalkDirection.RIGHT
    assert walk.last_position_change_frame == reversal_frame
    assert walk.frames_since_axis_change == REVERSAL_GRACE_FRAMES
    assert walk.successful_moves_since_reversal == 0
    assert not walk.wall_detection_armed


def test_file_fallback_stationary_snapshots_advance_frame_based_timeout() -> None:
    walk = FriendshipWalkController()
    walk.start("horizontal", frame=1000, x=10, y=10)
    snapshots = [
        {"source": "file", "frame": 1010, "x": 10, "y": 10},
        {"source": "file", "frame": 1020, "x": 10, "y": 11},
        {"source": "file", "frame": 1030, "x": 10, "y": 12},
        {"source": "file", "frame": 1036, "x": 10, "y": 12},
    ]

    for snapshot in snapshots:
        update = walk.update(snapshot["frame"], snapshot["x"], snapshot["y"])

    assert update.direction is WalkDirection.RIGHT
    assert update.status is WalkStatus.BLOCKED_REVERSING
    assert walk.successful_moves == 0


def test_fast_forwarded_emulator_frames_still_trigger_frame_timeout() -> None:
    walk = FriendshipWalkController()
    walk.start("horizontal", frame=10, x=4, y=7)

    blocked = walk.update(10 + BLOCKED_TIMEOUT_FRAMES + 12, 4, 7)

    assert blocked.direction is WalkDirection.RIGHT
    assert blocked.status is WalkStatus.BLOCKED_REVERSING


def test_horizontal_and_vertical_modes_ignore_the_other_axis() -> None:
    horizontal = FriendshipWalkController()
    horizontal.start("horizontal", 0, 4, 7)
    horizontal.update(20, 4, -200)
    assert horizontal.frames_since_axis_change == 20
    assert horizontal.successful_moves == 0

    vertical = FriendshipWalkController()
    vertical.start("vertical", 0, 4, 7)
    vertical.update(20, -200, 7)
    assert vertical.frames_since_axis_change == 20
    assert vertical.successful_moves == 0


def test_active_axis_change_resets_timeout_and_increments_move_counter() -> None:
    walk = FriendshipWalkController()
    walk.start("horizontal", frame=100, x=10, y=10)
    walk.update(130, 10, 50)
    assert walk.frames_since_axis_change == 30

    moved = walk.update(131, 9, 50)
    assert moved.successful_moves == 1
    assert walk.last_position_change_frame == 131
    assert walk.frames_since_axis_change == 0


def test_battle_connection_and_coordinate_failures_pause() -> None:
    walk = FriendshipWalkController()
    walk.start("horizontal", frame=0, x=1, y=1)

    battle = walk.update(1, 1, 1, battle_active=True)
    assert battle.status is WalkStatus.PAUSED_BATTLE
    assert battle.send_stop

    disconnected = FriendshipWalkController()
    disconnected.start("horizontal", frame=0, x=1, y=1)
    lost = disconnected.update(1, 1, 1, connected=False)
    assert lost.status is WalkStatus.PAUSED_RAM
    assert lost.send_stop

    invalid = FriendshipWalkController()
    invalid.start("horizontal", frame=0, x=1, y=1)
    unavailable = invalid.update(1, None, 1)
    assert unavailable.status is WalkStatus.PAUSED_COORDINATES
    assert unavailable.send_stop


def test_manual_input_and_stop_release_without_counting_wall_stall() -> None:
    walk = FriendshipWalkController()
    walk.start("horizontal", frame=0, x=1, y=1)
    walk.update(BLOCKED_TIMEOUT_FRAMES, 1, 1)

    result = walk.stop()

    assert not result.active
    assert result.status is WalkStatus.IDLE
    assert result.send_stop
    assert result.successful_moves == 0

    restarted = FriendshipWalkController()
    restarted.start("horizontal", frame=0, x=1, y=1)
    manual = restarted.update(1, 1, 1, manual_input=True)
    assert manual.status is WalkStatus.PAUSED_MANUAL
    assert manual.send_stop
