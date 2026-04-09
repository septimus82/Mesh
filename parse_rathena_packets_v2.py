"""
Parse rAthena clif_packetdb.hpp for PACKETVER 20190605 (pre-renewal).
PACKETVER = 20190605 / PACKETVER_MAIN_NUM = 20190605
PACKETVER_RE_NUM = undefined / PACKETVER_ZERO_NUM = undefined

All sizeof() expressions are pre-computed from struct analysis.
"""
import re

PACKETVER = 20190605
PACKETVER_MAIN_NUM = 20190605

# Pre-computed sizeof values for PACKETVER=20190605/MAIN_NUM=20190605
# Key condition: PACKETVER_MAIN_NUM >= 20181121 → TRUE → uint32 itemIds, uint32 cards
# EQUIPSLOTINFO = uint32 card[4] = 16 bytes
# ItemOptions = int16 + int16 + uint8 = 5 bytes; MAX_ITEM_OPTIONS = 5 → 25 bytes total
# NAME_LENGTH = 24, MESSAGE_SIZE = 80, TALKBOX_MESSAGE_SIZE = 80
# MAP_NAME_LENGTH = 12, MAP_NAME_LENGTH_EXT = 16
SIZEOF_MAP = {
    # ZC (server-to-client) packets
    "sizeof( struct PACKET_ZC_ITEM_ENTRY )": 19,       # 2+4+4+1+2+2+2+1+1
    "sizeof( struct packet_additem )": 69,              # 2+2+2+4+1+1+1+16+4+1+1+4+2+25+1+2
    "sizeof( struct PACKET_ZC_USE_ITEM_ACK )": 15,     # 2+2+4+4+2+1
    "sizeof( PACKET_ZC_ACK_TOUSESKILL )": 14,          # 2+2+4+4+1+1
    "sizeof( struct PACKET_ZC_ADD_EXCHANGE_ITEM )": 55, # 2+4+1+4+1+1+1+16+25
    "sizeof( struct PACKET_ZC_ADD_ITEM_TO_STORE )": 57, # 2+2+4+4+1+1+1+1+16+25
    "sizeof( struct PACKET_ZC_ADD_ITEM_TO_CART )": 57,  # 2+2+4+4+1+1+1+1+16+25
    "sizeof( struct PACKET_ZC_MVP_GETTING_ITEM )": 6,   # 2+4
    "sizeof( PACKET_ZC_ACK_REQMAKINGITEM )": 8,         # 2+2+4
    "sizeof( struct PACKET_ZC_TALKBOX_CHATCONTENTS )": 86, # 2+4+80
    "sizeof( struct PACKET_ZC_ACK_WEAPONREFINE )": 10,  # 2+4+4
    "sizeof( struct PACKET_ZC_CASH_TIME_COUNTER )": 10, # 2+4+4
    "sizeof( struct PACKET_ZC_CASH_ITEM_DELETE )": 8,   # 2+2+4
    "sizeof( struct PACKET_ZC_ITEM_PICKUP_PARTY )": 32, # 2+4+4+1+1+1+16+2+1
    "sizeof( struct PACKET_ZC_FAILED_TRADE_BUYING_STORE_TO_SELLER )": 8, # 2+2+4
    "sizeof( struct packet_roulette_generate_ack )": 23, # 2+1+2+2+4+4+4+4
    "sizeof( struct PACKET_ZC_ADD_ITEM_TO_MAIL )": 63,  # 2+1+2+2+4+1+1+1+1+16+25+2+1+4
    "sizeof( struct PACKET_ZC_REFINE_OPEN_WINDOW )": 2, # 2
    "sizeof(PACKET_ZC_ENTRY_QUEUE_INIT)": 2,            # 2
    "sizeof( PACKET_ZC_ACK_REQNAME_TITLE )": 58,        # 2+4+4+24+24  (MAIN >= 20180207)
    "sizeof( struct PACKET_ZC_ACK_REQNAMEALL )": 106,   # 2+4+24+24+24+24+4 (MAIN >= 20150225)
    "sizeof( PACKET_ZC_ACK_CASH_BARGAIN_SALE_ITEM_INFO )": 12, # 2+2+4+4
    "sizeof( PACKET_ZC_NOTIFY_BARGAIN_SALE_SELLING )": 10, # 2+4+4
    "sizeof( PACKET_ZC_NOTIFY_BARGAIN_SALE_CLOSE )": 6,    # 2+4
    "sizeof( PACKET_ZC_ACK_COUNT_BARGAIN_SALE_ITEM )": 10, # 2+4+4
    # Also match without spaces
    "sizeof(PACKET_ZC_ACK_REQNAME_TITLE)": 58,
    "sizeof(struct PACKET_ZC_ACK_REQNAMEALL)": 106,
    "sizeof(PACKET_ZC_ENTRY_QUEUE_INIT)": 2,
    # CZ (client-to-server) packets
    "sizeof( PACKET_CZ_REQ_MAKINGARROW )": 6,           # 2+4
    "sizeof( struct PACKET_CZ_REQMAKINGITEM )": 18,     # 2+4+12
    "sizeof( struct PACKET_CZ_REQ_ITEMREPAIR )": 25,    # 2+2+4+1+16
    "sizeof( struct PACKET_CZ_REQ_MAKINGITEM )": 8,     # 2+2+4
    "sizeof( struct PACKET_CZ_START_USE_SKILL )": 10,   # 2+2+2+4
    "sizeof( struct PACKET_CZ_STOP_USE_SKILL )": 4,     # 2+2
    "sizeof( struct PACKET_CZ_INVENTORY_EXPAND )": 2,   # 2
    "sizeof( struct PACKET_CZ_INVENTORY_EXPAND_CONFIRMED )": 2, # 2
    "sizeof( struct PACKET_CZ_INVENTORY_EXPAND_REJECTED )": 2,  # 2
    "sizeof( struct PACKET_CZ_PING )": 2,               # 2
    "sizeof(struct PACKET_CZ_SSILIST_ITEM_CLICK)": 14,  # 2+4+4+4 (MAIN >= 20181121)
    "sizeof( struct PACKET_CZ_SHORTCUT_KEY_CHANGE2 )": 13, # 2+2+2+7 (hotkey_data=7)
    "sizeof( struct PACKET_CZ_SHORTCUTKEYBAR_ROTATE2 )": 5, # 2+2+1
    "sizeof( struct PACKET_CZ_PRIVATE_AIRSHIP_REQUEST )": 22, # 2+16+4
    "sizeof( PACKET_CZ_REQ_APPLY_BARGAIN_SALE_ITEM )": 20,  # 2+4+4+4+4+2 (hours=uint16 for >=20150520)
    "sizeof( struct PACKET_CZ_REQ_REMOVE_BARGAIN_SALE_ITEM )": 10, # 2+4+4
    "sizeof( PACKET_CZ_GUILD_EMBLEM_CHANGE2 )": -1,    # variable
    "sizeof(PACKET_ZC_CHANGE_GUILD)": -1,               # won't be reached (PACKETVER < 20190724)
    # Previously unresolved CZ packets
    "sizeof( PACKET_CZ_REQ_REMOVE_BARGAIN_SALE_ITEM )": 10,  # 2+4+4 (uint32 itemId for MAIN>=20181121)
    "sizeof( struct PACKET_CZ_REFINE_ADD_ITEM )": 4,         # 2+2
    "sizeof( struct PACKET_CZ_REFINE_ITEM_REQUEST )": 9,     # 2+2+4+1 (uint32 itemId for MAIN>=20181121)
    "sizeof( struct PACKET_CZ_REFINE_WINDOW_CLOSE )": 2,     # 2
}

