-- BizHawk RAM-1 probe for the Pokemon Platinum EV Tracker.
-- Run this from EmuHawk's Lua Console while the Nintendo DS core is active.

local HOST = "127.0.0.1"
local PORT = 46387
local HEARTBEAT_INTERVAL = 120
local PARTY_INTERVAL = 30
local DOMAIN_REFRESH_INTERVAL = 600
local CONNECT_RETRY_INTERVAL = 300
local CONNECT_TIMEOUT_SECONDS = 0.03
local COMMAND_FILE_POLL_INTERVAL = 15
local WALK_REVERSAL_GRACE_FRAMES = 8
local MAX_FALLBACK_BYTES = 512 * 1024
local COORDINATE_SCAN_CHUNK_BYTES = 16384
local MAX_COORDINATE_SCAN_BYTES = 0x400000
local TEMP_ROOT = os.getenv("TEMP") or os.getenv("TMP") or os.getenv("TMPDIR")
local FALLBACK_FILE = TEMP_ROOT and (TEMP_ROOT .. "\\ev_tracker_bizhawk.jsonl") or nil
local COMMAND_FILE = TEMP_ROOT and (TEMP_ROOT .. "\\ev_tracker_bizhawk_command.txt") or nil
local COORDINATE_SCAN_FILE = TEMP_ROOT and (TEMP_ROOT .. "\\ev_tracker_bizhawk_coordinates.jsonl") or nil
local MAIN_RAM_BASE = 0x02000000
local PLATINUM_PARTY_POINTER_ADDRESS = 0x02101D2C
local PLATINUM_PARTY_COUNT_OFFSET = 0xD090
local PLATINUM_PARTY_RECORDS_OFFSET = 0xD094
local PARTY_POKEMON_SIZE = 236
local PARTY_BYTES = 4 + (6 * PARTY_POKEMON_SIZE)
local BATTLE_BATTLER_SIZE = 0xC0
local BATTLE_BATTLER_OFFSETS = {0x54598, 0x54658, 0x54718, 0x547D8}
local PLAYER_X_OFFSET = 0x001C5AFE
local PLAYER_Y_OFFSET = 0x001C5B02
-- This wall-time lease only detects a lost Python controller; movement timing is frame-based.
local WALK_COMMAND_LEASE_SECONDS = 4.0

local socket = nil
pcall(function()
    socket = require("socket")
end)

local client = nil
local last_connect_attempt = -999999
local pending_tcp_line = nil
local pending_tcp_offset = 1
local queued_tcp_line = nil
local last_domain_error = nil
local warned_null_core = false
local run_id = tostring(os.time()) .. "-" .. tostring(math.random(100000, 999999))
local command_buffer = ""
local last_command_file_poll_frame = -COMMAND_FILE_POLL_INTERVAL
local coordinate_scan = nil
local coordinate_preview = nil
local previous_preview_x = nil
local previous_preview_y = nil
local previous_player_x = nil
local previous_player_y = nil
local friendship_walk = {
    enabled = false,
    direction = nil,
    mode = nil,
    status = "Idle",
    pause_reason = nil,
    last_command_time = 0,
    injected_direction = nil,
    b_injected = false,
    pending_direction = nil,
    reversal_until_frame = nil,
    ack_sequence = nil,
    ack_frame = nil,
    ack_action = nil,
    release_pending = false,
}
local send_line
local write_fallback
local byte_hex = {}
for value = 0, 255 do
    byte_hex[value] = string.format("%02X", value)
end

local function json_escape(value)
    value = tostring(value or "")
    value = value:gsub("\\", "\\\\")
    value = value:gsub("\"", "\\\"")
    value = value:gsub("\b", "\\b")
    value = value:gsub("\f", "\\f")
    value = value:gsub("\n", "\\n")
    value = value:gsub("\r", "\\r")
    value = value:gsub("\t", "\\t")
    return value
end

local function json_value(value)
    local value_type = type(value)
    if value_type == "number" or value_type == "boolean" then
        return tostring(value)
    end
    if value_type == "table" then
        local parts = {}
        for index, item in ipairs(value) do
            parts[index] = json_value(item)
        end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    if value == nil then
        return "null"
    end
    return "\"" .. json_escape(value) .. "\""
end

local function json_object(fields)
    local parts = {}
    for index, pair in ipairs(fields) do
        parts[index] = "\"" .. pair[1] .. "\":" .. json_value(pair[2])
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function try_call(fn, fallback)
    local ok, result = pcall(fn)
    if ok then
        return result
    end
    return fallback
