"""
Parse rAthena clif_packetdb.hpp for PACKETVER 20190605 (pre-renewal).
PACKETVER_MAIN_NUM = 20190605
PACKETVER_RE_NUM = not defined
PACKETVER_ZERO_NUM = not defined
"""
import re, sys

PACKETVER = 20190605
PACKETVER_MAIN_NUM = 20190605
PACKETVER_RE_NUM = None  # undefined
PACKETVER_ZERO_NUM = None  # undefined

# Symbolic opcode resolutions for PACKETVER=20190605, MAIN_NUM=20190605
# Resolved from packets_struct.hpp and packets.hpp
SYMBOLIC_OPCODES = {
    # From packets.hpp DEFINE_PACKET_HEADER
    "HEADER_ZC_ITEM_ENTRY": 0x009d,
    "HEADER_ZC_MVP_GETTING_ITEM": 0x010a,
    "HEADER_ZC_ACK_TOUSESKILL": 0x0110,
    "HEADER_CZ_REQMAKINGITEM": 0x018e,
    "HEADER_ZC_ACK_REQMAKINGITEM": 0x018f,
    "HEADER_ZC_TALKBOX_CHATCONTENTS": 0x0191,
    "HEADER_CZ_REQ_MAKINGARROW": 0x01ae,
    "HEADER_CZ_REQ_ITEMREPAIR": 0x01fd,  # PACKETVER < 20191224 => 0x1fd
    "HEADER_ZC_ACK_WEAPONREFINE": 0x0223,
    "HEADER_CZ_REQ_MAKINGITEM": 0x025b,
    "HEADER_ZC_CASH_TIME_COUNTER": 0x0298,
    "HEADER_ZC_CASH_ITEM_DELETE": 0x0299,
    "HEADER_ZC_ITEM_PICKUP_PARTY": 0x02b8,  # PACKETVER < 20200916 => 0x2b8
    "HEADER_ZC_FAILED_TRADE_BUYING_STORE_TO_SELLER": 0x0824,
    "HEADER_ZC_SEARCH_STORE_INFO_ACK": 0x0836,  # not MAIN >= 20200916
    "HEADER_CZ_SSILIST_ITEM_CLICK": 0x083c,
    "HEADER_ZC_ENTRY_QUEUE_INIT": 0x090e,
    "HEADER_ZC_BROADCASTING_SPECIAL_ITEM_OBTAIN": 0x07fd,
    "HEADER_ZC_CLEAR_DIALOG": 0x08d6,
    "HEADER_CZ_NPC_MARKET_PURCHASE": 0x09d6,
    "HEADER_CZ_REQ_CASH_BARGAIN_SALE_ITEM_INFO": 0x09ac,
    "HEADER_CZ_REQ_APPLY_BARGAIN_SALE_ITEM": 0x09ae,
    "HEADER_CZ_REQ_APPLY_BARGAIN_SALE_ITEM2": 0x0a3d,
    "HEADER_CZ_REQ_REMOVE_BARGAIN_SALE_ITEM": 0x09b0,
    "HEADER_ZC_NOTIFY_BARGAIN_SALE_SELLING": 0x09b2,
    "HEADER_ZC_NOTIFY_BARGAIN_SALE_CLOSE": 0x09b3,
    "HEADER_ZC_ACK_COUNT_BARGAIN_SALE_ITEM": 0x09c4,
    "HEADER_ZC_REFINE_OPEN_WINDOW": 0x0aa0,
    "HEADER_CZ_REFINE_ADD_ITEM": 0x0aa1,
    "HEADER_ZC_REFINE_ADD_ITEM": 0x0aa2,
    "HEADER_CZ_REFINE_ITEM_REQUEST": 0x0aa3,
    "HEADER_CZ_REFINE_WINDOW_CLOSE": 0x0aa4,
    "HEADER_ZC_HAT_EFFECT": 0x0a3b,
    "HEADER_ZC_CHANGE_GUILD": 0x01b4,  # PACKETVER < 20190724 but actually >= per the logic
    "HEADER_CZ_GUILD_EMBLEM_CHANGE2": 0x0b46,
    "HEADER_CZ_SE_CASHSHOP_OPEN2": 0x0b6d,
    "HEADER_CZ_REQ_MOUNTOFF": 0x0b35,
    # From packets_struct.hpp enum
    "additemType": 0x0a37,         # PACKETVER >= 20160921 and not MAIN >= 20200916
    "inventorylistnormalType": 0x0991,  # PACKETVER >= 20120925 and not RE>=20180912/MAIN>=20181002
    "inventorylistequipType": 0x0a0d,   # PACKETVER >= 20150226 and not RE>=20180912/MAIN>=20181002
    "storageListNormalType": 0x0995,    # PACKETVER >= 20120925 and not RE>=20180829/MAIN>=20181002
    "storageListEquipType": 0x0a10,     # PACKETVER >= 20150226 and not RE>=20180829/MAIN>=20181002
    "cartlistnormalType": 0x0993,       # PACKETVER >= 20120925 and not RE>=20180829/MAIN>=20181002
    "cartlistequipType": 0x0a0f,        # PACKETVER >= 20150226 and not RE>=20180829/MAIN>=20181002
    "cartaddType": 0x0a0b,              # PACKETVER >= 20150226 and not MAIN>=20200916
    "storageaddType": 0x0a0a,           # PACKETVER >= 20150226 and not MAIN>=20200916
    "tradeaddType": 0x0a09,             # PACKETVER >= 20150226 and not MAIN>=20200916
    "useItemAckType": 0x01c8,           # PACKETVER >= 3
    "vendinglistType": 0x0800,          # PACKETVER >= 20100105 and not MAIN >= 20200916
    "openvendingType": 0x0136,          # not MAIN >= 20200916
    "viewequipackType": 0x0a2d,         # PACKETVER >= 20150226 and not MAIN>=20180801
    "cartaddType": 0x0a0b,
    # rodex
    "rodexread": 0x09eb,               # not MAIN >= 20200916
    "rodexadditem": 0x0a05,            # not MAIN >= 20200916
    "roulettgenerateackType": 0x0a20,
}