# Symbolic opcode resolution for our PACKETVER
SYMBOLIC_OPCODES = {
    # From packets.hpp DEFINE_PACKET_HEADER
    "HEADER_ZC_NOTIFY_CHAT": 0x008d,
    "HEADER_ZC_BROADCAST": 0x009a,
    "HEADER_ZC_ITEM_ENTRY": 0x009d,
    "HEADER_ZC_MVP_GETTING_ITEM": 0x010a,
    "HEADER_ZC_ACK_TOUSESKILL": 0x0110,
    "HEADER_CZ_REQMAKINGITEM": 0x018e,
    "HEADER_ZC_ACK_REQMAKINGITEM": 0x018f,
    "HEADER_ZC_TALKBOX_CHATCONTENTS": 0x0191,
    "HEADER_CZ_REQ_MAKINGARROW": 0x01ae,
    "HEADER_ZC_BROADCAST2": 0x01c3,
    "HEADER_ZC_SPIRITS": 0x01d0,
    "HEADER_CZ_REQ_ITEMREPAIR": 0x01fd,    # not MAIN >= 20200916
    "HEADER_ZC_NOTIFY_WEAPONITEMLIST": 0x0221,
    "HEADER_ZC_ACK_WEAPONREFINE": 0x0223,
    "HEADER_CZ_REQ_MAKINGITEM": 0x025b,
    "HEADER_ZC_CASH_TIME_COUNTER": 0x0298,
    "HEADER_ZC_CASH_ITEM_DELETE": 0x0299,
    "HEADER_ZC_ITEM_PICKUP_PARTY": 0x02b8,
    "HEADER_ZC_FAILED_TRADE_BUYING_STORE_TO_SELLER": 0x0824,
    "HEADER_ZC_SEARCH_STORE_INFO_ACK": 0x0836,
    "HEADER_CZ_SSILIST_ITEM_CLICK": 0x083c,
    "HEADER_ZC_ENTRY_QUEUE_INIT": 0x090e,
    "HEADER_ZC_BROADCASTING_SPECIAL_ITEM_OBTAIN": 0x07fd,
    "HEADER_CZ_REQ_CASH_BARGAIN_SALE_ITEM_INFO": 0x09ac,
    "HEADER_ZC_ACK_CASH_BARGAIN_SALE_ITEM_INFO": 0x09ad,
    "HEADER_CZ_REQ_APPLY_BARGAIN_SALE_ITEM": 0x09ae,
    "HEADER_CZ_REQ_REMOVE_BARGAIN_SALE_ITEM": 0x09b0,
    "HEADER_ZC_NOTIFY_BARGAIN_SALE_SELLING": 0x09b2,
    "HEADER_ZC_NOTIFY_BARGAIN_SALE_CLOSE": 0x09b3,
    "HEADER_ZC_ACK_COUNT_BARGAIN_SALE_ITEM": 0x09c4,
    "HEADER_CZ_NPC_MARKET_PURCHASE": 0x09d6,
    "HEADER_ZC_REFINE_OPEN_WINDOW": 0x0aa0,
    "HEADER_CZ_REFINE_ADD_ITEM": 0x0aa1,
    "HEADER_ZC_REFINE_ADD_ITEM": 0x0aa2,
    "HEADER_CZ_REFINE_ITEM_REQUEST": 0x0aa3,
    "HEADER_CZ_REFINE_WINDOW_CLOSE": 0x0aa4,
    "HEADER_ZC_HAT_EFFECT": 0x0a3b,
    "HEADER_CZ_REQ_APPLY_BARGAIN_SALE_ITEM2": 0x0a3d,
    "HEADER_ZC_CLEAR_DIALOG": 0x08d6,
    "HEADER_CZ_SE_CASHSHOP_OPEN2": 0x0b6d,
    "HEADER_CZ_GUILD_EMBLEM_CHANGE2": 0x0b46,
    "HEADER_ZC_CHANGE_GUILD": 0x01b4,  # PACKETVER < 20190724
    "HEADER_CZ_REQ_MOUNTOFF": 0x0b35,
    # From packets_struct.hpp enum
    "additemType": 0x0a37,
    "inventorylistnormalType": 0x0b09,  # MAIN_NUM >= 20181002
    "inventorylistequipType": 0x0b0a,   # MAIN_NUM >= 20181002
    "storageListNormalType": 0x0b09,    # MAIN_NUM >= 20181002
    "storageListEquipType": 0x0b0a,     # MAIN_NUM >= 20181002
    "cartlistnormalType": 0x0b09,       # MAIN_NUM >= 20181002
    "cartlistequipType": 0x0b0a,        # MAIN_NUM >= 20181002
    "cartaddType": 0x0a0b,
    "storageaddType": 0x0a0a,
    "tradeaddType": 0x0a09,
    "useItemAckType": 0x01c8,
    "vendinglistType": 0x0800,
    "openvendingType": 0x0136,
    "viewequipackType": 0x0b03,         # MAIN_NUM >= 20180801
    "roulettgenerateackType": 0x0a20,
    "rodexread": 0x09eb,
    "rodexadditem": 0x0a05,
    "rodexmailList": 0x0ac2,            # PACKETVER >= 20170419
}