end

local function get_core_name()
    return try_call(function() return emu.getsystemid() end, "unknown")
end

local function memory_domains_supported()
    local core = string.lower(tostring(get_core_name() or ""))
    if core == "null" or core == "nullhawk" then
        if not warned_null_core then
            print("EV Tracker: waiting for a loaded Nintendo DS ROM/core; NullHawk has no memory domains.")
            warned_null_core = true
        end
        return false
    end
    warned_null_core = false
    return true
end

local function get_frame_count()
    return try_call(function() return emu.framecount() end, 0)
end

local function domain_names()
    if not memory_domains_supported() then
        return {}
    end
    local ok, domains = pcall(function() return memory.getmemorydomainlist() end)
    if not ok then
        if domains ~= last_domain_error then
            print("EV Tracker: memory domains unavailable: " .. tostring(domains))
            last_domain_error = domains
        end
        return {}
    end
    local names = {}
    for key, value in pairs(domains) do
        if type(key) == "number" then
            table.insert(names, tostring(value))
        else
            table.insert(names, tostring(key))
        end
    end
    table.sort(names)
    return names
end

local function domain_size(name)
    if name == nil or not memory_domains_supported() then
        return nil
    end
    return try_call(function() return memory.getmemorydomainsize(name) end, nil)
end

local function is_readable_domain(name)
    if name == nil or not memory_domains_supported() then
        return false
    end
    local ok = pcall(function()
        memory.usememorydomain(name)
        memory.readbyte(0)
    end)
    return ok
end

local function choose_main_ram_domain(names)
    local readable = {}
    for _, name in ipairs(names) do
        if is_readable_domain(name) then
            local size = domain_size(name)
            table.insert(readable, {name = name, size = size or 0})
        end
    end

    for _, candidate in ipairs(readable) do
        local lowered = string.lower(candidate.name)
        if candidate.size >= 0x400000 and string.find(lowered, "main") and string.find(lowered, "ram") then
            return candidate.name
        end
    end

    for _, candidate in ipairs(readable) do
        if candidate.size == 0x400000 or candidate.size == 0x800000 then
            return candidate.name
        end
    end

    for _, candidate in ipairs(readable) do
        local lowered = string.lower(candidate.name)
        if string.find(lowered, "ram") then
            return candidate.name
        end
    end

    if #readable > 0 then
        return readable[1].name
    end
    return nil
end

local function diagnostic_reads(domain)
    local reads = {}
    if domain == nil then
        return reads
    end

    local addresses = {0x00000000, 0x00000004, 0x00001000, 0x00002000}
    memory.usememorydomain(domain)
    for _, address in ipairs(addresses) do
        local value = try_call(function() return memory.readbyte(address) end, nil)
        table.insert(reads, json_object({
            {"address", string.format("0x%08X", address)},
            {"value", value},
        }))
    end
    return reads
end

local function address_to_domain_offset(address)
    if address >= MAIN_RAM_BASE then
        return address - MAIN_RAM_BASE
    end
    return address
end

local function read_u32_le(domain, offset)
    if domain == nil or offset == nil then
        return nil
    end
    local ok, value = pcall(function()
        if memory.read_u32_le ~= nil then
            return memory.read_u32_le(offset, domain)
        end
        memory.usememorydomain(domain)
        local b0 = memory.readbyte(offset)
        local b1 = memory.readbyte(offset + 1)
        local b2 = memory.readbyte(offset + 2)
        local b3 = memory.readbyte(offset + 3)
        return b0 + (b1 * 0x100) + (b2 * 0x10000) + (b3 * 0x1000000)
    end)
    if ok then
        return value
    end
    return nil
end

local function read_u16_le(domain, offset)
    if domain == nil or offset == nil then
        return nil
    end
    local ok, value = pcall(function()
        if memory.read_u16_le ~= nil then
            return memory.read_u16_le(offset, domain)
        end
        memory.usememorydomain(domain)
        local b0 = memory.readbyte(offset)
        local b1 = memory.readbyte(offset + 1)
        return b0 + (b1 * 0x100)
    end)
    return ok and value or nil
end

local function read_bytes(domain, offset, length)
    if domain == nil or offset == nil then
        return nil
    end
    if memory.read_bytes_as_binary_string ~= nil then
        local ok, bytes = pcall(memory.read_bytes_as_binary_string, offset, length, domain)
        if ok and bytes ~= nil then
            return bytes
        end
    end
    if memory.read_bytes_as_array ~= nil then
        local ok, bytes = pcall(memory.read_bytes_as_array, offset, length, domain)
        if ok and bytes ~= nil then
            return bytes
        end
    end

    local ok, bytes = pcall(function()
        memory.usememorydomain(domain)
        local result = {}
        for index = 0, length - 1 do
            result[index + 1] = memory.readbyte(offset + index)
        end
        return result
    end)
    return ok and bytes or nil