# Wait - let me re-check conditions for PACKETVER_MAIN_NUM = 20190605

# inventorylistnormalType: 
# PACKETVER_RE_NUM >= 20180912 || PACKETVER_ZERO_NUM >= 20180919 || PACKETVER_MAIN_NUM >= 20181002 → MAIN 20190605 >= 20181002 → YES → 0xb09
# inventorylistequipType:
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO
# PACKETVER_RE_NUM >= 20180912 || PACKETVER_ZERO_NUM >= 20180919 || PACKETVER_MAIN_NUM >= 20181002 → YES → 0xb0a
# storageListNormalType:
# PACKETVER_RE_NUM >= 20180829 || PACKETVER_ZERO_NUM >= 20180919 || PACKETVER_MAIN_NUM >= 20181002 → YES → 0xb09
# storageListEquipType:
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO
# PACKETVER_RE_NUM >= 20180829 || PACKETVER_ZERO_NUM >= 20180919 || PACKETVER_MAIN_NUM >= 20181002 → YES → 0xb0a
# cartlistnormalType:
# PACKETVER_RE_NUM >= 20180829 || PACKETVER_ZERO_NUM >= 20180919 || PACKETVER_MAIN_NUM >= 20181002 → YES → 0xb09
# cartlistequipType:
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO
# PACKETVER_RE_NUM >= 20180829 || PACKETVER_ZERO_NUM >= 20180919 || PACKETVER_MAIN_NUM >= 20181002 → YES → 0xb0a
# cartaddType:
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO
# PACKETVER >= 20150226 → YES → 0xa0b
# storageaddType → same → 0xa0a
# tradeaddType:
# PACKETVER_MAIN_NUM >= 20200916 → NO
# PACKETVER >= 20150226 → YES → 0xa09
# additemType:
# PACKETVER < 20160921 → NO (20190605 >= 20160921)
# PACKETVER_MAIN_NUM >= 20200916 → NO
# else → 0xa37
# vendinglistType:
# PACKETVER >= 20100105 → YES, MAIN >= 20200916 → NO → 0x800
# openvendingType: MAIN >= 20200916 → NO → 0x136
# viewequipackType:
# PACKETVER_MAIN_NUM >= 20200916 → NO
# PACKETVER_MAIN_NUM >= 20180801 → YES (20190605 >= 20180801) → 0xb03
# authokType:
# PACKETVER >= 20160330 → YES → 0x2eb! Wait, let me re-check:
# PACKETVER < 20080102 → 0x73
# PACKETVER < 20141022 → 0x2eb
# PACKETVER < 20160330 → 0xa18
# else → 0x2eb
# Since 20190605 >= 20160330 → 0x2eb

