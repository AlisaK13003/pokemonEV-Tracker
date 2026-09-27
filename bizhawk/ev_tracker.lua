-- BizHawk RAM-1 probe for the Pokemon Platinum EV Tracker.
-- Run this from EmuHawk's Lua Console while the Nintendo DS core is active.

local HOST = "127.0.0.1"
local PORT = 46387
local HEARTBEAT_INTERVAL = 120
local PARTY_INTERVAL = 30
local TEMP_ROOT = os.getenv("TEMP") or os.getenv("TMP") or os.getenv("TMPDIR")
local FALLBACK_FILE = TEMP_ROOT and (TEMP_ROOT .. "\\ev_tracker_bizhawk.jsonl") or nil
local MAIN_RAM_BASE = 0x02000000
local PLATINUM_PARTY_POINTER_ADDRESS = 0x02101D2C
local PLATINUM_PARTY_COUNT_OFFSET = 0xD090
local PLATINUM_PARTY_RECORDS_OFFSET = 0xD094
local PARTY_POKEMON_SIZE = 236
local PARTY_BYTES = 4 + (6 * PARTY_POKEMON_SIZE)
local BATTLE_BATTLER_SIZE = 0xC0
local BATTLE_BATTLER_OFFSETS = {0x54598, 0x54658, 0x54718, 0x547D8}

local socket = nil
pcall(function()
    socket = require("socket")
end)

local client = nil
local last_connect_attempt = -999999
local last_domain_error = nil
local warned_null_core = false
local run_id = tostring(os.time()) .. "-" .. tostring(math.random(100000, 999999))

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

local function read_bytes_hex(domain, offset, length)
    if domain == nil or offset == nil then
        return nil
    end
    local ok, result = pcall(function()
        memory.usememorydomain(domain)
        local parts = {}
        for index = 0, length - 1 do
            parts[index + 1] = string.format("%02X", memory.readbyte(offset + index))
        end
        return table.concat(parts)
    end)
    if ok then
        return result
    end
    return nil
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

    local message_fields = {
        {"type", "party_memory"},
        {"run_id", run_id},
        {"frame", frame},
        {"core", get_core_name()},
        {"domain", domain},
        {"main_ram_base", string.format("0x%08X", MAIN_RAM_BASE)},
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
    for _, field in ipairs(battle_battler_fields) do
        table.insert(message_fields, field)
    end
    local message = json_object(message_fields)
    return message
end

local function ensure_client(frame)
    if socket == nil then
        return false
    end
    if client ~= nil then
        return true
    end
    if frame - last_connect_attempt < 60 then
        return false
    end

    last_connect_attempt = frame
    local ok, tcp = pcall(function() return socket.tcp() end)
    if not ok or tcp == nil then
        return false
    end
    tcp:settimeout(0.15)
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

local function write_fallback(line)
    if FALLBACK_FILE == nil then
        return
    end
    local handle = io.open(FALLBACK_FILE, "a")
    if handle ~= nil then
        handle:write(line)
        handle:write("\n")
        handle:close()
    end
end

local function send_line(line, frame)
    if ensure_client(frame) and client ~= nil then
        local ok = pcall(function()
            client:send(line .. "\n")
        end)
        if ok then
            return true
        end
        pcall(function() client:close() end)
        client = nil
    end
    write_fallback(line)
    return false
end

local domains = domain_names()
local active_domain = choose_main_ram_domain(domains)
print("EV Tracker BizHawk RAM-1 starting.")
print("Available memory domains:")
for _, name in ipairs(domains) do
    local size = domain_size(name)
    local size_text = size and tostring(size) or "unknown"
    print("  " .. name .. " (" .. size_text .. " bytes)")
end
print("Selected diagnostic domain: " .. tostring(active_domain))
print("Fallback heartbeat file: " .. tostring(FALLBACK_FILE or "disabled (no temp path)"))

while true do
    local frame = get_frame_count()
    if frame % HEARTBEAT_INTERVAL == 0 then
        domains = domain_names()
        active_domain = choose_main_ram_domain(domains)
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
        local connected = send_line(message, frame)
        print("EV Tracker heartbeat frame=" .. tostring(frame)
            .. " domain=" .. tostring(active_domain)
            .. " connected=" .. tostring(connected))
    end
    if frame % PARTY_INTERVAL == 0 then
        domains = domain_names()
        active_domain = choose_main_ram_domain(domains)
        local message = party_memory_message(frame, active_domain)
        send_line(message, frame)
    end
    emu.frameadvance()
end