end

local function read_bytes_hex(domain, offset, length)
    local bytes = read_bytes(domain, offset, length)
    if bytes == nil then
        return nil
    end
    local parts = {}
    for index = 1, length do
        local value
        if type(bytes) == "string" then
            value = string.byte(bytes, index)
        else
            value = bytes[index]
        end
        if value == nil then
            return nil
        end
        parts[index] = byte_hex[value]
    end
    return table.concat(parts)
end

local function bytes_to_hex(bytes, length)
    if bytes == nil then
        return nil
    end
    local parts = {}
    for index = 1, length do
        local value = type(bytes) == "string" and string.byte(bytes, index) or bytes[index]
        if value == nil then
            return nil
        end
        parts[index] = byte_hex[value]
    end
    return table.concat(parts)
end

local function read_coordinate(domain, offset, data_type)
    local value = read_u16_le(domain, offset)
    if value ~= nil and data_type == "s16" and value >= 0x8000 then
        value = value - 0x10000
    end
    return value
end

local function player_coordinates(domain)
    return read_coordinate(domain, PLAYER_X_OFFSET, "s16"),
        read_coordinate(domain, PLAYER_Y_OFFSET, "s16")
end

local function battler_record_active(domain, pointer_value, battler_index)
    if domain == nil or pointer_value == nil then
        return false
    end
    local relative_offset = BATTLE_BATTLER_OFFSETS[battler_index + 1]
    if relative_offset == nil then
        return false
    end
    local record_offset = address_to_domain_offset(pointer_value + relative_offset)
    local species = read_u16_le(domain, record_offset)
    local level = try_call(function()
        memory.usememorydomain(domain)
        return memory.readbyte(record_offset + 0x34)
    end, nil)
    return species ~= nil and species >= 1 and species <= 493
        and level ~= nil and level >= 1 and level <= 100
end

local function battle_active_now(domain)
    local pointer_offset = address_to_domain_offset(PLATINUM_PARTY_POINTER_ADDRESS)
    local pointer_value = read_u32_le(domain, pointer_offset)
    if pointer_value == nil then
        return false
    end
    return (battler_record_active(domain, pointer_value, 0)
            and battler_record_active(domain, pointer_value, 1))
        or (battler_record_active(domain, pointer_value, 2)
            and battler_record_active(domain, pointer_value, 3))
end

local function release_walk_input()
    pcall(function()
        joypad.set({Up = false, Down = false, Left = false, Right = false, B = false})
    end)
    friendship_walk.injected_direction = nil
    friendship_walk.b_injected = false
    friendship_walk.pending_direction = nil
    friendship_walk.reversal_until_frame = nil
    friendship_walk.release_pending = false
end

local function pause_friendship_walk(reason, status, release_input)
    friendship_walk.enabled = false
    friendship_walk.direction = nil
    friendship_walk.pending_direction = nil
    friendship_walk.reversal_until_frame = nil
    friendship_walk.pause_reason = reason
    friendship_walk.status = status
    friendship_walk.release_pending = release_input ~= false
end

local function apply_friendship_walk(frame, domain)
    if friendship_walk.enabled then
        if os.time() - friendship_walk.last_command_time > WALK_COMMAND_LEASE_SECONDS then
            pause_friendship_walk("command_stale", "Paused — Movement command channel lost", true)
        else
            local x, y = player_coordinates(domain)
            if x == nil or y == nil then
                pause_friendship_walk("coordinates", "Paused — Coordinates unavailable", true)
            elseif battle_active_now(domain) then
                pause_friendship_walk("battle", "Paused — Battle", true)
            end
        end
    end

    if friendship_walk.release_pending then
        release_walk_input()
    elseif friendship_walk.enabled then
        if friendship_walk.pending_direction ~= nil
            and frame >= (friendship_walk.reversal_until_frame or frame) then
            friendship_walk.direction = friendship_walk.pending_direction
            friendship_walk.pending_direction = nil
            friendship_walk.reversal_until_frame = nil
            friendship_walk.status = "Walking " .. friendship_walk.direction
        end
        local direction = friendship_walk.direction
        local inputs = {
            Up = direction == "Up",
            Down = direction == "Down",
            Left = direction == "Left",
            Right = direction == "Right",
            B = true,
        }
        local ok = pcall(function() joypad.set(inputs) end)
        if ok then
            friendship_walk.injected_direction = direction
            friendship_walk.b_injected = true
        else
            pause_friendship_walk("command", "Paused — Controller unavailable", true)
            release_walk_input()
        end
    end