# Let me FIX the symbolic opcodes:
SYMBOLIC_OPCODES.update({
    "inventorylistnormalType": 0x0b09,  # MAIN_NUM >= 20181002
    "inventorylistequipType": 0x0b0a,   # MAIN_NUM >= 20181002  
    "storageListNormalType": 0x0b09,    # MAIN_NUM >= 20181002
    "storageListEquipType": 0x0b0a,     # MAIN_NUM >= 20181002
    "cartlistnormalType": 0x0b09,       # MAIN_NUM >= 20181002
    "cartlistequipType": 0x0b0a,        # MAIN_NUM >= 20181002
    "viewequipackType": 0x0b03,         # MAIN_NUM >= 20180801
    "authokType": 0x02eb,
})

# Also check HEADER_CZ_REQ_ITEMREPAIR:
# The #if in packets.hpp:
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO
# else → 0x1fd
SYMBOLIC_OPCODES["HEADER_CZ_REQ_ITEMREPAIR"] = 0x01fd

# HEADER_ZC_CHANGE_GUILD: PACKETVER >= 20190724 → NO (20190605 < 20190724) 
# Hmm - but that block wraps both HEADER_CZ_GUILD_EMBLEM_CHANGE2 and HEADER_ZC_CHANGE_GUILD packet definitions,
# so they only exist if PACKETVER >= 20190724, which is NOT true for 20190605.
# So these packets are NOT registered.

# HEADER_ZC_ITEM_PICKUP_PARTY
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO → 0x2b8
SYMBOLIC_OPCODES["HEADER_ZC_ITEM_PICKUP_PARTY"] = 0x02b8

# ZC_SEARCH_STORE_INFO_ACK
# PACKETVER_MAIN_NUM >= 20200916 || PACKETVER_RE_NUM >= 20200724 → NO → 0x836
SYMBOLIC_OPCODES["HEADER_ZC_SEARCH_STORE_INFO_ACK"] = 0x0836

# Now we also need sizeof() for the struct-based packets
# These are harder to compute exactly, but many are known sizes.
# I'll read them from the source to get exact values.

filepath = r"D:\program\devrag\01_emulator\rathena_pre\src\map\clif_packetdb.hpp"

with open(filepath, "r") as f:
    lines = f.readlines()

# Build packet table by simulating the preprocessor
# We track opcode -> length for every packet() and parseable_packet() call

packet_db = {}

def eval_condition(cond_str):
    """Evaluate a preprocessor condition for our PACKETVER settings."""
    c = cond_str.strip()
    
    # Handle defined(X) 
    c = c.replace("defined(PACKETVER_ZERO)", "False")
    c = c.replace("defined( PACKETVER_ZERO )", "False")
    
    # Replace identifiers
    c = c.replace("PACKETVER_MAIN_NUM", str(PACKETVER_MAIN_NUM))
    c = c.replace("PACKETVER_RE_NUM", "0")  # undefined = 0 for comparison
    c = c.replace("PACKETVER_ZERO_NUM", "0")  # undefined
    c = c.replace("PACKETVER_ZERO", "0")
    c = c.replace("PACKETVER", str(PACKETVER))
    
    # Replace C operators
    c = c.replace("||", " or ")
    c = c.replace("&&", " and ")
    c = c.replace("!", " not ")
    # Fix "not =" → "!=" 
    c = c.replace(" not =", "!=")
    
    try:
        return bool(eval(c))
    except:
        return False