filepath = r"D:\program\devrag\01_emulator\rathena_pre\src\map\clif_packetdb.hpp"
with open(filepath, "r") as f:
    lines = f.readlines()

packet_db = {}

def eval_condition(cond_str):
    c = cond_str.strip()
    c = c.replace("defined(PACKETVER_ZERO)", "False")
    c = c.replace("defined( PACKETVER_ZERO )", "False")
    c = c.replace("defined(PACKETVER_RE)", "False")
    c = c.replace("PACKETVER_MAIN_NUM", str(PACKETVER_MAIN_NUM))
    c = c.replace("PACKETVER_RE_NUM", "0")
    c = c.replace("PACKETVER_ZERO_NUM", "0")
    c = c.replace("PACKETVER_ZERO", "0")
    c = c.replace("PACKETVER", str(PACKETVER))
    c = c.replace("||", " or ")
    c = c.replace("&&", " and ")
    c = c.replace("!", " not ")
    c = c.replace(" not =", "!=")
    try:
        return bool(eval(c))
    except:
        return False

def resolve_opcode(token):
    token = token.strip().rstrip(",").strip()
    if token.startswith("0x") or token.startswith("0X"):
        return int(token, 16)
    try:
        return int(token)
    except ValueError:
        pass
    if token in SYMBOLIC_OPCODES:
        return SYMBOLIC_OPCODES[token]
    key = "HEADER_" + token
    if key in SYMBOLIC_OPCODES:
        return SYMBOLIC_OPCODES[key]
    return None