end

local function party_memory_message(frame, domain)
    local pointer_offset = address_to_domain_offset(PLATINUM_PARTY_POINTER_ADDRESS)
    local pointer_value = read_u32_le(domain, pointer_offset)
    local party_address = nil
    local party_offset = nil
    local party_records_address = nil
    local party_records_offset = nil
    local party_count = nil
    local raw_party = nil
    local candidate_diagnostics = {}
    local battle_battler_fields = {}
    local party_count_valid = false

    if pointer_value ~= nil then
        party_address = pointer_value + PLATINUM_PARTY_COUNT_OFFSET
        party_offset = address_to_domain_offset(party_address)
        party_records_address = pointer_value + PLATINUM_PARTY_RECORDS_OFFSET
        party_records_offset = address_to_domain_offset(party_records_address)
        party_count = read_u32_le(domain, party_offset)
        party_count_valid = party_count ~= nil and party_count >= 0 and party_count <= 6
        raw_party = read_bytes_hex(domain, party_offset, PARTY_BYTES)
        for index, relative_offset in ipairs(BATTLE_BATTLER_OFFSETS) do
            local battler_index = index - 1
            local record_address = pointer_value + relative_offset
            local record_offset = address_to_domain_offset(record_address)
            local raw_record = read_bytes_hex(domain, record_offset, BATTLE_BATTLER_SIZE)
            local prefix = string.format("battle_battler_%d_", battler_index)
            table.insert(battle_battler_fields, {prefix .. "relative_offset", string.format("0x%X", relative_offset)})
            table.insert(battle_battler_fields, {prefix .. "address", string.format("0x%08X", record_address)})
            table.insert(battle_battler_fields, {prefix .. "raw_hex", raw_record})
        end
        candidate_diagnostics[1] = string.format(
            "count relative=0x%X address=0x%08X offset=0x%08X count=%s valid=%s",
            PLATINUM_PARTY_COUNT_OFFSET,
            party_address,
            party_offset,
            tostring(party_count),
            tostring(party_count_valid)
        )
        candidate_diagnostics[2] = string.format(
            "records relative=0x%X address=0x%08X offset=0x%08X stride=0x%X",
            PLATINUM_PARTY_RECORDS_OFFSET,
            party_records_address,
            party_records_offset,
            PARTY_POKEMON_SIZE
        )
    end

    local preview_x = coordinate_preview and read_coordinate(domain, coordinate_preview.x_offset, coordinate_preview.data_type) or nil
    local preview_y = coordinate_preview and read_coordinate(domain, coordinate_preview.y_offset, coordinate_preview.data_type) or nil
    local preview_previous_x = previous_preview_x
    local preview_previous_y = previous_preview_y
    local player_x, player_y = player_coordinates(domain)
    local player_delta_x = player_x ~= nil and previous_player_x ~= nil
        and player_x - previous_player_x or nil
    local player_delta_y = player_y ~= nil and previous_player_y ~= nil
        and player_y - previous_player_y or nil
    local message_fields = {
        {"type", "party_memory"},
        {"run_id", run_id},
        {"frame", frame},
        {"core", get_core_name()},
        {"domain", domain},
        {"main_ram_base", string.format("0x%08X", MAIN_RAM_BASE)},
        {"coordinate_preview_x", preview_x},
        {"coordinate_preview_y", preview_y},
        {"coordinate_preview_previous_x", preview_previous_x},
        {"coordinate_preview_previous_y", preview_previous_y},
        {"coordinate_preview_x_offset", coordinate_preview and string.format("0x%08X", coordinate_preview.x_offset) or nil},
        {"coordinate_preview_y_offset", coordinate_preview and string.format("0x%08X", coordinate_preview.y_offset) or nil},
        {"coordinate_preview_type", coordinate_preview and coordinate_preview.data_type or nil},
        {"player_x", player_x},
        {"player_y", player_y},
        {"player_delta_x", player_delta_x},
        {"player_delta_y", player_delta_y},
        {"player_coordinates_validated", true},
        {"player_x_offset", string.format("0x%08X", PLAYER_X_OFFSET)},
        {"player_y_offset", string.format("0x%08X", PLAYER_Y_OFFSET)},
        {"friendship_walk_enabled", friendship_walk.enabled},
        {"friendship_walk_mode", friendship_walk.mode},
        {"friendship_walk_direction", friendship_walk.direction or friendship_walk.pending_direction},
        {"friendship_walk_requested_direction", friendship_walk.direction or friendship_walk.pending_direction},
        {"friendship_walk_injected_direction", friendship_walk.injected_direction},
        {"friendship_walk_b_injected", friendship_walk.b_injected},
        {"friendship_walk_reversal_until_frame", friendship_walk.reversal_until_frame},
        {"friendship_walk_status", friendship_walk.status},
        {"friendship_walk_pause_reason", friendship_walk.pause_reason},
        {"friendship_walk_ack_sequence", friendship_walk.ack_sequence},
        {"friendship_walk_ack_frame", friendship_walk.ack_frame},
        {"friendship_walk_ack_action", friendship_walk.ack_action},
        {"pointer_address", string.format("0x%08X", PLATINUM_PARTY_POINTER_ADDRESS)},
        {"pointer_offset", string.format("0x%08X", pointer_offset)},
        {"pointer_value", pointer_value and string.format("0x%08X", pointer_value) or nil},
        {"party_relative_offset", pointer_value and string.format("0x%X", PLATINUM_PARTY_COUNT_OFFSET) or nil},
        {"party_offset_candidates", candidate_diagnostics},
        {"party_address", party_address and string.format("0x%08X", party_address) or nil},
        {"party_offset", party_offset and string.format("0x%08X", party_offset) or nil},
        {"party_records_address", party_records_address and string.format("0x%08X", party_records_address) or nil},
        {"party_records_offset", party_records_offset and string.format("0x%08X", party_records_offset) or nil},
        {"party_count", party_count},
        {"party_count_valid", party_count_valid},
        {"pokemon_size", PARTY_POKEMON_SIZE},
        {"raw_party_hex", raw_party},
    }
    if coordinate_preview then
        if preview_x ~= nil and preview_y ~= nil then
            previous_preview_x = preview_x
            previous_preview_y = preview_y
        end
    else
        previous_preview_x = nil
        previous_preview_y = nil
    end
    if player_x ~= nil and player_y ~= nil then
        previous_player_x = player_x
        previous_player_y = player_y
    else
        previous_player_x = nil
        previous_player_y = nil
    end
    for _, field in ipairs(battle_battler_fields) do
        table.insert(message_fields, field)
    end
    local message = json_object(message_fields)
    return message