def resolve_opcode(token):
    """Resolve a symbolic opcode or hex literal to int."""
    token = token.strip().rstrip(",")
    if token.startswith("0x") or token.startswith("0X"):
        return int(token, 16)
    try:
        return int(token)
    except ValueError:
        pass
    # Try symbolic lookup
    if token in SYMBOLIC_OPCODES:
        return SYMBOLIC_OPCODES[token]
    # Try with HEADER_ prefix
    key = "HEADER_" + token
    if key in SYMBOLIC_OPCODES:
        return SYMBOLIC_OPCODES[key]
    return None

def resolve_length(token):
    """Resolve a length value (might be int, sizeof(), or symbolic)."""
    token = token.strip().rstrip(",")
    if token.startswith("-"):
        return int(token)
    if token.startswith("0x") or token.startswith("0X"):
        return int(token, 16)
    try:
        return int(token)
    except ValueError:
        pass
    # sizeof() - we'll return None and note it
    if "sizeof" in token:
        return token  # return the string for now
    return None

def parse_packet_call(line):
    """Parse a packet() or parseable_packet() or ack_packet() call."""
    # packet(opcode, length)
    # parseable_packet(opcode, length, func, offsets...)
    # ack_packet(type, opcode, length, offsets...)
    
    line = line.strip().rstrip(";")
    
    m = re.match(r'(?:parseable_)?packet\s*\(\s*(.+?)\s*,\s*(.+?)[\s,)]', line)
    if m:
        op = resolve_opcode(m.group(1))
        ln = resolve_length(m.group(2))
        if op is not None:
            return op, ln
    
    m = re.match(r'ack_packet\s*\(\s*\w+\s*,\s*(.+?)\s*,\s*(.+?)[\s,)]', line)
    if m:
        op = resolve_opcode(m.group(1))
        ln = resolve_length(m.group(2))
        if op is not None:
            return op, ln
    
    return None, None

# Process the file tracking #if nesting
if_stack = []  # stack of (active, has_been_active) tuples
active = True   # whether current code is active

for line_raw in lines:
    line = line_raw.strip()
    
    # Handle preprocessor conditionals
    if line.startswith("#if ") or line.startswith("#if\t"):
        cond = line[4:].strip()
        if active:
            result = eval_condition(cond)
            if_stack.append((result, result))
            active = result
        else:
            if_stack.append((False, False))
            active = False
        continue
    
    if line.startswith("#elif "):
        cond = line[6:].strip()
        if if_stack:
            was_active, has_been_active = if_stack[-1]
            if has_been_active:
                # Already had a true branch
                if_stack[-1] = (False, True)
                active = False
            else:
                # Check parent
                parent_active = True
                for i in range(len(if_stack) - 1):
                    if not if_stack[i][0]:
                        parent_active = False
                        break
                if parent_active:
                    result = eval_condition(cond)
                    if_stack[-1] = (result, result)
                    active = result
                else:
                    if_stack[-1] = (False, False)
                    active = False
        continue
    
    if line.startswith("#else"):
        if if_stack:
            was_active, has_been_active = if_stack[-1]
            if has_been_active:
                if_stack[-1] = (False, True)
                active = False
            else:
                parent_active = True
                for i in range(len(if_stack) - 1):
                    if not if_stack[i][0]:
                        parent_active = False
                        break
                if parent_active:
                    if_stack[-1] = (True, True)
                    active = True
                else:
                    if_stack[-1] = (False, False)
                    active = False
        continue
    
    if line.startswith("#endif"):
        if if_stack:
            if_stack.pop()
        # Recompute active state
        active = all(s[0] for s in if_stack) if if_stack else True
        continue
    
    # Skip non-active code
    if not active:
        continue
    
    # Skip comments
    if line.startswith("//"):
        continue
    
    # Parse packet definitions
    if "packet(" in line or "parseable_packet(" in line or "ack_packet(" in line:
        op, ln = parse_packet_call(line)
        if op is not None and ln is not None:
            packet_db[op] = ln