def resolve_length(token):
    token = token.strip().rstrip(",").strip()
    # Check sizeof map first
    for pattern, size in SIZEOF_MAP.items():
        if pattern in token:
            return size
    if token.startswith("-"):
        return int(token)
    if token.startswith("0x") or token.startswith("0X"):
        return int(token, 16)
    try:
        return int(token)
    except ValueError:
        pass
    if "sizeof" in token:
        return f"UNRESOLVED:{token}"
    return None

def extract_args(text):
    """Extract first two comma-separated args from a parenthesized expression, handling nested parens."""
    # Find opening paren
    start = text.find('(')
    if start == -1:
        return None, None
    depth = 0
    args = []
    current = []
    for i in range(start + 1, len(text)):
        ch = text[i]
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            if depth == 0:
                args.append(''.join(current).strip())
                break
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
            if len(args) >= 2:
                break
        else:
            current.append(ch)
    if len(args) < 2:
        return None, None
    return args[0], args[1]

def parse_packet_call(line):
    line = line.strip().rstrip(";")
    # ack_packet(type, opcode, length, ...)
    if line.startswith("ack_packet"):
        start = line.find('(')
        if start != -1:
            inner = line[start+1:]
            # Skip first arg (type)
            depth = 0
            pos = 0
            for i, ch in enumerate(inner):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == ',' and depth == 0:
                    pos = i + 1
                    break
            remaining = "dummy(" + inner[pos:]
            arg1, arg2 = extract_args(remaining)
            if arg1 and arg2:
                op = resolve_opcode(arg1)
                ln = resolve_length(arg2)
                if op is not None:
                    return op, ln
    elif line.startswith("parseable_packet") or line.startswith("packet"):
        arg1, arg2 = extract_args(line)
        if arg1 and arg2:
            op = resolve_opcode(arg1)
            ln = resolve_length(arg2)
            if op is not None:
                return op, ln
    return None, None