end

local function close_client()
    if client ~= nil then
        pcall(function() client:close() end)
    end
    client = nil
    command_buffer = ""
    if coordinate_scan ~= nil and coordinate_scan.transport == "tcp" then
        coordinate_scan = nil
    end
end

local function send_scan_error(capture_id, message, transport)
    coordinate_scan = {
        capture_id = capture_id,
        stage = "error",
        message = message,
        transport = transport,
        file_started = false,
    }
end

local function process_command(line, frame, domain, transport)
    line = line:gsub("\r", "")
    local sequence, walk_mode = line:match("^WALK|(%d+)|START|(horizontal)$")
    if sequence == nil then
        sequence, walk_mode = line:match("^WALK|(%d+)|START|(vertical)$")
    end
    if sequence ~= nil then
        local x, y = player_coordinates(domain)
        if x == nil or y == nil then
            pause_friendship_walk("coordinates", "Paused — Coordinates unavailable", true)
        elseif battle_active_now(domain) then
            pause_friendship_walk("battle", "Paused — Battle", true)
        else
            friendship_walk.enabled = true
            friendship_walk.mode = walk_mode
            friendship_walk.direction = walk_mode == "horizontal" and "Left" or "Up"
            friendship_walk.pending_direction = nil
            friendship_walk.reversal_until_frame = nil
            friendship_walk.injected_direction = nil
            friendship_walk.b_injected = false
            friendship_walk.status = "Walking " .. friendship_walk.direction
            friendship_walk.pause_reason = nil
            -- This lease uses wall-clock time; movement/reversal remains frame-based.
            friendship_walk.last_command_time = os.time()
            friendship_walk.release_pending = false
        end
        friendship_walk.ack_sequence = tonumber(sequence)
        friendship_walk.ack_frame = frame
        friendship_walk.ack_action = "START"
        return
    end

    sequence = line:match("^WALK|(%d+)|STOP$")
    if sequence ~= nil then
        friendship_walk.enabled = false
        friendship_walk.direction = nil
        friendship_walk.pending_direction = nil
        friendship_walk.reversal_until_frame = nil
        friendship_walk.injected_direction = nil
        friendship_walk.b_injected = false
        friendship_walk.status = "Idle"
        friendship_walk.pause_reason = nil
        friendship_walk.release_pending = true
        friendship_walk.ack_sequence = tonumber(sequence)
        friendship_walk.ack_frame = frame
        friendship_walk.ack_action = "STOP"
        return
    end

    sequence = line:match("^WALK|(%d+)|PING$")
    if sequence ~= nil then
        if friendship_walk.enabled then
            friendship_walk.last_command_time = os.time()
        end
        friendship_walk.ack_sequence = tonumber(sequence)
        friendship_walk.ack_frame = frame
        friendship_walk.ack_action = "PING"
        return
    end
    local direction_sequence, walk_direction = line:match("^WALK|(%d+)|DIRECTION|(Left)$")
    if direction_sequence == nil then
        direction_sequence, walk_direction = line:match("^WALK|(%d+)|DIRECTION|(Right)$")
    end
    if direction_sequence == nil then
        direction_sequence, walk_direction = line:match("^WALK|(%d+)|DIRECTION|(Up)$")
    end
    if direction_sequence == nil then
        direction_sequence, walk_direction = line:match("^WALK|(%d+)|DIRECTION|(Down)$")
    end
    if walk_direction ~= nil and friendship_walk.enabled then
        friendship_walk.direction = nil
        friendship_walk.pending_direction = walk_direction
        friendship_walk.reversal_until_frame = frame + WALK_REVERSAL_GRACE_FRAMES
        friendship_walk.injected_direction = nil
        friendship_walk.status = "Blocked — reversing"
        friendship_walk.last_command_time = os.time()
        friendship_walk.ack_sequence = tonumber(direction_sequence)
        friendship_walk.ack_frame = frame
        friendship_walk.ack_action = "DIRECTION"
        return
    elseif direction_sequence ~= nil then
        friendship_walk.ack_sequence = tonumber(direction_sequence)
        friendship_walk.ack_frame = frame
        friendship_walk.ack_action = "DIRECTION"
        return
    end
    if line == "CLEAR_PREVIEW" then
        coordinate_preview = nil
        previous_preview_x = nil
        previous_preview_y = nil
        return
    end
    local x_offset, y_offset, data_type = line:match("^PREVIEW|(%d+)|(%d+)|(u16)$")
    if x_offset == nil then
        x_offset, y_offset, data_type = line:match("^PREVIEW|(%d+)|(%d+)|(s16)$")
    end
    if x_offset ~= nil then
        coordinate_preview = {
            x_offset = tonumber(x_offset),
            y_offset = tonumber(y_offset),
            data_type = data_type,
        }
        previous_preview_x = nil
        previous_preview_y = nil
        return
    end

    local capture_id, label, start_offset, length = line:match(
        "^CAPTURE|([%w%-]+)|([%w]+)|(%d+)|(%d+)$"
    )
    if capture_id == nil then
        return
    end
    if coordinate_scan ~= nil then
        send_scan_error(
            capture_id,
            "Another coordinate capture is already in progress.",
            transport
        )
        return
    end
    start_offset = tonumber(start_offset)
    length = tonumber(length)
    local total = domain_size(domain)
    if domain == nil or total == nil or start_offset + length > total
        or length < 2 or length > MAX_COORDINATE_SCAN_BYTES
        or start_offset % 2 ~= 0 or length % 2 ~= 0 then
        send_scan_error(
            capture_id,
            "Invalid Main RAM range or unavailable memory domain.",
            transport
        )
        return
    end
    coordinate_scan = {
        capture_id = capture_id,
        label = label,
        start_offset = start_offset,
        length = length,
        cursor = 0,
        domain = domain,
        stage = "start",
        transport = transport,
        file_started = false,
    }