# Now resolve sizeof() expressions
# We need the actual struct sizes. Let me compute known ones and hardcode.
# For PACKETVER=20190605, MAIN_NUM=20190605
sizeof_map = {
    # These need to be computed from the structs
    "sizeof( struct PACKET_ZC_ITEM_ENTRY )": 17,  # 0x9d - always 17
    "sizeof( struct packet_additem )": -1,  # variable/complex - let me check
    "sizeof( struct PACKET_ZC_USE_ITEM_ACK )": -1,
    "sizeof( PACKET_ZC_ACK_TOUSESKILL )": -1,
    "sizeof( struct PACKET_ZC_ADD_EXCHANGE_ITEM )": -1,
    "sizeof( struct PACKET_ZC_ADD_ITEM_TO_STORE )": -1,
    "sizeof( struct PACKET_ZC_ADD_ITEM_TO_CART )": -1, 
    "sizeof( struct PACKET_ZC_ACK_WEAPONREFINE )": -1,
    "sizeof( struct PACKET_ZC_TALKBOX_CHATCONTENTS )": -1,
    "sizeof( PACKET_ZC_ACK_REQMAKINGITEM )": -1,
    "sizeof( struct PACKET_ZC_CASH_TIME_COUNTER )": -1,
    "sizeof( struct PACKET_ZC_CASH_ITEM_DELETE )": -1,
    "sizeof( struct PACKET_ZC_ACK_REQNAMEALL )": -1,
    "sizeof( PACKET_ZC_ACK_REQNAME_TITLE )": -1,
    "sizeof( struct PACKET_ZC_ITEM_PICKUP_PARTY )": -1,
    "sizeof( struct PACKET_ZC_FAILED_TRADE_BUYING_STORE_TO_SELLER )": -1,
    "sizeof( struct PACKET_ZC_ADD_ITEM_TO_MAIL )": -1,
    "sizeof( struct packet_roulette_generate_ack )": -1,
    "sizeof( struct PACKET_ZC_REFINE_OPEN_WINDOW )": -1,
    "sizeof(PACKET_ZC_ENTRY_QUEUE_INIT)": -1,
}

# Print results
print("=" * 70)
print(f"rAthena Packet Length Table for PACKETVER {PACKETVER}")
print(f"PACKETVER_MAIN_NUM = {PACKETVER_MAIN_NUM}")
print(f"PACKETVER_RE_NUM = undefined")
print(f"PACKETVER_ZERO_NUM = undefined")
print("=" * 70)
print()

# Sort by opcode
sorted_packets = sorted(packet_db.items())

# First print the specific opcodes the user asked about
print("=== REQUESTED OPCODES ===")
requested = [0x0283, 0x02eb, 0x0069, 0x0071, 0x0073, 0x0086]
for op in requested:
    if op in packet_db:
        val = packet_db[op]
        if isinstance(val, str):
            print(f"  0x{op:04X} = {val} (sizeof - needs struct resolution)")
        else:
            print(f"  0x{op:04X} = {val}")
    else:
        print(f"  0x{op:04X} = NOT FOUND in packet_db")

print()
print("=== FULL PACKET TABLE (opcode → length) ===")
print(f"Total entries: {len(sorted_packets)}")
print()

sizeof_unresolved = []

for op, ln in sorted_packets:
    if isinstance(ln, str):
        sizeof_unresolved.append((op, ln))
        print(f"  0x{op:04X}: {ln}")
    else:
        vtype = "variable" if ln == -1 else f"fixed({ln})"
        print(f"  0x{op:04X}: {ln:>6}  # {vtype}")

if sizeof_unresolved:
    print()
    print("=== UNRESOLVED sizeof() expressions ===")
    for op, ln in sizeof_unresolved:
        print(f"  0x{op:04X}: {ln}")