# Process with preprocessor simulation
if_stack = []
active = True

for line_raw in lines:
    line = line_raw.strip()
    
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
                if_stack[-1] = (False, True)
                active = False
            else:
                parent_active = all(s[0] for s in if_stack[:-1]) if len(if_stack) > 1 else True
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
                parent_active = all(s[0] for s in if_stack[:-1]) if len(if_stack) > 1 else True
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
        active = all(s[0] for s in if_stack) if if_stack else True
        continue
    
    if not active:
        continue
    if line.startswith("//"):
        continue
    
    if "packet(" in line or "parseable_packet(" in line or "ack_packet(" in line:
        op, ln = parse_packet_call(line)
        if op is not None and ln is not None:
            packet_db[op] = ln

# Sort and output
sorted_packets = sorted(packet_db.items())

print("=" * 72)
print(f"rAthena COMPLETE Packet Length Table - PACKETVER {PACKETVER}")
print(f"PACKETVER_MAIN_NUM = {PACKETVER_MAIN_NUM}")
print(f"PACKETVER_RE_NUM   = undefined (pre-renewal)")
print(f"PACKETVER_ZERO_NUM = undefined")
print("=" * 72)
print()

# Specific requested opcodes
print("=== REQUESTED OPCODES (S2C focus) ===")
requested = {
    0x0283: "ZC_AID (Account ID notification)",
    0x02EB: "ZC_MAPPROPERTY_R2 / authokType (map auth OK)",
    0x0069: "AC_ACCEPT_LOGIN (login response)",
    0x0071: "HC_NOTIFY_ZONESVR (char select → map)",
    0x0073: "ZC_ACCEPT_ENTER (map auth OK, old)",
    0x0086: "ZC_NOTIFY_MOVE (entity move)",
}
for op, desc in requested.items():
    if op in packet_db:
        val = packet_db[op]
        if isinstance(val, str):
            print(f"  0x{op:04X} = {val}  -- {desc}")
        else:
            print(f"  0x{op:04X} = {val:>4}  -- {desc}")
    else:
        print(f"  0x{op:04X} = NOT IN packet_db  -- {desc}")
print()

# Full table
print("=== FULL PACKET LENGTH TABLE ===")
print(f"Total registered opcodes: {len(sorted_packets)}")
print()
print("  Opcode   Length   Notes")
print("  ------   ------   -----")

unresolved = []
for op, ln in sorted_packets:
    if isinstance(ln, str):
        unresolved.append((op, ln))
        print(f"  0x{op:04X}   ???      {ln}")
    elif ln == -1:
        print(f"  0x{op:04X}   {ln:>5}    variable-length")
    else:
        print(f"  0x{op:04X}   {ln:>5}    fixed")

if unresolved:
    print()
    print(f"=== {len(unresolved)} UNRESOLVED sizeof() expressions ===")
    for op, ln in unresolved:
        print(f"  0x{op:04X}: {ln}")

# Summary stats
fixed = sum(1 for _, l in sorted_packets if isinstance(l, int) and l > 0)
variable = sum(1 for _, l in sorted_packets if isinstance(l, int) and l == -1)
unres = sum(1 for _, l in sorted_packets if isinstance(l, str))
print()
print(f"=== SUMMARY ===")
print(f"  Fixed-length packets:    {fixed}")
print(f"  Variable-length packets: {variable}")
print(f"  Unresolved sizeof:       {unres}")
print(f"  Total:                   {len(sorted_packets)}")

# Output Python dict format for easy consumption
print()
print("=" * 72)
print("=== PYTHON DICT: opcode → length (-1=variable) ===")
print("=" * 72)
print("PACKET_LEN_TABLE = {")
for op, ln in sorted_packets:
    if isinstance(ln, int):
        print(f"    0x{op:04X}: {ln:>5},")
    else:
        print(f"    # 0x{op:04X}: {ln},")
print("}")