end

local function poll_command_file(frame, domain)
    if COMMAND_FILE == nil
        or frame - last_command_file_poll_frame < COMMAND_FILE_POLL_INTERVAL then
        return
    end
    last_command_file_poll_frame = frame
    local handle = io.open(COMMAND_FILE, "r")
    if handle == nil then
        return
    end
    local line = handle:read("*l")
    handle:close()
    os.remove(COMMAND_FILE)
    if line ~= nil and line ~= "" then
        process_command(line, frame, domain, "file")
    end
end

local function poll_commands(frame, domain)
    if client ~= nil then
        for _ = 1, 4 do
            local ok, line, receive_error, partial = pcall(function()
                return client:receive("*l")
            end)
            if not ok then
                close_client()
                break
            end
            if line ~= nil then
                local complete = command_buffer .. line
                command_buffer = ""
                process_command(complete, frame, domain, "tcp")
            elseif partial ~= nil and partial ~= "" then
                command_buffer = command_buffer .. partial
                if #command_buffer > 256 then
                    command_buffer = ""
                end
                break
            elseif receive_error == "closed" then
                close_client()
                break
            else
                break
            end
        end
    end
    poll_command_file(frame, domain)
end

local function send_coordinate_event(scan, line, frame)
    if scan.transport == "tcp" then
        return send_line(line, frame)
    end
    if COORDINATE_SCAN_FILE == nil then
        write_fallback(line)
        return false
    end
    local mode = scan.file_started and "a" or "w"
    local handle = io.open(COORDINATE_SCAN_FILE, mode)
    if handle == nil then
        write_fallback(line)
        return false
    end
    handle:write(line)
    handle:write("\n")
    handle:close()
    scan.file_started = true
    return true
end

local function advance_coordinate_scan(frame)
    local scan = coordinate_scan
    if scan == nil then
        return
    end
    if scan.transport == "tcp" and client == nil then
        coordinate_scan = nil
        return
    end
    if scan.transport == "tcp" and (pending_tcp_line ~= nil or queued_tcp_line ~= nil) then
        return
    end

    if scan.stage == "error" then
        send_coordinate_event(scan, json_object({
            {"type", "coordinate_scan_error"},
            {"capture_id", scan.capture_id},
            {"message", scan.message},
        }), frame)
        coordinate_scan = nil
        return
    end
    if scan.stage == "start" then
        send_coordinate_event(scan, json_object({
            {"type", "coordinate_scan_start"},
            {"capture_id", scan.capture_id},
            {"label", scan.label},
            {"start_offset", scan.start_offset},
            {"length", scan.length},
        }), frame)
        scan.stage = "chunks"
        return
    end
    if scan.cursor < scan.length then
        local chunk_length = math.min(COORDINATE_SCAN_CHUNK_BYTES, scan.length - scan.cursor)
        local chunk = read_bytes(scan.domain, scan.start_offset + scan.cursor, chunk_length)
        local encoded = bytes_to_hex(chunk, chunk_length)
        if encoded == nil then
            send_scan_error(
                scan.capture_id,
                "BizHawk could not read this RAM range.",
                scan.transport
            )
            return
        end
        send_coordinate_event(scan, json_object({
            {"type", "coordinate_scan_chunk"},
            {"capture_id", scan.capture_id},
            {"chunk_offset", scan.cursor},
            {"data_hex", encoded},
        }), frame)
        scan.cursor = scan.cursor + chunk_length
        return
    end
    send_coordinate_event(scan, json_object({
        {"type", "coordinate_scan_end"},
        {"capture_id", scan.capture_id},
    }), frame)
    coordinate_scan = nil
end

local function ensure_client(frame)
    if socket == nil then
        return false
    end
    if client ~= nil then
        return true
    end
    if frame - last_connect_attempt < CONNECT_RETRY_INTERVAL then
        return false
    end

    last_connect_attempt = frame
    local ok, tcp = pcall(function() return socket.tcp() end)
    if not ok or tcp == nil then
        return false
    end
    tcp:settimeout(CONNECT_TIMEOUT_SECONDS)
    local connected = tcp:connect(HOST, PORT)
    if connected == 1 or connected == true then
        tcp:settimeout(0)
        client = tcp
        print("EV Tracker: connected to Python TCP server at " .. HOST .. ":" .. PORT)
        return true
    end
    pcall(function() tcp:close() end)
    return false
end

write_fallback = function(line)
    if FALLBACK_FILE == nil then
        return
    end
    local handle = io.open(FALLBACK_FILE, "a")
    if handle ~= nil then
        local size = handle:seek("end") or 0
        if size >= MAX_FALLBACK_BYTES then
            handle:close()
            handle = io.open(FALLBACK_FILE, "w")
        end
    end
    if handle ~= nil then
        handle:write(line)
        handle:write("\n")
        handle:close()
    end
end

local function flush_tcp()
    if client == nil then
        return
    end
    if pending_tcp_line == nil and queued_tcp_line ~= nil then
        pending_tcp_line = queued_tcp_line
        pending_tcp_offset = 1
        queued_tcp_line = nil
    end
    if pending_tcp_line == nil then
        return
    end

    local ok, sent, send_error, last_sent = pcall(function()
        return client:send(pending_tcp_line, pending_tcp_offset)
    end)
    if not ok then
        send_error = sent
        sent = nil
        last_sent = nil
    end
    if sent ~= nil then
        pending_tcp_line = nil
        pending_tcp_offset = 1
    elseif send_error == "timeout" then
        pending_tcp_offset = (last_sent or (pending_tcp_offset - 1)) + 1
        if pending_tcp_offset > #pending_tcp_line then
            pending_tcp_line = nil
            pending_tcp_offset = 1
        end
    else
        pcall(function() client:close() end)
        client = nil
        if pending_tcp_line ~= nil then
            write_fallback(pending_tcp_line:sub(1, -2))
        end
        if queued_tcp_line ~= nil then
            write_fallback(queued_tcp_line:sub(1, -2))
        end
        pending_tcp_line = nil
        pending_tcp_offset = 1
        queued_tcp_line = nil
    end
end

send_line = function(line, frame)
    if ensure_client(frame) and client ~= nil then
        local data = line .. "\n"
        if pending_tcp_line == nil then
            pending_tcp_line = data
            pending_tcp_offset = 1
        else
            queued_tcp_line = data
        end
        flush_tcp()
        return true
    end
    write_fallback(line)
    return false
end

local domains = domain_names()
local active_domain = choose_main_ram_domain(domains)
print("EV Tracker RAM reader started; domain=" .. tostring(active_domain))

local next_domain_refresh = get_frame_count() + DOMAIN_REFRESH_INTERVAL
local last_domain_refresh_frame = get_frame_count()
local domain_refresh_ticks = 0
local last_heartbeat_frame = nil
local last_party_frame = nil

if COMMAND_FILE ~= nil then
    os.remove(COMMAND_FILE)
end

while true do
    local frame = get_frame_count()
    flush_tcp()
    domain_refresh_ticks = domain_refresh_ticks + 1
    if frame < last_domain_refresh_frame
        or frame >= next_domain_refresh
        or (active_domain == nil and domain_refresh_ticks >= HEARTBEAT_INTERVAL) then
        domains = domain_names()
        active_domain = choose_main_ram_domain(domains)
        last_domain_refresh_frame = frame
        next_domain_refresh = frame + (active_domain and DOMAIN_REFRESH_INTERVAL or HEARTBEAT_INTERVAL)
        domain_refresh_ticks = 0
    end

    poll_commands(frame, active_domain)
    apply_friendship_walk(frame, active_domain)
    if coordinate_scan ~= nil then
        if frame ~= last_party_frame and frame % PARTY_INTERVAL == 0 then
            last_party_frame = frame
            send_line(party_memory_message(frame, active_domain), frame)
        end
        if frame ~= last_heartbeat_frame and frame % HEARTBEAT_INTERVAL == 0
            and pending_tcp_line == nil and queued_tcp_line == nil then
            last_heartbeat_frame = frame
            local reads = diagnostic_reads(active_domain)
            local message = json_object({
                {"type", "heartbeat"},
                {"run_id", run_id},
                {"frame", frame},
                {"core", get_core_name()},
                {"domains", domains},
                {"active_domain", active_domain},
                {"diagnostic_reads", "__READS__"},
                {"transport", socket and "tcp_or_file" or "file"},
                {"connected", client ~= nil},
            })
            message = message:gsub("\"__READS__\"", "[" .. table.concat(reads, ",") .. "]")
            send_line(message, frame)
        else
            advance_coordinate_scan(frame)
        end
    else
        if frame ~= last_heartbeat_frame and frame % HEARTBEAT_INTERVAL == 0 then
            last_heartbeat_frame = frame
            local reads = diagnostic_reads(active_domain)
            local message = json_object({
                {"type", "heartbeat"},
                {"run_id", run_id},
                {"frame", frame},
                {"core", get_core_name()},
                {"domains", domains},
                {"active_domain", active_domain},
                {"diagnostic_reads", "__READS__"},
                {"transport", socket and "tcp_or_file" or "file"},
                {"connected", client ~= nil},
            })
            message = message:gsub("\"__READS__\"", "[" .. table.concat(reads, ",") .. "]")
            send_line(message, frame)
        end
        if frame ~= last_party_frame and frame % PARTY_INTERVAL == 0 then
            last_party_frame = frame
            local message = party_memory_message(frame, active_domain)
            send_line(message, frame)
        end
    end
    emu.frameadvance()
end
